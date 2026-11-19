"""Run the tvb_library test suite inside the pyjs/emscripten runtime.

This file is mounted at /work by ``wasm-tests/run.sh`` and executed by
pyjs-code-runner in headless chromium.  ``tvb`` and ``tvb_data`` are already
installed in the packed wasm environment, so we only need to locate the
upstream tests that ship inside the wheel.
"""

import glob
import os
import sys

import pytest

import tvb


# Tests that cannot work in the wasm build for environmental reasons.  These
# are skipped (rather than deleted) so the report still shows what was not
# exercised.
WASM_SKIPS = [
    # tvb-gdist is a C++ extension and has no emscripten build.
    (
        "patterns_test.py::TestPatterns::test_stimulisurface",
        "requires tvb-gdist (not available for emscripten-wasm32)",
    ),
    (
        "coupling_test.py::TestCouplingShape::test_shape",
        "requires tvb-gdist (not available for emscripten-wasm32)",
    ),
    (
        "monitors_test.py::TestProjectionMonitorsWithSubcorticalRegions::"
        "test_surface_sim_with_projections",
        "requires tvb-gdist (not available for emscripten-wasm32)",
    ),
    (
        "monitors_test.py::TestProjectionMonitorsWithNoSubcortical::"
        "test_surface_sim_with_projections",
        "requires tvb-gdist (not available for emscripten-wasm32)",
    ),
    (
        "simulator_test.py::TestSimulator::test_simulator_surface[True-False]",
        "requires tvb-gdist (not available for emscripten-wasm32)",
    ),
    (
        "simulator_test.py::TestSimulator::test_simulator_surface[False-False]",
        "requires tvb-gdist (not available for emscripten-wasm32)",
    ),
    # Numba's analysis pass for this generated kernel needs > 2 GiB.  The
    # pyjs runtime's WebAssembly memory is capped at 2 GiB (maximum:32768
    # pages), so compilation aborts with MemoryError.  The other Zerlaut
    # kernels compile and run fine.
    (
        "test_nb_hybrid.py::TestNbHybridZerlautSecondOrder",
        "numba JIT for this kernel exceeds the 2 GiB wasm memory limit",
    ),
    # Emscripten has no process support, which these tests explicitly
    # exercise through loky/joblib/multiprocessing.
    (
        "test_nb_hybrid_regression_prange_native.py::"
        "test_sjr_native_abort_prange_sweep_bounds_and_thread_matrix",
        "emscripten does not support processes (multiprocessing/joblib)",
    ),
    (
        "test_nb_hybrid_regression_prange_native.py::"
        "test_requested_workers_and_threads_reach_real_parallel_backend",
        "emscripten does not support processes (multiprocessing/joblib)",
    ),
    (
        "test_nb_hybrid_regression_prange_performance.py::"
        "test_warmed_cpu_prange_median_throughput_and_dispatch",
        "emscripten does not support processes (_multiprocessing missing)",
    ),
    # This benchmark allocates ~290 MiB on top of the live simulation and
    # hits the 2 GiB wasm memory ceiling.  Benchmarks are not meaningful in
    # the browser anyway.
    (
        "test_unified_sweep.py::TestBenchmark::test_throughput_kiter",
        "benchmark exceeds the 2 GiB wasm memory limit",
    ),
    # Emscripten cannot spawn a runtime g++ subprocess (dfungen.generate_lib);
    # stock generic models run from the build-time compiled table instead.
    (
        "test_cpp_hybrid_buildgen.py::test_user_model_ids_are_disjoint_from_builtin_range",
        "requires runtime g++ compilation via dfungen.generate_lib",
    ),
    (
        "test_cpp_hybrid_buildgen.py::test_runtime_range_starts_at_100_without_builtin_kernels",
        "requires runtime g++ compilation via dfungen.generate_lib",
    ),
    (
        "test_cpp_hybrid_buildgen.py::test_runtime_fallback_model_matches_numba",
        "requires runtime g++ compilation via dfungen.generate_lib",
    ),
    (
        "test_cpp_hybrid_buildgen.py::test_runtime_library_has_no_builtin_kernels",
        "requires runtime g++ compilation via dfungen.generate_lib",
    ),
    (
        "test_cpp_hybrid_buildgen.py::test_generate_lib_exclude_filters_discovered_models",
        "requires runtime g++ compilation via dfungen.generate_lib",
    ),
    (
        "test_cpp_hybrid_buildgen.py::test_unsupported_stock_model_still_runs_via_runtime_fallback",
        "requires runtime g++ compilation via dfungen.generate_lib",
    ),
]


class WasmSkipPlugin:
    def pytest_collection_modifyitems(self, config, items):
        for item in items:
            for pattern, reason in WASM_SKIPS:
                if pattern in item.nodeid:
                    item.add_marker(pytest.mark.skip(reason=reason))
                    break


def main():
    tests = os.path.join(os.path.dirname(os.path.abspath(tvb.__file__)), "tests", "library")
    if not os.path.isdir(tests):
        raise SystemExit(f"tvb_library tests not found at {tests}")

    paths = [tests]
    extra = []

    # run.sh runs the suite in chunks (a fresh browser per chunk keeps the
    # wasm memory ceiling out of the way).  Non-option lines are paths or
    # globs relative to the tests directory; option lines are pytest arguments.
    chunk_file = "/work/chunk.txt"
    if os.path.exists(chunk_file):
        with open(chunk_file) as handle:
            lines = [line.strip() for line in handle if line.strip()]
        if lines:
            paths = []
            ignored = set()
            for line in lines:
                if line.startswith("-"):
                    if line.startswith(("--ignore=", "--ignore-glob=")):
                        flag, val = line.split("=", 1)
                        if not os.path.isabs(val):
                            val = os.path.join(tests, val)
                        if flag == "--ignore":
                            ignored.add(os.path.normpath(val))
                        else:
                            ignored.update(os.path.normpath(p) for p in glob.glob(val))
                        extra.append(f"{flag}={val}")
                    else:
                        extra.append(line)
                else:
                    target = line if os.path.isabs(line) else os.path.join(tests, line)
                    matched = sorted(glob.glob(target))
                    paths.extend(matched if matched else [target])
            if ignored:
                paths = [p for p in paths if os.path.normpath(p) not in ignored]
            if not paths:
                paths = [tests]

    args = [
        "-q",
        "-p",
        "no:cacheprovider",
        "--basetemp=/tmp/tvbl-pytest",
        "--tb=short",
        "-rf",
        *extra,
        *paths,
    ]

    print("pytest", " ".join(args), flush=True)
    code = pytest.main(args, plugins=[WasmSkipPlugin()])
    print(f"pytest exit code: {code}", flush=True)
    if code != 0:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
