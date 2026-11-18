#!/usr/bin/env python3
"""Apply runtime patches to a built JupyterLite site for xeus-python WASM compatibility.

1. Patch xpython.js / pyjs_runtime_browser.js for Numba RTLD_GLOBAL:
   Numba array kernels require `_nrt_python...so` (which defines `NRT_adapt_ndarray_from_python`)
   to be dlopen'd RTLD_GLOBAL. The emscripten-forge pyjs/xpython runtime's `libraryType()` marks
   every `*cpython-3*-wasm32-emscripten.so` as "local" (RTLD_LOCAL), causing JIT-compiled side
   modules to fail with `Dynamic linking error: cannot resolve symbol NRT_adapt_ndarray_from_python`.

2. Patch tvb_library's logger builder for xeus-python streams:
   `xeus-python` replaces `sys.stdout` with a `stream.Stream` object without a `.name`
   attribute, causing `tvb.basic.logger.builder.set_loggers_level` (called on importing
   `tvb.simulator.lab`) to fail with `AttributeError: 'stream.Stream' object has no attribute 'name'`.

3. Bundle `tvbl` and `tvbl_docs.py` directly into `site-packages` inside the packed kernel
   environment (`xeus-python` ignores `.pth` files and starts in the notebook's subdirectory,
   so `/drive` is not on `sys.path`).
"""

from __future__ import annotations

import io
import os
import sys
import tarfile
from pathlib import Path

IGNORED_NAMES = {"__pycache__"}
IGNORED_SUFFIXES = (".pyc", ".nbc", ".nbi")


def patch_rtld_global(lite_dir: Path) -> bool:
    """Patch xpython.js / pyjs_runtime_browser.js so extension modules load RTLD_GLOBAL."""
    targets = [
        *lite_dir.rglob("xpython.js"),
        *lite_dir.rglob("pyjs_runtime_browser.js"),
    ]
    if not targets:
        print(f"Error: neither xpython.js nor pyjs_runtime_browser.js found in {lite_dir}", file=sys.stderr)
        return False

    old = 'return"local"'
    new = 'return"global"'
    patched_any = False

    for path in targets:
        source = path.read_text(encoding="utf-8")
        if old in source:
            path.write_text(source.replace(old, new), encoding="utf-8")
            print(f"Patched {path}: replaced {old} with {new}")
            patched_any = True
        elif new in source:
            print(f"Already patched {path}")
            patched_any = True
        else:
            print(f"Warning: patch point {old!r} not found in {path}", file=sys.stderr)

    return patched_any


def _collect_tvbl_files(code_dir: Path) -> dict[str, tuple[bytes, float]]:
    """Collect tvbl package and tvbl_docs.py bytes keyed by path relative to site-packages."""
    files: dict[str, tuple[bytes, float]] = {}
    tvbl_docs = code_dir / "tvbl_docs.py"
    if tvbl_docs.is_file():
        files["tvbl_docs.py"] = (tvbl_docs.read_bytes(), tvbl_docs.stat().st_mtime)

    tvbl_dir = code_dir / "tvbl"
    if tvbl_dir.is_dir():
        for item in sorted(tvbl_dir.rglob("*")):
            if not item.is_file():
                continue
            rel = item.relative_to(code_dir)
            if any(part in IGNORED_NAMES for part in rel.parts):
                continue
            if item.name.startswith("test_") or item.suffix in IGNORED_SUFFIXES:
                continue
            files[rel.as_posix()] = (item.read_bytes(), item.stat().st_mtime)
    return files


def _is_bundled_tvbl_member(name: str, site_packages_prefix: str | None) -> bool:
    """Return True for previously injected tvbl/tvbl_docs/tvbl_drive.pth site-packages entries."""
    if not site_packages_prefix or not name.startswith(site_packages_prefix + "/"):
        return False
    rel = name[len(site_packages_prefix) + 1:]
    return rel == "tvbl_drive.pth" or rel == "tvbl_docs.py" or rel == "tvbl" or rel.startswith("tvbl/")


def _patch_tvb_tarball(tar_path: Path, code_dir: Path) -> bool:
    """Patch tvb/basic/logger/builder.py and bundle tvbl/tvbl_docs.py into site-packages."""
    old = "if isinstance(handler, StreamHandler) and handler.stream.name == 'stdout':"
    new = "if isinstance(handler, StreamHandler) and getattr(handler.stream, 'name', None) == 'stdout':"

    bundled = _collect_tvbl_files(code_dir)
    site_packages_prefix: str | None = None
    existing_bundled: dict[str, bytes] = {}
    has_obsolete_pth = False
    logger_patched = False
    logger_needs_write = False

    with tarfile.open(tar_path, "r:gz") as src:
        members = src.getmembers()
        for member in members:
            if site_packages_prefix is None and "/site-packages/" in member.name:
                site_packages_prefix = member.name.split("/site-packages/", 1)[0] + "/site-packages"
            if member.isfile() and member.name.endswith("tvb/basic/logger/builder.py"):
                extracted = src.extractfile(member)
                if extracted is not None:
                    text = extracted.read().decode("utf-8")
                    if old in text:
                        logger_patched = True
                        logger_needs_write = True
                    elif new in text:
                        logger_patched = True

        if site_packages_prefix:
            for member in members:
                if _is_bundled_tvbl_member(member.name, site_packages_prefix):
                    rel = member.name[len(site_packages_prefix) + 1:]
                    if rel == "tvbl_drive.pth":
                        has_obsolete_pth = True
                    elif member.isfile():
                        extracted = src.extractfile(member)
                        if extracted is not None:
                            existing_bundled[rel] = extracted.read()

        bundled_needs_write = bool(
            site_packages_prefix
            and (
                has_obsolete_pth
                or set(existing_bundled) != set(bundled)
                or any(existing_bundled.get(k) != v[0] for k, v in bundled.items())
            )
        )

        if not logger_needs_write and not bundled_needs_write:
            if logger_patched:
                print(f"Already patched {tar_path}")
            else:
                print(f"Warning: logger patch point not found in {tar_path}", file=sys.stderr)
            return logger_patched

        tmp_path = tar_path.with_suffix(".tar.gz.tmp")
        with tarfile.open(tmp_path, "w:gz") as dst:
            for member in members:
                if _is_bundled_tvbl_member(member.name, site_packages_prefix):
                    continue
                if member.isfile() and member.name.endswith("tvb/basic/logger/builder.py"):
                    extracted = src.extractfile(member)
                    assert extracted is not None
                    data = extracted.read().decode("utf-8")
                    if old in data:
                        data = data.replace(old, new)
                    payload = data.encode("utf-8")
                    member_copy = tarfile.TarInfo(name=member.name)
                    member_copy.size = len(payload)
                    member_copy.mode = member.mode
                    member_copy.mtime = member.mtime
                    dst.addfile(member_copy, io.BytesIO(payload))
                elif member.isfile():
                    extracted = src.extractfile(member)
                    assert extracted is not None
                    dst.addfile(member, extracted)
                else:
                    dst.addfile(member)

            if site_packages_prefix:
                for rel, (payload, mtime) in bundled.items():
                    info = tarfile.TarInfo(name=f"{site_packages_prefix}/{rel}")
                    info.size = len(payload)
                    info.mode = 0o644
                    info.mtime = int(mtime)
                    dst.addfile(info, io.BytesIO(payload))

    os.replace(tmp_path, tar_path)
    print(f"Patched {tar_path} (logger={logger_patched}, bundled_files={len(bundled)})")
    return logger_patched


def patch_tvb_packages(lite_dir: Path, code_dir: Path) -> bool:
    """Patch all tvb_library kernel package archives in a built JupyterLite site."""
    tarballs = sorted(lite_dir.rglob("tvb_library-*.tar.gz"))
    if not tarballs:
        print(f"Error: no tvb_library-*.tar.gz found in {lite_dir}", file=sys.stderr)
        return False
    return all(_patch_tvb_tarball(path, code_dir) for path in tarballs)


def main() -> int:
    lite_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "_build/html/lite")
    if not lite_dir.exists():
        print(f"Error: directory {lite_dir} does not exist", file=sys.stderr)
        return 1

    code_dir = Path(__file__).resolve().parent.parent / "content" / "_code"
    ok_rtld = patch_rtld_global(lite_dir)
    ok_tvb = patch_tvb_packages(lite_dir, code_dir)
    return 0 if (ok_rtld and ok_tvb) else 1


if __name__ == "__main__":
    raise SystemExit(main())
