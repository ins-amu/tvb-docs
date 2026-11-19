#!/bin/bash
set -euxo pipefail

SRC_ROOT="$SRC_DIR/tvb_library"
if [ ! -f "$SRC_ROOT/CMakeLists.txt" ]; then
  echo "Expected CMakeLists.txt at $SRC_ROOT/CMakeLists.txt" >&2
  exit 1
fi

# Clean any in-source CMake or host extension artifacts copied from a dirty
# local checkout inside rattler-build's temporary $SRC_DIR tree.
rm -rf \
  "$SRC_ROOT/CMakeCache.txt" \
  "$SRC_ROOT/CMakeFiles" \
  "$SRC_ROOT/build.ninja" \
  "$SRC_ROOT/CMakeInit.txt" \
  "$SRC_ROOT/.skbuild-info.json" \
  "$SRC_ROOT/build" \
  "$SRC_ROOT/generated" \
  "$SRC_ROOT"/tvb/simulator/backend/cpp_hybrid/*.so \
  "$SRC_ROOT"/tvb/simulator/backend/cpp_hybrid/*.pyd \
  "$SRC_ROOT"/tvb/simulator/backend/cpp_hybrid/*.dylib

BUILD_PYTHON="$BUILD_PREFIX/bin/python"
if [ ! -x "$BUILD_PYTHON" ]; then
  echo "Expected native build python at $BUILD_PYTHON" >&2
  exit 1
fi

if [ -n "${TVB_CPP_PREGENERATED_DIR:-}" ] && [ -f "$TVB_CPP_PREGENERATED_DIR/models_gen.cpp" ]; then
  GEN_DIR="$TVB_CPP_PREGENERATED_DIR"
  echo "Using pre-generated dfuns from $GEN_DIR"
else
  GEN_DIR="$SRC_DIR/generated"
  mkdir -p "$GEN_DIR"
  PYTHONPATH="$SRC_ROOT${PYTHONPATH:+:$PYTHONPATH}" \
    "$BUILD_PYTHON" "$SRC_ROOT/tvb/simulator/backend/cpp_hybrid/dfungen.py" \
    --emit "$GEN_DIR/models_gen.cpp" \
    --meta "$GEN_DIR/models_gen.json" \
    --entry-name cph_builtin_dfun \
    --strict \
    --only-supported
fi

NANOBIND_DIR="$("$BUILD_PYTHON" -c 'import nanobind; print(nanobind.cmake_dir())')"

PY_INC="$(find "$PREFIX/include" -maxdepth 1 -type d -name 'python3.*' | sort | head -n 1)"
if [ -z "$PY_INC" ]; then
  echo "Could not find target Python headers under $PREFIX/include" >&2
  exit 1
fi
PY_VER_SHORT="$(basename "$PY_INC")"
TARGET_SP="${SP_DIR:-$PREFIX/lib/$PY_VER_SHORT/site-packages}"
PY_MM="${PY_VER_SHORT#python}"
PY_NODOT="${PY_MM//./}"
SOABI="cpython-${PY_NODOT}-wasm32-emscripten"

BUILD_DIR="$SRC_DIR/build-wasm"
STAGE_DIR="$SRC_DIR/stage-install"
CMAKE_RULES_OVERRIDE="$SRC_DIR/emscripten_shared_module.cmake"
rm -rf "$BUILD_DIR" "$STAGE_DIR"

# Emscripten.cmake sets TARGET_SUPPORTS_SHARED_LIBS=FALSE, which causes CMake to
# downgrade add_library(... MODULE ...) to a static `ar` archive instead of a
# WASM SIDE_MODULE. Re-enable shared/module linking after Platform/Emscripten
# is loaded inside enable_language(CXX).
cat > "$CMAKE_RULES_OVERRIDE" <<'EOF'
set_property(GLOBAL PROPERTY TARGET_SUPPORTS_SHARED_LIBS TRUE)
set(CMAKE_SHARED_LIBRARY_SUFFIX ".so")
set(CMAKE_SHARED_MODULE_SUFFIX ".so")
EOF

emcmake cmake \
  -S "$SRC_ROOT" \
  -B "$BUILD_DIR" \
  -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_FIND_ROOT_PATH_MODE_PACKAGE=BOTH \
  -DCMAKE_USER_MAKE_RULES_OVERRIDE_CXX="$CMAKE_RULES_OVERRIDE" \
  -DTVB_CPP_BUILD_EXTENSION=ON \
  -DTVB_CPP_GENERATE_MODELS=ON \
  -DTVB_CPP_PREGENERATED_DIR="$GEN_DIR" \
  -Dnanobind_DIR="$NANOBIND_DIR" \
  -DPython_EXECUTABLE="$BUILD_PYTHON" \
  -DPython_INCLUDE_DIR="$PY_INC" \
  -DPython_VERSION="$PY_MM" \
  -DPython_SOABI="$SOABI"

command cmake --build "$BUILD_DIR" --parallel "${CPU_COUNT:-4}"
command cmake --install "$BUILD_DIR" --prefix "$STAGE_DIR"

SO_PATH="$(find "$STAGE_DIR" -type f -name '_cpp_hybrid*.so' | head -n 1)"
if [ -z "$SO_PATH" ]; then
  echo "Built _cpp_hybrid*.so not found under $STAGE_DIR" >&2
  exit 1
fi
SO_NAME="$(basename "$SO_PATH")"

DEST_PKG="$TARGET_SP/tvb/simulator/backend/cpp_hybrid"
mkdir -p "$DEST_PKG"
install -m 755 "$SO_PATH" "$DEST_PKG/$SO_NAME"

DIST_INFO_NAME="tvb_cpp_hybrid-${PKG_VERSION}.dist-info"
DIST_INFO="$TARGET_SP/$DIST_INFO_NAME"
mkdir -p "$DIST_INFO"
cat > "$DIST_INFO/METADATA" <<EOF
Metadata-Version: 2.1
Name: tvb-cpp-hybrid
Version: ${PKG_VERSION}
Summary: Prebuilt WebAssembly C++ hybrid simulator extension (_cpp_hybrid) for tvb-library
License: GPL-3.0-or-later
EOF
printf 'conda\n' > "$DIST_INFO/INSTALLER"

"$BUILD_PYTHON" - "$TARGET_SP" "$DIST_INFO_NAME" "tvb/simulator/backend/cpp_hybrid/$SO_NAME" <<'PY'
import base64
import hashlib
import os
import sys

sp_dir, dist_info_name, so_rel = sys.argv[1:]
record_path = os.path.join(sp_dir, dist_info_name, "RECORD")
entries = [
    so_rel,
    f"{dist_info_name}/METADATA",
    f"{dist_info_name}/INSTALLER",
]
rows = []
for rel in entries:
    full = os.path.join(sp_dir, rel)
    with open(full, "rb") as f:
        data = f.read()
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
    rows.append(f"{rel},sha256={digest},{len(data)}\n")
rows.append(f"{dist_info_name}/RECORD,,\n")
with open(record_path, "w", encoding="utf-8") as f:
    f.writelines(rows)
PY
