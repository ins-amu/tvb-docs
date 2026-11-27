---
title: States and Observables
kernelspec:
  name: python3
  display_name: Python 3
  language: python
bibliography:
  - ../../references.bib
---

# States and Observables

The quantities a neural mass model integrates are not the quantities an
instrument records. A model's state might consist of mean membrane
potentials, synaptic gating variables or abstract coordinates of an
oscillator. An EEG electrode measures a potential difference on the scalp,
and fMRI measures a change in the blood's magnetic properties seconds after
the neural events that caused it. TVB keeps the two apart. The model defines
the state, and {term}`monitors <Monitor>` turn it into outputs, some of which
include an {term}`observer model <Observer model>` of a real measurement.
This page describes that chain in TVB's default simulator,
`simulator.Simulator`. Why the measurement has to be modelled at all is
discussed in [Forward models](../../explanation/forward-models.md).

```{code-cell} ipython3
:tags: [remove-cell]

import logging
import warnings

# Keep TVB's log lines and the optional-gdist warning out of the rendered output.
warnings.filterwarnings("ignore", message="Geodesic distance module")
logging.disable(logging.WARNING)
```

## The state space

At each node $i$, the model's state vector $\psi_i(t)$ collects the
{term}`state variables <State variable>` of the local dynamics
([Mathematical framework](../mathematical-framework.md)). In TVB they are
listed in `model.state_variables`. With conduction delays, the current
state alone does not determine the future. The coupling reads past values of
the coupled variables, so the history over the longest delay is part of the
state too ([Simulator](../bb-simulator.md#initial-conditions)).

State variables are defined by the model's equations, not by what an
instrument measures. Some have a direct physiological reading, such as the
postsynaptic potentials $y_0$, $y_1$, $y_2$ of the
[Jansen–Rit model](../../reference/model-cards/jansen-rit.md). Others are
auxiliary, such as its $y_3$, $y_4$, $y_5$, which are time derivatives that
turn second-order synaptic filters into first-order equations. Others again
are abstract, such as the $x$ and $y$ of the
[SupHopf oscillator](../../reference/model-cards/suphopf.md). None of them is
an EEG or BOLD signal.

(variables-of-interest)=
## Three lists on every model

Every TVB model declares three subsets of its variables:

```{code-cell} ipython3
from tvb.simulator import models

for model in (models.Generic2dOscillator(), models.JansenRit()):
    print(type(model).__name__)
    print("  state variables:      ", model.state_variables)
    print("  coupled (cvar):       ", tuple(model.state_variables[i] for i in model.cvar))
    print("  variables of interest:", model.variables_of_interest)
    print("  allowed choices:      ", type(model).variables_of_interest.element_choices)
```

- **State variables** are what the integrator advances.
- **Coupled variables** (`cvar`) are what each region sends to the others
  through the connectome ([Coupling](../bb-coupling.md)).
- **Variables of interest** are what monitors can see in TVB's default
  simulator; the code-generation backends work differently
  ([Data structures](data-structures.md#the-variable-axis)). At every
  integration step, the model's `observe` method evaluates every entry of
  `variables_of_interest` as an expression in the state variables. An entry
  can therefore be a combination, such as `"V + W"` for the
  `Generic2dOscillator`, but only from the model's list of allowed choices
  ([model source](https://docs.thevirtualbrain.org/_modules/tvb/simulator/models/base.html)).

A monitor's own `variables_of_interest` are indices into the model's list,
not into its state variables. Here the model exposes $V$, $W$ and $V + W$,
and the averaging monitor is given index 2:

```{code-cell} ipython3
import numpy as np
from tvb.datatypes import connectivity
from tvb.simulator import coupling, integrators, monitors, simulator

def single_node():
    node = connectivity.Connectivity(
        weights=np.zeros((1, 1)), tract_lengths=np.zeros((1, 1)),
        centres=np.zeros((1, 3)), region_labels=np.array(["node"]),
        speed=np.array([np.inf]))
    node.configure()
    return node

g2d = models.Generic2dOscillator(variables_of_interest=("V", "W", "V + W"))
sim = simulator.Simulator(
    connectivity=single_node(), model=g2d,
    coupling=coupling.Linear(a=np.array([0.0])),
    integrator=integrators.HeunDeterministic(dt=0.1),
    monitors=(monitors.Raw(),
              monitors.TemporalAverage(period=1.0, variables_of_interest=np.array([2]))),
)
np.random.seed(0)
sim.configure()
(_, raw), (_, avg) = sim.run(simulation_length=10.0)

print(f"Raw: {raw.shape}   TemporalAverage of index 2: {avg.shape}")
print("third variable of interest equals V + W:", np.allclose(raw[:, 2], raw[:, 0] + raw[:, 1]))
print("averaging monitor records 1 ms means of V + W:",
      np.allclose(avg[:, 0], (raw[:, 0] + raw[:, 1]).reshape(10, 10, 1, 1).mean(axis=1)))
```

The Jansen–Rit model shows why the distinction matters. Its EEG-like output
is $y_1 - y_2$, the mean membrane potential of the pyramidal cells
[@jansenRit1995], but that difference is not among the allowed choices.
Record $y_1$ and $y_2$ and subtract them after the run, as in the EEG
example below.

## From states to observables

An observable is a function of the state, usually lower-dimensional, often
filtered in time and recorded with noise. In the default simulator, the
monitors apply such a map to the variables of interest
([Monitors](../bb-monitors) describes each of them). `Raw`, `SubSample`,
`TemporalAverage`, `SpatialAverage` and `GlobalAverage` change only how the
variables are sampled or averaged: their outputs are still model variables,
in model units. The EEG, MEG, iEEG and `Bold` monitors add a model of a
recording device, described in the next two sections. Because each
observable has fewer dimensions than the state, different states can produce
the same recording, and so can different parameter sets. This is one reason
to constrain parameters with several data features, or several modalities,
rather than one ([Inference](../inference.md)).

(eeg-meg-and-seeg)=
## EEG, MEG and SEEG

The three electrophysiology monitors share one observation model. For each
variable of interest $x$, sensor $s$ records

$$
y_s(t) = \sum_i G_{si} \sum_m \bar{x}_{im}(t) + \eta_s(t),
$$

where $\bar{x}_{im}$ is the value of mode $m$ at node $i$, averaged over the
sampling period. $G$ is the gain, or {term}`lead field <Lead field>`, matrix,
and $\eta$ is observation noise. The map is linear and instantaneous; the
physics behind it is outlined in
[Forward models](../../explanation/forward-models.md#electromagnetic-signals-lead-fields).
In TVB, $G$ is built from a {term}`projection matrix <Projection matrix>`, a
set of sensors and a region mapping, or computed analytically when no
projection matrix is given. [Monitors](../bb-monitors) describes these inputs
and the defaults TVB provides for them.

The example uses the Jansen–Rit network of the
[alpha-network how-to](../../howtos/jansen-rit-alpha-network.md), without
noise, recording $y_1$ and $y_2$ both as 1024 Hz averages and as EEG.
Because the projection is linear, the EEG of $y_1$ minus the EEG of $y_2$ is
the EEG of the pyramidal potential $y_1 - y_2$:

```{code-cell} ipython3
import matplotlib.pyplot as plt

model = models.JansenRit(v0=np.array([6.0]), variables_of_interest=("y1", "y2"))
model.mu = model.p_min.copy()
conn = connectivity.Connectivity.from_file()
conn.weights = conn.weights / conn.weights.sum(axis=1).max()
cpl = coupling.SigmoidalJansenRit()
cpl.a = (model.p_max - model.p_min) / cpl.cmax

period = 1000.0 / 1024
eeg = monitors.EEG.from_file(period=period)
eeg.obsnoise = None                 # no observation noise
sim = simulator.Simulator(
    connectivity=conn, model=model, coupling=cpl,
    integrator=integrators.HeunDeterministic(dt=period / 8),
    monitors=(monitors.TemporalAverage(period=period), eeg),
)
np.random.seed(42)
sim.configure()
with np.errstate(over="ignore"):    # sigmoid overflow from the random start
    (t_src, source), (t_eeg, sensors) = sim.run(simulation_length=600.0)

pyramidal = source[:, 0, :, 0] - source[:, 1, :, 0]     # y1 - y2, per region
eeg_signal = sensors[:, 0, :, 0] - sensors[:, 1, :, 0]  # EEG of y1 - y2
print(f"regions: {source.shape}   sensors: {sensors.shape}   gain: {eeg.gain.shape}")
print("EEG of y1 - y2 equals G @ (y1 - y2):",
      np.allclose(eeg_signal, pyramidal @ eeg.gain.T))

keep = t_src >= 300.0               # discard the transient
print(f"peak-to-peak after 300 ms: regions {np.ptp(pyramidal[keep], axis=0).mean():.1f} mV, "
      f"electrodes {np.ptp(eeg_signal[keep], axis=0).mean():.2g} (arbitrary units)")

labels = list(eeg.sensors.labels)
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.4))
ax1.plot(t_src[keep], pyramidal[keep][:, ::15], lw=0.8)
ax1.set(xlabel="time [ms]", ylabel="$y_1 - y_2$ [mV]", title="regions (every 15th)")
for name in ("Fp1", "C3", "O1"):
    ax2.plot(t_eeg[keep], eeg_signal[keep, labels.index(name)], lw=0.8, label=name)
ax2.set(xlabel="time [ms]", ylabel="EEG [arbitrary units]", title="three electrodes")
ax2.legend(frameon=False, fontsize="small")
fig.tight_layout()
plt.show()
```

The sensor values are the state variable's units multiplied by those of the
gain matrix. TVB does not calibrate them to microvolts or femtotesla. Compare
spectra, correlations or normalised signals, or fit a scale factor.

Choosing the variable to project is part of the observation model. EEG and
MEG reflect the summed postsynaptic currents of pyramidal cells, which
$y_1 - y_2$ stands for here; a projected firing rate or an abstract
oscillator coordinate is a weaker approximation. For surface simulations with
EEG, MEG and SEEG together, see the
[surface forward-solution demo](../../demos/simulate_surface_seeg_eeg_meg.ipynb).

(bold)=
## BOLD

The `Bold` monitor does not integrate a haemodynamic model. It convolves the
recent history of each variable of interest, the last 20 s by default, with a
fixed {term}`haemodynamic response <Haemodynamic response>` kernel, and reports
the result once per sampling period, which plays the role of the TR. The
output is in arbitrary units.

The kernel decides how far, and with what shape, the BOLD signal lags the
neural activity. The default kernel, `FirstOrderVolterra`, peaks 0.8 s after
the input, and the others TVB provides peak seconds later
([Monitors](../bb-monitors) plots them). Because every region gets the same
kernel, the choice shifts all BOLD signals by the same amount. Zero-lag
correlations between regions change only through the kernel's filtering. The
delay itself matters when the BOLD signal is compared with stimulus timing or
with lags measured in real data.

The convolution is a linear, time-invariant approximation: the first-order
Volterra kernel is the linear part of the balloon model's response
[@friston_nonlinear_2000]. Measured BOLD responses are not linear. Glover
found that the response to a long stimulus could not be predicted by
convolving the response to a 1 s stimulus with a rectangular function
[@glover1999]. To include the nonlinearity, record the neural activity with
`TemporalAverage` and pass it to the Balloon–Windkessel analyzer afterwards.
The analyzer integrates the vasodilatory signal, blood flow, blood volume and
deoxyhaemoglobin content of every region, by default with the revised
coefficients of Stephan et al. [@stephan2007].

The example drives a single reduced Wong–Wang node with a 2 s block of input.
Its synaptic gating $S$, the kind of variable that usually drives the
haemodynamics
([Forward models](../../explanation/forward-models.md#the-bold-signal-a-slow-nonlinear-filter)),
is observed with the `Bold` monitor and its default kernel, and with the
Balloon–Windkessel analyzer applied to 10 ms averages of $S$. Each trace is shown as its change from the value just before
the block, scaled to its largest change, because the outputs have unrelated
units.

```{code-cell} ipython3
from tvb.analyzers.fmri_balloon import BalloonModel
from tvb.datatypes import equations, patterns, time_series

node = single_node()
onset = 25.0                      # s; after the 20 s start-up transient of the Bold buffer
block = equations.PulseTrain(parameters={"onset": onset * 1e3, "tau": 2e3, "T": 1e6, "amp": 1.0})
stimulus = patterns.StimuliRegion(temporal=block, connectivity=node, weight=np.array([0.002]))
default_bold = monitors.Bold(period=500.0)
sim = simulator.Simulator(
    connectivity=node, model=models.ReducedWongWang(),
    coupling=coupling.Linear(a=np.array([0.0])),
    integrator=integrators.HeunDeterministic(dt=2.0),
    stimulus=stimulus,
    monitors=(monitors.TemporalAverage(period=10.0), default_bold),
    initial_conditions=np.full((1, 1, 1, 1), 0.1),
)
sim.configure()
(t_s, s), (t_v, bold_v) = sim.run(simulation_length=onset * 1e3 + 25e3)

neural = time_series.TimeSeriesRegion(
    data=s, time=t_s, connectivity=node, sample_period=10.0, sample_period_unit="ms")
neural.configure()
balloon = BalloonModel(time_series=neural).evaluate()
print(f"neural input: {s.shape}, every {neural.sample_period:g} {neural.sample_period_unit}")
print(f"Bold monitor: {bold_v.shape}, every {default_bold.period:g} ms")
print(f"Balloon–Windkessel analyzer: {balloon.data.shape}, every {balloon.sample_period:g} {balloon.sample_period_unit}")

def response(t_seconds, y):
    """Change from the pre-stimulus value, scaled to its largest deviation."""
    change = y - y[np.searchsorted(t_seconds, onset - 0.1)]
    return change / np.abs(change).max()

traces = {"S (10 ms averages)": (t_s / 1e3, s[:, 0, 0, 0]),
          "Bold monitor, default kernel": (t_v / 1e3, bold_v[:, 0, 0, 0]),
          "Balloon–Windkessel analyzer": (balloon.time, balloon.data[:, 0, 0, 0])}

fig, ax = plt.subplots(figsize=(9, 3.6))
ax.axvspan(onset, onset + 2, color="0.9", zorder=0)
for name, (t, y) in traces.items():
    r = response(t, y)
    after = t > onset - 0.1
    peak = t[after][np.abs(r[after]).argmax()] - onset
    print(f"{name:<28} largest change {peak:4.2f} s after onset")
    ax.plot(t, r, lw=1.4, label=name)
ax.set(xlabel="time [s]", ylabel="change from baseline (scaled)", xlim=(onset - 5, onset + 25))
ax.legend(frameon=False, fontsize="small")
fig.tight_layout()
plt.show()
```

The input is on for 2 s (grey), starting once the start-up transients
described in [Timescales](timescales.md#transients) are over. $S$ settles to
its new level within about 0.4 s of the input starting, and returns as fast
after it stops. The default kernel follows $S$ with little delay, while the
Balloon–Windkessel response peaks about 2 s after the end of the block. The
monitor's output is sampled at the TR. The analyzer's output keeps the time
step of its input, which it also uses as its integration step, converted to
seconds through `sample_period_unit`; that unit must therefore be right, and
the output still has to be resampled to the TR of the recording. The
analyzer uses the first variable of interest unless
`neural_input_transformation` says otherwise
([analyzer source](https://docs.thevirtualbrain.org/_modules/tvb/analyzers/fmri_balloon.html)).

## Comparing with data

A simulation is compared with a recording through an observable of the same
kind, with matched sampling and preprocessing. The state variables themselves
have no counterpart in the data. In practice:

- simulate the modality you have, with its sensors, reference and TR;
- discard the transients of the model and of the monitor
  ([Timescales](timescales.md#transients));
- apply the same filtering, detrending and normalisation to both;
- compare features rather than raw traces, because the arbitrary amplitude
  scale and the noise make trace-by-trace agreement meaningless. Spectra and
  [functional connectivity](../../explanation/functional-connectivity.md) are
  common choices.
