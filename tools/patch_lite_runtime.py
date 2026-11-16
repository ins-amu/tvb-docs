#!/usr/bin/env python3
"""Patch xpython.js / pyjs_runtime_browser.js in a built JupyterLite site for Numba RTLD_GLOBAL.

Numba array kernels require `_nrt_python...so` (which defines `NRT_adapt_ndarray_from_python`)
to be dlopen'd RTLD_GLOBAL. The emscripten-forge pyjs/xpython runtime's `libraryType()` marks
every `*cpython-3*-wasm32-emscripten.so` as "local" (RTLD_LOCAL), causing JIT-compiled side
modules to fail with `Dynamic linking error: cannot resolve symbol NRT_adapt_ndarray_from_python`.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    lite_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "_build/html/lite")
    if not lite_dir.exists():
        print(f"Error: directory {lite_dir} does not exist", file=sys.stderr)
        return 1

    targets = [
        *lite_dir.rglob("xpython.js"),
        *lite_dir.rglob("pyjs_runtime_browser.js"),
    ]
    if not targets:
        print(f"Error: neither xpython.js nor pyjs_runtime_browser.js found in {lite_dir}", file=sys.stderr)
        return 1

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

    return 0 if patched_any else 1


if __name__ == "__main__":
    raise SystemExit(main())
