#!/usr/bin/env python3
"""Stage JupyterLite contents directory (_build/lite_contents) from content/.

This script unifies the MyST documentation tree and the JupyterLite environment:
1. Incrementally syncs `_build/lite_contents/` (preserving mtimes for JupyterLite's
   doit cache, using hardlinks where possible, and pruning stale files).
2. Copies `content/_code/tvbl/` and `content/_code/tvbl_docs.py` to the root of
   `_build/lite_contents/` so that `import tvbl` and `import tvbl_docs` work
   directly from any notebook.
3. Copies repo root `README.md` to `_build/lite_contents/README.md`.
4. Walks `content/` (excluding `_code/`, `_static/`, `_templates/`, and `.refs-cache.json`):
   - Syncs notebooks (.ipynb), Python scripts (.py), data files, and figures.
   - Converts MyST markdown (.md) containing executable code cells (`{code-cell}`)
     into Jupyter notebooks (.ipynb) at matching relative paths (only when changed),
     adapting any `sys.path` boilerplate so that `tvbl` and `tvbl_docs` are found.
   - Syncs generated notebooks to the downloadable notebooks folder (default
     `_build/html/notebooks/` or `--notebooks-dir`).

Pass `--notebooks-only` to convert only `{code-cell}` markdown files directly into
`--notebooks-dir` in milliseconds without staging the full 56 MB Lite contents tree.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil

def _get_jupytext():
    try:
        import jupytext
        return jupytext
    except ImportError:
        return None

DATA_EXTENSIONS = {
    ".zip", ".npy", ".pem", ".bib", ".toml", ".txt", ".csv",
    ".json", ".mat", ".h5", ".dat", ".rst",
}

FIGURE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".pdf", ".svg", ".gif", ".webp",
}

EXCLUDED_TOP_DIRS = {"_code", "_static", "_templates", ".refs-cache.json"}

SYS_PATH_BOILERPLATE_PATTERN = re.compile(
    r'_root\s*=\s*pathlib\.Path\.cwd\(\)\s*\n'
    r'\s*while\s+not\s*\(_root\s*/\s*"myst\.yml"\)\.exists\(\)\s+and\s+_root\s*!=\s*_root\.parent:\s*\n'
    r'\s*_root\s*=\s*_root\.parent\s*\n'
    r'\s*sys\.path\.insert\(0,\s*str\(_root\s*/\s*"content"\s*/\s*"_code"\)\)'
)

SYS_PATH_REPLACEMENT = (
    '_root = pathlib.Path.cwd()\n'
    'while not (_root / "tvbl_docs.py").exists() and not (_root / "myst.yml").exists() and _root != _root.parent:\n'
    '    _root = _root.parent\n'
    'if (_root / "tvbl_docs.py").exists():\n'
    '    if str(_root) not in sys.path:\n'
    '        sys.path.append(str(_root))\n'
    'elif (_root / "content" / "_code").exists():\n'
    '    if str(_root / "content" / "_code") not in sys.path:\n'
    '        sys.path.append(str(_root / "content" / "_code"))'
)

SITECUSTOMIZE_TEXT = (
    'import sys, pathlib\n'
    'for _dir in [pathlib.Path("/drive"), pathlib.Path.cwd(), *pathlib.Path.cwd().parents]:\n'
    '    if (_dir / "tvbl_docs.py").exists() and str(_dir) not in sys.path:\n'
    '        sys.path.insert(0, str(_dir))\n'
    '        break\n'
)

SCRIPT_MTIME_NS = Path(__file__).resolve().stat().st_mtime_ns


def patch_code_cell(source: str | list[str]) -> str | list[str]:
    """Adapt sys.path search in code cells so tvbl/tvbl_docs work in Lite and MyST."""
    is_list = isinstance(source, list)
    text = "".join(source) if is_list else source

    if SYS_PATH_BOILERPLATE_PATTERN.search(text):
        patched = SYS_PATH_BOILERPLATE_PATTERN.sub(SYS_PATH_REPLACEMENT, text)
        return patched.splitlines(keepends=True) if is_list else patched

    if '(_root / "myst.yml").exists()' in text and 'sys.path.insert' in text:
        lines = text.splitlines(keepends=True)
        new_lines: list[str] = []
        skip = False
        for line in lines:
            if '_root = pathlib.Path.cwd()' in line:
                new_lines.extend([l + "\n" for l in SYS_PATH_REPLACEMENT.splitlines()])
                skip = True
            elif skip and 'sys.path.insert' in line:
                skip = False
            elif not skip:
                new_lines.append(line)
        return new_lines if is_list else "".join(new_lines)

    return source


def convert_with_jupytext(md_path: Path, ipynb_path: Path, jupytext_mod) -> None:
    """Convert MyST markdown to Jupyter notebook using jupytext."""
    nb = jupytext_mod.read(md_path, fmt="myst")
    for cell in nb.cells:
        if cell.get("cell_type") == "code":
            cell["source"] = patch_code_cell(cell.get("source", ""))
    jupytext_mod.write(nb, ipynb_path, fmt="notebook")


def convert_with_fallback(md_path: Path, ipynb_path: Path) -> None:
    """Fallback converter when jupytext is not installed in the environment."""
    raw = md_path.read_text(encoding="utf-8")
    lines = raw.splitlines(keepends=True)

    meta = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.12",
        },
    }

    i = 0
    if lines and lines[0].strip() == "---":
        i = 1
        while i < len(lines) and lines[i].strip() != "---":
            i += 1
        if i < len(lines) and lines[i].strip() == "---":
            i += 1

    cells: list[dict] = []
    current_md: list[str] = []

    def flush_md() -> None:
        if current_md:
            src = "".join(current_md)
            if src.strip():
                cells.append({
                    "cell_type": "markdown",
                    "metadata": {},
                    "source": list(current_md),
                })
            current_md.clear()

    while i < len(lines):
        line = lines[i]
        if re.match(r"^```+(\{code-cell\}|\{code\}|code-cell)", line.strip()):
            flush_md()
            i += 1
            cell_meta: dict = {}
            code_lines: list[str] = []

            while i < len(lines) and lines[i].strip().startswith(":"):
                tag_line = lines[i].strip()
                if tag_line.startswith(":tags:"):
                    tag_match = re.search(r"\[(.*?)\]", tag_line)
                    if tag_match:
                        tags = [t.strip().strip("\"'") for t in tag_match.group(1).split(",")]
                        cell_meta["tags"] = tags
                i += 1

            if i < len(lines) and not lines[i].strip():
                i += 1

            while i < len(lines):
                if lines[i].strip().startswith("```"):
                    i += 1
                    break
                code_lines.append(lines[i])
                i += 1

            patched_code = patch_code_cell(code_lines)
            cells.append({
                "cell_type": "code",
                "execution_count": None,
                "metadata": cell_meta,
                "outputs": [],
                "source": patched_code if isinstance(patched_code, list) else patched_code.splitlines(keepends=True),
            })
        else:
            current_md.append(line)
            i += 1

    flush_md()

    nb_dict = {
        "cells": cells,
        "metadata": meta,
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    with open(ipynb_path, "w", encoding="utf-8") as f:
        json.dump(nb_dict, f, indent=1)


def convert_md_to_ipynb(md_path: Path, ipynb_path: Path) -> None:
    """Convert MyST markdown to Jupyter notebook using jupytext or fallback."""
    if ipynb_path.exists() or ipynb_path.is_symlink():
        ipynb_path.unlink()
    jupytext_mod = _get_jupytext()
    if jupytext_mod is not None:
        try:
            convert_with_jupytext(md_path, ipynb_path, jupytext_mod)
            return
        except Exception as exc:
            print(f"Warning: jupytext failed on {md_path} ({exc}); using fallback converter")
    convert_with_fallback(md_path, ipynb_path)


def sync_file(src: Path, dst: Path, *, hardlink: bool = True, force: bool = False) -> bool:
    """Sync src -> dst only when needed; returns True if dst was updated."""
    if dst.exists() and not dst.is_symlink() and not force:
        try:
            if hardlink and os.path.samefile(src, dst):
                return False
        except OSError:
            pass
        s_stat = src.stat()
        d_stat = dst.stat()
        if s_stat.st_size == d_stat.st_size and s_stat.st_mtime_ns == d_stat.st_mtime_ns:
            return False

    dst.parent.mkdir(parents=True, exist_ok=True)
    # Unlink before replacing so we never mutate a shared hardlink target.
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    if hardlink:
        try:
            os.link(src, dst)
            return True
        except OSError:
            pass
    shutil.copy2(src, dst)
    return True


def needs_convert(md_path: Path, ipynb_path: Path, *, force: bool = False) -> bool:
    if force or not ipynb_path.is_file():
        return True
    try:
        dst_mtime = ipynb_path.stat().st_mtime_ns
        src_mtime = max(md_path.stat().st_mtime_ns, SCRIPT_MTIME_NS)
        return dst_mtime < src_mtime
    except OSError:
        return True


def prune_stale(root_dir: Path, expected: set[Path]) -> int:
    """Delete files in root_dir not present in expected, plus empty directories."""
    if not root_dir.exists():
        return 0
    pruned = 0
    for path in sorted(root_dir.rglob("*"), reverse=True):
        if path.is_file() or path.is_symlink():
            if path.resolve() not in expected:
                path.unlink()
                pruned += 1
        elif path.is_dir():
            try:
                if not any(path.iterdir()):
                    path.rmdir()
            except OSError:
                pass
    return pruned


def write_if_changed(path: Path, text: str, *, force: bool = False) -> bool:
    if not force and path.is_file():
        try:
            if path.read_text(encoding="utf-8") == text:
                return False
        except OSError:
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        path.unlink()
    path.write_text(text, encoding="utf-8")
    return True


def is_excluded_content(parts: tuple[str, ...]) -> bool:
    if parts[0] in EXCLUDED_TOP_DIRS:
        return True
    if parts[:2] == ("reference", "api"):
        return True
    if any(p.startswith(".") for p in parts):
        return True
    if any(p == "__pycache__" for p in parts):
        return True
    return False


def stage_notebooks_only(
    content_dir: Path, download_dir: Path, *, force: bool = False
) -> None:
    download_dir.mkdir(parents=True, exist_ok=True)
    expected_downloads: set[Path] = set()
    converted = 0
    skipped = 0

    for item in sorted(content_dir.rglob("*.md")):
        if not item.is_file():
            continue
        rel = item.relative_to(content_dir)
        if is_excluded_content(rel.parts):
            continue
        text = item.read_text(encoding="utf-8")
        if "```{code-cell}" in text or "```code-cell" in text:
            download_dest = download_dir / rel.with_suffix(".ipynb")
            expected_downloads.add(download_dest.resolve())
            if needs_convert(item, download_dest, force=force):
                download_dest.parent.mkdir(parents=True, exist_ok=True)
                convert_md_to_ipynb(item, download_dest)
                converted += 1
            else:
                skipped += 1

    pruned = prune_stale(download_dir, expected_downloads)
    print(
        f"Notebooks staged ({download_dir}): "
        f"converted={converted}, unchanged={skipped}, pruned={pruned}"
    )


def stage_lite(
    root: Path,
    content_dir: Path,
    lite_contents_dir: Path,
    download_dir: Path,
    *,
    force: bool = False,
) -> None:
    lite_contents_dir.mkdir(parents=True, exist_ok=True)
    download_dir.mkdir(parents=True, exist_ok=True)

    expected_lite: set[Path] = set()
    expected_downloads: set[Path] = set()
    copied = 0
    skipped = 0
    converted = 0

    def record_copy(src: Path, dst: Path) -> None:
        nonlocal copied, skipped
        expected_lite.add(dst.resolve())
        if sync_file(src, dst, hardlink=True, force=force):
            copied += 1
        else:
            skipped += 1

    # 1. Sync tvbl package and tvbl_docs.py to lite_contents root
    tvbl_src = content_dir / "_code" / "tvbl"
    tvbl_dest = lite_contents_dir / "tvbl"
    if tvbl_src.exists():
        for item in sorted(tvbl_src.rglob("*")):
            if not item.is_file():
                continue
            rel_tvbl = item.relative_to(tvbl_src)
            if any(p == "__pycache__" or p.startswith(".") for p in rel_tvbl.parts):
                continue
            if item.suffix in {".pyc", ".nbc", ".nbi"} or item.name.startswith("test_"):
                continue
            record_copy(item, tvbl_dest / rel_tvbl)
    else:
        print(f"Warning: {tvbl_src} does not exist!")

    tvbl_docs_src = content_dir / "_code" / "tvbl_docs.py"
    if tvbl_docs_src.exists():
        record_copy(tvbl_docs_src, lite_contents_dir / "tvbl_docs.py")

    sitecustomize_path = lite_contents_dir / "sitecustomize.py"
    expected_lite.add(sitecustomize_path.resolve())
    if write_if_changed(sitecustomize_path, SITECUSTOMIZE_TEXT, force=force):
        copied += 1
    else:
        skipped += 1

    # 2. Sync README.md
    readme_src = root / "README.md"
    if readme_src.exists():
        record_copy(readme_src, lite_contents_dir / "README.md")

    # 3. Walk content/ and incrementally sync/convert files
    for item in sorted(content_dir.rglob("*")):
        if not item.is_file():
            continue

        rel = item.relative_to(content_dir)
        parts = rel.parts
        if is_excluded_content(parts):
            continue

        dest = lite_contents_dir / rel

        if item.suffix in {".ipynb", ".py"} or item.suffix in DATA_EXTENSIONS or item.suffix in FIGURE_EXTENSIONS or "figures" in parts:
            record_copy(item, dest)
        elif item.suffix == ".md":
            text = item.read_text(encoding="utf-8")
            if "```{code-cell}" in text or "```code-cell" in text:
                nb_dest = dest.with_suffix(".ipynb")
                expected_lite.add(nb_dest.resolve())
                if needs_convert(item, nb_dest, force=force):
                    nb_dest.parent.mkdir(parents=True, exist_ok=True)
                    convert_md_to_ipynb(item, nb_dest)
                    converted += 1
                else:
                    skipped += 1

                download_dest = download_dir / rel.with_suffix(".ipynb")
                expected_downloads.add(download_dest.resolve())
                sync_file(nb_dest, download_dest, hardlink=True, force=force)
            elif any(p in ("demos", "lab") for p in parts):
                record_copy(item, dest)

    pruned_lite = prune_stale(lite_contents_dir, expected_lite)
    pruned_dl = prune_stale(download_dir, expected_downloads)

    print(
        f"Staged Lite contents ({lite_contents_dir}): "
        f"updated={copied}, converted={converted}, unchanged={skipped}, "
        f"pruned={pruned_lite + pruned_dl}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Stage JupyterLite contents from content/")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent.parent,
                        help="Repository root directory")
    parser.add_argument("--content", type=Path, default=None,
                        help="Content directory (default: <root>/content)")
    parser.add_argument("--output", type=Path, default=None,
                        help="Output directory (default: <root>/_build/lite_contents)")
    parser.add_argument("--html", type=Path, default=None,
                        help="HTML build directory (default: <root>/_build/html)")
    parser.add_argument("--notebooks-dir", type=Path, default=None,
                        help="Downloadable notebooks directory (default: <html_dir>/notebooks)")
    parser.add_argument("--notebooks-only", action="store_true",
                        help="Only convert executable markdown files into notebooks-dir")
    parser.add_argument("--force", action="store_true",
                        help="Force re-copying and re-converting all files")

    args = parser.parse_args()
    root = args.root.resolve()
    content_dir = (args.content or (root / "content")).resolve()
    lite_contents_dir = (args.output or (root / "_build" / "lite_contents")).resolve()
    html_dir = (args.html or (root / "_build" / "html")).resolve()
    download_dir = (args.notebooks_dir or (html_dir / "notebooks")).resolve()

    if args.notebooks_only:
        stage_notebooks_only(content_dir, download_dir, force=args.force)
    else:
        stage_lite(root, content_dir, lite_contents_dir, download_dir, force=args.force)


if __name__ == "__main__":
    main()
