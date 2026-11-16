---
kernelspec:
  name: python3
  display_name: Python 3
  language: python
bibliography:
  - ../references.bib
---

# How-to: <Verb a Specific Task, e.g., Load a Custom Connectome Matrix>

:::{tip} Run interactively
Follow this recipe interactively in your browser with zero installation:
- **[Open in JupyterLite Lab](/lite/lab/index.html?path=howtos/<your-slug>.ipynb)**
- **[Download Notebook](/notebooks/howtos/<your-slug>.ipynb)**
:::

**Goal:** *<State the exact, practical goal in 1 sentence: what specific problem does this recipe solve, for whom, and what is the required outcome?>*

You will need foundational familiarity with running basic simulations (see [First Simulation](../tutorials/first-simulation.md)). For underlying dynamical principles, see [Explanation](../explanation/index.md); for parameter specs, see [Reference](../reference/index.md).

---

## Prerequisites

Briefly state assumptions, input file formats, or required variables:
- Input data requirements (e.g. `weights.txt`, `tract_lengths.txt`, or NumPy arrays).
- TVB version `3.0+` or `tvbl`.

```{code-cell} ipython3
%matplotlib inline
import numpy as np
import matplotlib.pyplot as plt

from tvb.simulator.lab import connectivity, models, integrators, coupling
from tvb.simulator import simulator
```

## Step 1: <First action step, e.g. Prepare or format the inputs>

Explain what this step does and why this configuration is chosen.

```{code-cell} ipython3
# Step 1 implementation
# Keep code modular, reproducible, and minimal
n_regions = 8
synthetic_weights = np.random.RandomState(42).uniform(0, 1, size=(n_regions, n_regions))
np.fill_diagonal(synthetic_weights, 0.0)

print(f"Prepared connectivity weight matrix with shape {synthetic_weights.shape}")
```

## Step 2: <Second action step, e.g. Instantiate and configure the TVB object>

Explain the parameters and options available.

```{code-cell} ipython3
# Step 2 implementation
custom_conn = connectivity.Connectivity(
    weights=synthetic_weights,
    tract_lengths=np.ones_like(synthetic_weights) * 20.0,
    region_labels=np.array([f"ROI_{i}" for i in range(n_regions)]),
    speed=np.array([4.0])
)
custom_conn.configure()

print(f"Successfully configured custom connectivity with {len(custom_conn.region_labels)} nodes.")
```

## Step 3: <Third action step, e.g. Execute and inspect output>

Demonstrate how to verify that the task completed successfully.

```{code-cell} ipython3
# Step 3 implementation & verification
fig, ax = plt.subplots(figsize=(5, 4))
im = ax.imshow(custom_conn.weights, cmap="viridis")
ax.set_title("Configured Weight Matrix")
plt.colorbar(im, ax=ax)
plt.tight_layout()
plt.show()
```

---

## Verification & Edge Cases

- **Validation:** What invariant or shape check confirms success?
- **Common pitfalls:** Mention 1–2 frequent mistakes (e.g., asymmetrical matrices, negative delays, zero speeds).

## Related documentation

- **Reference:** See the API datasheet in [Reference](../reference/index.md) for full class signatures and parameter types.
- **Explanation:** Read [Connectome & Propagation](../explanation/connectome.md) to understand signal transmission delays and matrix normalizations.
- **Tutorials:** Follow [First Simulation](../tutorials/first-simulation.md) for an end-to-end simulation pipeline.
