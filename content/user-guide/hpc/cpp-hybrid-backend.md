---
title: C++ Hybrid Backend
bibliography:
  - ../../references.bib
---

# C++ Hybrid Backend

The `cpp_hybrid` {term}`backend <Backend>` (`tvb.simulator.backend.cpp_hybrid`) compiles the TVB hybrid simulator into a single C++17 `nanobind` extension (`_cpp_hybrid`), enabling zero-JIT startup, multithreaded SIMD {term}`parameter sweeps <Parameter sweep>`, in-kernel monitoring, and streaming feature extraction.

This page documents the C++ backend architecture and the systems choices behind its speed. For scientific sweep workflows, see [Sweep Theory](../sweep/theory.md) and [Hybrid Sweep Workflows](../sweep/backends.ipynb); for API support matrices across backends, see [Backends and parameter sweeps](../hybrid/hybrid-backends-and-sweeps.md).

---

## 1. Zero-JIT Compilation & Model Coverage

Unlike Numba (`NbHybridBackend`), which compiles LLVM IR on first call and must recompile whenever global model parameters are swept in parallel, `_cpp_hybrid` ships precompiled inside `tvb-library` (and WebAssembly builds):

- **13 hand-written SIMD kernels (`_core.cpp`, `cph_dfuns.hpp`):** Hand-tuned C++17 derivative kernels for core models (`MontbrioPazoRoxin`, `Generic2dOscillator`, `Kuramoto`, `SupHopf`, `Linear`, `ReducedWongWang`, `WilsonCowan`, `JansenRit`, `Epileptor`, `Epileptor2D`, `ZerlautAdaptationFirstOrder`, `ZerlautAdaptationSecondOrder`, and `CerebellarMF`).
- **27 build-time generated kernels (`dfungen.py`):** At package build time, `dfungen` translates declarative `state_variable_dfuns` expressions into C++ functions compiled directly into `_cpp_hybrid` with the same optimization flags—covering all **30/30** `ModelsEnum` classes.
- **Runtime `g++` fallback (`ids >= 127`):** User-defined custom `Model` subclasses declaring `state_variable_dfuns` are compiled on first use via `$CXX` + `ctypes` without modifying the extension.
- **Compiler flags & `float32` parity:** Built with `-O3 -fopenmp-simd -ffp-contract=off` (and **without** `-ffast-math`), matching Numba's `float32` arithmetic without FMA contraction drift.

---

## 2. How Sweeps Scale: SIMD Lanes × GIL-Free Thread Pool

The execution engine (`simw<W>` in `_core.cpp`) vectorizes **across sweep members** rather than only across nodes:

```{mermaid}
flowchart LR
    Params["Sweep parameter rows<br/>(grid=True or lockstep zip)"] --> Batches["Pack W sweep members<br/>into innermost SIMD lanes (W ∈ {1,4,8,16})"]
    Batches --> Pool["GIL-free C++ thread pool<br/>(workers threads over lane-groups)"]
    Pool --> Step["Hybrid multi-dt C++ loop<br/>(dfuns + coupling + Philox RNG + stim)"]
    Step --> Mon["In-kernel engines<br/>(BalloonWindkessel / tavg / raw / OnlineFeatureAccum)"]
    Mon --> Res["SweepResult<br/>(squeezed, bw_global, bw_local, online_features)"]
```

- **Innermost SIMD lane layout (`width in {1, 4, 8, 16}`):** State arrays are laid out as `(n_svar, n_node, n_modes, W)`, so `W` independent parameter sets share instruction streams and contiguous vector loads (`notebook.default_width` selects `W = 4` on 128-bit ARM64 NEON / WebAssembly `-msimd128` and `W = 8` on x86_64 AVX2). Padding lanes at the end of an uneven batch are discarded before returning `SweepResult`.
- **GIL-free worker pool (`workers` / `n_workers`):** Lane-groups execute concurrently across C++ threads after releasing the Python GIL (`workers` defaults to half the host CPU count, or `1` in browser WebAssembly).
- **Zero recompilation across parameter types:** Both projection coupling parameters (`cfun` attributes) and per-subnetwork model parameters are stored as `(n_parm, W)` lane arrays, so sweeping model excitability, time constants, and coupling strengths runs inside the same precompiled binary with ~1–3 ms setup overhead.

---

## 3. In-Kernel Subsystems

To avoid Python callback overhead and intermediate memory copies during long or wide sweeps, four subsystems execute directly inside the C++ time loop:

### Nonlinear Balloon–Windkessel (`cph_balloon_windkessel.hpp`) & `kmon<W>` Monitors (`cph_monitors.hpp`)
- **`BalloonWindkessel` (`bw={"global": ..., "local": ...}`):** The primary hemodynamic BOLD engine in `cpp_hybrid`. Integrates the per-region biophysical balloon ODEs (two 5 ms RK4 steps per 10 ms complete neural drive window) in SIMD across `W ∈ {1, 4, 8, 16}` lanes, emitting midpoint-stamped fractional BOLD $\Delta S / S$ with no incomplete trailing periods.
- **Additional `kmon<W>` engines:** `TemporalAverage`, `Raw`, `SubSample`, `GlobalAverage`, `SpatialAverage`, legacy HRF `Bold` (`monitor="bold"`), and single-subnet `width=1` regional `EEG`/`MEG`/`iEEG` projections.

### Counter-Based Philox4x32-10 PRNG (`cph_rng.hpp`)
- Stochastic sweeps (`HeunStochastic`, `EulerStochastic` with `Additive` white or colored Ornstein–Uhlenbeck noise `ntau >= 0`) use stateless Philox4x32-10 counters indexed by `(step, subnet, node, lane)`.
- Passing `shared_noise=True` broadcasts one RNG key across all lanes (common random numbers), while `noise_seeds` assigns explicit per-member `uint64` seeds—both supporting exact `snapshot`/`resume`.

### Separable Analytic Stimuli (`cph_stim.hpp`)
- Evaluates separable `SpatioTemporalPattern` waveforms (`Linear`, `Sinusoid`, `Cosine`, `PulseTrain`, `Alpha`, `GeneralizedSigmoid`, `Gaussian`, `DoubleGaussian`, `Sigmoid`) on the master `dt0` clock inside the C++ loop without allocating dense 5D `(time, cvar, node, mode, W)` arrays.

### Two-Tier Data Feature Extraction (`cph_features.hpp`, `features.py`)
- **Tier-1 Online Streaming (`OnlineFeatureAccum<W>`, `monitor="features"`):** Accumulates 16 single-pass statistics (`mean`, `var`, `std`, `min`, `max`, `rms`, `abs_energy`, `average_power`, `auc`, `auc_trapz`, `zero_crossing`, `burstiness`, `moments`, `skewness`, `kurtosis`, `centroid`) directly inside the C++ step loop using $O(n_\text{voi} \cdot n_\text{node} \cdot W)$ memory—never allocating a time-series buffer.
- **Tier-2 Batch Post-Processing (`_cpp_hybrid.compute_features`):** Vectorized C++ kernels for order statistics (`median`, `iqr`, `mad`, `median_abs_dev`), binned `entropy`, and radix-2 + Bluestein Welch {term}`PSD <Power spectral density>` (`psd_raw`, `spectrum_stats`, `spectrum_auc`, `spectrum_moments`) executed over any time-first monitor output array.

---

## 4. Practical Tuning Levers

| Lever | Default | When to adjust |
|---|---|---|
| `width` | `4` (ARM64/WASM), `8` (x86_64) | Set `1` for very large networks ($N_\text{nodes} \cdot W > 100{,}000$) or `16` on wide-SIMD servers with many sweep rows. |
| `workers` / `n_workers` | `cpu_count // 2` | Match physical cores for compute-bound sweeps; reduce if running alongside other heavy processes. |
| `chunk_size` / `monitor_period` | `1` | Set to `istep` (e.g., `10` or `20`) when recording `TemporalAverage` to downsample before copying arrays to NumPy. |
| `monitor="features"` | `"tavg"` | Use for large Monte Carlo / SBI sweeps where only the 16 single-pass neural statistics are needed. |
| `bw={"global": ..., "local": ...}` | `None` | Use with `monitor="none"` or `"tavg"` for fractional-BOLD sweeps via `BalloonWindkessel`. |

---

## Next steps

- Scientific methodology and monitor–feature chaining: [Sweep Theory](../sweep/theory.md).
- Worked parameter-sweep notebooks: [Hybrid Sweep Workflows](../sweep/backends.ipynb) and [Monte Carlo Sampling](../sweep/mc-sampling.ipynb).
- Backend comparison across Python, Numba, C++, and CUDA: [Backends and parameter sweeps](../hybrid/hybrid-backends-and-sweeps.md).
