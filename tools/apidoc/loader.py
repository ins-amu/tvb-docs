"""Static `griffe` loader and module/re-export resolver for `tvb`."""

from __future__ import annotations

import ast
import logging
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import griffe

from .config import is_excluded_module


@dataclass
class LoadedPackage:
    """Normalized static view over `tvb` modules, symbols, and re-export aliases."""

    root_module: griffe.Module
    modules: dict[str, griffe.Module] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    star_exports: dict[str, dict[str, str]] = field(default_factory=dict)
    search_path: Path = Path(".")


def _collect_real_modules(module: griffe.Module, out: dict[str, griffe.Module], seen: set[str]) -> None:
    """Recursively collect non-alias public modules without revisiting re-export aliases."""
    if module.is_alias:
        return
    cpath = module.canonical_path
    if cpath in seen or is_excluded_module(cpath):
        return
    seen.add(cpath)
    out[cpath] = module
    for sub in sorted(module.modules.values(), key=lambda m: m.name):
        _collect_real_modules(sub, out, seen)


def _extract_models_lazy_aliases(models_init: Path) -> dict[str, str]:
    """Parse `_module_models` in `tvb/simulator/models/__init__.py` for lazy re-exports."""
    aliases: dict[str, str] = {}
    if not models_init.is_file():
        return aliases
    try:
        tree = ast.parse(models_init.read_text(encoding="utf-8"))
    except SyntaxError:
        return aliases

    enum_to_cls: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "ModelsEnum":
            for stmt in node.body:
                if (
                    isinstance(stmt, ast.Assign)
                    and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Name)
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)
                ):
                    enum_to_cls[stmt.targets[0].id] = stmt.value.value

    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "_module_models"
            and isinstance(node.value, ast.Dict)
        ):
            for k_node, v_node in zip(node.value.keys, node.value.values):
                if not (isinstance(k_node, ast.Constant) and isinstance(k_node.value, str)):
                    continue
                submod = k_node.value
                if not isinstance(v_node, ast.List):
                    continue
                for elt in v_node.elts:
                    if (
                        isinstance(elt, ast.Attribute)
                        and isinstance(elt.value, ast.Name)
                        and elt.value.id == "ModelsEnum"
                    ):
                        cls_name = enum_to_cls.get(elt.attr)
                        if cls_name:
                            aliases[f"tvb.simulator.models.{cls_name}"] = (
                                f"tvb.simulator.models.{submod}.{cls_name}"
                            )
    return aliases


def _extract_star_exports(module: griffe.Module) -> dict[str, str]:
    """Extract top-level imported/defined public bindings from a module (e.g. `tvb.simulator.lab`)."""
    exports: dict[str, str] = {}
    for name, member in module.members.items():
        if name.startswith("_"):
            continue
        if member.is_alias:
            try:
                exports[name] = member.target.canonical_path
            except Exception:
                target_path = getattr(member, "target_path", None)
                if target_path:
                    exports[name] = target_path
        else:
            exports[name] = member.canonical_path
    return exports


def load_tvb_package(search_path: Path, scope: str | None = None) -> LoadedPackage:
    """Load `tvb` statically via `griffe`, filtering private/broken modules and resolving re-exports."""
    griffe_logger = logging.getLogger("griffe")
    prev_level = griffe_logger.level
    griffe_logger.setLevel(logging.ERROR)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            root = griffe.load(
                "tvb",
                search_paths=[str(search_path)],
                docstring_parser="numpy",
                allow_inspection=False,
            )
    finally:
        griffe_logger.setLevel(prev_level)

    all_modules: dict[str, griffe.Module] = {}
    _collect_real_modules(root, all_modules, set())

    if scope:
        prefix = scope.rstrip(".")
        filtered = {
            k: v for k, v in all_modules.items() if k == prefix or k.startswith(prefix + ".")
        }
        # Keep ancestor packages if needed for navigation context? No, keep exact scope + root if matched.
        modules = dict(sorted(filtered.items()))
    else:
        modules = dict(sorted(all_modules.items()))

    aliases: dict[str, str] = {}
    for mod in all_modules.values():
        for name, member in mod.members.items():
            if name.startswith("_"):
                continue
            if member.is_alias:
                try:
                    target_path = member.target.canonical_path
                    if target_path.startswith("tvb.") and not is_excluded_module(target_path):
                        aliases[f"{mod.canonical_path}.{name}"] = target_path
                except Exception:
                    continue

    models_init = search_path / "tvb" / "simulator" / "models" / "__init__.py"
    aliases.update(_extract_models_lazy_aliases(models_init))

    star_exports: dict[str, dict[str, str]] = {}
    for star_mod in ("tvb.simulator.lab", "tvb.basic.neotraits.api"):
        if star_mod in all_modules:
            star_exports[star_mod] = _extract_star_exports(all_modules[star_mod])

    return LoadedPackage(
        root_module=root,
        modules=modules,
        aliases=aliases,
        star_exports=star_exports,
        search_path=search_path,
    )
