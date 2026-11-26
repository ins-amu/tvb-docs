---
title: Coupling
bibliography:
  - ../references.bib
---

# Coupling

The {term}`coupling function <Coupling function>` is the rule that turns
activity arriving over the long-range {term}`connectivity <Connectivity>` into
input to a node's local dynamics. The {term}`connectome` decides *who* talks to
whom and how strongly; the coupling function decides *how* the arriving signal
is transformed before it enters the {term}`neural mass model`.

This page covers three topics. Jump to whichever you need.

- **[What the coupling function does in a simulation](#coupling-role)**.
- **[How to choose and set one up](#coupling-setup-guide)**.
- **[API reference](#coupling-api-reference)**, with commentary and common pitfalls.

---

(coupling-role)=
## What the coupling function does in a simulation

:::{note}
Everything on this page is written from the point of view of a simulation that
uses delays and a history buffer. The same concepts apply if you don't have
delays: drop $\tau_{kj}$ and read the neighbourhood state at the current time.
Nothing else about the pipeline changes.
:::

Coupling functions are of two kinds, **pre-synaptic** and **post-synaptic**.
The pipeline is always the same four steps:

1. The **pre-synaptic** function is applied to the (delayed) state of the
   neighbours.
2. A **dot product** of the weights with this "new" state: $u_{kj}\,S(\cdot)$.
3. The **rows are summed** — each target node collects everything addressed to it.
4. The **post-synaptic** function is applied to that sum, last.

In one line, for target region $k$:

$$
I_k(t) = Z\!\left(\sum_{j=1}^{l} u_{kj}\, S\!\left(\Psi_k(t),\,\Psi_j(t-\tau_{kj})\right)\right),
\qquad
\tau_{kj} = \frac{\ell_{kj}}{v},
$$

where $S$ is the {term}`presynaptic transformation <Presynaptic transformation>`,
$Z$ the {term}`postsynaptic transformation <Postsynaptic transformation>`,
$u_{kj}$ the weight **from $j$ onto $k$** (rows are targets, see
[weights](bb-connectivity.md#weights-section)), and $\tau_{kj}$ the
{term}`propagation delay <Propagation delay>`.

The result $I_k(t)$ is exactly the `coupling` argument that the model receives
in `dfun()`.

### Only some state variables travel

A model declares which of its state variables are exchanged over the network:
its `cvar`. Only those enter the history buffer and therefore the coupling
function. A model with `cvar = [0]` sends one variable; `SigmoidalJansenRit`
and dynamic `PreSigmoidal` assume **two**, and will misbehave silently if the
model provides fewer.

This matters when you swap coupling functions between models: the function is
written against a specific number of coupling variables, not against the state
vector as a whole.

### Where the gain enters

Nothing about "how strong the coupling is overall" lives in the simulator. The
overall gain comes from exactly two places:

- the `a` (or `G`, `cmax`) parameter of the coupling function, which scales the
  summed afferents, and
- the model's own coupling term, where several models carry a global coupling
  parameter multiplied by the incoming `coupling` array.

See [global coupling](#coupling-global) below for the double-counting trap.

---

(coupling-object)=
## Description of the Coupling class

`tvb.simulator.coupling.Coupling` is not a container of arrays like
`Connectivity`. It is a small callable object with no data of its own beyond a
handful of parameters.

The simulator calls it as

```python
node_coupling = sim.coupling(step, sim.history)
```

and the base class implements that call as pre → weighted sum → post. A
subclass therefore **should not override `__call__`**; it overrides `pre` and
`post`.

| Method | Receives | Returns | Default |
|---|---|---|---|
| `pre(x_i, x_j)` | current state of the target, delayed state of every source | per-connection transformed activity, shape $(l, l)$ | `x_j` — pass through |
| `post(gx)` | the row-summed, weighted activity, shape $(l,)$ | the vector that enters `dfun()` | `gx` — pass through |

The defaults make the base class a plain linear-weighted-sum coupling. Any
function that only rescales or shifts the summed input needs `post` alone; any
function that saturates or compares source with target needs `pre`, because it
must act *before* the weights are applied.

### Built-in functions

| Class | Formula | Stage | Parameters (defaults) |
|---|---|---|---|
| `Linear` | $a\,gx + b$ | post | `a`=0.00390625, `b`=0 |
| `Scaling` | $a\,gx$ | post | `a`=0.00390625 |
| `Difference` | $a\,(x_j - x_i)$ | pre | `a`=0.1 |
| `Kuramoto` | $\frac{a}{N}\sin(x_j - x_i)$ | pre | `a`=1.0 |
| `HyperbolicTangent` | $a\left(1+\tanh\frac{b\,x_j-\theta}{\sigma}\right)$ | pre | `a`=1, `b`=1, `midpoint`=0, `sigma`=1 |
| `Sigmoidal` | $c_{min}+\dfrac{c_{max}-c_{min}}{1+\exp\left(-a\,\frac{gx-\theta}{\sigma}\right)}$ | post | `cmin`=-1, `cmax`=1, `midpoint`=0, `a`=1, `sigma`=230 |
| `SigmoidalJansenRit` | $c_{min}+\dfrac{c_{max}-c_{min}}{1+\exp\left(r(\theta-(x_{j,0}-x_{j,1}))\right)}$, then $a\,gx$ | pre + post | `cmin`=0, `cmax`=0.005, `midpoint`=6, `r`=0.56, `a`=1 |
| `PreSigmoidal` | $H\left(Q+\tanh\left(G(P\,x_j-\theta)\right)\right)$ | pre | `H`=0.5, `Q`=1, `G`=60, `P`=1, `theta`=0.5, `dynamic`, `globalT` |

`gx` is the weighted row sum; $N$ is the number of nodes.

#### Choosing between them

- **`Linear` / `Scaling`** when the model itself does the nonlinearity. This is
  the default and the right choice for most neural mass models, including
  `JansenRit` and `ReducedWongWang`, whose equations already contain a sigmoid.
- **`Difference` / `Kuramoto`** for phase and oscillator models, where what
  matters is the mismatch between nodes and a common drive would be
  unphysical.
- **`Sigmoidal`** when the summed input should saturate. Applied post-summation,
  so it cannot be undone by the weights.
- **`HyperbolicTangent` / `SigmoidalJansenRit` / `PreSigmoidal`** when the
  saturation belongs to the source, i.e. each connection carries a bounded
  amount of activity regardless of how many afferents hit the target.

(parameters)=
### Parameters

All parameters are `NArray` attributes and may be scalars or arrays, so gain can
vary per node or per mode.

:::{warning}
**Defaults are historical, not physical.** The `a` of `1/256` in `Linear` is a
normalisation constant inherited from early 76-region simulations; `sigma = 230`
in `Sigmoidal` comes from a model whose coupling variable is in a different
range. Both are applied to whatever state your model produces. Set them against
the scale of your model's `cvar`, not by inheritance.
:::

`Sigmoidal` and `SigmoidalJansenRit` both put the sigmoid at different stages,
which is the single most common source of confusion. `Sigmoidal` saturates the
*weighted sum* (post); `SigmoidalJansenRit` saturates each *source's
difference* first (pre) and only then sums. Identical parameter values do not
give identical behaviour.

(coupling-global)=
### Global coupling

There is no simulator-level global coupling parameter. An overall gain is
expressed either as `a` in the coupling function or as the model's coupling
term — and several models have their own (`G`, `J`, `c`…). Check which of the
two your model expects before adding the other.

:::{caution}
`connectivity.scaled_weights('region')` and a coupling gain both scale the same
row sums. Normalise weights *and* leave the gain at 1, or leave the weights
raw *and* set the gain — not both. A network coupled twice over runs, looks
plausible, and is wrong.
:::

Diagonal (self-connection) weights matter here too: they are not removed by
default, so a large diagonal adds a term that no delay and no neighbour
contributes to.

### Sparse evaluation

Most built-ins derive from `SparseCoupling` and evaluate only afferents with a
non-zero weight; TVB 3.0 stores history sparsely for the same reason. The three
sigmoids (`Sigmoidal`, `SigmoidalJansenRit`, `PreSigmoidal`) derive from the base
class and touch the full $l \times l$ matrix.

A custom coupling function should subclass `SparseCoupling` and implement
`pre`/`post` — no other change is needed for it to be fast.

---

(coupling-setup-guide)=
## Setup guide

### 1. Pick the function for your model

Ask where the nonlinearity already is. If the model equations contain a
sigmoid, the coupling should not — use `Linear`. If the model is a phase
oscillator, use `Difference` or `Kuramoto`. Only reach for a pre-synaptic
sigmoid when the source activity itself must be bounded.

Check the number of coupling variables the model provides before choosing a
two-variable function.

### 2. Set the gain

```python
import numpy as np
from tvb.simulator.lab import coupling

coupling.Linear(a=np.array([0.004]))          # explicit gain
```

Leave `b` at zero unless you deliberately want to inject a constant offset
into every node — it is not a bias term of the model, it is added to the
coupling input of all nodes at once.

### 3. Attach it to a simulation

```python
from tvb.simulator.lab import simulator, models, integrators, monitors, connectivity

conn = connectivity.Connectivity.from_file("my_connectivity.zip")
conn.speed = np.array([3.0])

sim = simulator.Simulator(
    connectivity=conn,
    coupling=coupling.Linear(a=np.array([0.004])),
    model=models.JansenRit(),
    integrator=integrators.HeunDeterministic(dt=0.1),
    monitors=[monitors.Raw(), monitors.AfferentCoupling()],
)
sim.configure()
results = sim.run()
```

Do not call `configure()` on the coupling function yourself. `Simulator.configure()` does it.

### 4. Verify what arrives at the model

Attach `monitors.AfferentCoupling()` and look at the recorded input before
interpreting any dynamics. Its magnitude should be comparable to the terms the
model's equations expect — if the coupling input is orders of magnitude larger
than the local dynamics, the gain is wrong and the network is being driven, not
coupled.

The same monitor is the fastest way to check that a new connectome and a new
coupling function agree on the weights convention.

---

(coupling-api-reference)=
## API reference

:::{note}
**To do:** link to the generated API reference for `tvb.simulator.coupling`.
Until it exists, this section carries the guidance.
:::
