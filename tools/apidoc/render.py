"""MyST Markdown page renderer, xref/search JSON emitters, cache, and TOC merger."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

import griffe
import yaml

from .backlinks import Backlink
from .callgraph import ClassHierarchy
from .config import AnchorRegistry, GitSourceInfo
from .docstring import first_sentence, render_docstring, sanitize_inline_rst
from .loader import LoadedPackage
from .traits import TraitInfo, class_is_has_traits, extract_trait

CACHE_FILENAME = ".apidoc-cache.json"


@dataclass(frozen=True)
class SymbolEntry:
    """Canonical documented symbol metadata used for xrefs and fuzzy search."""

    canonical_path: str
    name: str
    kind: str  # module | class | method | function | trait | attribute
    module_path: str
    anchor: str
    page_file: str  # filename relative to output dir (e.g. tvb.simulator.models.oscillator.md)
    page_slug: str  # MyST basename-derived slug (dots -> dashes or exact Myst slug)
    signature: str
    summary: str


def _myst_slug_for_filename(filename: str) -> str:
    """Predict MyST basename slug (`title2name` behavior: lowercase alphanumeric/dashes)."""
    stem = Path(filename).stem
    # mystmd's title2name replaces dots, underscores, and non-alnum runs with `-`
    return re.sub(r"[^a-zA-Z0-9-]+", "-", stem).strip("-").lower()


def _format_signature(fn: griffe.Function) -> str:
    """Format a readable Python signature for a function or method."""
    parts: list[str] = []
    for param in fn.parameters:
        s = param.name
        if param.kind == griffe.ParameterKind.var_positional:
            s = f"*{s}"
        elif param.kind == griffe.ParameterKind.var_keyword:
            s = f"**{s}"
        if param.annotation is not None:
            s = f"{s}: {param.annotation}"
        if param.default is not None:
            s = f"{s} = {param.default}"
        parts.append(s)
    ret = f" -> {fn.returns}" if fn.returns is not None else ""
    return f"({', '.join(parts)}){ret}"


def _read_source_lines(filepath: Path, lineno: int | None, endlineno: int | None) -> str:
    """Extract exact source lines for collapsible dropdowns."""
    if not filepath.is_file() or lineno is None:
        return ""
    try:
        lines = filepath.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    start = max(0, lineno - 1)
    end = min(len(lines), endlineno) if endlineno is not None else min(len(lines), start + 1)
    return "\n".join(lines[start:end])


def build_symbol_table(
    pkg: LoadedPackage,
    anchors: AnchorRegistry,
) -> tuple[dict[str, SymbolEntry], dict[str, str], dict[str, str]]:
    """Build canonical symbols, unambiguous short names, and anchor->symbol lookup."""
    symbols: dict[str, SymbolEntry] = {}
    short_candidates: dict[str, list[str]] = {}
    anchor_to_symbol: dict[str, str] = {}

    for mod_path, mod in pkg.modules.items():
        page_file = f"{mod_path}.md"
        page_slug = _myst_slug_for_filename(page_file)
        mod_anchor = anchors.anchor_for("module", mod_path)
        mod_entry = SymbolEntry(
            canonical_path=mod_path,
            name=mod.name,
            kind="module",
            module_path=mod_path,
            anchor=mod_anchor,
            page_file=page_file,
            page_slug=page_slug,
            signature="",
            summary=first_sentence(mod.docstring),
        )
        symbols[mod_path] = mod_entry
        anchor_to_symbol[mod_anchor] = mod_path
        short_candidates.setdefault(mod.name, []).append(mod_path)

        for member_name, member in sorted(mod.members.items()):
            if member_name.startswith("_") or member.is_alias:
                continue
            cpath = member.canonical_path

            if isinstance(member, griffe.Class):
                cls_anchor = anchors.anchor_for("class", cpath)
                cls_sig = ""
                init_fn = member.members.get("__init__")
                if isinstance(init_fn, griffe.Function):
                    cls_sig = _format_signature(init_fn)
                symbols[cpath] = SymbolEntry(
                    canonical_path=cpath,
                    name=member.name,
                    kind="class",
                    module_path=mod_path,
                    anchor=cls_anchor,
                    page_file=page_file,
                    page_slug=page_slug,
                    signature=cls_sig,
                    summary=first_sentence(member.docstring),
                )
                anchor_to_symbol[cls_anchor] = cpath
                short_candidates.setdefault(member.name, []).append(cpath)

                for sub_name, sub in sorted(member.members.items()):
                    if sub.is_alias:
                        continue
                    if sub_name.startswith("_") and sub_name != "__init__":
                        continue
                    sub_cpath = sub.canonical_path
                    if isinstance(sub, griffe.Function):
                        m_anchor = anchors.anchor_for("method", sub_cpath)
                        symbols[sub_cpath] = SymbolEntry(
                            canonical_path=sub_cpath,
                            name=f"{member.name}.{sub.name}",
                            kind="method",
                            module_path=mod_path,
                            anchor=m_anchor,
                            page_file=page_file,
                            page_slug=page_slug,
                            signature=_format_signature(sub),
                            summary=first_sentence(sub.docstring),
                        )
                        anchor_to_symbol[m_anchor] = sub_cpath
                        short_candidates.setdefault(f"{member.name}.{sub.name}", []).append(sub_cpath)
                    elif isinstance(sub, griffe.Attribute):
                        trait = extract_trait(sub)
                        kind = "trait" if trait is not None else "attribute"
                        a_anchor = anchors.anchor_for(kind, sub_cpath)
                        summary = (
                            (trait.doc or trait.label)
                            if trait is not None
                            else first_sentence(sub.docstring)
                        )
                        symbols[sub_cpath] = SymbolEntry(
                            canonical_path=sub_cpath,
                            name=f"{member.name}.{sub.name}",
                            kind=kind,
                            module_path=mod_path,
                            anchor=a_anchor,
                            page_file=page_file,
                            page_slug=page_slug,
                            signature=trait.type_expr if trait else (str(sub.annotation) if sub.annotation else ""),
                            summary=summary[:180],
                        )
                        anchor_to_symbol[a_anchor] = sub_cpath
                        short_candidates.setdefault(f"{member.name}.{sub.name}", []).append(sub_cpath)

            elif isinstance(member, griffe.Function):
                f_anchor = anchors.anchor_for("function", cpath)
                symbols[cpath] = SymbolEntry(
                    canonical_path=cpath,
                    name=member.name,
                    kind="function",
                    module_path=mod_path,
                    anchor=f_anchor,
                    page_file=page_file,
                    page_slug=page_slug,
                    signature=_format_signature(member),
                    summary=first_sentence(member.docstring),
                )
                anchor_to_symbol[f_anchor] = cpath
                short_candidates.setdefault(member.name, []).append(cpath)

    short_name_map = {
        short: paths[0]
        for short, paths in short_candidates.items()
        if len(paths) == 1
    }
    return symbols, short_name_map, anchor_to_symbol


def _relative_doc_link(from_page: Path, to_path_from_repo: Path, repo_root: Path) -> str:
    """Return a clean relative path from `from_page` to a doc under `repo_root`."""
    rel = os.path.relpath(repo_root / to_path_from_repo, start=from_page.parent)
    return Path(rel).as_posix()


def _link_symbol_list(
    targets: list[str],
    symbols: dict[str, SymbolEntry],
    current_page: str,
) -> str:
    links: list[str] = []
    for t in targets:
        entry = symbols.get(t)
        if not entry:
            continue
        href = f"#{entry.anchor}" if entry.page_file == current_page else f"{entry.page_file}#{entry.anchor}"
        links.append(f"[`{entry.name}`]({href})")
    return ", ".join(links)


def _render_source_dropdown(
    obj: griffe.Object,
    git_info: GitSourceInfo | None,
    search_path: Path,
) -> list[str]:
    """Emit a collapsible source dropdown + optional pinned `[View on Git]` link."""
    if not obj.filepath or obj.lineno is None:
        return []
    fpath = Path(str(obj.filepath))
    code = _read_source_lines(fpath, obj.lineno, obj.endlineno)
    if not code.strip():
        return []

    lines: list[str] = []
    if git_info is not None:
        try:
            rel_py = fpath.resolve().relative_to(search_path.resolve()).as_posix()
            url = git_info.blob_url(rel_py, obj.lineno, obj.endlineno)
            lines.append(f"[View on Git]({url}) · `{rel_py}#L{obj.lineno}`")
            lines.append("")
        except ValueError:
            pass

    lines.extend(
        [
            ":::{dropdown} Source code",
            f"```{{code-block}} python",
            f":linenos:",
            f":lineno-start: {obj.lineno}",
            "",
            code,
            "```",
            ":::",
        ]
    )
    return lines


def _render_backlinks_section(
    sym_path: str,
    backlinks: dict[str, list[Backlink]],
    page_path: Path,
    repo_root: Path,
    heading_level: int = 3,
) -> list[str]:
    hits = backlinks.get(sym_path)
    if not hits:
        return []
    h = "#" * heading_level
    lines = [f"{h} Used in Demos & Tutorials", ""]
    for bl in hits[:15]:
        rel_href = _relative_doc_link(page_path, Path(bl.doc_path), repo_root)
        sec = f" — *{bl.section_heading}*" if bl.section_heading and bl.section_heading != bl.doc_title else ""
        lines.append(f"- [{bl.doc_title}]({rel_href}){sec} (`{bl.location}`)")
    if len(hits) > 15:
        lines.append(f"- *…and {len(hits) - 15} more locations*")
    return lines


def _render_traits_table(
    traits: list[tuple[TraitInfo, SymbolEntry]],
    resolve_xref,
) -> list[str]:
    lines = [
        "| Attribute | Kind | Type / Dtype | Default | Domain / Choices | Description |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for tr, entry in traits:
        desc_raw = tr.doc or tr.label or "—"
        desc = sanitize_inline_rst(desc_raw, resolve_xref).replace("|", "\\|")
        typ = tr.type_expr.replace("|", "\\|")
        default = tr.default_expr.replace("|", "\\|")
        dom = tr.domain_expr.replace("|", "\\|")
        # Emit inline anchor inside first column via span or heading-free target
        lines.append(
            f"| <span id=\"{entry.anchor}\"></span>`{tr.name}` | `{tr.trait_kind}` | `{typ}` | `{default}` | `{dom}` | {desc} |"
        )
    return lines


def render_module_page(
    mod: griffe.Module,
    pkg: LoadedPackage,
    symbols: dict[str, SymbolEntry],
    short_name_map: dict[str, str],
    hierarchy: ClassHierarchy,
    static_uses: dict[str, list[str]],
    backlinks: dict[str, list[Backlink]],
    git_info: GitSourceInfo | None,
    out_dir: Path,
    repo_root: Path,
) -> str:
    """Render one module/package page as complete MyST Markdown."""
    mod_path = mod.canonical_path
    mod_entry = symbols[mod_path]
    current_page = mod_entry.page_file
    page_path = out_dir / current_page

    def resolve_xref(target: str, _kind: str | None = None) -> str | None:
        t = target.strip().lstrip("~")
        t = pkg.aliases.get(t, t)
        if t not in symbols and "." not in t:
            # Check module-local symbol, then unambiguous short name
            local = f"{mod_path}.{t}"
            if local in symbols:
                t = local
            elif t in short_name_map:
                t = short_name_map[t]
        elif t not in symbols and "." in t:
            # Handle `Class.method` relative to current module
            local = f"{mod_path}.{t}"
            if local in symbols:
                t = local
            elif t in short_name_map:
                t = short_name_map[t]
        entry = symbols.get(t)
        if not entry:
            return None
        return f"#{entry.anchor}" if entry.page_file == current_page else f"{entry.page_file}#{entry.anchor}"

    lines: list[str] = [
        "---",
        f"title: \"{mod_path}\"",
        "---",
        "",
        f"# `{mod_path}`",
        "",
        f"({mod_entry.anchor})=",
        "## Module Reference",
        "",
    ]

    mod_doc = render_docstring(mod.docstring, resolve_xref, heading_level=2)
    if mod_doc:
        lines.extend([mod_doc, ""])

    # Package child submodules summary table
    submods = [
        sub for sub in sorted(mod.modules.values(), key=lambda m: m.name)
        if not sub.is_alias and sub.canonical_path in pkg.modules
    ]
    if submods:
        lines.extend(["## Submodules", "", "| Module | Summary |", "| --- | --- |"])
        for sub in submods:
            se = symbols[sub.canonical_path]
            lines.append(f"| [`{sub.canonical_path}`]({se.page_file}#{se.anchor}) | {se.summary or '—'} |")
        lines.append("")

    classes = [
        m for m in sorted(mod.members.values(), key=lambda x: x.name)
        if not m.is_alias and not m.name.startswith("_") and isinstance(m, griffe.Class)
    ]
    functions = [
        m for m in sorted(mod.members.values(), key=lambda x: x.name)
        if not m.is_alias and not m.name.startswith("_") and isinstance(m, griffe.Function)
    ]

    if classes or functions:
        lines.extend(["## Overview", "", "| Symbol | Kind | Summary |", "| --- | --- | --- |"])
        for c in classes:
            ce = symbols[c.canonical_path]
            lines.append(f"| [`{c.name}`](#{ce.anchor}) | class | {ce.summary or '—'} |")
        for f in functions:
            fe = symbols[f.canonical_path]
            lines.append(f"| [`{f.name}`](#{fe.anchor}) | function | {fe.summary or '—'} |")
        lines.append("")

    # Module-level backlinks
    mod_bl = _render_backlinks_section(mod_path, backlinks, page_path, repo_root, heading_level=2)
    if mod_bl:
        lines.extend([*mod_bl, ""])

    if classes:
        lines.extend(["## Classes", ""])
        for cls in classes:
            cpath = cls.canonical_path
            ce = symbols[cpath]
            lines.extend([
                f"({ce.anchor})=",
                f"### `class {cls.name}{ce.signature}`",
                "",
            ])

            # Inheritance & Subclasses
            base_links = _link_symbol_list(hierarchy.bases.get(cpath, []), symbols, current_page)
            sub_links = _link_symbol_list(hierarchy.subclasses.get(cpath, []), symbols, current_page)
            if base_links:
                lines.append(f"**Inherits from:** {base_links}")
                lines.append("")
            if sub_links:
                lines.append(f"**Subclasses:** {sub_links}")
                lines.append("")

            cls_doc = render_docstring(cls.docstring, resolve_xref, heading_level=4)
            if cls_doc:
                lines.extend([cls_doc, ""])

            # Neotraits & plain attributes
            trait_rows: list[tuple[TraitInfo, SymbolEntry]] = []
            plain_attrs: list[tuple[griffe.Attribute, SymbolEntry]] = []
            for mname, mem in sorted(cls.members.items()):
                if mname.startswith("_") or mem.is_alias or not isinstance(mem, griffe.Attribute):
                    continue
                if mem.canonical_path not in symbols:
                    continue
                tr = extract_trait(mem)
                if tr is not None:
                    trait_rows.append((tr, symbols[mem.canonical_path]))
                else:
                    plain_attrs.append((mem, symbols[mem.canonical_path]))

            if trait_rows:
                heading = "#### Traits / Configurable Attributes" if class_is_has_traits(cls) else "#### Declarative Attributes"
                lines.extend([heading, "", *_render_traits_table(trait_rows, resolve_xref), ""])

            if plain_attrs:
                lines.extend([
                    "#### Class Attributes",
                    "",
                    "| Attribute | Value / Type | Description |",
                    "| --- | --- | --- |",
                ])
                for attr, ae in plain_attrs:
                    val_str = str(attr.value).replace("\n", " ")[:60] if attr.value is not None else "—"
                    desc = ae.summary or "—"
                    lines.append(
                        f"| <span id=\"{ae.anchor}\"></span>`{attr.name}` | `{val_str.replace('|', '\\|')}` | {desc.replace('|', '\\|')} |"
                    )
                lines.append("")

            # Class-level Uses & Backlinks & Source
            cls_uses = _link_symbol_list(static_uses.get(cpath, []), symbols, current_page)
            if cls_uses:
                lines.extend(["#### Uses / References (static)", "", cls_uses, ""])

            cls_bl = _render_backlinks_section(cpath, backlinks, page_path, repo_root, heading_level=4)
            if cls_bl:
                lines.extend([*cls_bl, ""])

            src_lines = _render_source_dropdown(cls, git_info, pkg.search_path)
            if src_lines:
                lines.extend([*src_lines, ""])

            # Methods
            methods = [
                m for m in sorted(cls.members.values(), key=lambda x: x.name)
                if not m.is_alias
                and isinstance(m, griffe.Function)
                and (not m.name.startswith("_") or m.name == "__init__")
                and m.canonical_path in symbols
            ]
            if methods:
                lines.extend(["#### Methods", ""])
                for meth in methods:
                    mpath = meth.canonical_path
                    me = symbols[mpath]
                    lines.extend([
                        f"({me.anchor})=",
                        f"##### `{meth.name}{me.signature}`",
                        "",
                    ])
                    mdoc = render_docstring(meth.docstring, resolve_xref, heading_level=6)
                    if mdoc:
                        lines.extend([mdoc, ""])
                    m_uses = _link_symbol_list(static_uses.get(mpath, []), symbols, current_page)
                    if m_uses:
                        lines.extend([f"**Uses / References (static):** {m_uses}", ""])
                    m_bl = _render_backlinks_section(mpath, backlinks, page_path, repo_root, heading_level=6)
                    if m_bl:
                        lines.extend([*m_bl, ""])
                    m_src = _render_source_dropdown(meth, git_info, pkg.search_path)
                    if m_src:
                        lines.extend([*m_src, ""])

    if functions:
        lines.extend(["## Functions", ""])
        for fn in functions:
            fpath = fn.canonical_path
            fe = symbols[fpath]
            lines.extend([
                f"({fe.anchor})=",
                f"### `def {fn.name}{fe.signature}`",
                "",
            ])
            fdoc = render_docstring(fn.docstring, resolve_xref, heading_level=4)
            if fdoc:
                lines.extend([fdoc, ""])
            f_uses = _link_symbol_list(static_uses.get(fpath, []), symbols, current_page)
            if f_uses:
                lines.extend(["#### Uses / References (static)", "", f_uses, ""])
            f_bl = _render_backlinks_section(fpath, backlinks, page_path, repo_root, heading_level=4)
            if f_bl:
                lines.extend([*f_bl, ""])
            f_src = _render_source_dropdown(fn, git_info, pkg.search_path)
            if f_src:
                lines.extend([*f_src, ""])

    return "\n".join(lines).rstrip() + "\n"


def emit_xref_and_search_indexes(
    symbols: dict[str, SymbolEntry],
    short_name_map: dict[str, str],
    aliases: dict[str, str],
    backlinks: dict[str, list[Backlink]],
    out_dir: Path,
    static_dir: Path,
) -> tuple[Path, Path]:
    """Write `api-xref-map.json` (for MyST plugin) and `api-symbols.json` (for fuzzy search)."""
    xref_symbols = {
        cpath: {
            "anchor": e.anchor,
            "page": e.page_file,
            "slug": e.page_slug,
            "url": f"/{e.page_slug}#{e.anchor}",
            "kind": e.kind,
            "name": e.name,
            "summary": e.summary,
        }
        for cpath, e in sorted(symbols.items())
    }
    xref_payload = {
        "symbols": xref_symbols,
        "shortNames": short_name_map,
        "aliases": {k: v for k, v in sorted(aliases.items()) if v in symbols},
    }
    xref_path = out_dir / "api-xref-map.json"
    xref_path.write_text(json.dumps(xref_payload, separators=(",", ":")), encoding="utf-8")

    # Compact symbol list for client-side fuzzy jump palette (<200KB gzipped)
    search_items = [
        {
            "id": e.canonical_path,
            "name": e.name,
            "kind": e.kind,
            "module": e.module_path,
            "signature": e.signature[:120],
            "summary": e.summary[:140],
            "url": f"/{e.page_slug}#{e.anchor}",
            "anchor": e.anchor,
            "page": e.page_file,
            "used_in_count": len(backlinks.get(e.canonical_path, ())),
        }
        for e in sorted(symbols.values(), key=lambda x: (x.canonical_path, x.kind))
    ]
    static_dir.mkdir(parents=True, exist_ok=True)
    symbols_path = static_dir / "api-symbols.json"
    symbols_path.write_text(json.dumps(search_items, separators=(",", ":")), encoding="utf-8")
    return xref_path, symbols_path


def _sphinx_chapters_to_myst_toc(chapters: list[dict], api_tree: list[dict]) -> list[dict]:
    """Convert `_toc.yml` chapter trees into `myst.yml` `project.toc` entries, attaching API tree."""
    out: list[dict] = []
    for ch in chapters:
        item: dict = {}
        if "file" in ch:
            item["file"] = ch["file"]
        if "title" in ch:
            item["title"] = ch["title"]
        children: list[dict] = []
        if "sections" in ch:
            children = _sphinx_chapters_to_myst_toc(ch["sections"], api_tree)
        if ch.get("file") == "content/reference/api/index.md":
            children = [*children, *api_tree]
        if children:
            item["children"] = children
        out.append(item)
    return out


def build_api_toc_tree(pkg: LoadedPackage) -> list[dict]:
    """Build nested MyST TOC children matching `tvb` package/submodule hierarchy."""
    mod_paths = sorted(pkg.modules.keys())
    mod_set = set(mod_paths)

    def children_of(parent: str) -> list[dict]:
        prefix = f"{parent}."
        direct = sorted(
            m for m in mod_set
            if m.startswith(prefix) and "." not in m[len(prefix):]
        )
        entries: list[dict] = []
        for child in direct:
            node: dict = {
                "file": f"content/reference/api/{child}.md",
                "title": child.rsplit(".", 1)[-1],
            }
            sub = children_of(child)
            if sub:
                node["children"] = sub
            entries.append(node)
        return entries

    top_roots = [m for m in mod_paths if "." not in m]
    if not top_roots:
        # Scoped run (e.g. tvb.simulator.models): find shallowest prefixes
        min_depth = min(m.count(".") for m in mod_paths)
        top_roots = [m for m in mod_paths if m.count(".") == min_depth]

    tree: list[dict] = []
    for root_mod in top_roots:
        entry: dict = {
            "file": f"content/reference/api/{root_mod}.md",
            "title": root_mod,
        }
        sub = children_of(root_mod)
        if sub:
            entry["children"] = sub
        tree.append(entry)
    return tree


def write_merged_myst_config(repo_root: Path, pkg: LoadedPackage, out_config: Path) -> Path:
    """Merge `myst.yml` + `_toc.yml` + generated API tree into a gitignored `.myst.apidoc.yml`."""
    myst_cfg = yaml.safe_load((repo_root / "myst.yml").read_text(encoding="utf-8"))
    toc_cfg = yaml.safe_load((repo_root / "_toc.yml").read_text(encoding="utf-8"))

    api_tree = build_api_toc_tree(pkg)
    myst_toc: list[dict] = [{"file": toc_cfg["root"]}]
    for part in toc_cfg.get("parts", []):
        if "file" in part and "chapters" not in part:
            # Single-page part (`- caption: X` + `file:`): link straight to the page
            # instead of wrapping it in a one-child collapsible group.
            myst_toc.append({"file": part["file"], "title": part["caption"]})
            continue
        part_entry: dict = {"title": part["caption"]}
        if "chapters" in part:
            part_entry["children"] = _sphinx_chapters_to_myst_toc(part["chapters"], api_tree)
        myst_toc.append(part_entry)

    # Compute exact index* slugs assigned by mystmd project.toc (where root README gets `index`).
    index_slugs: dict[str, str] = {}
    idx_counter = 1

    def walk_toc(entries: list[dict]) -> None:
        nonlocal idx_counter
        for item in entries:
            f = item.get("file", "")
            if f and Path(f).stem == "index":
                index_slugs[f] = f"/index-{idx_counter}"
                idx_counter += 1
            if "children" in item:
                walk_toc(item["children"])

    walk_toc(myst_toc[1:])
    nav_file_map = {
        "Tutorials": "content/tutorials/index.md",
        "How-to guides": "content/howtos/index.md",
        "Reference": "content/reference/index.md",
        "Explanation": "content/explanation/index.md",
        "Demos": "content/demos/index.md",
    }
    for nav_item in myst_cfg.get("site", {}).get("nav", []):
        target_file = nav_file_map.get(nav_item.get("title", ""))
        if target_file and target_file in index_slugs:
            nav_item["url"] = index_slugs[target_file]

    myst_cfg.setdefault("project", {})["toc"] = myst_toc
    out_config.write_text(yaml.safe_dump(myst_cfg, sort_keys=False), encoding="utf-8")
    return out_config


def write_pages_with_cache(
    pages: dict[str, str],
    out_dir: Path,
    *,
    use_cache: bool = True,
) -> tuple[int, int]:
    """Write rendered Markdown pages using content-hash caching; prune stale generated `.md` files."""
    cache_path = out_dir / CACHE_FILENAME
    old_cache: dict[str, str] = {}
    if use_cache and cache_path.is_file():
        try:
            old_cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            old_cache = {}

    new_cache: dict[str, str] = {}
    written = 0
    cached = 0

    for filename, content in sorted(pages.items()):
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        new_cache[filename] = digest
        target = out_dir / filename
        if use_cache and old_cache.get(filename) == digest and target.is_file():
            cached += 1
            continue
        target.write_text(content, encoding="utf-8")
        written += 1

    # Remove stale generated tvb*.md files from previous scopes
    for existing in out_dir.glob("tvb*.md"):
        if existing.name not in pages:
            existing.unlink()

    cache_path.write_text(json.dumps(new_cache, indent=2, sort_keys=True), encoding="utf-8")
    return written, cached
