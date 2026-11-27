---
title: Backends and parameter sweeps
bibliography:
  - ../../references.bib
---

# Choosing a Backend & Running Parameter Sweeps

The TVB Hybrid Simulator provides multiple execution {term}`backends <Backend>` to balance flexibility, prototyping ease, and extreme performance scaling. This guide helps you select the right backend for your workload, understand what each backend supports or rejects, execute {term}`parameter sweeps <Parameter sweep>` using the unified API, configure multirate time-stepping, and review relative performance benchmarks.

---

## 1. Choosing an Execution Path

Use the decision diagram and capability matrix below to choose the optimal execution backend for your simulation or parameter sweep.

### Decision Diagram

```{mermaid}
flowchart TD
    Start["What is your task?"] --> Prototyping["Prototyping custom models / exact float64 reference"]
    Prototyping --> PythonRef["Pure Python reference<br/>Simulator(..., backend='python')"]

    Start --> SingleRun["Single run with host Python monitors / reference parity"]
    SingleRun --> NumbaCPU["Numba CPU single<br/>Simulator(..., backend='numba')"]

    Start --> SingleCpp["Fast single run (Raw / Bold / BalloonWindkessel / EEG-MEG)"]
    SingleCpp --> CppSingle["C++ SIMD single (width=1)<br/>CppHybridBackend"]

    Start --> CPU_Sweep["Numba CPU coupling sweep"]
    CPU_Sweep --> NumbaSweep["Numba CPU sweep<br/>cpu-seq / cpu-prange"]

    Start --> FastSweep["Fast sweeps over coupling, model params, noise, & BW BOLD"]
    FastSweep --> CppSimd["C++ SIMD sweep (width=4/8/16)<br/>CppHybridBackend / notebook.sweep"]

    Start --> GPUSweep["Large-scale GPU sweeps (uniform dt, no CerebellarMF)"]
    GPUSweep --> CUDA["CUDA GPU sweep<br/>NbHybridCUDASweepBackend (backend='cuda' / 'auto')"]
```

### Capability Matrix

| Capability / Feature | Pure Python (`python`) | Numba Single (`numba`) | Numba Sweep (`cpu-seq` / `cpu-prange`) | C++ Single (`width=1`) | C++ SIMD Sweep (`width=4/8/16`) | CUDA Sweep (`cuda`) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **JIT / Setup Cost** | None (interpreted) | Cold: ~5–6 s; Warm: ~20–40 ms | Cold: ~5–6 s; Warm: ~20–40 ms | Zero JIT (~1–3 ms setup) | Zero JIT (~1–3 ms setup) | Cold: ~1–3 s; Warm: ~50 ms |
| **Numeric Precision** | `float64` states & monitors | `float32` | `float32` | `float32` | `float32` | `float32` |
| **Supported Models** | All Python models | 29 built-in models | 29 built-in models | 13 core + 27 built-in + custom fallback | 13 core + 27 built-in + custom fallback | Symbolic, combined, & Zerlaut models |
| **State Clamps & Bounds** | Supported | Supported | Supported | Supported (`bounds` + explicit clamps) | Supported (`bounds` + explicit clamps) | Rejects explicit clamps |
| **Sweepable Parameters** | None (single runs) | N/A | Coupling (`cfun`) & model params | Coupling & model parameters | Coupling & model parameters (zero recompile) | Coupling & global model params |
| **Multirate (`multi-dt`)** | Uniform $\Delta t$ only | Supported | Supported | Supported | Supported | Uniform $\Delta t$ only |
| **Stochastic Noise** | Supported | Supported (`Additive`) | Supported (`Additive`) | Supported (`numpy` / `philox`, OU) | Supported (`philox`, `shared_noise`, `noise_seeds`, OU) | Supported (`Additive`) |
| **`Bold` / `BalloonWindkessel`** | Host `FirstOrderVolterra` | Host `FirstOrderVolterra` | Host `FirstOrderVolterra` | In-kernel HRF `Bold`, `BalloonWindkessel`, or host | `monitor="bold"` (HRF), `bw={...}` (`BalloonWindkessel`), `features` | Host or device Euler |

---

## 2. Backend Support & Rejections

### Numba (`NbHybridBackend`, `backend="numba"`)
- **Supports:** 29 built-in models (including `ZerlautAdaptationFirstOrder`, `ZerlautAdaptationSecondOrder`, and `CerebellarMF`), 8 coupling classes (`Linear`, `Scaling`, `Sigmoidal`, `SigmoidalJansenRit`, `Kuramoto`, `Difference`, `HyperbolicTangent`, `PreSigmoidal`) plus `None`, `Heun`/`Euler` deterministic and stochastic integrators with `Additive` noise, state bounds and explicit clamps, `snapshot`/`resume`, and host `FirstOrderVolterra` `Bold` monitors.
- **Rejects:** Nonzero `local_coupling`, `modification=True` on Epileptor models, `dynamic=True` on Hopfield, `shift_sigmoid=False` on Wilson-Cowan, and non-`"combined"` `dfun_mode` on `ReducedSet*` models.
- **Note on Sweeps:** `cpu-prange` (`n_workers > 1`) restricts parameter sweeps strictly to coupling (`cfun`) parameters; sweeping global model parameters automatically falls back to `cpu-seq` and recompiles per parameter value.

### C++ (`CppHybridBackend`)
- **Supports:** Prebuilt extension with zero JIT for 13 hand-written + 27 build-time generated models (covering all 30 `ModelsEnum` classes, plus runtime `g++`/`ctypes` fallback via `dfungen` for custom symbolic models), all 8 hybrid coupling classes, separable analytic {term}`stimuli <Stimulus>`, `width=1` single runs with in-kernel `kmon` engines (`Raw`, `SubSample`, `TemporalAverage`, `GlobalAverage`, `SpatialAverage`, HRF `Bold`, `BalloonWindkessel`, regional `EEG`/`MEG`/`iEEG`), and multithreaded SIMD sweeps (`width in {1, 4, 8, 16}`, auto-defaulting to `4` on ARM64/WASM and `8` on x86_64) over both coupling and model parameters with zero recompilation.
- **Sweep Monitors & Streaming Features:** `CppHybridBackend.sweep` and `notebook.sweep` support `monitor` in `("tavg", "raw", "subsample", "bold", "none", "features")` with `monitor_period`, `bold_period`, and `chunk_size`; Tier-1 online streaming feature accumulators (`monitor="features"`, $O(n_\text{voi} \cdot n_\text{node} \cdot W)$ memory); C++ Tier-2 batch features (`features.compute_features` / `SweepResult.features`); Philox4x32-10 stochastic sweeps (`shared_noise`, `noise_seeds`, colored OU noise `ntau >= 0`); and explicit fractional-BOLD `bw={"global": BalloonWindkessel(...), "local": {"subnet": BalloonWindkessel(...)}}` sweeps (with `monitor="none"` or `"tavg"`).
- **Current Limits:** `bw` sweeps cannot be combined with `bold_period` or `features` in the same call, global `BalloonWindkessel` requires matching observed VOIs (`n_modes == 1`, complete disjoint `node_indices`, master `dt0` dividing `10 ms`), `EEG`/`MEG`/`iEEG` are single-subnet `width=1` only, and `local_coupling` is rejected.

### CUDA (`NbHybridCUDASweepBackend`, `backend="cuda"` / `"auto"`)
- **Supports:** Large-scale sweeps over coupling and global model parameters (excluding `Zerlaut` model parameters) with automatic VRAM batching.
- **Rejects:** Unequal subnetwork time steps (uniform $\Delta t$ only), `CerebellarMF`, and explicit integrator state clamps. When `backend="auto"` encounters unsupported features, it falls back to CPU execution.

---

## 3. Named Parameter Sweep API

Parameter sweeps are unified across `NbHybridBackend.sweep`, `CppHybridBackend.sweep`, and `notebook.sweep`:

- **Parameter Naming:**
  - Shorthand aliases: `coupling_scale`, `scale`, `coupling_a`, `coupling_b`, `sigma`, `midpoint`.
  - Projection-qualified attributes: `{src}_to_{tgt}.{attr}` or `{subnet}.intra.{attr}`.
  - Subnetwork-qualified model parameters: `{subnet}.{param}` (e.g. `cortex.mu`).
  - Use `nb.available_sweep_params(ns)` to inspect valid coupling aliases, inter-projection targets, and subnetwork model parameters (see [Parameter Types](../sweep/parameter-types.ipynb) for full introspection including intra-projections).

:::{important} Elementwise lockstep vs. Cartesian `grid=True`
By default (`grid=False`), passing multiple 1D arrays pairs them **elementwise (lockstep zip)**, which is ideal for Monte Carlo or Sobol designs. In `notebook.sweep`, pass `grid=True` to expand a full Cartesian product (equivalent to `np.meshgrid(..., indexing="ij")`, with the last parameter varying fastest):

```python
from tvb.simulator.backend.cpp_hybrid import notebook as nb

# Cartesian grid via notebook.sweep(..., grid=True)
res = nb.sweep(
    ns, nstep=2000, grid=True,
    coupling_scale=[0.5, 1.0, 2.0],
    **{"cortex.mu": [0.0, 0.1, 0.2]},
)
```
:::

- **`SweepResult` Dataclass:** Fields include `tavg`, `ctavg`, `merged_tavg`, `raw`, `bold`, `bw_global`, `bw_local`, `online_features`, `times`, `sweep_values`, `param_keys`, `backend`, `elapsed`, plus helper methods `res.squeezed()`, `res.ts()`, `res.to_dataframe()`, and `res.features(...)`.

---

## 4. Multirate Time Stepping (`multi-dt`)

When brain regions evolve on disparate timescales, the multirate extension allows each subnetwork $b$ to specify an integration step $h_b$ that is an integer multiple of the master clock:

- **The Integer-Multiple Rule:** $h_b = \kappa_b \, h_0$, where $h_0 = \min_a h_a$ and $\kappa_b \ge 1$ is a positive integer. Non-integer ratios raise a `ValueError`.
- **Causality & Interpolation:** Intra-projections evaluate without interpolation on due ticks. Inter-projections use causal linear interpolation ($d \ge 1$) or zero-order hold ($d = 0$) across committed source history states.
- **Master Grid:** Monitors, stimuli, and output time axes all live on the master $h_0$ grid (while local `BalloonWindkessel` / `Recorder` monitors sample eligible source updates on the subnetwork's own clock).
- **Backend Support:** Supported in `NbHybridBackend` and `CppHybridBackend` single runs and sweeps (not pure-Python `Simulator._run_python` or CUDA sweeps).

---

## 5. Performance Summary

Measured benchmarks on Apple A18 Pro demonstrate dramatic speedups:
- **Setup Overhead:** Zero-JIT C++ setup takes ~1–3 ms compared to Numba cold compilation (~5–6 s).
- **Sweep Scaling:** `cpp-simd` ($W=8$) runs 3–4× faster than `cpu-prange` on coupling sweeps and >14× faster warm (>170× faster cold) on global model-parameter sweeps.

---

## 6. Next Steps

- Explore the dedicated [Parameter Sweeps](../sweep/theory.md) section covering [Parameter Types](../sweep/parameter-types.ipynb), [Bifurcation Sweeps](../sweep/bifurcation.ipynb), [Monte Carlo Sampling](../sweep/mc-sampling.ipynb), and [Fast C++ Hybrid Sweeps](../sweep/backends.ipynb).
- Review the [Conceptual model](hybrid-concepts.md) for architectural foundations and [API contracts and common pitfalls](hybrid-contracts.md) for debugging tips.
- Explore hands-on tutorials in [Hands-on tutorials](hybrid-tutorials.md) and standalone C++ demo notebooks ([C++ SIMD sweep](../../demos/cpp_hybrid_sweep.ipynb), [Regional Balloon–Windkessel](../../demos/cpp_hybrid_balloon_windkessel.ipynb), [Multirate BW sweep](../../demos/cpp_hybrid_multirate_bw_sweep.ipynb), [Multirate stepping](../../demos/simulate_hybrid_multi_dt.ipynb)).
