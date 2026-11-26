---
title: API contracts and common pitfalls
bibliography:
  - ../../references.bib
---

# API Contracts & Common Pitfalls

The TVB Hybrid Simulator decouples subnetworks and projections so you can compose heterogeneous local models, integration schemes, and pathway-specific couplings. Because several conventions differ subtly from classic single-model TVB, this page surfaces the six essential contracts up front to prevent silent bugs.

---

## Quick-Reference Checklist

| # | Contract / Pitfall | Symptom / Risk | Correct Approach |
|---|---|---|---|
| 1 | **CSR matrix orientation** | Transpose errors (`68 × 8` vs. `8 × 68`) or shape mismatches between unequally sized subnetworks. | Always use `(n_target, n_source)`: `conn.weights[np.ix_(target_indices, source_indices)]` or `extract_connectivity_subset(...)`. |
| 2 | **`source_cvar` vs. `target_cvar`** | Confusing state-variable indices with `dfun` input slots causes silent no-ops (e.g., targeting slot `1` on `JansenRit`). | `source_cvar` indexes `model.state_variables`; `target_cvar` indexes `dfun` slots `0 .. len(model.cvar)-1`. Use integer slots for models like `CerebellarMF`. |
| 3 | **Default `InterProjection.mode_map`** | Combined-mode targets ($M_b = 3$) receive $3\times$ effective gain because default `mode_map` is all-ones. | Compensate via `scale` or supply an explicit `mode_map` (e.g., `np.full((1, 3), 1.0 / 3.0)`). |
| 4 | **Shared `Integrator` instances** | `Subnetwork.configure()` mutates boundaries, clamps, and noise buffer shapes in place. | Instantiate a separate `Integrator` object for each `Subnetwork`. |
| 5 | **Observation layouts** | Unexpected block-concatenated vs. connectome-ordered shapes, or losing modes under global `observe(flat=True)`. | Set `node_indices` + equal VOI counts + equal `dt` for merged output, or attach per-subnetwork `Recorder`s *after* `sim.configure()`. |
| 6 | **Stiff initial conditions** | Default uniform sampling from `JansenRit.state_variable_range` ($[-500, 500]$) overflows `exp()` on step 1. | Pass bounded explicit `initial_conditions` arrays of shape `(n_state_vars, nnodes, n_modes)` to `sim.run(...)`. |

---

## 1. CSR `weights` and `lengths` Are Strictly `(n_target, n_source)`

Every `IntraProjection` and `InterProjection` expects compressed sparse row (CSR) matrices with shape **`(n_target, n_source)`**—rows correspond to target nodes and columns correspond to source nodes.

When projecting from a 68-node cortex to an 8-node thalamus, the inter-projection slice must be `8 × 68`, **not** `68 × 8`.

:::{tip} Use built-in subset extraction or `np.ix_`
```python
import numpy as np
import scipy.sparse as sp
from tvb.simulator.hybrid.projection_utils import extract_connectivity_subset

# Extracts weights and lengths of shape (n_target, n_source)
weights, lengths = extract_connectivity_subset(
    conn, source_indices=cortex_indices, target_indices=thalamus_indices
)

# Equivalent manual CSR slicing:
W_sub = sp.csr_matrix(conn.weights[np.ix_(thalamus_indices, cortex_indices)].astype(np.float32))
L_sub = sp.csr_matrix(conn.tract_lengths[np.ix_(thalamus_indices, cortex_indices)].astype(np.float32))
```
:::

:::{note} Delays require `cv` and `dt`
When passing `lengths`, you must also supply conduction velocity `cv` (mm/ms) and the source time step `dt` (ms). Omitting `lengths` produces zero transmission delay.
:::

---

## 2. `source_cvar` vs. `target_cvar` (and String Resolution)

Projection variable indices have asymmetric semantics:

- **`source_cvar`**: Indexes coordinates in the source model's state history (`model.state_variables`).
- **`target_cvar`**: Indexes **incoming coupling slots passed to `dfun`** (`0 .. len(model.cvar) - 1`), **not** state-variable indices.
- **String names**: Both `source_cvar` and `target_cvar` resolve strings against `[model.state_variables[i] for i in model.cvar]`, **not** `model.coupling_terms`.

### Example 1: `JansenRit` (`cvar = [1, 2]` $\to$ `['y1', 'y2']`)

In `JansenRit`, `'y1'` is state index `1` as a source, but input **slot `0`** as a target. Because `JansenRit.dfun` only reads slot `0` (and ignores slot `1`), passing `target_cvar=1` thinking of `y1` is a silent no-op:

```python
# Right: target slot 0 (or string "y1") feeds JansenRit's excitatory synaptic filter
proj = InterProjection(
    source=thalamus,
    target=cortex,      # JansenRit
    source_cvar="V",    # state index 0 of Generic2dOscillator
    target_cvar=0,      # input slot 0 of JansenRit.dfun (NOT 1!)
    weights=W_sparse,
    scale=1e-3,
)
```

### Example 2: `CerebellarMF` (`cvar = [0, 1]`, `coupling_terms = ['mossy', 'parallel']`)

Because string lookup inspects `model.state_variables` at `model.cvar` (`'GrC'`, `'GoC'`) rather than `coupling_terms` (`'mossy'`, `'parallel'`), pass **integer slot indices** `0` (mossy fibers) or `1` (parallel fibers):

```python
# Route external drive to mossy fibers (slot 0) or parallel fibers (slot 1)
proj_mossy = InterProjection(
    source=driver,
    target=cerebellum,
    source_cvar="x",
    target_cvar=0,      # 0 = mossy, 1 = parallel
    weights=W_sparse,
    scale=1.0,
)
```

---

## 3. Default `InterProjection.mode_map` Multiplies Gain on Combined-Mode Targets

`InterProjection.mode_map` defaults to an all-ones $(M_a, M_b)$ matrix (whereas `IntraProjection` uses the identity on modes).

:::{warning} Receiver-side mode summation on 3-mode models
On combined-mode receivers (`ReducedSetFitzHughNagumo` and `ReducedSetHindmarshRose`, where $M_b = 3$ by default), the all-ones `mode_map` replicates a 1-mode source signal into all $M_b = 3$ target modes. Because `dfun` sums incoming slot `0` across all target modes ($c = \sum_{m=1}^{M_b} u_{0m}$) before updating each mode, the effective scalar gain is multiplied by $M_b = 3$ unless compensated in `scale` or `mode_map`.
:::

```python
# Normalize gain explicitly across the 3 target modes
proj = InterProjection(
    source=cortex,      # JansenRit (M_a = 1)
    target=thalamus,    # ReducedSetFitzHughNagumo (M_b = 3)
    source_cvar="y1",
    target_cvar="xi",
    weights=W_sparse,
    scale=0.1,
    mode_map=np.full((1, 3), 1.0 / 3.0),
)
```

---

## 4. Never Share an `Integrator` Instance Across Subnetworks

`Subnetwork.configure()` mutates its attached `scheme` in place—writing `state_variable_boundaries`, clamps, and (for stochastic integrators) the noise buffer shape `(nvar, nnodes, nmodes)`.

:::{warning} Do not reuse one integrator object
Sharing a single `Integrator` across subnetworks with different models or node counts overwrites boundaries and noise-buffer state.
:::

```python
# WRONG: sharing one integrator across two subnetworks
shared = HeunStochastic(dt=0.1, noise=noise.Additive(nsig=sigma))
cortex = Subnetwork(name="cortex", model=JansenRit(), scheme=shared, nnodes=38)
thalamus = Subnetwork(name="thalamus", model=Generic2dOscillator(), scheme=shared, nnodes=38)

# RIGHT: instantiate a distinct integrator per subnetwork
cortex = Subnetwork(
    name="cortex",
    model=JansenRit(),
    scheme=HeunStochastic(dt=0.1, noise=noise.Additive(nsig=sigma)),
    nnodes=38,
).configure()
thalamus = Subnetwork(
    name="thalamus",
    model=Generic2dOscillator(),
    scheme=HeunStochastic(dt=0.1, noise=noise.Additive(nsig=sigma)),
    nnodes=38,
).configure()
```

---

## 5. Observation Layouts: Global Monitors vs. Per-Subnetwork `Recorder`

Global {term}`monitors <Monitor>` attached to `Simulator` receive `NetworkSet.observe(flat=True)`, which automatically selects one of two output layouts:

1. **Block-concatenated layout** `(T, sum(n_voi), sum(nnodes), M_0)`:
   Used whenever any subnetwork omits `node_indices`, subnetworks have different VOI counts, or subnetworks use different `dt`. Each subnetwork's VOIs are summed over modes into trailing index `0` and placed in diagonal `(voi, node)` blocks in `subnets` order (with zeros off-diagonal and in trailing indices $\ge 1$ if $M_0 > 1$).
2. **Connectome-ordered (merged) layout** `(T, n_voi, sum(nnodes), M_0)`:
   Activated automatically when **every** subnetwork supplies `node_indices`, all subnetworks expose the **same number of VOIs**, and all subnetworks share **equal `dt`**.

To inspect a subnetwork's full mode-resolved activity (retaining all $M_b$ modes before mode summation), attach a per-subnetwork `Recorder` **after** `sim.configure()`:

```python
from tvb.simulator.monitors import TemporalAverage

sim = Simulator(nets=nets, simulation_length=100.0)  # no global monitors required
sim.configure()

# Attach and preallocate per-subnetwork recorder AFTER sim.configure()
cortex.add_monitor(TemporalAverage(period=1.0))
cortex.monitors[-1].configure(sim.simulation_length)

sim.run(initial_conditions=[ic_cortex, ic_thalamus])
t_ctx, y_ctx = cortex.monitors[0].to_arrays()
```

:::{note} Numerical precision across paths
Python state integration and global `Simulator` monitors run in `float64`, whereas projection history buffers, per-subnetwork `Recorder` accumulators, and compiled Numba / C++ / CUDA kernels operate in `float32`.
:::

---

## 6. Supply Bounded `initial_conditions` for Stiff Sigmoids (`JansenRit`)

Calling `sim.run()` without explicit `initial_conditions` samples initial states uniformly from each model's `state_variable_range`. For `JansenRit`, `y1` and `y5` span $[-500, 500]$, so large negative draws of $y_1 - y_2$ can overflow $\exp[r(v_0 - (y_1 - y_2))]$ on the first step.

Pass a list of explicit arrays—one per subnetwork, with shape `(n_state_vars, nnodes, n_modes)`:

```python
ic_cortex = np.zeros((6, n_ctx, 1))     # JansenRit: 6 state vars, 1 mode
ic_thalamus = np.zeros((4, n_thal, 3))  # ReducedSetFitzHughNagumo: 4 state vars, 3 modes

((t, y),) = sim.run(initial_conditions=[ic_cortex, ic_thalamus])
```

---

## 7. Attach Stimuli to `Subnetwork`, Not `NetworkSet`

:::{important} `Subnetwork.add_stimulus(...)`
External {term}`stimuli <Stimulus>` belong to the target `Subnetwork` and inject into its designated coupling slot:

```python
subnet.add_stimulus(
    stimulus=stim_pattern,
    stimulus_cvar=np.r_[0],
    projection_scale=1.0,
)
```
:::

---

## Next Steps

- Review the [Conceptual model](hybrid-concepts.md) for architecture and ownership seams.
- Compare runtimes in [Backends and parameter sweeps](hybrid-backends-and-sweeps.md).
- Run complete examples in [Hands-on tutorials](hybrid-tutorials.md).
