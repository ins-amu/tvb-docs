---
title: Model
bibliography:
  - ../references.bib
---

# Model

The model is the local dynamics of one subnetwork: the equations solved at
every node, every step. The `Subnetwork` decides *which* nodes and *which*
integrator; the model decides how many {term}`state variables <State variable>` 
it carries, how many {term}`modes <Mode>` and which variables are used for coupling.

The {term}`hybrid simulation <Hybrid simulation>` has no single model: it has one
per subnetwork, and they may differ. A `NetworkSet` can mix 1-mode and 3-mode
models, and subnetworks can run at different time steps.

This page covers what the model does in the simulation, what it declares,
and how to pick, attach and verify one.

---

(hybrid-model-role)=
## What the model does in the simulation

Every node of a subnetwork carries the same set of
{term}`state variables <State variable>` — potentials, firing rates, synaptic
gates, whatever the model's equations describe. The model owns
that state and does four things with it:

- **Holds the state.** One value per variable per node, laid out as
  `(nvar, nnodes, modes)`. Modes are parallel copies of the model per node —
  `1` everywhere except `ReducedSetFitzHughNagumo` and
  `ReducedSetHindmarshRose`, which use `3`.
- **Computes the derivative.** `dfun` is the model's equations: given the
  current state and everything arriving from the network, the rate of change
  of each state variable. The integrator then advances the state.
- **Declares the coupling variables.** cvar selects which state variables affect the rest of the network,
   and which coupling slots its dfun reads.
- **Reports the output.** `variables_of_interest` picks what `observe(nx)`
  returns and monitors record.

Each integration step the model's dfun is called once, as `dfun(x, c)`:

- `x` is the current node state.
- `c` is the coupling array, shape `(len(cvar), nnodes, modes)`. It represents
  the state of the rest of the network, and it's effects on the node.

The derivative `dfun` returns is integrated by the subnetwork's scheme, then
the state is clamped to `state_variable_boundaries` where the model declares
them, and `observe(nx)` selects `variables_of_interest` for monitors.

`c` is filled by the simulator, through [Connectivity](bb-connectivity.md) and/or [Conceptual model](hybrid/hybrid-concepts.md) 
for more details. The rest of this section covers the model side: what reaches `dfun`, and what
happens to its output.

### The coupling array `dfun` receives

The array `c`, in `dfun(x, c)`, has the shape `(len(cvar), nnodes, modes)`.
Its first axis is coupling slots, not state-variable indices. 
Slot `i` corresponds to `model.cvar[i]`: a model declaring `cvar = [0, 3]` has two slots,
and slot `1` maps to state index `3`.

Declaring a slot is not the same as reading it. `JansenRit` declares
`cvar = [1, 2]`, giving it two slots — slot `0` for `y1`, slot `1` for `y2` —
but its `dfun` reads only `c[0]`. A projection with `target_cvar=1` therefore
writes into the `y2` slot and changes nothing. Use `target_cvar=0` (or
`target_cvar="y1"`) to drive a `JansenRit` target. See
[API contracts](hybrid/hybrid-contracts.md) for the resolution rules and the
`source_cvar` / `target_cvar` asymmetry.

### Coupling in terms of the model
TODO review

A model's `cvar` sets both ends of a projection. The two ends are not
symmetric.

**As a source**, `cvar` lists the state variables the model can send. Name a
source variable as a string and it must be in `cvar`, or the projection is
rejected. An integer `source_cvar` skips that check and indexes the state
directly.

**As a target**, `cvar` sets how much the model can receive: exactly
`len(cvar)` slots, and no projection can create more.

The two ends need not match in size, so:

- **The projection addresses fewer slots than the target has.** Only the
  addressed slots receive input; the others stay at zero until another
  projection or a stimulus writes into them.
- **One source variable, several target slots.** The same value lands in every
  slot listed. Supply as many source variables as slots to map them one to one.
- **A coupling function expects more variables than the target has slots.**
  `SigmoidalJansenRit` and dynamic `PreSigmoidal` both expect two and misbehave
  with fewer. See [coupling functions](bb-coupling.md).

### Stimuli enter through coupling slots

A stimulus targets one of the model's `cvar` slots and arrives inside `c`, so the model's equations see it as coupling.

### Modes

`model.number_of_modes` is read per subnetwork. Three things follow:

- **`mode_map` on inter-projections** defaults to an all-ones $(M_a, M_b)$
  matrix, so a 1-mode source is replicated into all $M_b$ target modes.
  `ReducedSet*` targets then sum incoming slots across modes, multiplying the
  effective gain by $M_b$.
- **Monitors sum over modes.** `NetworkSet.observe` calls
  `model.observe(x).sum(axis=-1)`, so global monitors never show individual
  modes. Attach a per-subnetwork `Recorder` to keep them.
- **`dfun_mode`.** `ReducedSet*` models must keep the default
  `dfun_mode = "combined"`; accelerated backends reject the alternatives.

### Local coupling is always zero

`local_coupling` is effectively deprecated with this version of TVB. The `local_coupling` argument `dfun` receives is always `0.0`. 
If you need local coupling, express it as an
`IntraProjection` over the neighbourhood weights (for a surface simulation,
the local connectivity matrix), with its own coupling function.

Any model whose equations contain a local term — `JansenRit`'s `local_coupling * (y1 - y2)`,
the `LarterBreakspear` and `Zerlaut` local drives — silently loses it inside a
hybrid simulation.

TODO @maedoc how is this fixed?


---

(hybrid-model-class)=
## What a model declares

Everything the hybrid framework needs from a model is a class-level or
configure-time declaration. `Subnetwork.model` accepts any
`tvb.simulator.models` instance, and `Subnetwork.configure()` calls
`model.configure()` before anything else.

| Declaration | Used for |
|---|---|
| `state_variables`, `nvar` | State array shape `(nvar, nnodes, M)`; history layout |
| `cvar` | Number of coupling slots; source variables that can be routed |
| `number_of_modes` | Mode axis; `mode_map` shape; mode summation in monitors |
| `stvar` | Nothing — ignored in hybrid (stimuli target `cvar` slots) |
| `state_variable_range` | Initial conditions: each variable is drawn uniformly from its `[lo, hi]` |
| `state_variable_boundaries` | Per-variable clamps the integrator applies after each step |
| `non_integrated_variables`, `nintvar` | Boundary/clamp re-indexing; no built-in model uses it |
| `variables_of_interest` | What `observe(x)` returns and monitors record |
| `coupling_terms` | Nothing — documentation only; string resolution uses `cvar` |
| `dfun(x, c)` | Local derivative; must broadcast over nodes and modes |
| `observe(x)` | Selection of `variables_of_interest`, built during `configure()` |
| `update_derived_parameters()` | Derived matrices and tables used by `dfun` |

Points worth knowing beyond the table:

- **`state_variable_range` and `state_variable_boundaries` are different
  things.** The range bounds *initial conditions only*. The boundaries are
  clamps the integrator applies *after each step*, and only in models that
  declare them: `ReducedWongWang*`, `Zerlaut*`, `MontbrioPazoRoxin`,
  `KIonEx`, `CerebellarMF`, `CoombesByrne*`, `DecoBalancedExcInh`,
  `DumontGutkin`, `Gast*`. Clamping is a post-hoc clip of the state, not a
  constraint inside `dfun`.
- **`variables_of_interest` has a per-model default, usually a subset.** The
  model decides what monitors see. The base class default is empty. Set the list yourself when the default is not what you want to measure.
- **`nvar` is a plain attribute each model sets by hand** `Hopfield` rewrites `_nvar` and `cvar` inside `configure()` when `dynamic=True` — read those attributes *after* configuring, never from the class.
- **`coupling_terms` in `CerebellarMF`** names its slots
  `["mossy", "parallel"]`, but string resolution looks at `cvar`, i.e.
  `["GrC", "GoC"]`. Pass integer slots `0` and `1` for that model.

### Initial conditions

With no initial conditions supplied, `Subnetwork.initial_state` calls
`model.initial(dt, history_shape, rng)`, which draws each state variable
uniformly from its `state_variable_range` entry, independently for every node
and mode. The draw always uses `numpy.random`, not the integrator's noise
stream, so seed it for reproducible runs:

```python
import numpy as np

np.random.seed(42)
state = cortex.initial_state()    # shape (nvar, nnodes, modes)
```

To set exact starting values, pass `initial_conditions` to `sim.run()`; see
[initial conditions](bb-initial-conditions.md) and the
[hybrid tutorials](hybrid/hybrid-tutorials.md).

### Built-in models

Only the fields that matter for routing are shown. `n` is `nvar`, `M` is
`number_of_modes`; the last column lists the state variables behind each slot.

| Model | `n` | `M` | Slots (`cvar`) | Notes |
|---|---|---|---|---|
| `Linear` | 1 | 1 | 1 → `x` | Driver/source subnetwork |
| `ReducedWongWang` | 1 | 1 | 1 → `S` | Sigmoid already inside `dfun` |
| `ReducedWongWangExcInh` | 2 | 1 | 1 → `S_e` | One slot shared by both populations |
| `Kuramoto` | 1 | 1 | 1 → `theta` | Pair with `Kuramoto`/`Difference` coupling |
| `Generic2dOscillator` | 2 | 1 | 1 → `V` | Cheap stand-in dynamics |
| `SupHopf` | 2 | 1 | 2 → `x`, `y` | |
| `MontbrioPazoRoxin` | 2 | 1 | 2 → `r`, `V` | Used in the multirate examples |
| `JansenRit` | 6 | 1 | 2 → `y1`, `y2` | `dfun` reads slot 0 only |
| `ZetterbergJansen` | 12 | 1 | 1 → `v6` | |
| `WilsonCowan` | 2 | 1 | 2 → `E`, `I` | |
| `Epileptor` | 6 | 1 | 2 → `x1`, `x2` | `modification=True` unsupported on accelerated backends |
| `Epileptor2D` | 2 | 1 | 1 → `x1` | As above |
| `EpileptorRestingState` | 8 | 1 | 3 → `x1`, `x2`, `x_rs` | As above |
| `LarterBreakspear` | 3 | 1 | 1 → `V` | Local term lost (see above) |
| `Hopfield` | 2 | 1 | 1 → `x`; 2 when `dynamic=True` | Slot count depends on a parameter |
| `KIonEx` | 5 | 1 | 1 → `x` | |
| `CoombesByrne` | 4 | 1 | 4 → `r`, `V`, `g`, `q` | Four-slot target |
| `CoombesByrne2D` | 2 | 1 | 2 → `r`, `V` | |
| `GastSchmidtKnosche_SD` / `_SF` | 4 | 1 | 4 → `r`, `V`, `A`, `B` | |
| `DumontGutkin` | 8 | 1 | 4 → `r_e`, `V_e`, `r_i`, `V_i` | |
| `ZerlautAdaptationFirstOrder` | 5 | 1 | 1 → `E` | Second order: `n = 8`, same slot |
| `ReducedSetFitzHughNagumo` | 4 | 3 | 2 → `xi`, `alpha` | Mode gain trap (`mode_map`) |
| `ReducedSetHindmarshRose` | 6 | 3 | 2 → `xi`, `alpha` | As above |
| `CerebellarMF` | 5 | 1 | 2 → `GrC`, `GoC` | Slots mean *mossy* / *parallel*; integer slots only |
| `Dody` | 6 | 1 | 3 → `r`, `V`, `u` | Custom hybrid-era model |

### Choosing a model per subnetwork
TODO maybe remove?
- **Prefer the smallest model that carries the mechanism.** A `Linear` driver
  subnetwork is often enough to test a projection topology before using a
  second `JansenRit` block.
- **Keep mode counts deliberate.** Mixing $M = 1$ and $M = 3$ is supported, but it changes the gain through `mode_map` unless compensated.

### Backend support

TODO move to backend file? reference from here?

The pure-Python path accepts any Python model. Accelerated backends do not:

- **Numba** (`backend="numba"`, `cpu-seq`, `cpu-prange`) — 29 built-in models,
  Heun/Euler deterministic or stochastic, uniform `dt`; rejects
  `modification=True` on `Epileptor*`, `dynamic=True` on `Hopfield`,
  `shift_sigmoid=False` on `WilsonCowan`, non-`"combined"` `dfun_mode` on
  `ReducedSet*`, and nonzero `local_coupling`.
- **C++** (`CppHybridBackend`) — 13 core plus 25 built-in models, with a custom
  symbolic fallback.
- **CUDA** (`backend="cuda"`, `"auto"`) — uniform `dt` only, no `CerebellarMF`.

A custom model needs `state_variable_dfuns` (or a custom Mako template, as
`CerebellarMF` does) to run outside the Python path. See
[Backends and parameter sweeps](hybrid/hybrid-backends-and-sweeps.md) for the
full matrix.

(hybrid-model-parameters)=
### Parameters

Parameters belong to the model instance, and each subnetwork holds its own
instance. Two rules:

**No spatialisation pass.** Classic TVB reshapes region-sized parameter
arrays to `(nnodes, 1)` inside `Simulator.configure()`. The hybrid simulator
does not. Scalars broadcast fine; a per-node parameter must already have shape
`(nnodes, 1)` to align with `(nvar, nnodes, M)`. A flat `(nnodes,)` array
broadcasts along the wrong axis and produces silently wrong dynamics.

```python
import numpy as np

jr = JansenRit(mu=np.array([[0.0]] * 38))   # per-node, shape (38, 1)
jr = JansenRit(mu=np.array([0.1]))          # single value, broadcasts
```

**Configure before use.** `model.configure()` fills derived parameters (the
`Aik`/`Bik` matrices of `ReducedSet*`, transfer tables of `CerebellarMF`,
`observe`). `Subnetwork.configure()` does it for you; calling `configure()`
twice is harmless.

Parameter sweeps address models by subnetwork-qualified name, e.g.
`cortex.mu`, through the unified sweep API described in
[Backends and parameter sweeps](hybrid/hybrid-backends-and-sweeps.md).

### One model instance per subnetwork

A model instance is mutable state: `configure()` writes `stvar`,
`state_variable_mask`, `nintvar` and rebuilds `observe`. Two subnetworks that
share one instance share that state, and any later `configure()` overwrites
it. Instantiate per subnetwork, exactly as you would for integrators:

```python
cortex = Subnetwork(name="cortex", model=JansenRit(), scheme=HeunDeterministic(dt=0.1), nnodes=38)
thalamus = Subnetwork(name="thalamus", model=JansenRit(), scheme=HeunDeterministic(dt=0.1), nnodes=38)
```

---

(hybrid-model-setup-guide)=
## Setup guide

### 1. Pick one model per subnetwork

Decide the mechanism each block must carry, then the smallest model that
carries it. Write down each model's `n`, `M` and slot count before writing
projection code — the projections are shaped by those numbers.

### 2. Read the declarations, don't guess them

```python
from tvb.simulator.models import JansenRit, ReducedSetFitzHughNagumo

for model in (JansenRit(), ReducedSetFitzHughNagumo()):
    model.configure()                       # required before reading cvar-derived fields
    slots = [model.state_variables[int(i)] for i in model.cvar]
    print(type(model).__name__,
          "nvar =", model.nvar,
          "modes =", model.number_of_modes,
          "slots =", slots)
# JansenRit nvar = 6 modes = 1 slots = ['y1', 'y2']
# ReducedSetFitzHughNagumo nvar = 4 modes = 3 slots = ['xi', 'alpha']
```

Then confirm which slots `dfun` actually reads. A slot that is declared and
never used accepts projections without effect.

### 3. Attach the model to a subnetwork

```python
import numpy as np
import scipy.sparse as sp
from tvb.simulator.hybrid import Subnetwork, NetworkSet, InterProjection, Simulator
from tvb.simulator.integrators import HeunDeterministic
from tvb.simulator.models import JansenRit, ReducedSetFitzHughNagumo
from tvb.simulator.monitors import TemporalAverage

dt = 0.1
cortex = Subnetwork(name="cortex", model=JansenRit(),
                    scheme=HeunDeterministic(dt=dt), nnodes=38).configure()
thalamus = Subnetwork(name="thalamus", model=ReducedSetFitzHughNagumo(),
                      scheme=HeunDeterministic(dt=dt), nnodes=8).configure()

# Slice the connectome strictly as (n_target, n_source) = (8, 38)
w_thalamus_cortex = sp.csr_matrix(conn.weights[38:46, :38].astype(np.float32))
l_thalamus_cortex = sp.csr_matrix(conn.tract_lengths[38:46, :38].astype(np.float32))

proj = InterProjection(
    source=cortex, target=thalamus,
    source_cvar="y1",          # a coupling variable of the *source* model
    target_cvar=0,             # slot 0 of the *target* coupling array
    weights=w_thalamus_cortex,
    lengths=l_thalamus_cortex,
    cv=7.0, dt=dt, scale=0.1,
)
nets = NetworkSet(subnets=[cortex, thalamus], projections=[proj])
sim = Simulator(nets=nets, simulation_length=500.0, monitors=[TemporalAverage(period=1.0)])
sim.configure()
((t, y),) = sim.run(initial_conditions=[np.zeros((6, 38, 1)), np.zeros((4, 8, 3))])
```

Let `Subnetwork.configure()` own the operative `configure()` call: it runs the
model's `configure()` and also configures the integrator boundaries that
depend on the model. Call `model.configure()` yourself only to inspect
declarations.

### 4. Verify what the model actually received

Attach an `AfferentCoupling` monitor to the subnetwork. It records the summed
coupling array — all slots, external plus intra plus stimuli — rather than the
state, which is exactly what `dfun` sees.

```python
from tvb.simulator.monitors import AfferentCoupling

thalamus.add_monitor(AfferentCoupling())
thalamus.monitors[-1].configure(sim.simulation_length)
sim.configure()
sim.run(initial_conditions=[...])

t, c = thalamus.monitors[-1].to_arrays()   # shape (T, n_slots, nnodes, M)
```

Check three things: the slot axis length equals `len(model.cvar)`; the slot you
intended to drive is the one that is non-zero; and the magnitude is comparable
to the terms the model's equations expect. Coupling input orders of magnitude
larger than the local dynamics means the network is driving the model, not
perturbing it.

---

(hybrid-model-api-reference)=
## API reference

- [`tvb.simulator.models.base`](../reference/api/tvb.simulator.models.base.md) —
  the `Model` base class consumed by `Subnetwork.model`.
- [`tvb.simulator.models`](../reference/api/tvb.simulator.models.md) — the
  built-in models.
- [`tvb.simulator.hybrid.cvar_utils`](../reference/api/tvb.simulator.hybrid.cvar_utils.md) —
  cvar name resolution used by projections and stimuli.

---

## Next steps

- [Conceptual model](hybrid/hybrid-concepts.md) — ownership seams and multirate clocks.
- [API contracts and common pitfalls](hybrid/hybrid-contracts.md) — matrix orientation, slot indexing.
- [Hands-on tutorials](hybrid/hybrid-tutorials.md) — mixed-model, multi-slot and sweep scripts.
- [Coupling functions](bb-coupling.md) — what happens to the value on each edge.
- [Model zoo](../model-zoo/intro.md) — per-model background and equations.
