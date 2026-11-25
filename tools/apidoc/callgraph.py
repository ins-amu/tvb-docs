"""Static AST implementation call-graph, inheritance, and type-annotation linker."""

from __future__ import annotations

import ast
import warnings
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import griffe

from .loader import LoadedPackage


@dataclass(frozen=True)
class ClassHierarchy:
    """Inheritance edges across all documented classes."""

    bases: dict[str, list[str]]
    subclasses: dict[str, list[str]]


def _attr_chain(node: ast.AST) -> list[str] | None:
    """Return dotted parts for `ast.Name` / `ast.Attribute` chains, else None."""
    parts: list[str] = []
    cur: ast.AST | None = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
        parts.reverse()
        return parts
    return None


def _collect_module_bindings(
    tree: ast.Module,
    mod_path: str,
    pkg: LoadedPackage,
) -> dict[str, str]:
    """Collect module-level import and definition bindings for static symbol resolution."""
    bindings: dict[str, str] = {}
    pkg_parts = mod_path.split(".")

    # Module's own top-level classes/functions/attributes
    mod = pkg.modules.get(mod_path)
    if mod is not None:
        for name, member in mod.members.items():
            if not name.startswith("_") and not member.is_alias:
                bindings[name] = member.canonical_path

    for stmt in tree.body:
        if isinstance(stmt, ast.Import):
            for alias in stmt.names:
                asname = alias.asname or alias.name.split(".")[0]
                bindings[asname] = alias.name
        elif isinstance(stmt, ast.ImportFrom):
            base_mod = stmt.module or ""
            if stmt.level > 0:
                anchor = pkg_parts[: max(0, len(pkg_parts) - (stmt.level - 1))]
                # If mod_path is a file module (not __init__), drop leaf module name first
                is_pkg_init = mod is not None and mod.filepath and Path(str(mod.filepath)).name == "__init__.py"
                if not is_pkg_init:
                    anchor = pkg_parts[: max(0, len(pkg_parts) - stmt.level)]
                base_mod = ".".join([*anchor, *(base_mod.split(".") if base_mod else [])])
            for alias in stmt.names:
                if alias.name == "*":
                    bindings.update(pkg.star_exports.get(base_mod, {}))
                else:
                    asname = alias.asname or alias.name
                    candidate = f"{base_mod}.{alias.name}" if base_mod else alias.name
                    bindings[asname] = pkg.aliases.get(candidate, candidate)
    return bindings


def resolve_dotted_symbol(
    candidate: str,
    known_symbols: set[str],
    aliases: dict[str, str],
) -> str | None:
    """Resolve a dotted candidate path against aliases and documented symbols."""
    target = aliases.get(candidate, candidate)
    if target in known_symbols:
        return target
    return None


def _resolve_chain(
    parts: list[str],
    bindings: dict[str, str],
    known_symbols: set[str],
    aliases: dict[str, str],
    current_class: str | None = None,
    class_mro_members: dict[str, dict[str, str]] | None = None,
) -> str | None:
    """Resolve an `ast.Name`/`ast.Attribute` chain to a canonical documented symbol."""
    if not parts:
        return None
    head = parts[0]
    if head in ("self", "cls") and current_class and class_mro_members and len(parts) >= 2:
        member_target = class_mro_members.get(current_class, {}).get(parts[1])
        if member_target and member_target in known_symbols:
            return member_target
        return None

    if head in bindings:
        full = ".".join([bindings[head], *parts[1:]]) if len(parts) > 1 else bindings[head]
        res = resolve_dotted_symbol(full, known_symbols, aliases)
        if res:
            return res

    # Also test raw dotted path (e.g., `tvb.simulator.models.Generic2dOscillator`)
    raw = ".".join(parts)
    return resolve_dotted_symbol(raw, known_symbols, aliases)


def build_class_hierarchy(pkg: LoadedPackage, known_symbols: set[str]) -> ClassHierarchy:
    """Build documented `Inherits from` and `Subclasses` mappings."""
    bases_map: dict[str, list[str]] = defaultdict(list)
    subclasses_map: dict[str, list[str]] = defaultdict(list)

    for mod in pkg.modules.values():
        for member in mod.members.values():
            if member.is_alias or not isinstance(member, griffe.Class):
                continue
            cls_path = member.canonical_path
            if cls_path not in known_symbols:
                continue
            try:
                resolved = list(member.resolved_bases)
            except Exception:
                resolved = []
            seen_bases: set[str] = set()
            for rbase in resolved:
                bpath = pkg.aliases.get(rbase.canonical_path, rbase.canonical_path)
                if bpath in known_symbols and bpath != cls_path and bpath not in seen_bases:
                    seen_bases.add(bpath)
                    bases_map[cls_path].append(bpath)
                    subclasses_map[bpath].append(cls_path)

    for k in list(subclasses_map):
        subclasses_map[k] = sorted(set(subclasses_map[k]))
    return ClassHierarchy(bases=dict(bases_map), subclasses=dict(subclasses_map))


def _build_class_member_lookup(
    pkg: LoadedPackage,
    hierarchy: ClassHierarchy,
) -> dict[str, dict[str, str]]:
    """Map each class path to `{member_name: canonical_member_path}` including documented bases."""
    direct: dict[str, dict[str, str]] = {}
    for mod in pkg.modules.values():
        for member in mod.members.values():
            if member.is_alias or not isinstance(member, griffe.Class):
                continue
            cmap: dict[str, str] = {}
            for mname, sub in member.members.items():
                if not mname.startswith("__") or mname == "__init__":
                    if not sub.is_alias:
                        cmap[mname] = sub.canonical_path
            direct[member.canonical_path] = cmap

    inherited: dict[str, dict[str, str]] = {}
    for cls_path, own in direct.items():
        merged: dict[str, str] = {}
        for base_path in reversed(hierarchy.bases.get(cls_path, [])):
            merged.update(direct.get(base_path, {}))
        merged.update(own)
        inherited[cls_path] = merged
    return inherited


def extract_static_uses(
    pkg: LoadedPackage,
    known_symbols: set[str],
    hierarchy: ClassHierarchy,
) -> dict[str, list[str]]:
    """Extract statically resolved `Uses / References (static)` targets per function/method/class."""
    uses: dict[str, list[str]] = {}
    class_members = _build_class_member_lookup(pkg, hierarchy)

    for mod_path, mod in pkg.modules.items():
        if not mod.filepath:
            continue
        fpath = Path(str(mod.filepath))
        if not fpath.is_file():
            continue
        try:
            source = fpath.read_text(encoding="utf-8")
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", SyntaxWarning)
                tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue

        bindings = _collect_module_bindings(tree, mod_path, pkg)

        def scan_node(node: ast.AST, owner_path: str, current_class: str | None) -> list[str]:
            refs: set[str] = set()
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    chain = _attr_chain(child.func)
                    if chain:
                        target = _resolve_chain(
                            chain, bindings, known_symbols, pkg.aliases, current_class, class_members
                        )
                        if target and target != owner_path:
                            refs.add(target)
                elif isinstance(child, (ast.Attribute, ast.Name)):
                    chain = _attr_chain(child)
                    if chain:
                        target = _resolve_chain(
                            chain, bindings, known_symbols, pkg.aliases, current_class, class_members
                        )
                        if target and target != owner_path and target != mod_path:
                            refs.add(target)
            return sorted(refs)

        for stmt in tree.body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fn_path = f"{mod_path}.{stmt.name}"
                if fn_path in known_symbols:
                    found = scan_node(stmt, fn_path, None)
                    if found:
                        uses[fn_path] = found
            elif isinstance(stmt, ast.ClassDef):
                cls_path = f"{mod_path}.{stmt.name}"
                if cls_path not in known_symbols:
                    continue
                cls_refs: set[str] = set()
                for cstmt in stmt.body:
                    if isinstance(cstmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        meth_path = f"{cls_path}.{cstmt.name}"
                        found = scan_node(cstmt, meth_path, cls_path)
                        if meth_path in known_symbols and found:
                            uses[meth_path] = found
                        cls_refs.update(found)
                    elif isinstance(cstmt, ast.Assign):
                        # Capture references in trait declarations (e.g. Attr(field_type=Connectivity))
                        found = scan_node(cstmt, cls_path, cls_path)
                        cls_refs.update(found)
                cls_refs.discard(cls_path)
                cls_prefix = f"{cls_path}."
                ext_refs = sorted(r for r in cls_refs if not r.startswith(cls_prefix))
                if ext_refs:
                    uses[cls_path] = ext_refs

    return uses
