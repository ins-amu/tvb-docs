---
title: Hands-on tutorials
kernelspec:
  name: python3
  display_name: Python 3
  language: python
bibliography:
  - ../../references.bib
---

# Hands-On Hybrid Simulation Tutorials

:::{tip} Run interactively
Run these tutorials interactively in your browser with zero installation:
- **[Open in JupyterLite Lab](/lite/lab/index.html?path=user-guide/hybrid/hybrid-tutorials.ipynb)**
- **[Download Notebook](/notebooks/user-guide/hybrid/hybrid-tutorials.ipynb)**
:::

This page walks through five end-to-end hybrid simulation workflows: mixed-model coupling, localized stimulation and per-subnetwork recording, multi-slot cerebellar pathway routing, stochastic dynamics with BOLD observation, and accelerated parameter sweeps with multirate stepping.

For a self-contained spatial example without connectome data, work through
[A sparse 1D field with three long-range connections](hybrid-1d-field.ipynb).
It builds a 128-site ring, checks a below-onset operating point, and sweeps
excitability, local coupling, and non-local coupling across 128 combinations,
with activity maps, a stability boundary, and a brief performance summary.

## Setup and imports

```{code-cell} ipython3
%matplotlib inline
import warnings
warnings.filterwarnings("ignore")

from pathlib import Path
import numpy as np
import scipy.sparse as sp
import matplotlib.pyplot as plt

from tvb.datatypes.connectivity import Connectivity
from tvb.datatypes import patterns, equations
from tvb.simulator.models import (
    JansenRit,
    ReducedSetFitzHughNagumo,
    Generic2dOscillator,
    MontbrioPazoRoxin,
)
from tvb.simulator.models.cerebellar_mf import CerebellarMF
from tvb.simulator.models.linear import Linear as LinearModel
from tvb.simulator.integrators import (
    HeunDeterministic,
    EulerDeterministic,
    HeunStochastic,
    noise,
)
from tvb.simulator.monitors import Raw, TemporalAverage, Bold
from tvb.simulator.hybrid import (
    Subnetwork,
    IntraProjection,
    InterProjection,
    NetworkSet,
    Simulator,
)
from tvb.simulator.hybrid.coupling import Linear as HybridLinear
from tvb.simulator.backend.cpp_hybrid.backend import CppHybridBackend
from tvb.simulator.backend.cpp_hybrid import notebook as cpp_nb

# Load the vendored 76-region TVB connectome
_conn_path = Path("../../tutorials/data/connectivity_76.zip").resolve()
conn76 = Connectivity.from_file(str(_conn_path)) if _conn_path.exists() else Connectivity.from_file("connectivity_76.zip")
conn76.configure()
print(f"Loaded connectome: {conn76.number_of_regions} regions")
```

---

## Tutorial 1 — Mixed-model projection (`JansenRit` $\to$ `ReducedSetFitzHughNagumo`)

Couple a 10-node cortical subnetwork (`JansenRit`, 1 mode) to a 10-node thalamic subnetwork (`ReducedSetFitzHughNagumo`, 3 modes) by routing `y1` $\to$ `xi`, and compare against an uncoupled control run. Under default parameters, the uncoupled 3-mode `ReducedSetFitzHughNagumo` exhibits intrinsic limit-cycle oscillations; adding positive cortical drive shifts its operating point toward upper saturation and reduces oscillation amplitude.

```{code-cell} ipython3
dt = 0.1
n_nodes = 10
sim_len = 300.0

def run_mixed_model(coupled=True):
    cortex = Subnetwork(
        name="cortex",
        model=JansenRit(),
        scheme=HeunDeterministic(dt=dt),
        nnodes=n_nodes,
    ).configure()
    thalamus = Subnetwork(
        name="thalamus",
        model=ReducedSetFitzHughNagumo(),
        scheme=HeunDeterministic(dt=dt),
        nnodes=n_nodes,
    ).configure()

    projs = []
    if coupled:
        rng = np.random.RandomState(42)
        w = sp.csr_matrix(np.abs(rng.randn(n_nodes, n_nodes)) * 0.01)
        l = sp.csr_matrix((n_nodes, n_nodes))
        projs.append(
            InterProjection(
                source=cortex,
                target=thalamus,
                source_cvar="y1",
                target_cvar="xi",
                weights=w,
                lengths=l,
                cv=7.0,
                dt=dt,
                scale=0.1,
            )
        )

    nets = NetworkSet(subnets=[cortex, thalamus], projections=projs)
    sim = Simulator(
        nets=nets,
        simulation_length=sim_len,
        monitors=[TemporalAverage(period=1.0)],
    )
    sim.configure()
    ic = [np.zeros((6, n_nodes, 1)), np.zeros((4, n_nodes, 3))]
    ((t, y),) = sim.run(initial_conditions=ic)
    assert np.isfinite(y).all(), "Non-finite values in mixed-model output"
    # Block-concatenated: cortex VOIs 0:4, thalamus VOIs 4:6
    y_ctx = y[:, 1, :n_nodes, 0].mean(axis=1)   # mean y1
    y_thal = y[:, 4, n_nodes:, 0].mean(axis=1)  # mean xi
    return t, y_ctx, y_thal

t1, ctx_c, thal_c = run_mixed_model(coupled=True)
_, _, thal_u = run_mixed_model(coupled=False)

late = t1 >= 150.0
print(f"Uncoupled thalamus late-window peak-to-peak: {np.ptp(thal_u[late]):.3f}")
print(f"Coupled   thalamus late-window peak-to-peak: {np.ptp(thal_c[late]):.3f}")

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 4.2), sharex=True, layout="constrained")
ax1.plot(t1, ctx_c, color="#275b97", lw=1.3)
ax1.set(title="Tutorial 1: JansenRit cortex → ReducedSetFitzHughNagumo thalamus", ylabel="Mean $y_1$ (mV)")
ax2.plot(t1, thal_c, color="#9e4830", lw=1.3, label="Projection present")
ax2.plot(t1, thal_u, color="#182435", lw=1.0, ls="--", label="Projection removed")
ax2.set(xlabel="Time (ms)", ylabel="Mean $\\xi$ (a.u.)")
ax2.legend(frameon=False)
plt.show()
```

---

## Tutorial 2 — Targeted stimulus, per-subnetwork `Recorder`, and connectome-ordered `node_indices`

### Part 2a: Localized stimulus via `Subnetwork.add_stimulus`

Inject a constant bias into node 0 of a 5-node uncoupled `Generic2dOscillator` subnetwork and verify that unstimulated node 4 remains unaffected.

```{code-cell} ipython3
n5 = 5
mini_conn = Connectivity(
    centres=np.ones((n5, 3)),
    weights=np.zeros((n5, n5)),
    tract_lengths=np.zeros((n5, n5)),
    region_labels=np.array([f"R{i}" for i in range(n5)]),
    speed=np.array([1.0]),
)
mini_conn.configure()

temporal_const = equations.Linear()
temporal_const.parameters["a"] = 0.0
temporal_const.parameters["b"] = 1.0
stim_w = np.zeros(n5)
stim_w[0] = 1.0

stim_pat = patterns.StimuliRegion(temporal=temporal_const, connectivity=mini_conn, weight=stim_w)
sub_stim = Subnetwork(name="osc", model=Generic2dOscillator(), scheme=EulerDeterministic(dt=0.1), nnodes=n5)
sub_stim.add_stimulus(stimulus=stim_pat, stimulus_cvar=np.r_[0], projection_scale=1.0)

sim_stim = Simulator(nets=NetworkSet(subnets=[sub_stim], projections=[]), simulation_length=100.0, monitors=[Raw()])
sim_stim.configure()
((t_s, y_s),) = sim_stim.run(initial_conditions=[np.zeros((2, n5, 1))])
assert np.isfinite(y_s).all()
print(f"Final V — stimulated node 0: {y_s[-1, 0, 0, 0]:.3f}, unstimulated node 4: {y_s[-1, 0, 4, 0]:.3f}")
```

### Part 2b: Per-subnetwork `Recorder` and connectome-ordered `node_indices`

Attach local `Recorder`s **after** `sim.configure()` using bounded zero initial conditions for `JansenRit`, and demonstrate connectome-ordered merged output when all subnetworks supply `node_indices`, equal VOI counts, and equal `dt`.

```{code-cell} ipython3
# Per-subnetwork Recorder (no global monitors needed)
sub_jr = Subnetwork(name="jr", model=JansenRit(), scheme=HeunDeterministic(dt=0.1), nnodes=6)
sub_g2 = Subnetwork(name="g2", model=Generic2dOscillator(), scheme=EulerDeterministic(dt=0.1), nnodes=6)
sim_rec = Simulator(nets=NetworkSet(subnets=[sub_jr, sub_g2], projections=[]), simulation_length=100.0)
sim_rec.configure()

sub_jr.add_monitor(TemporalAverage(period=1.0))
sub_jr.monitors[-1].configure(sim_rec.simulation_length)
sub_g2.add_monitor(TemporalAverage(period=1.0))
sub_g2.monitors[-1].configure(sim_rec.simulation_length)

out_global = sim_rec.run(initial_conditions=[np.zeros((6, 6, 1)), np.zeros((2, 6, 1))])
assert out_global == []
t_jr_r, y_jr_r = sub_jr.monitors[0].to_arrays()
t_g2_r, y_g2_r = sub_g2.monitors[0].to_arrays()
assert np.isfinite(y_jr_r).all() and np.isfinite(y_g2_r).all()
print(f"Per-subnet recorders — JR: {y_jr_r.shape}, G2D: {y_g2_r.shape}")

# Connectome-ordered (merged) output on the 76-region connectome
idx_a = np.arange(0, 38)
idx_b = np.arange(38, 76)
m_a = JansenRit(variables_of_interest=("y0", "y1"))
m_b = Generic2dOscillator(variables_of_interest=("V", "W"))
sn_a = Subnetwork(name="a", model=m_a, scheme=HeunDeterministic(dt=0.1), nnodes=38, node_indices=idx_a)
sn_b = Subnetwork(name="b", model=m_b, scheme=HeunDeterministic(dt=0.1), nnodes=38, node_indices=idx_b)
sim_merged = Simulator(
    nets=NetworkSet(subnets=[sn_a, sn_b], projections=[]),
    simulation_length=20.0,
    monitors=[TemporalAverage(period=1.0)],
)
sim_merged.configure()
((t_m, y_m),) = sim_merged.run(initial_conditions=[np.zeros((6, 38, 1)), np.zeros((2, 38, 1))])
print(f"Connectome-ordered merged output shape: {y_m.shape}  (time, n_voi=2, total_nodes=76, modes=1)")
```

---

## Tutorial 3 — Multi-slot pathway routing (`CerebellarMF` slot `0` vs. slot `1`)

`CerebellarMF` exposes two distinct afferent input pathways: **mossy fibers** (integer slot `0`) and **parallel fibers** (integer slot `1`). Because string lookup resolves against `cvar` state-variable names rather than `coupling_terms`, we route a constant 20 Hz (`0.02` ms$^{-1}$) `Linear(gamma=0)` driver via integer `target_cvar=0` vs. `target_cvar=1` and verify selective activation across `GrC`, `GoC`, `MLI`, and `PC`.

```{code-cell} ipython3
def run_cerebellar_pathway(target_slot=None, drive=0.02):
    dt_cb = 0.02
    src_sn = Subnetwork(
        name="driver",
        model=LinearModel(gamma=np.array([0.0])),
        scheme=HeunDeterministic(dt=dt_cb),
        nnodes=4,
    )
    crbl_mod = CerebellarMF()
    crbl_mod.use_legacy_goc_e_e = np.array([False])
    crbl_mod.external_input_ex_ex = np.array([0.05])
    crbl_mod.variables_of_interest = ("GrC", "GoC", "MLI", "PC")
    crbl_sn = Subnetwork(
        name="cerebellum",
        model=crbl_mod,
        scheme=HeunDeterministic(dt=dt_cb),
        nnodes=4,
    )
    projs = []
    if target_slot is not None:
        projs.append(
            InterProjection(
                source=src_sn,
                target=crbl_sn,
                source_cvar="x",
                target_cvar=target_slot,
                weights=sp.eye(4, format="csr", dtype=np.float64),
                lengths=sp.csr_matrix((4, 4), dtype=np.float64),
                cv=3.0,
                dt=dt_cb,
                scale=1.0,
            )
        )
    sim = Simulator(
        nets=NetworkSet(subnets=[src_sn, crbl_sn], projections=projs),
        simulation_length=100.0,
        monitors=[TemporalAverage(period=1.0)],
    )
    sim.configure()
    ic_src = np.full((1, 4, 1), drive, dtype=np.float64)
    ic_cb = np.zeros((5, 4, 1), dtype=np.float64)
    ic_cb[:4, :, 0] = np.array([[0.045], [0.012], [0.083], [0.064]])
    ((t, y),) = sim.run(initial_conditions=[ic_src, ic_cb])
    assert np.isfinite(y).all()
    # Row 0 is driver x; rows 1:5 and nodes 4:8 belong to cerebellum
    return y[-1, 1:, 4:, 0].mean(axis=1) * 1000.0

pops = ["GrC", "GoC", "MLI", "PC"]
base_hz = run_cerebellar_pathway(None)
mossy_hz = run_cerebellar_pathway(0)
par_hz = run_cerebellar_pathway(1)

for p, b, m, pr in zip(pops, base_hz, mossy_hz, par_hz):
    print(f"{p:3s}: baseline={b:6.2f} Hz | mossy(0)={m:6.2f} Hz | parallel(1)={pr:6.2f} Hz")

x = np.arange(len(pops))
w = 0.25
fig, ax = plt.subplots(figsize=(6.5, 3.2), layout="constrained")
ax.bar(x - w, base_hz, width=w, color="#8a99ad", label="No afferent")
ax.bar(x, mossy_hz, width=w, color="#275b97", label="Mossy (slot 0)")
ax.bar(x + w, par_hz, width=w, color="#9e4830", label="Parallel (slot 1)")
ax.set_xticks(x, pops)
ax.set(title="Tutorial 3: CerebellarMF dual-pathway routing", ylabel="Final firing rate (Hz)")
ax.legend(frameon=False)
plt.show()
```

---

## Tutorial 4 — Stochastic dynamics with `TemporalAverage` and `Bold` monitors

Connect 10 `JansenRit` nodes and 10 `Generic2dOscillator` nodes bidirectionally using **two separate `HeunStochastic` integrator instances**, explicit zero initial conditions, and the corrected `target_cvar=0` on the return projection into `JansenRit` (since `JansenRit.dfun` only consumes slot `0`).

```{code-cell} ipython3
dt_st = 0.1
n_st = 10
sigma = np.array([(1e-4) ** 2 / 2.0])

scheme_ctx = HeunStochastic(dt=dt_st, noise=noise.Additive(nsig=sigma))
scheme_thal = HeunStochastic(dt=dt_st, noise=noise.Additive(nsig=sigma))

ctx_st = Subnetwork(
    name="cortex",
    model=JansenRit(variables_of_interest=("y0", "y1")),
    scheme=scheme_ctx,
    nnodes=n_st,
).configure()
thal_st = Subnetwork(
    name="thalamus",
    model=Generic2dOscillator(variables_of_interest=("V",)),
    scheme=scheme_thal,
    nnodes=n_st,
).configure()

rng = np.random.RandomState(42)
w_st = sp.csr_matrix(np.abs(rng.randn(n_st, n_st)) * 0.01)
l_st = sp.csr_matrix((n_st, n_st))

p_c2t = InterProjection(
    source=ctx_st, target=thal_st, source_cvar=np.array([1]), target_cvar=np.array([0]),
    weights=w_st, lengths=l_st, cv=1.0, dt=dt_st, scale=1e-3,
)
# Target slot 0 on JansenRit (slot 1 would be silently ignored by JansenRit.dfun)
p_t2c = InterProjection(
    source=thal_st, target=ctx_st, source_cvar=np.array([0]), target_cvar=np.array([0]),
    weights=w_st, lengths=l_st, cv=1.0, dt=dt_st, scale=1e-3,
)

sim_st = Simulator(
    nets=NetworkSet(subnets=[ctx_st, thal_st], projections=[p_c2t, p_t2c]),
    simulation_length=6000.0,
    monitors=[TemporalAverage(period=10.0), Bold(period=2000.0)],
)
sim_st.configure()

(t_tavg, y_tavg), (t_bold, y_bold) = sim_st.run(
    initial_conditions=[np.zeros((6, n_st, 1)), np.zeros((2, n_st, 1))]
)
assert np.isfinite(y_tavg).all() and np.isfinite(y_bold).all()
print(f"TemporalAverage: {y_tavg.shape} | BOLD: {y_bold.shape}")

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 4.2), sharex=True, layout="constrained")
ax1.plot(t_tavg, y_tavg[:, 1, :n_st, 0].mean(axis=1), color="#275b97", lw=1.0, label="Cortex $y_1$")
ax1.set(title="Tutorial 4: Stochastic bidirectional network + BOLD", ylabel="Neural TAVG")
ax1.legend(frameon=False)
ax2.plot(t_bold, y_bold[:, 1, :n_st, 0].mean(axis=1), "o-", color="#9e4830", label="Cortex BOLD")
ax2.set(xlabel="Time (ms)", ylabel="BOLD signal")
ax2.legend(frameon=False)
plt.show()
```

---

## Tutorial 5 — Parameter sweeps (`CppHybridBackend`) and multirate stepping (`multi-dt`)

### Part 5a: Zero-JIT C++ SIMD sweeps (`coupling_scale` and `cortex.mu`)

Partition the 76-region connectome into 68 cortical + 8 thalamic `JansenRit` nodes using the **corrected `(8, 68)` `(target, source)` slice**, and run both a 16-point coupling sweep and a 16-point model-parameter (`cortex.mu`) sweep with `cpp_nb.sweep`.

```{code-cell} ipython3
dt_sw = 0.1
n_ctx, n_thal = 68, 8

jr_ctx = JansenRit(); jr_ctx.configure()
ctx_sw = Subnetwork(name="cortex", model=jr_ctx, scheme=HeunDeterministic(dt=dt_sw), nnodes=n_ctx)
ctx_sw.projections = [
    IntraProjection(
        source_cvar=np.array([0], dtype=np.int_),
        target_cvar=np.array([0], dtype=np.int_),
        weights=sp.csr_matrix(conn76.weights[:n_ctx, :n_ctx].astype(np.float32)),
        lengths=sp.csr_matrix(conn76.tract_lengths[:n_ctx, :n_ctx].astype(np.float32)),
        cv=1.0, dt=dt_sw, scale=1.0, cfun=HybridLinear(a=np.array([0.03])),
    )
]
ctx_sw.configure()

jr_thal = JansenRit(); jr_thal.configure()
thal_sw = Subnetwork(name="thalamus", model=jr_thal, scheme=HeunDeterministic(dt=dt_sw), nnodes=n_thal).configure()

# Strictly (n_target, n_source) = (8, 68)
c2t_sw = InterProjection(
    source=ctx_sw, target=thal_sw,
    source_cvar=1, target_cvar=0,
    weights=sp.csr_matrix(conn76.weights[n_ctx:76, :n_ctx].astype(np.float32)),
    lengths=sp.csr_matrix(conn76.tract_lengths[n_ctx:76, :n_ctx].astype(np.float32)),
    cv=1.0, dt=dt_sw, scale=1.0, cfun=HybridLinear(a=np.array([0.01])),
)
ns_sw = NetworkSet(subnets=[ctx_sw, thal_sw], projections=[c2t_sw]).configure()

c_vals = np.linspace(0.002, 0.1, 16).astype(np.float32)
res_c = cpp_nb.sweep(ns_sw, 2000, coupling_scale=c_vals, progress=False, workers=2)

mu_vals = np.linspace(0.0, 0.3, 16).astype(np.float32)
res_mu = cpp_nb.sweep(ns_sw, 2000, **{"cortex.mu": mu_vals}, progress=False, workers=2)

thal_y0 = res_c.squeezed("thalamus")[:, :, 0, :].mean(axis=(1, 2))
thal_y1 = res_c.squeezed("thalamus")[:, :, 1, :].mean(axis=(1, 2))
ctx_y0_mu = res_mu.squeezed("cortex")[:, :, 0, :].mean(axis=(1, 2))
assert np.isfinite(thal_y0).all() and np.isfinite(ctx_y0_mu).all()
print(f"Coupling sweep backend: {res_c.backend} ({res_c.elapsed*1e3:.1f} ms)")
print(f"Model    sweep backend: {res_mu.backend} ({res_mu.elapsed*1e3:.1f} ms)")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.2, 3.2), layout="constrained")
ax1.plot(c_vals, thal_y0, "o-", color="#275b97", ms=4, label="Target $y_0$ (left)")
ax1.set(title="Coupling sweep (8×68 connectome)", xlabel="coupling_scale", ylabel="Mean $y_0$ (mV)")
ax1r = ax1.twinx()
ax1r.plot(c_vals, thal_y1, "--", color="#9e4830", label="Target $y_1$ (right)")
ax1r.set_ylabel("Mean $y_1$ (mV)", color="#9e4830")

ax2.plot(mu_vals, ctx_y0_mu, "s-", color="#275b97", ms=4)
ax2.set(title="Model parameter sweep (cortex.mu)", xlabel="cortex.mu", ylabel="Cortex mean $y_0$ (mV)")
plt.show()
```

### Part 5b: Integer-multiple multirate stepping (`multi-dt`)

Build a 2:1 multirate `MontbrioPazoRoxin` network (`dt=0.01` ms cortex, `dt=0.02` ms thalamus), run it with `CppHybridBackend`, and confirm that a non-integer step ratio (`1.5 * dt0`) is rejected cleanly.

```{code-cell} ipython3
dt0 = 0.01
def make_mpr(name, dt_val, n=4):
    m = MontbrioPazoRoxin(); m.configure()
    return Subnetwork(name=name, model=m, scheme=HeunDeterministic(dt=dt_val), nnodes=n).configure()

fast_sn = make_mpr("cortex", dt0)
slow_sn = make_mpr("thalamus", 2 * dt0)
w_mr = sp.csr_matrix(np.full((4, 4), 0.05, dtype=np.float32) * (1 - np.eye(4, dtype=np.float32)))
p_f2s = InterProjection(
    source=fast_sn, target=slow_sn, source_cvar=np.array([0]), target_cvar=np.array([0]),
    weights=w_mr, lengths=sp.csr_matrix((w_mr != 0).astype(np.float32) * dt0),
    cfun=HybridLinear(), scale=0.02, cv=1.0, dt=dt0,
)
ns_mr = NetworkSet(subnets=[fast_sn, slow_sn], projections=[p_f2s]).configure()
mr_out = CppHybridBackend().compile(ns_mr).run(500)
t_mr, d_mr, _ = mr_out[0]
assert np.isfinite(d_mr).all()
print(f"2:1 multirate C++ run OK — cortex output shape: {np.asarray(d_mr).shape}")

# Non-integer step ratio (1.5 * dt0) raises ValueError
bad_sn = make_mpr("bad", 1.5 * dt0)
ns_bad = NetworkSet(subnets=[fast_sn, bad_sn], projections=[]).configure()
try:
    CppHybridBackend().compile(ns_bad)
except ValueError as exc:
    print("Non-integer ratio rejected as expected:", exc)
```

---

## Next steps

- Revisit the [Conceptual model](hybrid-concepts.md) for architecture and ownership seams.
- Keep [API contracts and common pitfalls](hybrid-contracts.md) handy when wiring custom models or connectomes.
- See [Backends and parameter sweeps](hybrid-backends-and-sweeps.md) for full backend capability tables and CUDA sweep options.
