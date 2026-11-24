#!/usr/bin/env python3
"""Stage JupyterLite contents directory (_build/lite_contents) from content/.

This script unifies the MyST documentation tree and the JupyterLite environment:
1. Cleans and creates `_build/lite_contents/`.
2. Copies `content/_code/tvbl/` and `content/_code/tvbl_docs.py` to the root of
   `_build/lite_contents/` so that `import tvbl` and `import tvbl_docs` work
   directly from any notebook.
3. Copies repo root `README.md` to `_build/lite_contents/README.md`.
4. Walks `content/` (excluding `_code/`, `_static/`, and `.refs-cache.json`):
   - Copies notebooks (.ipynb), Python scripts (.py), data files (.zip, .npy, .pem, .bib, .toml, .txt, etc.),
     and figures (.png, .jpg, .svg, .pdf).
   - Converts MyST markdown (.md) containing executable code cells (`{code-cell}`)
     into Jupyter notebooks (.ipynb) at matching relative paths, adapting any
     `sys.path` boilerplate so that `tvbl` and `tvbl_docs` are found seamlessly.
   - Copies generated notebooks to `_build/html/notebooks/` for direct download links.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys

try:
    import jupytext
except ImportError:
    jupytext = None

DATA_EXTENSIONS = {
    ".zip", ".npy", ".pem", ".bib", ".toml", ".txt", ".csv",
    ".json", ".mat", ".h5", ".dat", ".rst",
}

FIGURE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".pdf", ".svg", ".gif", ".webp",
}

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


def patch_code_cell(source: str | list[str]) -> str | list[str]:
    """Adapt sys.path search in code cells so tvbl/tvbl_docs work in Lite and MyST."""
    is_list = isinstance(source, list)
    text = "".join(source) if is_list else source

    if SYS_PATH_BOILERPLATE_PATTERN.search(text):
        patched = SYS_PATH_BOILERPLATE_PATTERN.sub(SYS_PATH_REPLACEMENT, text)
        return patched.splitlines(keepends=True) if is_list else patched

    if '(_root / "myst.yml").exists()' in text and 'sys.path.insert' in text:
        # Fallback line-by-line replacement if indentation or formatting differs
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


def convert_with_jupytext(md_path: Path, ipynb_path: Path) -> None:
    """Convert MyST markdown to Jupyter notebook using jupytext."""
    nb = jupytext.read(md_path, fmt="myst")
    for cell in nb.cells:
        if cell.get("cell_type") == "code":
            cell["source"] = patch_code_cell(cell.get("source", ""))
    jupytext.write(nb, ipynb_path, fmt="notebook")


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
    # Parse frontmatter if present
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

            # Check for directive tags e.g. :tags: [remove-cell]
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
    if jupytext is not None:
        try:
            convert_with_jupytext(md_path, ipynb_path)
            return
        except Exception as exc:
            print(f"Warning: jupytext failed on {md_path} ({exc}); using fallback converter")
    convert_with_fallback(md_path, ipynb_path)


def stage_lite(root: Path, content_dir: Path, lite_contents_dir: Path, html_dir: Path) -> None:
    print(f"=== Staging JupyterLite contents ===")
    print(f"  Root:           {root}")
    print(f"  Content dir:    {content_dir}")
    print(f"  Lite contents:  {lite_contents_dir}")
    print(f"  HTML dir:       {html_dir}")

    # 1. Clean and create lite_contents directory
    if lite_contents_dir.exists():
        shutil.rmtree(lite_contents_dir)
    lite_contents_dir.mkdir(parents=True, exist_ok=True)

    # 2. Copy tvbl package and tvbl_docs.py to lite_contents root
    tvbl_src = content_dir / "_code" / "tvbl"
    tvbl_dest = lite_contents_dir / "tvbl"
    if tvbl_src.exists():
        shutil.copytree(
            tvbl_src,
            tvbl_dest,
            ignore=shutil.ignore_patterns(
                "__pycache__", "*.pyc", "*.nbc", "*.nbi", "test_*.py"
            ),
        )
        print(f"Copied {tvbl_src} -> {tvbl_dest}")
    else:
        print(f"Warning: {tvbl_src} does not exist!")

    tvbl_docs_src = content_dir / "_code" / "tvbl_docs.py"
    tvbl_docs_dest = lite_contents_dir / "tvbl_docs.py"
    if tvbl_docs_src.exists():
        shutil.copy2(tvbl_docs_src, tvbl_docs_dest)
        print(f"Copied {tvbl_docs_src} -> {tvbl_docs_dest}")

    # Ensure sys.path in Lite finds root if launched from anywhere
    sitecustomize_path = lite_contents_dir / "sitecustomize.py"
    sitecustomize_path.write_text(
        'import sys, pathlib\n'
        'for _dir in [pathlib.Path("/drive"), pathlib.Path.cwd(), *pathlib.Path.cwd().parents]:\n'
        '    if (_dir / "tvbl_docs.py").exists() and str(_dir) not in sys.path:\n'
        '        sys.path.insert(0, str(_dir))\n'
        '        break\n',
        encoding="utf-8",
    )

    # 3. Copy README.md to lite_contents
    readme_src = root / "README.md"
    readme_dest = lite_contents_dir / "README.md"
    if readme_src.exists():
        shutil.copy2(readme_src, readme_dest)
        print(f"Copied {readme_src} -> {readme_dest}")

    # 4. Walk content/ and copy/convert files
    copied_count = 0
    converted_count = 0
    download_dir = html_dir / "notebooks"
    download_dir.mkdir(parents=True, exist_ok=True)

    for item in sorted(content_dir.rglob("*")):
        if not item.is_file():
            continue

        rel = item.relative_to(content_dir)
        parts = rel.parts

        # Skip excluded dirs and files
        if parts[0] in ("_code", "_static", "_templates", ".refs-cache.json"):
            continue
        if parts[:2] == ("reference", "api"):
            continue
        if any(p.startswith(".") for p in parts):
            continue
        if any(p == "__pycache__" for p in parts):
            continue

        dest = lite_contents_dir / rel

        # Case A: Notebooks
        if item.suffix == ".ipynb":
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)
            copied_count += 1

        # Case B: Python scripts
        elif item.suffix == ".py":
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)
            copied_count += 1

        # Case C: Data files
        elif item.suffix in DATA_EXTENSIONS:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)
            copied_count += 1

        # Case D: Figures and images
        elif item.suffix in FIGURE_EXTENSIONS or "figures" in parts:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dest)
            copied_count += 1

        # Case E: Markdown files
        elif item.suffix == ".md":
            text = item.read_text(encoding="utf-8")
            if "```{code-cell}" in text or "```code-cell" in text:
                # Convert executable markdown to ipynb
                nb_dest = dest.with_suffix(".ipynb")
                nb_dest.parent.mkdir(parents=True, exist_ok=True)
                convert_md_to_ipynb(item, nb_dest)
                converted_count += 1

                # Copy to downloadable notebooks folder
                download_dest = download_dir / rel.with_suffix(".ipynb")
                download_dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(nb_dest, download_dest)
            else:
                # Non-executable markdown docs in demos or lab
                if any(p in ("demos", "lab") for p in parts):
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(item, dest)
                    copied_count += 1

    print(f"\nStaging complete!")
    print(f"  Copied files:     {copied_count}")
    print(f"  Converted .md:    {converted_count}")
    print(f"  Lite contents at: {lite_contents_dir}")
    print(f"  Downloads at:     {download_dir}")


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

    args = parser.parse_args()
    root = args.root.resolve()
    content_dir = (args.content or (root / "content")).resolve()
    lite_contents_dir = (args.output or (root / "_build" / "lite_contents")).resolve()
    html_dir = (args.html or (root / "_build" / "html")).resolve()

    stage_lite(root, content_dir, lite_contents_dir, html_dir)


if __name__ == "__main__":
    main()
