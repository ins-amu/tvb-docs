---
title: Timescales
kernelspec:
  name: python3
  display_name: Python 3
  language: python
bibliography:
  - ../../references.bib
---

# Timescales

A whole-brain simulation spans more than six orders of magnitude in time,
from integration steps of a fraction of a millisecond to recordings of
minutes. Choosing `dt`, the monitor periods and the simulation length decides
which of these timescales the output resolves, and how much of the slowest
ones it covers. This page describes how TVB measures time and what each
setting controls, for TVB's default simulator, `simulator.Simulator`.

```{code-cell} ipython3
:tags: [remove-cell]

import logging
import warnings

# Keep TVB's log lines and the optional-gdist warning out of the rendered output.
warnings.filterwarnings("ignore", message="Geodesic distance module")
logging.disable(logging.WARNING)
```

## One clock, in milliseconds

TVB measures simulated time in milliseconds. The integration step `dt`, every
monitor `period`, `simulation_length`, the sample times returned by monitors
and the transmission delays all share this unit. Delays are computed as tract
length in mm divided by conduction speed in mm/ms
([Connectivity](../bb-connectivity.md)). Rates are therefore per millisecond:
the Jansen–Rit input `mu = 0.22` is 0.22 ms⁻¹, or 220 pulses/s
([model card](../../reference/model-cards/jansen-rit.md)).

The integrator does not know about units. It advances whatever equations the
model defines by `dt`, so the millisecond convention holds only if the
model's own time constants are in milliseconds. For models with physiological
parameters, such as Jansen–Rit and the reduced Wong–Wang model, they are.

Phenomenological models need more care. The SupHopf oscillator has no
intrinsic time constant, so its default angular frequency of 1 rad per unit of
time becomes 1 rad/ms, about 159 Hz. Deco et al. wrote the same equations in
seconds, at frequencies of a few hundredths of a hertz
([model card](../../reference/model-cards/suphopf.md)). The Epileptor has a
parameter, `tt`, that rescales the whole system to real time. Whenever a
model's equations were written in other units, rescale its parameters before
reading the output in milliseconds. Otherwise the delays, the BOLD monitor's
haemodynamics and any spectrum in hertz all assume a time unit the model does
not have.

## The timescales of a simulation

| process | in TVB | set by |
|---|---|---|
| integration step | 0.0122 ms by default; 0.1 ms in most examples on these pages | `integrator.dt` |
| conduction delays | 0–46 ms on the default connectome at 3 mm/ms | `connectivity.tract_lengths`, `connectivity.speed` |
| local time constants | 10 and 20 ms (Jansen–Rit), 100 ms (reduced Wong–Wang) | model parameters |
| sampling of electrophysiology | 0.9765625 ms (1024 Hz) by default | `monitor.period` |
| haemodynamic response | peaks between 0.8 and 6 s, depending on the kernel; 20 s kernel | `Bold.hrf_kernel`, `Bold.hrf_length` |
| fMRI sampling | 2000 ms by default | `Bold.period` |
| recording | as long as the analysis needs | `simulation_length` |

The fastest process sets `dt`: the step has to resolve the model's dynamics,
which [Integrators](../bb-integrators.md) discusses. Delays are rounded to
whole steps, so `dt` also sets their resolution. The slowest process sets the
simulation length.

(sampling-and-the-integration-step)=
## Sampling and the integration step

In the default simulator, monitors do not interpolate. A monitor samples
every $k$ integration steps, so its period should be a whole number of steps
([Monitors](../bb-monitors) describes how to choose it). A period that is not
is rounded without a warning, while `monitor.period` keeps the requested
value, so take the sampling interval from the returned time vector. For
1024 Hz, any `dt = 0.9765625 / k` works, including the integrators' default
of 0.01220703125 ms (`k = 80`).

The sampling period also fixes the highest frequency the output can
represent, $1/(2\,\text{period})$: 500 Hz for 1 ms samples. Faster activity
does not vanish from the output. `SubSample` does not filter, so it aliases
into lower frequencies. Averaging, in `TemporalAverage` and in the EEG, MEG
and iEEG monitors, attenuates it but does not remove it. If a model has
activity near or above that frequency, sample faster and filter afterwards.

## Transients

A simulation starts from an initial history, by default drawn at random from
each state variable's `state_variable_range`
([Simulator](../bb-simulator.md#initial-conditions)). The first part of the
output shows the network relaxing from that arbitrary start towards its
attractor rather than the behaviour of interest. How long that
{term}`transient <Transient>` lasts depends on the slowest relaxation in the
model, not on anything TVB sets. Near a stable fixed point it scales as
$1/|\mathrm{Re}\,\lambda|$ for the least stable eigenvalue $\lambda$. Close to
a bifurcation that rate approaches zero and relaxation becomes very slow, as
the [SupHopf card](../../reference/model-cards/suphopf.md#typical-dynamics)
shows for $a = 0$. Check the transient on the output, for example by
comparing statistics of the first and second halves of a run, and discard it.

Monitors that keep a memory have a transient of their own. The `Bold` monitor
convolves its input with a kernel `hrf_length` long, 20 s by default, and its
buffer is filled with zeros at the start of a run
([monitor source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/monitors.html)).
Until 20 s of activity have been recorded, each BOLD sample mixes the
simulated activity with those zeros. A reduced Wong–Wang node started close
to its resting state makes the effect visible. Its synaptic gating $S$ barely
changes over the run, yet its BOLD signal does:

```{code-cell} ipython3
import matplotlib.pyplot as plt
import numpy as np
from tvb.datatypes import connectivity, equations
from tvb.simulator import coupling, integrators, models, monitors, simulator

def single_node():
    node = connectivity.Connectivity(
        weights=np.zeros((1, 1)), tract_lengths=np.zeros((1, 1)),
        centres=np.zeros((1, 3)), region_labels=np.array(["node"]),
        speed=np.array([np.inf]))
    node.configure()
    return node

kernels = {"FirstOrderVolterra (default)": equations.FirstOrderVolterra(),
           "MixtureOfGammas": equations.MixtureOfGammas()}
sim = simulator.Simulator(
    connectivity=single_node(), model=models.ReducedWongWang(),
    coupling=coupling.Linear(a=np.array([0.0])),
    integrator=integrators.HeunDeterministic(dt=2.0),
    monitors=(monitors.TemporalAverage(period=10.0),)
             + tuple(monitors.Bold(period=500.0, hrf_kernel=k) for k in kernels.values()),
    initial_conditions=np.full((1, 1, 1, 1), 0.1),
)
sim.configure()
(t_s, s), *bold_outputs = sim.run(simulation_length=40e3)
print(f"S over the run: {s.min():.4f} to {s.max():.4f}")

fig, ax = plt.subplots(figsize=(8, 3.2))
for name, (t, b) in zip(kernels, bold_outputs):
    y = b[:, 0, 0, 0]
    unsettled = np.abs(y - y[-1]) >= 0.01 * abs(y[-1])
    print(f"{name:<29} within 1 % of its final value from {t[unsettled][-1] / 1e3 + 0.5:4.1f} s")
    ax.plot(t / 1e3, y / y[-1], "o-", ms=3, lw=1, label=name)
ax.axvspan(0, 20, color="0.9", zorder=0)
ax.text(14, 0.15, "first hrf_length (20 s): buffer still holds start-up zeros",
        ha="center", fontsize="small")
ax.set(xlabel="time [s]", ylabel="BOLD / final value", xlim=(0, 40))
ax.legend(frameon=False, fontsize="small")
fig.tight_layout()
plt.show()
```

The default kernel decays within a few seconds, so its output settles early.
The mixture of gammas has weight over most of its 20 s, and its output
settles only once the buffer is free of the start-up zeros. Discard at least
`hrf_length` of BOLD output, in addition to the neural transient.

## Simulation length

The simulation length $T$ sets what can be estimated from the output:

- **Spectra.** A recording of length $T$ resolves frequencies $1/T$ apart:
  1 Hz for 1 s, 0.017 Hz for 60 s. Averaging the spectra of shorter segments,
  as in Welch's method, trades that resolution for lower variance.
- **BOLD.** The number of volumes is $T/\text{TR}$: 150 for 5 min at a TR of
  2 s. For a correlation near zero, the standard error of the
  Fisher-transformed coefficient is about $1/\sqrt{N-3}$, 0.08 for 150
  volumes. Consecutive BOLD samples are autocorrelated, so the effective $N$
  is smaller and the true error larger.
- **Cost.** The run takes $T/dt$ integration steps whatever is recorded:
  3 million for 5 min at `dt = 0.1` ms, 25 million at the default `dt`.
  Runtime grows linearly with $T$
  ([Integrators](../bb-integrators.md#runtime-with-the-same-model)).

Taken together, a resting-state fMRI comparison needs minutes of simulated
time after the transients are discarded. An evoked-response comparison may
need only a few hundred milliseconds per trial, sampled at the rate of the
recording.
