---
title: Backends and parameter sweeps
bibliography:
  - ../../references.bib
---

# Choosing a Backend & Running Parameter Sweeps

The TVB Hybrid Simulator provides multiple execution backends to balance flexibility, prototyping ease, and extreme performance scaling. This guide helps you select the right backend for your workload, understand what each backend supports or rejects, execute parameter sweeps using the unified API, configure multirate time-stepping, and review relative performance benchmarks.

---

## 1. Choosing an Execution Path

Use the decision diagram and capability matrix below to choose the optimal execution backend for your simulation or parameter sweep.

### Decision Diagram

```{mermaid}
flowchart TD
    Start["What is your task?"] --> Prototyping["Prototyping custom models / exact float64 reference"]
    Prototyping --> PythonRef["Pure Python reference<br/>Simulator(..., backend='python')"]

    Start --> SingleRun["Single run with Bold / clamps / stochastic noise"]
    SingleRun --> NumbaCPU["Numba CPU single<br/>Simulator(..., backend='numba')"]

    Start --> SingleCpp["Fast single run (Raw / Bold via kmon)"]
    SingleCpp --> CppSingle["C++ SIMD single (width=1)<br/>CppHybridBackend"]

    Start --> CPU_Sweep["CPU parameter sweep (coupling or model params)"]
    CPU_Sweep --> NumbaSweep["Numba CPU sweep<br/>cpu-seq / cpu-prange"]

    Start --> FastSweep["Fast sweeps over coupling & model parameters"]
    FastSweep --> CppSimd["C++ SIMD sweep (width=8)<br/>CppHybridBackend / notebook.sweep"]

    Start --> GPUSweep["Large-scale GPU sweeps (uniform dt, no CerebellarMF)"]
    GPUSweep --> CUDA["CUDA GPU sweep<br/>NbHybridCUDASweepBackend (backend='cuda' / 'auto')"]
```

### Capability Matrix

| Capability / Feature | Pure Python (`python`) | Numba Single (`numba`) | Numba Sweep (`cpu-seq` / `cpu-prange`) | C++ Single (`width=1`) | C++ SIMD Sweep (`width=8`) | CUDA Sweep (`cuda`) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **JIT / Setup Cost** | None (interpreted) | Cold: ~5–6 s; Warm: ~20–40 ms | Cold: ~5–6 s; Warm: ~20–40 ms | Zero JIT (0.7–3 ms setup) | Zero JIT (0.7–3 ms setup) | Cold: ~1–3 s; Warm: ~50 ms |
| **Numeric Precision** | `float64` states & monitors | `float32` | `float32` | `float32` | `float32` | `float32` |
| **Supported Models** | All Python models | 29 built-in models | 29 built-in models | 13 core + 25 built-in + custom fallback | 13 core + 25 built-in + custom fallback | Symbolic, combined, & Zerlaut models |
| **State Clamps & Bounds** | Supported | Supported | Supported | `MontbrioPazoRoxin` only | `MontbrioPazoRoxin` only | Rejects explicit clamps |
| **Sweepable Parameters** | None (single runs) | N/A | Coupling (`cfun`) & model params | Coupling & model parameters | Coupling & model parameters | Coupling & global model params |
| **Multirate (`multi-dt`)** | Uniform $\Delta t$ only | Supported | Supported | Supported | Supported | Uniform $\Delta t$ only |
| **Stochastic Noise** | Supported | Supported (`Additive`) | Supported (`Additive`) | Supported (`Additive`) | Not in `sweep()` yet | Supported (`Additive`) |
| **`Bold` Monitor Support** | Host `FirstOrderVolterra` | Host `FirstOrderVolterra` | Host `FirstOrderVolterra` | In-kernel `kmon` or host | `monitor="tavg"` only | Host or device Euler |

---

## 2. Backend Support & Rejections

### Numba (`NbHybridBackend`, `backend="numba"`)
- **Supports:** 29 built-in models (including `ZerlautAdaptationFirstOrder`, `ZerlautAdaptationSecondOrder`, and `CerebellarMF`), 8 coupling classes (`Linear`, `Scaling`, `Sigmoidal`, `SigmoidalJansenRit`, `Kuramoto`, `Difference`, `HyperbolicTangent`, `PreSigmoidal`) plus `None`, `Heun`/`Euler` deterministic and stochastic integrators with `Additive` noise, state bounds and explicit clamps, `snapshot`/`resume`, and host `FirstOrderVolterra` `Bold` monitors.
- **Rejects:** Nonzero `local_coupling`, `modification=True` on Epileptor models, `dynamic=True` on Hopfield, `shift_sigmoid=False` on Wilson-Cowan, and non-`"combined"` `dfun_mode` on `ReducedSet*` models.
- **Note on Sweeps:** `cpu-prange` (`n_workers > 1`) restricts parameter sweeps strictly to coupling (`cfun`) parameters; sweeping global model parameters automatically falls back to `cpu-seq` and recompiles per parameter value.

### C++ (`CppHybridBackend`)
- **Supports:** Prebuilt extension with zero JIT for 13 core + 25 built-in models (plus runtime fallback via `dfungen` for custom symbolic models), `width=1` single runs with in-kernel `kmon` engines (`Raw`, `SubSample`, `Bold`), and `width=8` thread-pool SIMD sweeps (`cpp-simd`) over both coupling and model parameters with zero recompilation.
- **Current Limits:** `CppHybridBackend.sweep()` supports `monitor="tavg"` only (no `bold_period` or per-step stochastic noise inside `sweep()` yet), single `target_cvar` per projection unless split, state clamping restricted to `MontbrioPazoRoxin`, and `resume` does not yet restore history rings.

### CUDA (`NbHybridCUDASweepBackend`, `backend="cuda"` / `"auto"`)
- **Supports:** Large-scale sweeps over coupling and global model parameters (excluding `Zerlaut` model parameters) with automatic VRAM batching.
- **Rejects:** Unequal subnetwork time steps (uniform $\Delta t$ only), `CerebellarMF`, and explicit integrator state clamps. When `backend="auto"` encounters unsupported features, it falls back to CPU execution.

---

## 3. Named Parameter Sweep API

Parameter sweeps are unified across `NbHybridBackend.sweep`, `CppHybridBackend.sweep`, and `notebook.sweep`:

- **Parameter Naming:**
  - Shorthand aliases: `coupling_scale`, `scale`, `coupling_a`, `coupling_b`, `sigma`, `midpoint`.
  - Projection-qualified attributes: `{proj}.{attr}` or `{subnet}.intra.{attr}` (discoverable via `nb.available_sweep_params(ns)`).
  - Subnetwork-qualified model parameters: `{subnet}.{param}` (e.g. `cortex.mu`).

:::{important} Elementwise lockstep contract
Passing multiple 1D arrays to a sweep pairs them **elementwise (lockstep zip)**, NOT as a full Cartesian product. To create a 2D grid, use the standard NumPy `meshgrid` idiom:

```python
scales, mus = np.meshgrid(
    [0.5, 1.0, 2.0], [0.0, 0.1, 0.2], indexing="ij"
)
sweep_params = {
    "coupling_scale": scales.ravel(),
    "cortex.mu": mus.ravel(),
}
```
:::

- **`SweepResult` Dataclass:** Fields include `tavg`, `ctavg`, `merged_tavg`, `times`, `sweep_values`, `backend`, `elapsed`, plus helper methods `res.squeezed()`, `res.to_dataframe()`, and `features.extract_features()` (available in `cpp_hybrid`).

---

## 4. Multirate Time Stepping (`multi-dt`)

When brain regions evolve on disparate timescales, the multirate extension allows each subnetwork $b$ to specify an integration step $h_b$ that is an integer multiple of the master clock:

- **The Integer-Multiple Rule:** $h_b = \kappa_b \, h_0$, where $h_0 = \min_a h_a$ and $\kappa_b \ge 1$ is a positive integer. Non-integer ratios raise a `ValueError`.
- **Causality & Interpolation:** Intra-projections evaluate without interpolation on due ticks. Inter-projections use causal linear interpolation ($d \ge 1$) or zero-order hold ($d = 0$) across committed source history states.
- **Master Grid:** Monitors, stimuli, and output time axes all live on the master $h_0$ grid.
- **Backend Support:** Supported in `NbHybridBackend` and `CppHybridBackend` single runs and sweeps (not pure-Python `Simulator._run_python` or CUDA sweeps).

---

## 5. Performance Summary

Measured benchmarks on Apple A18 Pro demonstrate dramatic speedups:
- **Setup Overhead:** Zero-JIT C++ setup takes ~1–3 ms compared to Numba cold compilation (~5–6 s).
- **Sweep Scaling:** `cpp-simd` ($W=8$) runs 3–4× faster than `cpu-prange` on coupling sweeps and >14× faster warm (>170× faster cold) on global model-parameter sweeps.

---

## 6. Next Steps

- Review the [Conceptual model](hybrid-concepts.md) for architectural foundations.
- Consult [API contracts and common pitfalls](hybrid-contracts.md) for debugging tips.
- Explore hands-on tutorials in [Hands-on tutorials](hybrid-tutorials.md) and standalone demo notebooks ([C++ SIMD sweep](../../demos/cpp_hybrid_sweep.ipynb), [Multirate stepping](../../demos/simulate_hybrid_multi_dt.ipynb)).
