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

The {term}`Simulator` assembles the components described in the previous
sections. A neural mass model governs activity in each brain region, while the connectome and coupling
function determine how regions interact. The integrator advances the model,
and monitors record its activity. The simulator also stores past states for
connections with transmission delays [@sanzleon2013; @hashemi2025].

## Initial conditions

The simulator needs an {term}`initial condition` and, when connections have
delays, a history of activity before the run begins. If `initial_conditions`
is omitted, TVB draws the initial history at random, sampling each state
variable from its `state_variable_range`.

For the `Generic2dOscillator`, it draws $V$ uniformly from $[-2,4]$ and $W$
from $[-6,6]$. Set the random seed before `configure()` to reproduce the draw
([model source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/models/oscillator.html),
[initialisation source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/models/base.html)).

The history is stored as a four-dimensional array with axes **time × state
variable × brain region × mode**. The model sets the length of the
{term}`mode <Mode>` axis through `number_of_modes`. The `Generic2dOscillator`
has one mode, so each region has one $V$ and one $W$ value at each time point.
The array below sets $V=-0.5$ and $W=0$ in every region at the start of the
run. It supplies only one time point; TVB generates the earlier states needed
for transmission delays from the model's sampling ranges.

```{code-cell} ipython3
import numpy as np
from tvb.datatypes import connectivity
from tvb.simulator import integrators, models, monitors, simulator

model = models.Generic2dOscillator()
conn = connectivity.Connectivity.from_file()
print(f"Modes per region: {model.number_of_modes}")
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

The 300 ms run below uses a separate simulator with model-drawn history.
To prescribe the entire history, supply enough time points to cover the
longest transmission delay. During `configure()`, TVB checks the state
variable, region, and mode dimensions. A mismatch raises `Incorrect history
sample shape`
([history source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/history.html)).

TVB uses `state_variable_range` to draw default history. It accepts supplied
initial values outside that range. Some models also define
`state_variable_boundaries`, which the integrator enforces. Starting far
outside the model's usual range can produce overflow, invalid-value warnings,
or non-finite trajectories. If that happens, inspect the model's ranges, the
supplied history, and the integration step
([model source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/models/base.html),
[integrator source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/integrators.html)).


## Whole-brain simulation

We now run a `Generic2dOscillator` at each of the 76 regions in TVB's default
connectome. The simulation uses the default `Linear` coupling and a history
drawn from the model's ranges. We set `dt=0.1` ms and record $V$ at every step
with `Raw`. A `TemporalAverage` monitor also records its mean over successive
1 ms intervals. The run covers 300 ms of simulated time.

```{code-cell} ipython3
import numpy as np
from tvb.datatypes import connectivity
from tvb.simulator import integrators, models, monitors, simulator

sim = simulator.Simulator(
    connectivity=connectivity.Connectivity.from_file(),
    model=models.Generic2dOscillator(),
    integrator=integrators.HeunDeterministic(dt=0.1),
    monitors=(monitors.Raw(), monitors.TemporalAverage(period=1.0)),
)
np.random.seed(7)  # Repeat the same randomly initialised history.
sim.configure()

(time, activity), (mean_time, mean_activity) = sim.run(simulation_length=300.0)
print(f"Regions: {sim.connectivity.number_of_regions}")
print(f"Raw samples: {len(time)}; array shape: {activity.shape}")
print(f"TemporalAverage samples: {len(mean_time)}; array shape: {mean_activity.shape}")
```

`sim.run()` returns one `(time, activity)` pair for each monitor, in the order
listed in `monitors`. The `Raw` array has shape `(3000, 1, 76, 1)` and the
1 ms averages have shape `(300, 1, 76, 1)`. The axes are **time × recorded
variable × brain region × mode**. Each average covers ten integration steps
([monitor source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/monitors.html)).
The model evolves $V$ and $W$; its default
`variables_of_interest` records $V$ alone
([Generic2dOscillator API](https://docs.thevirtualbrain.org/api/tvb.simulator.models.html)).
The final dimension has length one for this model. With a multimode model,
`activity[:, variable, region, mode]` selects a time series for one mode.

With `INFO` logging enabled, TVB also prints estimates of memory, storage,
and runtime. After the run, *elapsed* gives the measured wall-clock time;
*x real time* compares it with the 0.3 s of simulated time. A warning about
`random_state supplied for non-stochastic integration` may appear: the run
loop calls the integrator's random-state method even for deterministic Heun.
The integration remains deterministic
([Simulator source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/simulator.html),
[Integrator source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/integrators.html)).

The following plot shows $V$ in the first three brain regions. Thin lines
show every integration step; thicker lines of the same colour show the 1 ms
averages. These are model trajectories; EEG, MEG, and fMRI signals require
the appropriate monitors.

```{code-cell} ipython3
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(9, 3.5))
for region in range(3):
    line, = ax.plot(time, activity[:, 0, region, 0], linewidth=0.7, alpha=0.5,
                    label=f"{region}: {sim.connectivity.region_labels[region]}")
    ax.plot(mean_time, mean_activity[:, 0, region, 0],
            color=line.get_color(), linewidth=1.5)
ax.set(xlabel="Time (ms)", ylabel="$V$ (model units)")
ax.set_xlim(0, 300)
ax.legend(title="Brain region", ncol=3, fontsize="small")
fig.tight_layout()
plt.show()
```

## What happens during a run

`configure()` converts tract lengths and conduction speed into delays measured
in integration steps. It allocates the history needed for those delays,
initialises the model state, and configures the monitors. If an initial history
was supplied, TVB uses it when setting up the history buffer.

During `run()`, the simulator reads delayed source activity from the history
buffer, evaluates the coupling, and passes it to the local model. The
integrator computes the next state, which TVB adds to the history and passes
to the monitors. This sequence continues for the requested simulation length
([Simulator source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/simulator.html)).
TVB's default `ReferenceBackend` supplies the NumPy operations used by the
simulator. The integrator performs the state update
([reference backend source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/backend/ref.html)).

The example specifies a connectome, model, integrator, and two monitors. Other
`Simulator` arguments let you change the coupling function or conduction
speed, supply initial conditions or a stimulus, and include a cortical
surface. The [Simulator API](https://docs.thevirtualbrain.org/api/tvb.simulator.simulator.html)
lists them all.

`run()` collects each monitor's samples into arrays. For a longer simulation,
`sim(simulation_length=...)` yields samples as they become available, allowing
you to process them without storing the full recording. Another call on the
same configured simulator continues from its current state and history. For
an independent run, create a new simulator.

The [connectivity](bb-connectivity.md), [model](bb-model.md),
[coupling](bb-coupling.md), [integrator](bb-integrators.md), and
[monitor](bb-monitors.md) pages discuss each component in more detail. The
[first-simulation tutorial](../tutorials/first-simulation.md) extends this
example to a longer run with two monitors.
