---
kernelspec:
  name: python3
  display_name: Python 3
  language: python
---

# How-to: write a new model

*How-to guide — add a neural mass of your own to a simulation by subclassing* `Model`.

A model in TVB is a class, and only a small one: a list of state variables, a set of
parameters declared as traits, and one drift function — `dfun` — that returns the
time-derivatives of the state. Delays, connectivity, coupling strength, integration and
monitoring are all handled by the simulation machinery around it. This recipe writes a
new two-variable model using TVB's canonical `tvb.simulator.models.base.Model` class,
wires it into a network simulation with `tvb.simulator.simulator.Simulator`, and plots
what it does.

For what the equations are made of, see
[Neural mass models](../explanation/neural-mass-models.md); for the models that already
ship, see the [model cards](../reference/model-cards/wilson-cowan.md).

## What a `Model` subclass has to declare

| Class attribute | What it is |
|---|---|
| `state_variables`, `_nvar` | names and count of the ODEs, in the order `dfun` returns them |
| traits built with `NArray(...)` / `Range(...)` | the parameters; `default` is used unless you pass a keyword at construction |
| `dfun(self, state_variables, coupling, local_coupling=0.0)` | the drift function; returns derivatives, one row per state variable |
| `cvar` | indices of the state variables broadcast to the other regions |
| `stvar` | indices of the state variables that stimulus (and some monitors) write into |
| `coupling_terms` | names of the coupling rows `dfun` reads |
| `variables_of_interest` | which variables monitors record |
| `state_variable_range` | `[lo, hi]` used for initialisation and plot axes |

---

## 1. Define the class

Write a **two-variable rate unit with a slow adaptive brake** — the shape of a
spike-frequency-adaptation model: a fast population rate $x$ that self-excites through a
saturating transfer function, and a slow inhibitory variable $a$ that $x$ drives up and
that then shuts $x$ off.

$$
\begin{aligned}
\dot{x} &= \tfrac{1}{\tau}\big(-x + \phi(u) + C + \lambda x\big) \\[3pt]
\dot{a} &= \tfrac{1}{\tau_a}\big(-a + \beta\,\phi(u) + q\big) \\[3pt]
\phi(u) &= \tfrac{1}{2}\big(1 + \tanh u\big), \qquad u = \kappa x - a - \theta
\end{aligned}
$$

with $C$ the network coupling (`coupling[0]`) and $\lambda$ the local coupling. Read the
terms as: $-x$ leaks the rate back to zero at rate $1/\tau$; $\phi(u)$ is the population's
input–output curve, saturating at 1 so the rate cannot run away; $\kappa$ is self-excitation,
$\theta$ the threshold, $a$ the adaptive brake with gain $\beta$ and its own, slower, time
constant $\tau_a$; $q$ is a tonic drive on the adaptive variable. Because $\phi$ is bounded
while $\kappa x$ is not, the $x$-nullcline is N-shaped — a silent branch, an active branch
and an unstable one in between — as soon as $\kappa > 4$. Whether the unit uses all three
branches is decided by the brake: with $\beta$ small the slow variable never wins and the
unit rests at a single stable fixed point, while past a threshold just below $\kappa$
($\beta \approx 7$ for $\kappa = 8$ at the defaults below) the brake takes over, shuts $x$
off, recovers, and the unit becomes a relaxation oscillator.

Declare the parameters as traits, then implement `dfun`:

```{code-cell} ipython3
%matplotlib inline
from pathlib import Path
import numpy
import matplotlib.pyplot as plt

from tvb.simulator.models.base import Model
from tvb.basic.neotraits.api import NArray, Range, Final, List
from tvb.simulator.lab import connectivity, coupling, integrators, monitors
from tvb.simulator import simulator


class AdaptRate(Model):
    r"""AdaptRate: a saturating rate variable with a slow adaptive brake.

    dx/dt = (-x + phi(u) + C + local_coupling * x) / tau
    da/dt = (-a + beta * phi(u) + q) / tau_a
    with phi(u) = 0.5 * (1 + tanh(u)) and u = kappa*x - a - theta.
    """

    tau = NArray(
        label=r":math:`\tau`",
        default=numpy.array([1.0]),
        domain=Range(lo=0.1, hi=10.0, step=0.1),
        doc="Time constant of the rate variable [ms].",
    )

    tau_a = NArray(
        label=r":math:`\tau_a`",
        default=numpy.array([30.0]),
        domain=Range(lo=1.0, hi=200.0, step=1.0),
        doc="Time constant of the adaptive variable [ms].",
    )

    kappa = NArray(
        label=r":math:`\kappa`",
        default=numpy.array([8.0]),
        domain=Range(lo=4.0, hi=20.0, step=0.1),
        doc="Self-excitation gain; must exceed 4 for the N-shaped nullcline.",
    )

    beta = NArray(
        label=r":math:`\beta`",
        default=numpy.array([10.0]),
        domain=Range(lo=0.0, hi=20.0, step=0.1),
        doc="Gain of the adaptive brake.",
    )

    theta = NArray(
        label=r":math:`\theta`",
        default=numpy.array([0.3]),
        domain=Range(lo=-2.0, hi=2.0, step=0.05),
        doc="Threshold of the transfer function.",
    )

    q = NArray(
        label=r":math:`q`",
        default=numpy.array([0.0]),
        domain=Range(lo=-5.0, hi=5.0, step=0.1),
        doc="Tonic drive on the adaptive variable.",
    )

    state_variable_range = Final(
        label="State Variable ranges [lo, hi]",
        default={"x": numpy.array([0.0, 1.5]), "a": numpy.array([0.0, 12.0])},
        doc="Ranges used for initialisation and for plot axes; coupling can push x above 1.",
    )

    variables_of_interest = List(
        of=str,
        label="Variables watched by Monitors",
        choices=("x", "a"),
        default=("x", "a"),
    )

    coupling_terms = Final(label="Coupling terms", default=["c"])

    state_variables = ("x", "a")
    _nvar = 2
    cvar = numpy.array([0], dtype=numpy.int32)

    def dfun(self, state_variables, coupling, local_coupling=0.0):
        x = state_variables[0, :]
        a = state_variables[1, :]
        c_0 = coupling[0, :]

        # bounded transfer function: tanh saturates, so no overflow and no blow-up
        phi = 0.5 * (1.0 + numpy.tanh(self.kappa * x - a - self.theta))

        derivative = numpy.empty_like(state_variables)
        derivative[0] = (-x + phi + c_0 + local_coupling * x) / self.tau
        derivative[1] = (-a + self.beta * phi + self.q) / self.tau_a
        return derivative
```

`dfun` receives `state_variables` with shape `(n_var, n_regions, n_modes)`, indexing
into `x` and `a` in the order declared by `state_variables`, and returns a derivative
array of the same shape — that ordering is the contract the integrator expects.

Instantiate the model (traits can be overridden by keyword) and check what the
class resolved to:

```{code-cell} ipython3
model = AdaptRate(tau_a=numpy.array([30.0]))
names = ("tau", "tau_a", "kappa", "beta", "theta", "q")
params = ", ".join(f"{p} = {getattr(model, p).ravel()[0]:g}" for p in names)
print(f"State variables: {model.state_variables}")
print(f"Coupling variable (cvar): {model.cvar.tolist()} (x is broadcast)")
print(f"Monitored: {model.variables_of_interest}")
print(f"Parameters: {params}")
```

---

## 2. Wire it into a simulation

Load the region-level connectome with `connectivity.Connectivity.from_file`, set the
coupling function via TVB's `coupling.Linear`, and step the system forward with a
deterministic Heun integrator:

```{code-cell} ipython3
connectivity_path = Path("../tutorials/data/connectivity_76.zip").resolve()
white_matter = connectivity.Connectivity.from_file(str(connectivity_path))
white_matter.speed = numpy.array([4.0])  # conduction velocity [mm/ms]
white_matter.configure()
print(f"Connectome: {len(white_matter.region_labels)} regions, "
      f"{int((white_matter.weights > 0).sum() / 2)} undirected tracts.")
```

Assemble the components inside TVB's `Simulator`. We use `coupling.Linear(a=numpy.array([0.05]))`
for the long-range coupling strength, `integrators.HeunDeterministic(dt=0.1)`, and a `Raw` monitor:

```{code-cell} ipython3
sim = simulator.Simulator(
    model=model,
    connectivity=white_matter,
    coupling=coupling.Linear(a=numpy.array([0.05])),
    integrator=integrators.HeunDeterministic(dt=0.1),
    monitors=(monitors.Raw(),),
)
sim.configure()
```

Integrate for 400 ms. The simulator is an iterable yielding monitor outputs at each sampling step:

```{code-cell} ipython3
raw_data, raw_time = [], []
for (raw,) in sim(simulation_length=400.0):
    if raw is not None:
        raw_time.append(raw[0])
        raw_data.append(raw[1])

RAW = numpy.array(raw_data)
time = numpy.array(raw_time)
print(f"Integrated {len(time)} steps of dt = 0.1 ms = {time[-1]:.0f} ms of simulated time.")
print(f"Raw trace shape (time, state_variables, nodes, modes): {RAW.shape}")
```

---

## 3. Look at the result

The activity variable is `RAW[:, 0, :, 0]` (state variable `x`, all nodes); the adaptive
variable is `RAW[:, 1, :, 0]`. Plot the time series and, for region 0, the $(a, x)$
phase plane — the closed loop is the relaxation cycle:

```{code-cell} ipython3
fig, axes = plt.subplots(1, 2, figsize=(9, 3.2))

# Time series of activity x(t) across all regions
axes[0].plot(time, RAW[:, 0, :, 0], alpha=0.5, lw=0.8)
axes[0].set_xlabel("time (ms)")
axes[0].set_ylabel("x(t)")
axes[0].set_title("AdaptRate: activity of coupled regions")

# Phase plane (a vs x) for region 0
axes[1].plot(RAW[:, 1, 0, 0], RAW[:, 0, 0, 0], lw=1.2)
axes[1].set_xlabel("a (adaptive variable)")
axes[1].set_ylabel("x")
axes[1].set_title("Region 0: phase plane (a, x)")

fig.tight_layout()
plt.show()
```

Each region alternates between a silent branch ($x \approx 0$) and an active one
($x \approx 1$); the delayed coupling pulls the regions towards a common rhythm. Drop
`beta` to 6 and the loop collapses onto the active fixed point; raise `theta` to 2 and the
unit goes silent instead.

---

## Coupling hooks

`dfun`'s second argument is where the network enters your equations. Three things decide
what it looks like:

- **`cvar` selects what leaves the node.** It lists the state variables whose value is
  written into the history buffer and broadcast to the other regions. `cvar = [0]` (as
  here) broadcasts $x$ only; `cvar = [0, 1]` broadcasts both, and `coupling` then has two
  rows — one per entry — which `dfun` reads as `coupling[0]`, `coupling[1]`. Declare
  exactly the rows you use: an unused row is allocated and summed for nothing, and a row
  you index but did not declare is a shape error.
- **`coupling` is already weighted and delayed.** Each row is
  $\sum_j w_{ij}\,s_j(t - d_{ij})$ over the incoming edges of region $i$ — the sum, not the
  individual terms. In TVB the coupling function and strength come from the `Coupling`
  datatype (e.g. `coupling.Linear(a=numpy.array([0.05]))`).
- **local coupling is a separate argument.** `local_coupling` is a scalar set by the
  simulation's local-coupling datatype (diffusion over nearest neighbours in a surface or
  field model), not a row of `coupling`. Models that do not use short-range interaction
  simply ignore it; `AdaptRate` adds $\lambda x$ so you can see the difference.

**`stvar`** is the sibling hook for input rather than output: it names the state variables
that a stimulus is added to (`Simulator(stimulus=…)` and the hybrid `Stim` layer both
resolve variables by name). See
[Write a custom stimulus](../howtos/custom-stimulus.md) for that side of the API.

---

## Gotchas

- **`dfun` must be total.** It is called on arrays of shape
  `(n_state_variables, n_nodes, …)` every step: no Python `if` on a state value, no
  in-place mutation of `state`, and no unbounded `exp` — use `tanh`/`clip` or a rational
  saturation instead. A NaN in one step poisons the whole trace.
- **`_nvar`, `cvar` and the `dfun` order must agree.** `_nvar` is the number of rows the
  integrator allocates, `state_variables` names them, and `dfun` must return exactly that
  many rows in that order.
- **Traits are class attributes, not `__init__` assignments.** TVB's declarative trait system
  inspects class-level trait declarations (`NArray`, `Final`, etc.). Parameters set directly
  in `__init__` bypass validation, type conversions, `summary_info`, parameter sweeps, and
  the TVB GUI.
- **Stability is your problem, not the integrator's.** The default Heun step with
  `dt = 0.1 ms` is fine for these time constants, but a stiff model (fast sodium-like
  terms, $\tau \ll 1$ ms) will blow up; shrink `dt` or move to an implicit integrator.

---

## Where to go next

- [Wilson–Cowan](../reference/model-cards/wilson-cowan.md),
  [Generic2dOscillator](../reference/model-cards/generic-2d-oscillator.md) and
  [SupHopf](../reference/model-cards/suphopf.md) — read a real card before writing your
  own: `AdaptRate` is the same shape as `Generic2dOscillator`'s cubic nullcline with the
  cubic replaced by a bounded transfer function.
- [Neural mass models](../explanation/neural-mass-models.md) — where these equations come
  from and what the variables mean.
- [Interactive phase planes](../tutorials/phase-plane.md) — analyse the nullclines of the
  standard models the same way you would check this one.
- [Your first simulation](../tutorials/first-simulation.md) — the complete TVB simulation
  pipeline with connectivity, coupling, and monitors explained end to end.
