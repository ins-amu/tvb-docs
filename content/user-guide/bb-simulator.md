---
title: Simulator
kernelspec:
  name: python3
  display_name: Python 3
  language: python
bibliography:
  - ../references.bib
---

# Simulator

The {term}`Simulator` brings the parts of a TVB simulation together. The
connectome links brain regions, a neural mass model describes the activity
within each region, and coupling determines how activity arriving from other
regions enters the model. The integrator solves the resulting equations, while
monitors record selected signals. The simulator also retains the past activity
needed for transmission delays. Together, these components turn the
[mathematical framework](mathematical-framework.md) into simulated time series
[@sanzleon2013; @hashemi2025].

## Initial conditions

The simulator needs an {term}`initial condition` and, for delayed connections,
activity from before the start of the run. When `initial_conditions` is omitted,
TVB draws this history from the model's `state_variable_range`. For the
`Generic2dOscillator`, $V$ is drawn uniformly from $[-2,4]$ and $W$ from
$[-6,6]$. There is no single default starting state; the seed before
`configure()` makes the draws repeatable
([model source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/models/oscillator.html),
[initialisation source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/models/base.html)).

To choose a starting state, supply a four-dimensional array ordered as
**time × state variable × brain region × mode**. A {term}`mode <Mode>` is one
component of the local model's state representation at each region. The
`Generic2dOscillator` has one mode containing both $V$ and $W$. TVB's
reduced-set FitzHugh–Nagumo and Hindmarsh–Rose models have three: their modes
are components of a reduced
description of a heterogeneous neuronal population, with a value of each state
variable in each mode
([Stefanescu–Jirsa model source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/models/stefanescu_jirsa.html)).
The model determines the size of this axis. The example below starts every
region at $V=-0.5$ and $W=0$:

```{code-cell} ipython3
import numpy as np
from tvb.datatypes import connectivity
from tvb.simulator import integrators, models, monitors, simulator

model = models.Generic2dOscillator()
conn = connectivity.Connectivity.from_file()
for variable in model.state_variables:
    print(f"{variable} initial draw range: {model.state_variable_range[variable]}")
initial_history = np.zeros((1, model.nvar, len(conn.region_labels), model.number_of_modes))
initial_history[:, model.state_variables.index("V"), :, :] = -0.5

sim_with_ic = simulator.Simulator(
    connectivity=conn,
    model=model,
    integrator=integrators.HeunDeterministic(dt=0.1),
    monitors=(monitors.Raw(),),
    initial_conditions=initial_history,
)
np.random.seed(7)
sim_with_ic.configure()
print(f"Supplied history shape: {initial_history.shape}")
print(f"History points needed for delays: {sim_with_ic.good_history_shape[0]}")
print(f"First region's starting state: {sim_with_ic.current_state[:, 0, 0]}")
```

This prepares an alternative run with chosen starting values. The 300 ms run
below uses model-drawn history.

The single supplied time point sets the state at the start of a run. Here
the longest propagation delay requires more history than that, so TVB fills
the earlier points using the model's default sampling ranges. To specify the
entire history, supply enough time points to cover that delay. TVB checks the
state-variable, region, and mode dimensions; a mismatch raises `Incorrect
history sample shape` during `configure()`
([history source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/history.html)).

The `state_variable_range` governs default sampling; it does not restrict
values supplied in `initial_conditions`. Models can separately define
`state_variable_boundaries` that the integrator enforces. A supplied state
outside the sampling range therefore need not produce a warning, but an
implausible start can lead to overflow, invalid-value warnings, or non-finite
trajectories. Check the model's ranges and dynamics, the supplied history,
and the integration step if that happens
([model source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/models/base.html),
[integrator source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/integrators.html)).

## A regional simulation

This example uses TVB's 76-region connectome and the `Generic2dOscillator`.
We set a 0.1 ms integration step and use a `Raw` monitor to sample the model's
observed variables at every step. The simulator uses its default `Linear`
coupling and draws its initial history from the model's ranges. The requested
300 ms is simulated time; the time taken to run the code on a computer will be
different.

```{code-cell} ipython3
import numpy as np
from tvb.datatypes import connectivity
from tvb.simulator import integrators, models, monitors, simulator

sim = simulator.Simulator(
    connectivity=connectivity.Connectivity.from_file(),
    model=models.Generic2dOscillator(),
    integrator=integrators.HeunDeterministic(dt=0.1),
    monitors=(monitors.Raw(),),
)
np.random.seed(7)  # Repeat the same randomly initialised history.
sim.configure()

time, activity = sim.run(simulation_length=300.0)[0]
print(f"Regions: {sim.connectivity.number_of_regions}")
print(f"Samples: {len(time)}; last time: {time[-1]:g} ms")
print(f"Recorded array shape: {activity.shape}")
```

The three printed lines identify the connectome size and describe the returned
data. `run()` gives one `(time, activity)` pair for each monitor; `[0]` selects
the `Raw` output. Here `activity.shape` is `(3000, 1, 76, 1)`: **time ×
recorded variable × brain region × mode**. The samples span 0.1 to 300 ms.
The model has two state variables, but its default
`variables_of_interest` contains only $V$, so the recorded-variable dimension
has length one
([Generic2dOscillator API](https://docs.thevirtualbrain.org/api/tvb.simulator.models.html)).

TVB can write diagnostic messages alongside these three lines. With `INFO`
logging enabled, its memory, storage, and runtime estimates describe the
expected cost of the run. The final *elapsed* time is the measured time on
your computer; *x real time* is that time divided by 300 ms. Neither is a
simulated signal. Depending on the installation, you may also see warnings:
`hemispheres not found` means that the example connectome has no hemisphere
annotations, and `Geodesic distance module is unavailable` concerns surface
calculations, which this regional example does not use. Current TVB versions
may warn `random_state supplied for non-stochastic integration` because the
run loop calls the integrator's random-state method even for deterministic
Heun; this does not add noise
([Simulator source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/simulator.html),
[Integrator source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/integrators.html)).

Here is $V$ in the first three brain regions. The traces are model activity;
EEG, MEG, and fMRI require different monitors to produce their respective
signals. In this run, the trajectories start at different values and settle
towards the same level over the 300 ms window.

```{code-cell} ipython3
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(9, 3.5))
for region in range(3):
    ax.plot(time, activity[:, 0, region, 0],
            label=f"{region}: {sim.connectivity.region_labels[region]}")
ax.set(xlabel="Time (ms)", ylabel="$V$ (model units)")
ax.set_xlim(0, 300)
ax.legend(title="Brain region", ncol=3, fontsize="small")
fig.tight_layout()
plt.show()
```

## What happens during a run

`configure()` prepares the components to work together. For example, TVB
converts tract lengths and conduction speed into delays measured in integration
steps, allocates the activity history needed for those delays, and configures
the monitor. It uses a supplied initial history when present and calls the
model's initialisation method otherwise.

During `run()`, the simulator reads each region's connected sources from the
appropriate points in that history. It evaluates the coupling, passes it to
the local model, and asks the integrator for the next state. That state is
written back to the history and offered to the monitors. The loop repeats for
the requested simulation length
([Simulator source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/simulator.html)).
TVB's default `ReferenceBackend` supplies NumPy operations used by the
simulator; the chosen integrator performs the state update
([reference backend source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/backend/ref.html)).

The `Simulator` can also take a different coupling function, conduction speed,
initial conditions, a stimulus, or a cortical surface. Their effects depend
on the model and the spatial scale of the simulation; the
[Simulator API](https://docs.thevirtualbrain.org/api/tvb.simulator.simulator.html)
lists the available arguments. In this example, the explicit inputs are the
connectome, model, integrator, and monitor.

`run()` collects each monitor's samples into arrays, as above. For a longer
simulation, `sim(simulation_length=...)` yields monitor samples as they become
available, so they can be processed without retaining the whole recording in
memory. Another call on the same configured simulator continues from its
current state and history; make a new simulator for an independent run.

The [connectivity](bb-connectivity.md), [model](bb-model.md),
[coupling](bb-coupling.md), [integrator](bb-integrators.md), and
[monitor](bb-monitors.md) pages discuss each component in more detail. The
[first-simulation tutorial](../tutorials/first-simulation.md) extends this
example to a longer run with two monitors.
