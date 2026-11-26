---
kernelspec:
  name: python3
  display_name: Python 3
  language: python
bibliography:
  - ../references.bib
---

# How-to: Simulate the Hopf whole-brain model

:::{tip} Run interactively
Follow this recipe interactively in your browser with zero installation:
- **[Open in JupyterLite Lab](/lite/lab/index.html?path=howtos/hopf-whole-brain-model.ipynb)**
- **[Download Notebook](/notebooks/howtos/hopf-whole-brain-model.ipynb)**
:::

**Goal:** *simulate resting-state "BOLD" signals with the whole-brain Hopf
model of Deco et al. [@deco2017] at its best homogeneous working point
($a = 0$, $G = 2.85$), with diffusive coupling, noise of standard deviation
$\beta = 0.02$ and sampling at the scanner TR, keeping the units consistent
throughout.*

You will need foundational familiarity with running basic simulations (see
[First Simulation](../tutorials/first-simulation.md)). For the model's
equations and parameters, see the
[SupHopf model card](../reference/model-cards/suphopf.md); for why the coupling
function matters, see
[bifurcation analysis](../explanation/bifurcation-analysis.md#coupling-and-network-rest).

---

## Prerequisites

- TVB `3.0+` with `tvb-data`, which provides the 68-region connectome.
- **Units:** Deco et al. use intrinsic frequencies of 0.04–0.07 Hz, so this
  recipe measures time in **seconds**: `dt`, the monitor period and the
  simulation length are all in s.

```{code-cell} ipython3
%matplotlib inline
import numpy as np
import matplotlib.pyplot as plt

from tvb.simulator.lab import connectivity, models, integrators, coupling, monitors, noise
from tvb.simulator import simulator
```

## Step 1: Prepare the connectome

Deco et al. used DTI connectomes of their own participants, which are not
part of TVB; the 68-region connectome shipped with `tvb-data` stands in for
them here. As in the paper, remove self-connections and scale the weights to
a maximum of 0.2. Their equations have no conduction delays, so set the speed
to infinity.

```{code-cell} ipython3
conn = connectivity.Connectivity.from_file("connectivity_68.zip")
np.fill_diagonal(conn.weights, 0.0)
conn.weights = 0.2 * conn.weights / conn.weights.max()
conn.speed = np.array([np.inf])
conn.configure()
n = conn.number_of_regions
print(f"{n} regions, max weight {conn.weights.max():.2f}")
```

## Step 2: Configure the nodes and the coupling

Place every node at the bifurcation, $a = 0$. Deco et al. took each region's
intrinsic frequency from its BOLD spectrum; without data, use 0.05 Hz for all
regions, $\omega = 2\pi \times 0.05$ rad/s. Use `Difference` coupling,
$G\sum_j w_{ij}(x_j - x_i)$, with $G = 2.85$, the value of their homogeneous
optimum.

```{code-cell} ipython3
hopf = models.SupHopf(a=np.zeros(n), omega=2 * np.pi * 0.05 * np.ones(n))
diff = coupling.Difference(a=np.array([2.85]))
```

## Step 3: Set the noise in TVB's convention

TVB's `Additive` noise adds $\sqrt{2D}\,dW$ for `nsig` $= D$. Noise of
standard deviation $\beta$ therefore needs `nsig` $= \beta^2/2$, not $\beta$.
Fixing `noise_seed` makes the run, and the random initial conditions,
reproducible.

```{code-cell} ipython3
beta = 0.02
heun = integrators.HeunStochastic(
    dt=0.01, noise=noise.Additive(nsig=np.array([beta ** 2 / 2] * 2), noise_seed=42))
```

## Step 4: Sample at the TR and simulate

`TemporalAverage` with a period of 1.94 s, the TR of the data Deco et al.
fitted, turns $x$ into one "BOLD" sample per volume. Run 10 minutes and drop
the first minute, during which the random initial state relaxes.

```{code-cell} ipython3
sim = simulator.Simulator(
    model=hopf, connectivity=conn, coupling=diff, integrator=heun,
    monitors=(monitors.TemporalAverage(period=1.94),),
    simulation_length=600.0,
).configure()
(t, d), = sim.run()

keep = t >= 60.0
bold = d[keep, 0, :, 0]
fc = np.corrcoef(bold.T)
off_diag = fc[~np.eye(n, dtype=bool)]
print(f"{bold.shape[0]} volumes x {n} regions; mean FC {off_diag.mean():.2f}")

fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.5))
ax1.plot(t[keep], bold[:, ::10], lw=0.8)
ax1.set(xlabel="time [s]", ylabel="$x$", title="every 10th region")
im = ax2.imshow(fc, vmin=-1, vmax=1, cmap="RdBu_r")
ax2.set_title("simulated FC")
plt.colorbar(im, ax=ax2)
plt.tight_layout()
plt.show()
```

---

## Verification & Edge Cases

- **Validation:** there should be one sample every 1.94 s, and $x$ should
  fluctuate around zero with a standard deviation of about 0.02. The
  simulated FC should resemble the connectome; in this run their off-diagonal
  entries correlate at about 0.4.
- **Mixed units:** a monitor period of `1940` (the TR in ms) with $\omega$ in
  rad/s averages about 97 oscillation cycles into each sample, which leaves
  about 4 % of the signal's standard deviation. Pick one unit and use it for
  `dt`, the period, the simulation length and $\omega$.
- **Noise level:** setting `nsig = beta` instead of `beta**2 / 2` makes the
  noise ten times stronger; `nsig = 2 * sqrt(beta**2 / 2)` makes it about
  twelve times stronger.
- **Coupling function:** with `Difference` coupling, no delays and $a < 0$,
  the network stays at rest apart from noise, for any $G$. `Linear` coupling
  would instead make it oscillate once $G\,\lambda_{max}(W) > -a$.

## Related documentation

- **Reference:** the [SupHopf model card](../reference/model-cards/suphopf.md) lists the equations, parameters and coupling points.
- **Explanation:** [Bifurcation analysis](../explanation/bifurcation-analysis.md#coupling-and-network-rest) explains how the coupling function shapes a network's resting state.
- **Tutorials:** [First Simulation](../tutorials/first-simulation.md) walks through an end-to-end simulation.
