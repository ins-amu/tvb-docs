---
kernelspec:
  name: python3
  display_name: Python 3
  language: python
bibliography:
  - ../references.bib
---

# How-to: Keep a Jansen–Rit network in the alpha regime

:::{tip} Run interactively
Follow this recipe interactively in your browser with zero installation:
- **[Open in JupyterLite Lab](/lite/lab/index.html?path=howtos/jansen-rit-alpha-network.ipynb)**
- **[Download Notebook](/notebooks/howtos/jansen-rit-alpha-network.ipynb)**
:::

**Goal:** *configure a whole-brain Jansen–Rit network so that every region
receives an input within 120–320 pulses/s, the range Jansen & Rit used to
obtain alpha activity [@jansenRit1995], and check that the network produces
it.*

You will need foundational familiarity with running basic simulations (see
[First Simulation](../tutorials/first-simulation.md)). For the model's
equations and parameters, see the
[Jansen–Rit model card](../reference/model-cards/jansen-rit.md); for why the
input window matters, see
[bifurcation analysis](../explanation/bifurcation-analysis.md#jansen-rit-diagram).

---

## Prerequisites

- TVB `3.0+` with `tvb-data`, which provides the default 76-region connectome.
- Time in TVB is in ms, so input rates are in ms⁻¹: `0.12` means 120 pulses/s.

```{code-cell} ipython3
%matplotlib inline
import numpy as np
import matplotlib.pyplot as plt

from tvb.simulator.lab import connectivity, models, integrators, coupling, monitors, noise
from tvb.simulator import simulator
```

## Step 1: Configure the column as published

Use the sigmoid threshold of the original paper, `v0 = 6` mV. With the TVB
default of 5.52 mV, a column at the default input oscillates at about 7 Hz
rather than in the alpha band. Set the constant input to the lower end of the
paper's range, `p_min`; the network will add the rest.

```{code-cell} ipython3
jrm = models.JansenRit(v0=np.array([6.0]))
jrm.mu = jrm.p_min.copy()

print(f"constant input: {jrm.mu[0] * 1e3:.0f} pulses/s, "
      f"target window: {jrm.p_min[0] * 1e3:.0f}-{jrm.p_max[0] * 1e3:.0f} pulses/s")
```

## Step 2: Bound the network input

`SigmoidalJansenRit` sends each region at most
$a_c\,c_{max}\sum_j w_{ij}$: the coupling gain times the maximum firing rate
times the region's in-strength. Normalise the weights so that the largest
in-strength is 1, and choose the gain so that this maximum is
$p_{max} - p_{min}$.

```{code-cell} ipython3
conn = connectivity.Connectivity.from_file()
conn.weights = conn.weights / conn.weights.sum(axis=1).max()
conn.configure()

cpl = coupling.SigmoidalJansenRit()
cpl.a = (jrm.p_max - jrm.p_min) / cpl.cmax

max_input = (jrm.mu + cpl.a * cpl.cmax * conn.weights.sum(axis=1)) * 1e3
print(f"largest possible input per region: {max_input.min():.0f}-{max_input.max():.0f} pulses/s")
```

## Step 3: Add the input fluctuations where the input enters

Jansen & Rit's input is noisy. The input enters the equation of `y4` with
gain $A\,a$, so put the noise there. TVB's `Additive` noise has amplitude
$\sqrt{2D}$ for `nsig` $= D$, so the value below adds white noise to the input
with an amplitude of $(p_{max} - p_{min})/2$, the scaling used in the TVB demo.
Fixing `noise_seed` makes the run, and the random initial conditions,
reproducible.

```{code-cell} ipython3
nsig = np.zeros(6)
nsig[4] = ((jrm.a * jrm.A * (jrm.p_max - jrm.p_min) / 2) ** 2 / 2).item()

heun = integrators.HeunStochastic(dt=2 ** -4, noise=noise.Additive(nsig=nsig, noise_seed=42))
```

## Step 4: Simulate and check the rhythm

Run 2 s, discard the first second (a transient from the random initial
conditions, which TVB draws from the wide `state_variable_range`), and look at
$y_1 - y_2$, the model's EEG-like output.

```{code-cell} ipython3
sim = simulator.Simulator(
    model=jrm, connectivity=conn, coupling=cpl, integrator=heun,
    monitors=(monitors.TemporalAverage(period=2 ** -2),),
    simulation_length=2000.0,
).configure()
# The random initial state is far from rest, so the sigmoid's exp() overflows
# for the first few ms; it then saturates correctly at 0, so the warning is moot.
with np.errstate(over="ignore"):
    (t, d), = sim.run()

keep = t >= 1000.0
v = d[keep, 1, :, 0] - d[keep, 2, :, 0]            # y1 - y2, one column per region

freqs = np.fft.rfftfreq(v.shape[0], d=2 ** -2 * 1e-3)
power = np.abs(np.fft.rfft(v - v.mean(axis=0), axis=0)) ** 2
peak = freqs[1:][np.argmax(power[1:], axis=0)]
print(f"regions with an 8-13 Hz spectral peak: {np.mean((peak >= 8) & (peak <= 13)):.0%}")
print(f"median peak frequency: {np.median(peak):.1f} Hz")
print(f"median mean of y1 - y2: {np.median(v.mean(axis=0)):.1f} mV")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.5))
ax1.plot(t[keep], v[:, ::8], lw=0.8)
ax1.set(xlabel="time [ms]", ylabel="$y_1 - y_2$ [mV]", title="every 8th region")
ax2.semilogy(freqs[1:], power[1:].mean(axis=1))
ax2.set(xlabel="frequency [Hz]", ylabel="mean power", xlim=(0, 40), title="spectrum")
plt.tight_layout()
plt.show()
```

---

## Verification & Edge Cases

- **Validation:** most regions should have their spectral peak in the alpha
  band, and the mean of $y_1 - y_2$ should stay in single-digit mV. Regions
  with little or no incoming connectivity receive barely more than `p_min`,
  120 pulses/s. That is inside the 113.58–137.38 pulses/s window where slow
  spike-like cycles coexist with alpha, so these regions can show slower
  activity.
- **Unnormalised weights:** `SigmoidalJansenRit(a=10)` on the raw default
  connectome can deliver up to 3550 pulses/s. Most regions then receive more
  than 315.70 pulses/s, beyond the upper Hopf bifurcation, and settle at
  constant potentials of tens of mV.
- **Noise on the wrong variable:** with the same noise on `y3`, no region
  keeps its alpha peak. The noise is scaled for the input, which only enters
  the `y4` equation.
- **Stimuli:** a TVB stimulus is applied to `model.stvar`, which defaults to
  `y1` and `y2`. To add an input pulse instead, set `jrm.stvar = np.array([4])`
  and scale the pulse by $A\,a$.

## Related documentation

- **Reference:** the [Jansen–Rit model card](../reference/model-cards/jansen-rit.md) lists the equations, parameters and coupling points.
- **Explanation:** [Bifurcation analysis](../explanation/bifurcation-analysis.md#jansen-rit-diagram) explains why inputs in the 120–320 pulses/s range give alpha.
- **Tutorials:** [First Simulation](../tutorials/first-simulation.md) walks through an end-to-end simulation.
