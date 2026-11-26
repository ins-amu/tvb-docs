---
title: Stimulus
kernelspec:
  name: python3
  display_name: Python 3
  language: python
bibliography:
  - ../references.bib
---

# Stimulus

In TVB one can define an external stimulation of any subset of nodes with a specific temporal profile. The main high-level class through which this is achieved is called `StimuliRegion`.

You can use it to represent, for example:

- A constant input applied to one or more regions.
- A brief pulse of input to a particular region.
- A time-varying input applied to several regions with different amplitudes.
- A regional input that is subsequently mapped onto the vertices of a cortical surface.

The central idea is simple: **you define which regions receive the stimulus, how strongly each region is stimulated, and how the stimulus changes over time.**

The stimulus is a prescribed external input. `StimuliRegion` does not itself model the electric field, membrane polarization, or the biophysical effects of electrical stimulation.

## Main ingredients of regional stimulation

A `StimuliRegion` object is defined by three essential ingredients:

| Ingredient | TVB attribute | Meaning |
|---|---|---|
| Brain network | `connectivity` | Which regions exist and their ordering |
| Regional scaling | `weight` | How strongly each region is stimulated |
| Temporal equation | `temporal` | How the stimulus varies over time |

The resulting stimulus for region $i$ at time $t$ is

$$
I_i(t)=w_i T(t)
$$

where $w_i$ is the regional weight and $T(t)$ is the temporal equation.

## Utilization example

```{code-cell} ipython3
:tags: [remove-stderr]

from tvb.simulator.lab import patterns, connectivity, equations, plot_pattern
import numpy as np
import matplotlib.pyplot as plt
```

```{code-cell} ipython3
conn = connectivity.Connectivity.from_file("connectivity_76.zip")
nregions = len(conn.region_labels)               # Number of regions
conn.speed = np.array(np.inf)                    # Set the conduction speed
conn.configure()
```

We can define the spatial profile of the stimulus. For this purpose we create a zero array of weights for the stimulation amplitude and set only the anatomical regions of interest to a non-zero amplitude.

```{code-cell} ipython3
# configure stimulus spatial pattern
weighting = np.zeros((conn.number_of_regions, ))
weighting[[0, 7, 13, 33, 42]] = np.array([2.0 ** -2, 2.0 ** -3, 2.0 ** -4, 2.0 ** -5, 2.0 ** -6])
```

```{code-cell} ipython3
plt.figure(figsize=(10,3))
plt.stem(weighting)
plt.xticks(range(0, conn.number_of_regions), conn.region_labels, fontsize=7, rotation=90);
```

Second, we define the temporal profile. In TVB, this is achieved parametrically to allow for flexibility in other components (e.g. independence on dt of the integration).

```{code-cell} ipython3
# temporal profile
eqn_t = equations.Gaussian()
eqn_t.parameters["midpoint"] = 4000.0 # ms
eqn_t.parameters["sigma"] = 200.0 # ms
eqn_t
```

Putting the regional scaling with the temporal profile together gives us the stimulus object:

```{code-cell} ipython3
stimulus = patterns.StimuliRegion(temporal=eqn_t,
                                  connectivity=conn,
                                  weight=weighting)
```

```{code-cell} ipython3
stimulus
```

```{code-cell} ipython3
stimulus.configure_space()
stimulus.configure_time(np.arange(0., 10e3))
plot_pattern(stimulus)
```

Afterwards the stimulus object can be passed to a `simulator.Simulator` class object as an additional attribute of the stimulation.
