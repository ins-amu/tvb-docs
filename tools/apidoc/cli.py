"""CLI entry point for TVB API documentation generation and link checking."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .backlinks import scan_tutorial_backlinks
from .callgraph import build_class_hierarchy, extract_static_uses
from .config import AnchorRegistry, find_repo_root, find_tvb_search_path, load_tvb_git_info
from .loader import load_tvb_package
from .render import (
    build_symbol_table,
    emit_xref_and_search_indexes,
    render_module_page,
    write_merged_myst_config,
    write_pages_with_cache,
)


def generate_docs(
    *,
    scope: str | None = None,
    out_dir: Path | None = None,
    use_cache: bool = True,
    write_myst_config: bool = True,
) -> dict[str, int | float]:
    """Run the full static API extraction, cross-linking, and MyST rendering pipeline."""
    t0 = time.perf_counter()
    repo_root = find_repo_root()
    search_path = find_tvb_search_path(repo_root)
    git_info = load_tvb_git_info(search_path, repo_root)

    api_dir = (out_dir or (repo_root / "content" / "reference" / "api")).resolve()
    api_dir.mkdir(parents=True, exist_ok=True)
    static_dir = repo_root / "_build" / "apidoc"

    pkg = load_tvb_package(search_path, scope=scope)
    anchors = AnchorRegistry()
    symbols, short_name_map, anchor_to_symbol = build_symbol_table(pkg, anchors)
    known_symbols = set(symbols.keys())

    hierarchy = build_class_hierarchy(pkg, known_symbols)
    static_uses = extract_static_uses(pkg, known_symbols, hierarchy)
    backlinks = scan_tutorial_backlinks(
        repo_root / "content",
        pkg,
        known_symbols,
        short_name_map,
        anchor_to_symbol,
    )

    pages: dict[str, str] = {}
    for mod_path, mod in pkg.modules.items():
        pages[f"{mod_path}.md"] = render_module_page(
            mod=mod,
            pkg=pkg,
            symbols=symbols,
            short_name_map=short_name_map,
            hierarchy=hierarchy,
            static_uses=static_uses,
            backlinks=backlinks,
            git_info=git_info,
            out_dir=api_dir,
            repo_root=repo_root,
        )

    written, cached = write_pages_with_cache(pages, api_dir, use_cache=use_cache)
    emit_xref_and_search_indexes(
        symbols=symbols,
        short_name_map=short_name_map,
        aliases=pkg.aliases,
        backlinks=backlinks,
        out_dir=api_dir,
        static_dir=static_dir,
    )

    if write_myst_config:
        write_merged_myst_config(repo_root, pkg, repo_root / ".myst.apidoc.yml")

    elapsed = time.perf_counter() - t0
    return {
        "modules": len(pages),
        "symbols": len(symbols),
        "written": written,
        "cached": cached,
        "backlinked_symbols": len(backlinks),
        "elapsed": elapsed,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m tools.apidoc",
        description="Generate native MyST API reference pages for tvb-library.",
    )
    parser.add_argument(
        "--scope",
        default=None,
        help="Optional dotted package/module prefix (e.g. tvb.simulator.models).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: content/reference/api).",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Re-write all generated Markdown files ignoring content hashes.",
    )
    parser.add_argument(
        "--no-myst-config",
        action="store_true",
        help="Skip writing merged .myst.apidoc.yml.",
    )
    args = parser.parse_args(argv)

    stats = generate_docs(
        scope=args.scope,
        out_dir=args.out,
        use_cache=not args.no_cache,
        write_myst_config=not args.no_myst_config,
    )
    print(
        f"Generated API docs in {stats['elapsed']:.2f}s: "
        f"{stats['modules']} modules, {stats['symbols']} symbols, "
        f"{stats['written']} written, {stats['cached']} cached, "
        f"{stats['backlinked_symbols']} symbols with tutorial backlinks."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
