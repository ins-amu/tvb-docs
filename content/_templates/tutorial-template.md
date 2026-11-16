---
kernelspec:
  name: python3
  display_name: Python 3
  language: python
bibliography:
  - ../references.bib
---

# <Tutorial Title>

:::{tip} Run interactively
Run this tutorial interactively in your browser with zero installation:
- **[Open in JupyterLite Lab](/lite/lab/index.html?path=tutorials/<your-slug>.ipynb)**
- **[Download Notebook](/notebooks/tutorials/<your-slug>.ipynb)**
:::

*<1-sentence orientation explaining what the learner will build, run, and observe by following this hands-on tutorial.>*

## Introduction

In this tutorial, you will walk step-by-step through setting up, configuring, and executing `<Topic / Workflow>`.
By the end of this guide, you will have generated `<Expected Output / Figure>` and verified that `<Key Result>` matches the expected theoretical behavior.

## Setup and imports

All tutorials execute at build time and inside the browser-based JupyterLite kernel. Ensure your dependencies are imported cleanly:

```{code-cell} ipython3
%matplotlib inline
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt

# TVB core modules
from tvb.simulator.lab import connectivity, coupling, integrators, models, monitors
from tvb.simulator import simulator
```

## Step 1: Prepare the data and connectome

Describe the input dataset, structural connectivity, or configuration parameters. Always prefer deterministic, minimal datasets that run in seconds:

```{code-cell} ipython3
# Load a lightweight structural connectivity or construct a synthetic network
# Use data/connectivity_76.zip or load via TVB connectivity module
conn = connectivity.Connectivity.from_file()
conn.speed = np.array([4.0])  # conduction speed in mm/ms
conn.configure()

print(f"Loaded connectome with {len(conn.region_labels)} regions.")
```

## Step 2: Configure model dynamics and integration

Set up the neural mass model, coupling function, and numerical integration scheme.

```{code-cell} ipython3
# Instantiate the neural mass model
model = models.Generic2dOscillator(a=np.array([0.5]))

# Configure network coupling
coup = coupling.Linear(a=np.array([0.01]))

# Choose a deterministic or stochastic integrator
# Use small simulation lengths for build verification
integrator = integrators.HeunDeterministic(dt=0.1)

print(f"Configured {model.__class__.__name__} with {integrator.__class__.__name__}")
```

## Step 3: Configure monitors and run simulation

Attach monitors (e.g. `Raw`, `TemporalAverage`, `BOLD`) and advance the simulation:

```{code-cell} ipython3
mon_raw = monitors.Raw()
mon_tavg = monitors.TemporalAverage(period=1.0)

sim = simulator.Simulator(
    model=model,
    connectivity=conn,
    coupling=coup,
    integrator=integrator,
    monitors=(mon_raw, mon_tavg),
    simulation_length=50.0  # Keep <= 100 ms for fast deterministic builds
)
sim.configure()

print("Running simulation...")
(time_raw, data_raw), (time_tavg, data_tavg) = sim.run()
print(f"Completed simulation: {data_raw.shape[0]} raw time steps recorded.")
```

## Step 4: Visualize and verify results

Plot the resulting time series or trajectories. Check the output against the expected physical or dynamical regime.

```{code-cell} ipython3
fig, ax = plt.subplots(figsize=(10, 4))
ax.plot(time_tavg, data_tavg[:, 0, :5, 0])
ax.set_xlabel("Time (ms)")
ax.set_ylabel("State Variable Amplitude")
ax.set_title("Temporal Average Signal across Regions")
ax.grid(True, linestyle="--", alpha=0.6)
plt.tight_layout()
plt.show()
```

### Expected output check
Verify that:
1. Signal oscillates stably around `<expected equilibrium or baseline>`.
2. Phase relationships or amplitude values reflect the specified coupling strength.
3. No `NaN` or divergent values appear in the traces.

## Next steps

Now that you have completed this tutorial, explore the related quadrants:
- **How-to recipes**: See [How-to guides](../howtos/index.md) to customize stimuli, adapt connectivity matrices, or configure different monitors.
- **Reference details**: Check [Model Cards](../reference/model-cards/index.md) for full mathematical definitions and parameter tables.
- **Deeper theory**: Read [Dynamical Systems Explanation](../explanation/dynamical-systems-theory.md) to understand bifurcation regimes and phase-space geometry.
