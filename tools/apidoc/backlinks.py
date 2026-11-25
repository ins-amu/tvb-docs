"""Scan `.ipynb` and `.md` docs/tutorials to build automated symbol backlinks."""

from __future__ import annotations

import ast
import json
import re
import warnings
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from .callgraph import _attr_chain
from .loader import LoadedPackage

_CODE_FENCE_RE = re.compile(
    r"^```+\s*(?:\{code-cell\}\s*[^\n]*|python|ipython3|python3)\s*\n(.*?)^```+",
    re.MULTILINE | re.DOTALL,
)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
_PY_ROLE_RE = re.compile(r"\{py\}`([^`]+)`")
_API_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)#\s]*tvb(?:\.[A-Za-z0-9_]+)*\.md)(?:#([^)\s]+))?\)")


@dataclass(frozen=True)
class Backlink:
    """A human-authored doc/notebook location referencing a documented API symbol."""

    doc_path: str
    doc_title: str
    section_heading: str
    location: str


def _extract_title(text: str, fallback: str) -> str:
    for m in _HEADING_RE.finditer(text):
        if len(m.group(1)) == 1:
            return m.group(2).strip().strip("*_")
    return fallback


def _bindings_from_code(
    tree: ast.Module,
    bindings: dict[str, str],
    pkg: LoadedPackage,
) -> None:
    """Update cumulative import bindings for a notebook/doc page from an AST cell."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                asname = alias.asname or alias.name.split(".")[0]
                if alias.asname:
                    bindings[asname] = alias.name
                else:
                    # `import tvb.simulator.models` binds `tvb` -> `tvb`
                    root_name = alias.name.split(".")[0]
                    bindings[root_name] = root_name
        elif isinstance(node, ast.ImportFrom):
            base_mod = node.module or ""
            for alias in node.names:
                if alias.name == "*":
                    bindings.update(pkg.star_exports.get(base_mod, {}))
                else:
                    asname = alias.asname or alias.name
                    candidate = f"{base_mod}.{alias.name}" if base_mod else alias.name
                    bindings[asname] = pkg.aliases.get(candidate, candidate)


def _symbols_in_code(
    source: str,
    bindings: dict[str, str],
    pkg: LoadedPackage,
    known_symbols: set[str],
) -> set[str]:
    """Parse a code cell/fence and return canonical `tvb.*` symbols referenced in it."""
    found: set[str] = set()
    # Strip IPython magics / shell escapes line-by-line before parsing
    cleaned_lines = [
        "" if line.lstrip().startswith(("%", "!", "?")) else line
        for line in source.splitlines()
    ]
    cleaned = "\n".join(cleaned_lines)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(cleaned)
    except SyntaxError:
        return found

    _bindings_from_code(tree, bindings, pkg)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = pkg.aliases.get(alias.name, alias.name)
                if target in known_symbols:
                    found.add(target)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if base in known_symbols:
                found.add(base)
            for alias in node.names:
                if alias.name != "*":
                    cand = f"{base}.{alias.name}" if base else alias.name
                    target = pkg.aliases.get(cand, cand)
                    if target in known_symbols:
                        found.add(target)
        elif isinstance(node, (ast.Attribute, ast.Name)):
            chain = _attr_chain(node)
            if not chain:
                continue
            head = chain[0]
            if head in bindings:
                cand = ".".join([bindings[head], *chain[1:]]) if len(chain) > 1 else bindings[head]
                target = pkg.aliases.get(cand, cand)
                if target in known_symbols:
                    found.add(target)
            raw = ".".join(chain)
            target = pkg.aliases.get(raw, raw)
            if target in known_symbols:
                found.add(target)
    return found


def _resolve_py_role_target(raw_body: str, short_name_map: dict[str, str], known_symbols: set[str]) -> str | None:
    target = raw_body.strip()
    m = re.match(r"^.+?\s*<([^>]+)>$", target)
    if m:
        target = m.group(1).strip()
    target = target.lstrip("~")
    if target in known_symbols:
        return target
    return short_name_map.get(target)


def _scan_markdown_text(
    md_text: str,
    doc_path: str,
    doc_title: str,
    bindings: dict[str, str],
    pkg: LoadedPackage,
    known_symbols: set[str],
    short_name_map: dict[str, str],
    anchor_to_symbol: dict[str, str],
    out: dict[str, list[Backlink]],
    *,
    cell_label: str | None = None,
) -> None:
    lines = md_text.splitlines()
    current_heading = doc_title
    in_fence = False
    fence_lang = ""
    fence_lines: list[str] = []
    fence_start_line = 1

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not in_fence and stripped.startswith("```"):
            lang = stripped[3:].strip()
            if lang.startswith("{code-cell}") or lang in ("python", "ipython3", "python3"):
                in_fence = True
                fence_lang = lang
                fence_lines = []
                fence_start_line = idx
                continue
        elif in_fence and stripped.startswith("```"):
            loc = cell_label or f"line {fence_start_line}"
            for sym in _symbols_in_code("\n".join(fence_lines), bindings, pkg, known_symbols):
                out[sym].append(Backlink(doc_path, doc_title, current_heading, loc))
            in_fence = False
            fence_lang = ""
            fence_lines = []
            continue

        if in_fence:
            fence_lines.append(line)
            continue

        hm = _HEADING_RE.match(line)
        if hm:
            current_heading = hm.group(2).strip()
            continue

        for pm in _PY_ROLE_RE.finditer(line):
            sym = _resolve_py_role_target(pm.group(1), short_name_map, known_symbols)
            if sym:
                loc = cell_label or f"line {idx}"
                out[sym].append(Backlink(doc_path, doc_title, current_heading, loc))

        for lm in _API_LINK_RE.finditer(line):
            anchor = lm.group(2)
            sym = anchor_to_symbol.get(anchor or "")
            if sym:
                loc = cell_label or f"line {idx}"
                out[sym].append(Backlink(doc_path, doc_title, current_heading, loc))


def scan_tutorial_backlinks(
    content_dir: Path,
    pkg: LoadedPackage,
    known_symbols: set[str],
    short_name_map: dict[str, str],
    anchor_to_symbol: dict[str, str],
) -> dict[str, list[Backlink]]:
    """Scan all `.md` and `.ipynb` files under `content/` (excluding `reference/api/`) for API usage."""
    raw_hits: dict[str, list[Backlink]] = defaultdict(list)

    for path in sorted(content_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(content_dir)
        parts = rel.parts
        if parts[0] in ("_code", "_static", "_templates") or parts[:2] == ("reference", "api"):
            continue
        if any(p.startswith(".") or p == "__pycache__" for p in parts):
            continue

        rel_doc = f"content/{rel.as_posix()}"
        if path.suffix == ".md":
            text = path.read_text(encoding="utf-8", errors="ignore")
            title = _extract_title(text, path.stem.replace("-", " ").title())
            bindings: dict[str, str] = {}
            _scan_markdown_text(
                text, rel_doc, title, bindings, pkg, known_symbols, short_name_map, anchor_to_symbol, raw_hits
            )
        elif path.suffix == ".ipynb":
            try:
                nb = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            cells = nb.get("cells", [])
            title = path.stem.replace("_", " ").title()
            for c in cells:
                if c.get("cell_type") == "markdown":
                    md = "".join(c.get("source", []))
                    t = _extract_title(md, "")
                    if t:
                        title = t
                        break
            bindings = {}
            current_heading = title
            for cell_idx, cell in enumerate(cells, start=1):
                ctype = cell.get("cell_type")
                src = "".join(cell.get("source", []))
                if ctype == "markdown":
                    for hm in _HEADING_RE.finditer(src):
                        current_heading = hm.group(2).strip()
                    _scan_markdown_text(
                        src,
                        rel_doc,
                        title,
                        bindings,
                        pkg,
                        known_symbols,
                        short_name_map,
                        anchor_to_symbol,
                        raw_hits,
                        cell_label=f"cell {cell_idx}",
                    )
                elif ctype == "code":
                    for sym in _symbols_in_code(src, bindings, pkg, known_symbols):
                        raw_hits[sym].append(Backlink(rel_doc, title, current_heading, f"cell {cell_idx}"))

    # Deduplicate by (doc_path, section_heading) while keeping deterministic ordering
    deduped: dict[str, list[Backlink]] = {}
    for sym, links in raw_hits.items():
        seen: set[tuple[str, str]] = set()
        unique: list[Backlink] = []
        for bl in links:
            key = (bl.doc_path, bl.section_heading)
            if key not in seen:
                seen.add(key)
                unique.append(bl)
        deduped[sym] = unique
    return deduped
