#!/usr/bin/env bash
#
# Run the upstream tvb_library test suite in the emscripten-wasm32 runtime
# used by JupyterLite, under headless chromium via pyjs-code-runner.
#
# Usage:
#   ./wasm-tests/run.sh
#
# Useful overrides:
#   TVBL_WASM_ENV       existing emscripten env prefix (default: $MAMBA_ROOT_PREFIX/envs/tvbl-wasm)
#   TVB_LIBRARY_SRC     local tvb_library checkout (default: ../tvb/tvb_library)
#   TVB_LIBRARY_SPEC    pip requirement to use when TVB_LIBRARY_SRC is absent
#   TVB_CPP_WASM_SO     prebuilt _cpp_hybrid*.so to stage into site-packages
#   TVB_CPP_WASM_CONDA  prebuilt tvb-cpp-hybrid-*.conda to extract _cpp_hybrid*.so from
#   PYJS_RUNNER         pyjs_code_runner binary
#   HOST_PYTHON         host Python used only to build/copy pure-Python wheels
#   TVBL_SKIP_ENV=1     do not create/recreate the wasm env
#   TVBL_SKIP_INSTALL=1 do not reinstall tvb_library/tvb-data
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MAMBA_ROOT_PREFIX="${MAMBA_ROOT_PREFIX:-$HOME/.micromamba}"
export MAMBA_ROOT_PREFIX
ENV_PREFIX="${TVBL_WASM_ENV:-$MAMBA_ROOT_PREFIX/envs/tvbl-wasm}"
PYJS_RUNNER="${PYJS_RUNNER:-$HOME/.venvs/pyjs-runner/bin/pyjs_code_runner}"
HOST_PYTHON="${HOST_PYTHON:-python3}"
CACHE_DIR="${PYJS_CACHE_DIR:-$ROOT/wasm-tests/.cache}"
PATCHED_PYJS="${PYJS_PATCH_DIR:-$ROOT/wasm-tests/.pyjs-patched}"
TVB_LIBRARY_SPEC="${TVB_LIBRARY_SPEC:-tvb-library @ git+https://github.com/the-virtual-brain/tvb-root.git@3b4e3c6c69c0f107756fd4d5f397e05ef38feff4#subdirectory=tvb_library}"

if [ -z "${LD_LIBRARY_PATH:-}" ] && [ -d /tmp/marmaduke-tvb/micromamba/envs/rattler-build/lib ]; then
    export LD_LIBRARY_PATH="/tmp/marmaduke-tvb/micromamba/envs/rattler-build/lib"
fi
if [ -n "${PLAYWRIGHT_BROWSERS_PATH:-}" ]; then
    export PLAYWRIGHT_BROWSERS_PATH
elif [ -d /tmp/marmaduke-tvb/browsers ]; then
    export PLAYWRIGHT_BROWSERS_PATH="/tmp/marmaduke-tvb/browsers"
fi

if [ -d "${TVB_LIBRARY_SRC:-$ROOT/../tvb/tvb_library}" ]; then
    TVB_LIBRARY_SRC="${TVB_LIBRARY_SRC:-$ROOT/../tvb/tvb_library}"
else
    TVB_LIBRARY_SRC=""
fi

if [ ! -d "$ENV_PREFIX" ] && [ "${TVBL_SKIP_ENV:-0}" != 1 ]; then
    if ! command -v micromamba >/dev/null 2>&1; then
        echo "micromamba is required to create $ENV_PREFIX (see README.md)" >&2
        exit 1
    fi
    echo "creating emscripten env $ENV_PREFIX" >&2
    micromamba create -y -p "$ENV_PREFIX" --platform emscripten-wasm32 \
        -c https://repo.prefix.dev/emscripten-forge-4x \
        -c https://repo.prefix.dev/emscripten-forge-dev \
        -c https://repo.prefix.dev/conda-forge \
        python numpy scipy 'matplotlib<3.11' autograd tqdm scikit-learn ipywidgets \
        joblib setuptools pandas numba pytest pytest-benchmark pyjs \
        networkx numexpr mako deprecated six autopep8 docutils packaging \
        pip h5py
fi

if [ ! -x "$PYJS_RUNNER" ]; then
    echo "pyjs-code-runner not found at $PYJS_RUNNER" >&2
    echo "install it with: uv venv ~/.venvs/pyjs-runner && uv pip install --python ~/.venvs/pyjs-runner/bin/python pyjs-code-runner && ~/.venvs/pyjs-runner/bin/playwright install chromium" >&2
    exit 1
fi

SITE_PACKAGES="$(find "$ENV_PREFIX/lib" -maxdepth 2 -type d -name site-packages | head -1)"
if [ -z "$SITE_PACKAGES" ]; then
    echo "could not find site-packages under $ENV_PREFIX/lib" >&2
    exit 1
fi

if [ "${TVBL_SKIP_INSTALL:-0}" != 1 ]; then
    TMP="$(mktemp -d)"
    trap 'rm -rf "$TMP"' EXIT
    echo "installing tvb_library into $SITE_PACKAGES" >&2
    if command -v uv >/dev/null 2>&1; then
        PIP=(uv pip install --python "$HOST_PYTHON" --no-deps)
    else
        PIP=("$HOST_PYTHON" -m pip install --no-deps)
    fi
    if [ -n "$TVB_LIBRARY_SRC" ]; then
        CMAKE_ARGS="-DTVB_CPP_BUILD_EXTENSION=OFF" \
            "${PIP[@]}" -Ccmake.args=-DTVB_CPP_BUILD_EXTENSION=OFF \
            --target "$TMP/tvb" "$TVB_LIBRARY_SRC"
    else
        CMAKE_ARGS="-DTVB_CPP_BUILD_EXTENSION=OFF" \
            "${PIP[@]}" -Ccmake.args=-DTVB_CPP_BUILD_EXTENSION=OFF \
            --target "$TMP/tvb" "$TVB_LIBRARY_SPEC"
    fi
    rm -f "$TMP/tvb/tvb/simulator/backend/cpp_hybrid"/*.abi3.so
    "${PIP[@]}" --target "$TMP/tvb-data" tvb-data

    rm -rf "$SITE_PACKAGES/tvb" "$SITE_PACKAGES/tvb_data" \
        "$SITE_PACKAGES"/tvb_library-*.dist-info "$SITE_PACKAGES"/tvb_data-*.dist-info
    cp -R "$TMP/tvb/." "$SITE_PACKAGES/"
    cp -R "$TMP/tvb-data/." "$SITE_PACKAGES/"

    # Stage prebuilt emscripten _cpp_hybrid*.so if provided via TVB_CPP_WASM_SO,
    # TVB_CPP_WASM_CONDA, or the recipe output directory.
    CPH_SO_STAGE=""
    if [ -n "${TVB_CPP_WASM_SO:-}" ] && [ -f "$TVB_CPP_WASM_SO" ]; then
        CPH_SO_STAGE="$TVB_CPP_WASM_SO"
    else
        CPH_CONDA="${TVB_CPP_WASM_CONDA:-}"
        if [ -z "$CPH_CONDA" ]; then
            for cand in "$ROOT/wasm-tests/recipes/tvb-cpp-hybrid/output/emscripten-wasm32"/tvb-cpp-hybrid-*.conda; do
                if [ -f "$cand" ]; then
                    CPH_CONDA="$cand"
                fi
            done
        fi
        if [ -n "$CPH_CONDA" ] && [ -f "$CPH_CONDA" ]; then
            echo "extracting _cpp_hybrid from $CPH_CONDA" >&2
            rm -rf "$TMP/cph-pkg"
            micromamba package extract "$CPH_CONDA" "$TMP/cph-pkg"
            CPH_SO_STAGE="$(find "$TMP/cph-pkg" -type f -name '_cpp_hybrid*.so' | head -n 1)"
        fi
    fi
    if [ -n "$CPH_SO_STAGE" ] && [ -f "$CPH_SO_STAGE" ]; then
        SO_NAME="$(basename "$CPH_SO_STAGE")"
        rm -f "$SITE_PACKAGES/tvb/simulator/backend/cpp_hybrid"/*.abi3.so
        install -m 755 "$CPH_SO_STAGE" "$SITE_PACKAGES/tvb/simulator/backend/cpp_hybrid/$SO_NAME"
        for dist in "$SITE_PACKAGES"/tvb_library-*.dist-info; do
            if [ -f "$dist/RECORD" ]; then
                printf 'tvb/simulator/backend/cpp_hybrid/%s,,\n' "$SO_NAME" >> "$dist/RECORD"
            fi
        done
        echo "staged WASM extension: $SO_NAME" >&2
    fi

    # empack only sees pip packages when INSTALLER says "pip".
    for dist in "$SITE_PACKAGES"/tvb_library-*.dist-info "$SITE_PACKAGES"/tvb_data-*.dist-info; do
        printf 'pip\n' > "$dist/INSTALLER"
    done
fi

# pyjs dlopen()s cpython extension modules RTLD_LOCAL, but numba/llvmlite
# JIT-compile side modules that import numba's NRT_* symbols and need
# RTLD_GLOBAL.  Patch a private copy of the runtime instead of the env.
rm -rf "$PATCHED_PYJS"
mkdir -p "$PATCHED_PYJS"
cp "$ENV_PREFIX/lib_js/pyjs/pyjs_runtime_browser.js" \
   "$ENV_PREFIX/lib_js/pyjs/pyjs_runtime_browser.wasm" "$PATCHED_PYJS/"
"$HOST_PYTHON" - "$PATCHED_PYJS/pyjs_runtime_browser.js" <<'PY'
import sys
path = sys.argv[1]
source = open(path).read()
old = 'return"local"'
new = 'return"global"'
if old not in source:
    raise SystemExit("pyjs runtime patch point changed; inspect libraryType()")
open(path, "w").write(source.replace(old, new))
PY

# The env cache is keyed by package metadata, not by files we copied in, so
# drop the tvb package tarballs before every run.
mkdir -p "$CACHE_DIR"
rm -f "$CACHE_DIR"/tvb_library-*.tar.gz "$CACHE_DIR"/tvb_data-*.tar.gz

# The wasm runtime is capped at 2 GiB.  A single pytest process running the
# whole suite slowly accumulates memory (numba JIT code, simulation caches)
# and starts failing late with MemoryError.  Running each directory in its own
# browser process keeps peak memory low at the cost of a short bootstrap per
# chunk.
CHUNK_FILE="$ROOT/wasm-tests/chunk.txt"
STATUS=0

run_chunk() {
    local name="$1"
    shift
    printf '%s\n' "$@" > "$CHUNK_FILE"
    echo "== tvb_library tests: $name" >&2
    if ! "$PYJS_RUNNER" run script browser-main \
        --conda-env "$ENV_PREFIX" \
        --script /work/run_wasm_tests.py \
        --mount "$ROOT/wasm-tests:/work" \
        --pyjs-dir "$PATCHED_PYJS" \
        --file-filter "$ROOT/wasm-tests/empack_config.yaml" \
        --env-cache-dir "$CACHE_DIR" \
        --headless \
        -w /home/web_user; then
        STATUS=1
    fi
}

should_run_chunk() {
    local target="$1"
    if [ "$#" -eq 1 ]; then
        return 0
    fi
    shift
    for wanted in "$@"; do
        if [ "$wanted" = "$target" ]; then
            return 0
        fi
    done
    return 1
}

if should_run_chunk basic "$@"; then
    run_chunk basic basic
fi
if should_run_chunk datatypes "$@"; then
    run_chunk datatypes datatypes
fi
if should_run_chunk simulator "$@"; then
    run_chunk "simulator (top-level)" \
        simulator \
        --ignore=simulator/backend \
        --ignore=simulator/hybrid
fi
if should_run_chunk simulator/backend "$@"; then
    run_chunk "simulator/backend (nb)" \
        simulator/backend \
        --ignore-glob=simulator/backend/test_cpp_hybrid_*.py
    run_chunk "simulator/backend (cpp_hybrid battery)" \
        simulator/backend/test_cpp_hybrid_battery.py
    run_chunk "simulator/backend (cpp_hybrid models)" \
        simulator/backend/test_cpp_hybrid_models.py
    run_chunk "simulator/backend (cpp_hybrid)" \
        "simulator/backend/test_cpp_hybrid_*.py" \
        --ignore=simulator/backend/test_cpp_hybrid_battery.py \
        --ignore=simulator/backend/test_cpp_hybrid_models.py
fi
if should_run_chunk simulator/hybrid "$@"; then
    run_chunk "simulator/hybrid" simulator/hybrid
fi

exit "$STATUS"
