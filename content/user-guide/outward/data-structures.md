---
title: Data Structures
kernelspec:
  name: python3
  display_name: Python 3
  language: python
bibliography:
  - ../../references.bib
---

# Data Structures

A TVB simulation does not hand back the model's state. It hands back what
each {term}`monitor <Monitor>` recorded, as a pair of NumPy arrays per
monitor: a vector of sample times and a block of samples. This page describes
those arrays and how to wrap them in TVB's `TimeSeries` datatypes, for TVB's
default simulator, `simulator.Simulator`. What the recorded quantities mean
is the subject of [States and observables](states-observables.md).

```{code-cell} ipython3
:tags: [remove-cell]

import logging
import warnings

# Keep TVB's log lines and the optional-gdist warning out of the rendered output.
warnings.filterwarnings("ignore", message="Geodesic distance module")
logging.disable(logging.WARNING)
```

## What a run returns

We record a `Generic2dOscillator` network with five monitors. The model is
told to expose both of its state variables, $V$ and $W$, to monitors. The
third monitor records $W$ alone.

```{code-cell} ipython3
import numpy as np
from tvb.datatypes import connectivity
from tvb.simulator import integrators, models, monitors, simulator

model = models.Generic2dOscillator(variables_of_interest=("V", "W"))
sim = simulator.Simulator(
    connectivity=connectivity.Connectivity.from_file(),
    model=model,
    integrator=integrators.HeunDeterministic(dt=0.1),
    monitors=(
        monitors.Raw(),
        monitors.TemporalAverage(period=1.0),
        monitors.TemporalAverage(period=1.0, variables_of_interest=np.array([1])),
        monitors.SubSample(period=1.0),
        monitors.GlobalAverage(period=1.0),
    ),
)
np.random.seed(42)
sim.configure()
results = sim.run(simulation_length=100.0)

print(f"{'monitor':<16} {'data shape':<17} first and last sample times")
for monitor, (time, data) in zip(sim.monitors, results):
    print(f"{type(monitor).__name__:<16} {str(data.shape):<17} "
          f"{time[0]:5.1f} … {time[-1]:5.1f} ms")
print(f"model state held by the simulator: {sim.current_state.shape}")
```

`run()` returns a list with one `(time, data)` tuple per monitor, in the
order the monitors were given. `time` is one-dimensional and in milliseconds.
With TVB's default simulator, `data` always has four axes:

| axis | name | length |
|---|---|---|
| 0 | time | number of samples the monitor produced |
| 1 | variable | the variables of interest this monitor records |
| 2 | space | regions, vertices, sensors or groups, depending on the monitor |
| 3 | mode | the model's `number_of_modes`, or 1 |

The layout follows the model's own state, which the simulator holds as
*state variable × node × mode*, with time prepended. The same index
therefore picks out the same region in the state, in the connectivity and in
every region-level output.

(the-variable-axis)=
### The variable axis

The variable axis lists the model's variables of interest, not its state
variables, or the subset of them a monitor selects: the third monitor above
selects $W$. What the variables of interest are, and how a monitor selects
from them, is explained in
[States and observables](states-observables.md#variables-of-interest).

This holds for TVB's default simulator. The NumPy and Numba code-generation
backends, which support only a few models and a `Raw` or `TemporalAverage`
monitor, return every state variable whatever the variables of interest are.
The NumPy backend also drops the mode axis, so its `Raw` output has three axes
([using backends](../../demos/using_backends.ipynb)).

### The space axis

Monitors that keep every node have one entry per region in a region
simulation, or one per cortical vertex plus one per non-cortical region in a
surface simulation. Monitors that average over space or project onto sensors
have one entry per group of nodes or per sensor instead. What each monitor
reduces is described in [Monitors](../bb-monitors).

### The mode axis

The mode axis has the length of the model's `number_of_modes`, which is 1 for
most models. The reduced Stefanescu–Jirsa models carry three modes per node
[@stefanescu2008], and region-level monitors keep them. The EEG, MEG and iEEG
monitors sum over modes before projecting onto the sensors
([States and observables](states-observables.md#eeg-meg-and-seeg)), so their
mode axis has length 1:

```{code-cell} ipython3
modal = models.ReducedSetFitzHughNagumo()
conn = connectivity.Connectivity.from_file()
conn.speed = np.array([np.inf])         # no delays: one initial state is enough
conn.configure()
start = np.random.default_rng(0).uniform(
    -0.1, 0.1, size=(1, modal.nvar, conn.number_of_regions, modal.number_of_modes))

period = 1000.0 / 1024
eeg = monitors.EEG.from_file(period=period)
eeg.obsnoise = None
modal_sim = simulator.Simulator(
    connectivity=conn, model=modal,
    integrator=integrators.HeunDeterministic(dt=period / 16),
    monitors=(monitors.TemporalAverage(period=period), eeg),
    initial_conditions=start,
)
modal_sim.configure()
(_, regions), (_, sensors) = modal_sim.run(simulation_length=20.0)

print(f"modes per node: {modal.number_of_modes}, variables of interest: {modal.variables_of_interest}")
print(f"TemporalAverage: {regions.shape}   (time, variable, region, mode)")
print(f"EEG:             {sensors.shape}   (time, variable, sensor, 1)")
```

## Time stamps

The time vector belongs to the data and should be used as it is. Three
details matter when aligning outputs:

- **The first sample is not at $t=0$.** The simulator records after each
  integration step, starting at step 1, so `Raw` starts at one `dt`.
- **Averaging monitors stamp the middle of their window.** `TemporalAverage`
  and the EEG, MEG and iEEG monitors give each average the time
  $(n - k/2)\,dt$, where $n$ is the step that closes the window and $k$ the
  number of steps in it. `SubSample`, `SpatialAverage`, `GlobalAverage` and
  `Bold` use the time of the closing step.
- **The clock continues between calls.** Calling the simulator again resumes
  from its current state, history and step count.

The cell below continues the run above. `sim(...)` returns a generator that yields, after each integration
step, a list with an entry per monitor: `None` if that monitor has nothing to
report yet, otherwise a `(time, sample)` pair. `run()` only collects these
lists.

```{code-cell} ipython3
names = [type(m).__name__[:10] for m in sim.monitors]
print("step  " + "  ".join(f"{n:>10}" for n in names))
for step, output in enumerate(sim(simulation_length=1.0), start=1):
    stamps = ["—" if entry is None else f"{entry[0]:.1f}" for entry in output]
    print(f"{step:4d}  " + "  ".join(f"{s:>10}" for s in stamps))
```

The continuation picks up at 100.1 ms. The 1 ms average of the window
(100, 101] ms becomes available at the step that closes it, stamped 100.5 ms,
while `SubSample` reports 101.0 ms.

## Memory

The arrays are dense double-precision NumPy arrays, so a recording needs
$8 \times n_t \times n_{\text{var}} \times n_{\text{space}} \times n_{\text{mode}}$
bytes:

```{code-cell} ipython3
time, data = results[0]
print(f"Raw recording above: {data.nbytes:,} bytes = 8 × {' × '.join(map(str, data.shape))}")

per_sample = 8 * 1 * 76 * 1                 # one variable, 76 regions, one mode
steps = int(10 * 60e3 / 0.1)                # 10 minutes at dt = 0.1 ms
print(f"10 min of one variable at every step: {steps:,} samples, "
      f"{steps * per_sample / 2**30:.1f} GiB")
print(f"the same run as 1 ms averages:        {steps // 10:,} samples, "
      f"{steps // 10 * per_sample / 2**30:.2f} GiB")
```

For long runs, record at the rate the analysis needs, or iterate over the
generator and reduce or save each sample as it arrives.

(timeseries-datatypes)=
## TimeSeries datatypes

The arrays carry no labels or units. TVB's `TimeSeries` datatypes add them.
They are the input format of the analyzers in `tvb.analyzers` and of the
interactive viewers, and the form in which the TVB web interface stores time
series in its H5 files. The monitors know which subclass suits their output:

| monitor output | datatype | `labels_ordering` |
|---|---|---|
| regions | `TimeSeriesRegion` | Time, State Variable, Region, Mode |
| surface vertices | `TimeSeriesSurface` | Time, State Variable, Vertex, Mode |
| EEG / MEG / iEEG sensors | `TimeSeriesEEG`, `TimeSeriesMEG`, `TimeSeriesSEEG` | Time, SV, *sensor type*, Mode |
| `GlobalAverage`, custom `SpatialAverage` masks | `TimeSeries` | Time, State Variable, Space, Mode |

`monitor.create_time_series(...)` returns an instance of the right subclass,
without data. To fill one by hand, pass the data, the time vector, the sampling
period with its unit, and the labels of the variable and space axes:

```{code-cell} ipython3
from tvb.datatypes import time_series

time, data = results[1]
tsr = time_series.TimeSeriesRegion(
    title="Generic2dOscillator, 1 ms averages",
    data=data,
    time=time,
    connectivity=sim.connectivity,
    sample_period=float(np.diff(time)[0]),
    sample_period_unit="ms",
    labels_dimensions={
        "State Variable": list(model.variables_of_interest),
        "Region": list(sim.connectivity.region_labels),
    },
)
tsr.configure()

info = tsr.summary_info()
for key in ("Time-series type", "Dimensions", "Sample period", "Time units", "Length"):
    print(f"{key:<17} {info[key]}")
print(f"{'Sample rate':<17} {tsr.sample_rate:.0f} Hz")

w = tsr.get_state_variable("W")
region = list(tsr.space_labels).index("rV1")
print(f"\nW only: {w.shape}; rV1, first three samples: {np.round(w.data[:3, 0, region, 0], 3)}")
```

A few fields deserve care:

- **`sample_period` and `sample_period_unit`.** Together they give
  `sample_rate` in Hz, which some analyzers use. The unit defaults to
  `"ms"`, which matches the simulator. Take the period from the time vector,
  not from `monitor.period`
  ([Timescales](timescales.md#sampling-and-the-integration-step)).
- **`labels_dimensions`.** Keys must match the names in `labels_ordering`.
  With them, `get_state_variable("W")` and attribute access such as `tsr.W`
  return a reduced copy. To select regions, look up their positions in
  `tsr.space_labels` and index `tsr.data`, as above.
- **`time`.** Optional for the datatype, but some analyzers read it, so store
  it.

## From arrays to analysis

For most work the arrays are enough: they slice, average and plot directly.
The `TimeSeries` wrapper pays off when a tool needs to know the sampling rate
or the labels. The Fourier analyzer is a minimal example. It splits the
series into segments of a given length, in the series' own time unit, and
returns a `FourierSpectrum` with one more axis for the segments:

```{code-cell} ipython3
from tvb.analyzers import fft

spectrum = fft.compute_fast_fourier_transform(
    tsr, segment_length=20.0, window_function=None, detrend=True)
print(f"spectrum: {spectrum.array_data.shape}  (frequency, variable, region, mode, segment)")
print(f"average power over segments: {spectrum.average_power.shape}")
print(f"frequency axis: {spectrum.frequency[0]} … {spectrum.frequency[-1]} per ms")
```

The frequencies come out in cycles per unit of `sample_period`. With
millisecond samples that is kHz: the step of 0.05 is 50 Hz, the inverse of
the 20 ms segments, and the last value is the 500 Hz Nyquist frequency of
1 ms sampling. Multiply by 1000 for Hz.

Other analyzers in `tvb.analyzers` compute coherence, principal and
independent components, wavelet transforms and synchrony and metastability
metrics. The Balloon–Windkessel analyzer turns recorded neural activity into
BOLD ([States and observables](states-observables.md#bold)). The
long-recording viewer is shown in
[exploring longer time series](../../demos/exploring_longer_time_series.ipynb),
and the export to TVB's H5 format in
[generating a TimeSeries H5 file](../../demos/generate_ts_h5_from_library.ipynb).
Worked analyses are in [power spectra](../../demos/analyze_power_spectra.ipynb)
and [region correlation coefficients](../../demos/analyze_region_corrcoef.ipynb).
