---
kernelspec:
  name: python3
  display_name: Python 3
  language: python
---

# Your first tvb-lite simulation

*Tutorial — a guided first run of the FitzHugh–Nagumo network.*

In this tutorial you run a small **FitzHugh–Nagumo** network simulation using the
numpy-only `tvbl` engine that backs these docs. The same analysis is the single
source of truth behind the [How-to](../howtos/tvbl-inference.md),
[Reference](../reference/model-cards/fitzhugh-nagumo.md) and
[Explanation](../explanation/tvbl-sim-to-inference.md) pages.

```{code-cell} ipython3
:tags: [remove-cell]

import sys, pathlib

# The vendored tvb-lite engine lives in content/_code; make it importable from any page.
_root = pathlib.Path.cwd()
while not (_root / "myst.yml").exists() and _root != _root.parent:
    _root = _root.parent
sys.path.insert(0, str(_root / "content" / "_code"))

import tvbl_docs as td
```

## 1. Run the simulation

One call builds a random delayed connectome and integrates the model:

```{code-cell} ipython3
trace = td.run_sim()
print(f"Trace shape (time, state, node, item): {trace.shape}")
```

## 2. Look at the activity

Each node's activity variable `x(t)` is in `trace[:, 0, :, 0]`:

```{code-cell} ipython3
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(7, 2.5))
ax.plot(trace[:, 0, :, 0], "k", alpha=0.3)
ax.set_xlabel("time (ms)")
ax.set_ylabel("x(t)")
ax.set_title("FitzHugh–Nagumo network activity")
plt.show()
```

You should see a mix of quiescent and oscillating nodes — the network's delayed
coupling is what makes some nodes fire rhythmically. Next, the
[How-to guide](../howtos/tvbl-inference.md) shows how to *infer* the parameters
that produced activity like this.
