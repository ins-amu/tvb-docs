---
title: Model
bibliography:
  - ../references.bib
---

# Model

The model is the local dynamics of one subnetwork.
The `Subnetwork` decides *which* nodes and *which* integrator; the model decides
*how many* {term}`state variables <State variable>` it carries, how many modes,
which variables it exchanges with the rest of the network, and what shape of
input its `dfun` accepts. Projections, integrators, stimuli and monitors are all
built around those declarations.

A {term}`hybrid simulation <Hybrid simulation>` has no single model: it has one
per subnetwork, and they may differ in dimension, time step and mode count.
There is also no hybrid-specific model class — the framework consumes
`tvb.simulator.models.Model` unchanged, so `JansenRit`, `WilsonCowan` or
`ReducedSetFitzHughNagumo` run identically in classic TVB and inside a
subnetwork.

This page covers three topics. Jump to whichever you need.

- **[What the model does in a hybrid simulation](#hybrid-model-role)**.
- **[How to choose and attach a model](#hybrid-model-setup-guide)**.
- **[API reference and model contract](#hybrid-model-api-reference)**, with
  commentary and common pitfalls.

---

(hybrid-model-role)=
## What the model does in a hybrid simulation

:::{note}
Everything on this page is written for a subnetwork that owns its own `dt`,
its own history buffers and its own projection set. Nothing assumes a
homogeneous network: a `NetworkSet` may mix 1-mode and 3-mode models, and
subnetworks may run at different integer-multiple time steps.

The state of a subnetwork always has shape `(nvar, nnodes, number_of_modes)`.
:::

The pipeline is always the same six steps:

1. **Intra coupling.** Every `IntraProjection` attached to the subnetwork reads
   (possibly delayed) source states from its own history buffer and writes into
   the subnetwork's coupling slots.
2. **Inter coupling.** Every `InterProjection` addressed at the subnetwork adds
   afferents from other subnetworks into the **target's** coupling slots.
3. **Stimuli.** Stimuli owned by the subnetwork add into their designated
   slot.
4. **`dfun`.** The model is called as `dfun(x, total_c)`; the integrator's own
   `local_coupling` and `stimulus` arguments are passed as `0.0`, because
   stimuli were already folded into a slot at step 3.
5. **Integration.** The subnetwork's own `scheme` advances the state and then
   applies the model's boundaries and clamps.
6. **Observation.** `model.observe(nx)` selects `variables_of_interest`. Local
   `Recorder`s see per-subnetwork state; global monitors see mode-summed output.

In one line, for subnetwork $b$:

$$
\dot{x}_b = f_b\!\left(x_b,\; c_b\right),
\qquad
c_b = \sum_{p\,\rightarrow\, b} P_p\!\left(x_{\text{src}}(t-\tau_p)\right) + c_b^{\text{stim}},
$$

where $P_p$ is the projection (weights, delays, {term}`coupling function
<Coupling function>`), $f_b$ is `model.dfun`, and $c_b$ is a stack of coupling
slots with shape $\left(\lvert \text{cvar}_b \rvert,\; n_b,\; M_b\right)$.

Steps 1–3 all write into the same array. That array, and nothing else, is what
`dfun` receives as its second argument.

### The coupling array the model receives

The first axis of $c_b$ is **coupling slots**, not state-variable indices. Slot
$i$ corresponds to `model.cvar[i]` and lives in $0 \ldots \lvert
\text{cvar}_b \rvert - 1$. A model that declares `cvar = [0, 3]` has two slots;
slot `1` maps to state index `3`.

This distinction is the single most common silent bug in hybrid models. Some
models declare two slots but read only the first — `JansenRit` has `cvar =
[1, 2]` and its `dfun` uses only `c[0]`. Projecting into slot `1` of a
`JansenRit` target therefore changes nothing. See
[API contracts](hybrid-contracts.md) for the resolution rules and for the
`source_cvar` / `target_cvar` asymmetry.

### Only declared variables cross a boundary

A model declares which of its state variables travel: its `cvar`. As a
**source**, `cvar` selects entries of the history buffer, so only those
variables can be routed out. As a **target**, the same declaration fixes how
many slots exist.

Two consequences when mixing models:

- A projection from a 1-slot source into a 2-slot target can only fill one slot;
  the other receives nothing unless a second projection or a stimulus supplies
  it.
- Coupling functions are written against a fixed number of coupling variables.
  `SigmoidalJansenRit` and dynamic `PreSigmoidal` expect **two**, and misbehave
  when the target model supplies fewer. See
  [coupling functions](../bb-coupling.md).

### Modes belong to the model, not the simulator

`model.number_of_modes` is read per subnetwork. `ReducedSetFitzHughNagumo` and
`ReducedSetHindmarshRose` carry $M = 3$; almost everything else carries $M = 1$.
Three things follow:

- **`mode_map` on inter-projections.** It defaults to an all-ones
  $(M_a, M_b)$ matrix, so a 1-mode source is replicated into all $M_b$ target
  modes. `ReducedSet*` then sums incoming slots across modes, multiplying the
  effective gain by $M_b$.
- **Monitors sum over modes.** `NetworkSet.observe` calls
  `model.observe(x).sum(axis=-1)`, so global monitors never show individual
  modes. Attach a per-subnetwork `Recorder` to keep them.
- **`dfun_mode`.** `ReducedSet*` models must keep the default
  `dfun_mode = "combined"`; accelerated backends reject the alternatives.

### `local_coupling` is always zero

`Subnetwork.step` calls the integrator as `scheme(x, dfun, total_c, 0.0, 0.0)`.
The fourth argument is `local_coupling`, and it is hardwired to zero. Any model
whose equations contain a local term — `JansenRit`'s
`local_coupling * (y1 - y2)`, the `LarterBreakspear` and `Zerlaut` local drives
— silently loses it inside a hybrid simulation.

There is no flag to turn it on. If you need that term, express it as an
`IntraProjection` over the neighbourhood weights (for a surface simulation, the
local connectivity matrix), with its own coupling function. It then enters
through a coupling slot, and the model's own local term stays at zero.

---

(hybrid-model-class)=
## Description of the model inside a `Subnetwork`

`Subnetwork.model` is declared as `t.Attr(Model)`: any `tvb.simulator.models`
instance is accepted, and `Subnetwork.configure()` calls `model.configure()`
before anything else.

```python
from tvb.simulator.hybrid import Subnetwork
from tvb.simulator.integrators import HeunDeterministic
from tvb.simulator.models import JansenRit

cortex = Subnetwork(
    name="cortex",
    model=JansenRit(),                    # <----
    scheme=HeunDeterministic(dt=0.1),
    nnodes=38,
).configure()
```

Everything the hybrid framework needs from a model is a class-level or
configure-time declaration. The table lists what is read and when.

| Declaration | Read when | Used for |
|---|---|---|
| `state_variables`, `nvar` | `configure()`, buffer setup | State array shape `(nvar, nnodes, M)`, history ring layout |
| `cvar` | projection validation, buffer setup | Number of coupling slots; source variables that may be routed |
| `number_of_modes` | buffer setup, `observe` | Mode axis; `mode_map` shape; mode summation in monitors |
| `stvar` | buffer setup | Variables actually stored in history (defaults to `cvar`) |
| `non_integrated_variables`, `nintvar` | `Subnetwork.configure()` | Boundary/clamping reconfiguration in the integrator |
| `state_variable_range` | `random_states()` | Default initial conditions when none are supplied |
| `state_variable_boundaries` | integrator configuration | Per-variable clamps after each step |
| `variables_of_interest` | monitor configuration | Channel count and layout of recorded output |
| `coupling_terms` | *nothing* | Documentation only — string cvar names resolve against `cvar`, not this |
| `dfun(x, c)` | every step | Local derivative; must broadcast over nodes and modes |
| `observe(x)` | every step | Selection of `variables_of_interest` for monitors |
| `update_derived_parameters()` | `model.configure()` | Filling derived matrices/vectors used by `dfun` |

`coupling_terms` is the trap worth remembering: `CerebellarMF` names its slots
`["mossy", "parallel"]`, but string resolution looks at `cvar`, i.e. at
`["GrC", "GoC"]`. Pass integer slots `0` and `1` for that model.

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

`Hopfield` rewrites `_nvar` and `cvar` inside `configure()` when `dynamic=True`,
so read those attributes *after* configuring, never from the class.

#### Choosing a model per subnetwork

- **Match the coupling function to the model, not the other way round.** Models
  whose equations already saturate (`JansenRit`, `ReducedWongWang`) want
  `Linear` projectors. Oscillator models want `Difference` or `Kuramoto`.
- **Prefer the smallest model that carries the mechanism.** A `Linear` driver
  subnetwork is often enough to test a projection topology before paying for a
  second `JansenRit` block.
- **Check slot count before wiring.** Two-slot targets (`WilsonCowan`,
  `JansenRit`, `MontbrioPazoRoxin`, `ReducedSet*`, `CerebellarMF`) reward an
  explicit look at `dfun`, because declaring a slot is not the same as reading
  it.
- **Keep mode counts deliberate.** Mixing $M = 1$ and $M = 3$ is supported and
  is the main reason to use a hybrid model at all, but it changes the gain
  through `mode_map` unless compensated.

(hybrid-model-parameters)=
### Parameters

Parameters belong to the model *instance*, and each subnetwork holds its own
instance. Two rules:

**No spatialisation pass.** Classic TVB reshapes region-sized parameter arrays
to `(nnodes, 1)` inside `Simulator.configure()`. The hybrid simulator does not.
Scalars broadcast fine; a per-node parameter must already have shape
`(nnodes, 1)` to align with `(nvar, nnodes, M)`. A flat `(nnodes,)` array
broadcasts along the wrong axis and produces silently wrong dynamics.

```python
import numpy as np

jr = JansenRit(mu=np.array([[0.0]] * 38))   # per-node, shape (38, 1)
jr = JansenRit(mu=np.array([0.1]))          # single value, broadcasts
```

**Configure before use.** `model.configure()` fills derived parameters (the
`Aik`/`Bik` matrices of `ReducedSet*`, transfer tables of `CerebellarMF`,
`stvar`, `observe`). `Subnetwork.configure()` does it for you; calling
`configure()` twice is harmless.

Parameter sweeps address models by subnetwork-qualified name, e.g.
`cortex.mu`, through the unified sweep API described in
[Backends and parameter sweeps](hybrid-backends-and-sweeps.md).

### One model instance per subnetwork

A model instance is mutable state: `configure()` writes `stvar`,
`state_variable_mask`, `nintvar` and rebuilds `observe`. Two subnetworks that
share one instance share that state, and any later `configure()` overwrites it.
Instantiate per subnetwork, exactly as you would for integrators:

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
model's `configure()` and also configures the integrator boundaries that depend
on the model. Call `model.configure()` yourself only to inspect declarations.

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

`tvb.simulator.models.base.Model` — the base class consumed by
`Subnetwork.model`. Only `dfun` is abstract; every other attribute in the table
above has a default.

Relevant declarations, in the order the hybrid framework touches them:

```python
state_variables: tuple[str]          # names, length == nvar
_nvar: int                           # exposed as model.nvar (read-only property)
number_of_modes: int = 1
cvar: numpy.ndarray[int]             # coupling variables, defines slot count
stvar: numpy.ndarray[int] | None     # defaults to cvar in configure()
non_integrated_variables: tuple[str] | None
state_variable_range: dict[str, list[float]]
state_variable_boundaries: dict[str, numpy.ndarray] | None
variables_of_interest: tuple[str]
coupling_terms: tuple[str]           # documentation only

def dfun(self, state_variables, coupling, local_coupling=0.0): ...
def observe(self, state_variables): ...     # built in configure()
def update_derived_parameters(self): ...    # called from configure()
```

`tvb.simulator.hybrid.cvar_utils` — name resolution used by projections and
stimuli:

| Function | Accepts | Returns |
|---|---|---|
| `resolve_source_cvar(model, spec)` | names of coupling variables, or ints | state-variable indices (history-buffer positions) |
| `resolve_target_cvar(model, spec)` | names of coupling variables, or ints | coupling-slot indices (`0 … len(cvar)-1`) |
| `validate_cvar_indices(model, idx)` | int array | `True`, or `ValueError` outside `0 … nvar-1` |
| `validate_target_cvar_indices(model, idx)` | int array | `True`, or `ValueError` outside `0 … len(cvar)-1` |

Error messages name the offending variable and list the valid ones, e.g.
`"'mossy' is not a coupling variable of CerebellarMF. Coupling variables are:
['GrC', 'GoC']"`.

### Backend support

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
[Backends and parameter sweeps](hybrid-backends-and-sweeps.md) for the full
matrix.

---

## Next steps

- [Conceptual model](hybrid-concepts.md) — ownership seams and multirate clocks.
- [API contracts and common pitfalls](hybrid-contracts.md) — matrix orientation, slot indexing.
- [Hands-on tutorials](hybrid-tutorials.md) — mixed-model, multi-slot and sweep scripts.
- [Coupling functions](../bb-coupling.md) — what happens to the value on each edge.
