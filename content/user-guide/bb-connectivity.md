---
title: Connectivity
bibliography:
  - ../references.bib
---

# Connectivity

The {term}`connectome` is the anatomical scaffold of a TVB simulation. The
dynamics live in the {term}`neural mass model` of each {term}`node`; the
connectome decides which nodes can influence each other, how strongly, and
with what delay.

This page covers three topics. Jump to whichever you need.

- **[What the connectome does in a simulation](#role)**.
- **[How to set up a connectome in your simulation](#setup-guide)**.
- **[API reference](#api-reference)**, with commentary and common pitfalls.

---

(role)=
## What the connectome does in a simulation

The connectome is a mathematical representation of how the individual brain regions are interconnected. It consists of two matrices. One representing connection strengths, and the second one representing the delay (or length, see [tract lengths](#delays) for more details) of those connections. While the individual nodes hold their state, the connectome holds the information on which nodes this state affects and with how much delay.

### Nodes come from a parcellation

A {term}`parcellation` or an **atlas** divides the brain into regions. Each region becomes one
{term}`node` with its own neural mass model, so the number of regions is the
size of the network. TVB places no constraint on how many regions you use.

### Edges come from tractography

The {term}`edges <Edge>` are inferred from {term}`Diffusion-weighted MRI`.
{term}`Tractography` algorithms follow **directional bias** through the volume, tracing candidate pathways called {term}`streamlines <Streamline>`, from one voxel to the next. These streamlines represent white matter bundles.

The endpoints of the streamlines are assigned to parcels. Counting the number of streamlines between region k and region j gives the edge weight, the standard proxy for how strong the connection between them is [@hagmann2008; @schirner2015]. The
streamline path length gives the edge's physical distance, which becomes a
delay once a {term}`conduction speed`[@lemarechal2022] is assumed.

### How the simulator uses the connectome data

The connection weights become the coupling terms. For region $k$, the delayed
activity arriving from the rest of the network is

$$
u_{kj}\,\Gamma\!\left(\Psi_k(t),\,\Psi_j(t-\tau_{kj})\right),
\qquad
\tau_{kj} = \frac{\ell_{kj}}{v},
$$

where $u_{kj}$ is the weight from region $j$ to region $k$, $\ell_{kj}$ is the
**tract length**, $v$ the **conduction speed**, and $\Gamma$ the coupling function, see [coupling](bb-coupling.md).


(object)=
## Description of the Connectivity class

`tvb.datatypes.connectivity.Connectivity` is a collection of arrays, all indexed
by region. $l$ is the number of regions.

For a definitive API reference, see [TODO link api reference].

| Field | Required | Shape | Units | Set by | Notes |
|---|---|---|---|---|---|
| `weights` | yes | $(l, l)$ | arbitrary | you | Expects to be asymmetric by default. Rows are targets. |
| `tract_lengths` | yes | $(l, l)$ | mm | you | Fallback: straight-line distance from `centres`. |
| `speed` | yes | $(1,)$ or $(l, l)$ | mm/ms | you | Default 3.0 if unset. 3.8 recommended by [@lemarechal2022]. If you're not using delays, you may set speed to `float(inf)` |
| `delays` | - | $(l, l)$ | ms | derived | `tract_lengths / speed`, in `configure()`. |
| `idelays` | - | $(l, l)$ int | integration steps | `set_idelays(dt)` | What the solver actually uses. |
| `centres` | yes | $(l, 3)$ | mm | you | Required for surfaces and forward models. Can be approximated by the `centres_*()` methods. |
| `region_labels` | yes | $(l,)$ str | - | you | Fallback: `create_region_labels()`, which generates `region_000`, `region_001`, … |
| `cortical` | no | $(l,)$ bool | - | you | Cortex or not. |
| `hemispheres` | no | $(l,)$ bool | - | you | `True' corresponds to the right hemisphere. Fallback: label prefix. |
| `orientations` | no | $(l, 3)$ | unit vector | you | Zeros where unknown. |
| `areas` | no | $(l,)$ | mm² | you | Surface area per region. |
| `undirected` | - | bool | - | derived | False by default, set to True if weights are a symetrical matrix |
| `number_of_regions` | - | int | - | derived | $l$, from the shape of `weights`. |
| `number_of_connections` | - | int | - | derived | Non-zero entries. Counts both directions. |
| `parent_connectivity` | no | str | - | lesion tools | Source of an edited connectome. |
| `saved_selection` | no | list of int | - | lesion tools | Regions kept. |

Only `weights` lacks any form of fallback. All other parameters either have a fallback, a default value, or are derived. A fallback refers to an alternative method for estimating the data when it is missing (e.g., calling `centres_spherical()` instead of loading `centres.txt`). A default, on the other hand, is a predefined value used when no assignment is provided.


(weights-section)=
### Weights

`weights[k, j]` is the strength of the projection **from region $j$ onto region
$k$**. Rows index targets, columns index sources.

:::{warning}
This is the **inverse** of the convention used by the Brain Connectivity Toolbox
and most graph-theory code. A matrix exported from BCT and loaded without a
transpose will couple the network backwards. It will run, produce plausible
spectra, and be wrong. Transpose on import and check one known asymmetric edge
by hand.
:::

The matrix is directed by default unless it happens to be symmetric. `configure()` sets
`undirected` to `True` when it finds an exactly symmetric matrix.

#### The diagonal

Self-connections live on the diagonal, and the library does not remove these by default. `transform_remove_self_connections()` returns a copy with
the diagonal zeroed.

#### Normalization

`scaled_weights(mode)` returns a scaled copy; it does not modify `self`.

| `mode` | Divisor | Result |
|---|---|---|
| `'tract'` | divides the matrix by the largest weight value | weights will be in range 0-1 |
| `'region'` | largest absolute row sum (in-strength) | row sums will be in range 0-1 |
| `'none'`, `None` | 1.0 | no change to the original weights |

If these options are insufficient, you may wish to normalize weights matrix outside of the TVB ecosystem. For example, in a population study you may wish to pick a single normalization constant across all subjects an normalize without the use of the `scaled_weights` method. Log normalization is also an option. Neither one of these two methods are provided by TVB.

While normalization should be viewed as part of preprocessing, coupling functions can have similar effects on the weights, see **global coupling**

The [coupling page](bb-coupling.md) covers the gain side.

---
(delays)=
### Tract lengths, conduction speed and delays

`tract_lengths[k, j]` is the physical length of the fibre pathway between
regions $k$ and $j$, in millimetres. The matrix has the same orientation as weights,
so rows are targets. Tractography cannot tell direction, so
these matrices usually are symmetric. However, nothing in TVB enforces symmetricity.

If you supply `centres` but not `tract_lengths`, `configure()` fills them with
Euclidean distances between region centres. That is a straight-line proxy, not recommended.

`speed` is one number for the whole network, or a full matrix if you want
heterogeneous conduction speeds. Its unit is mm/ms, and the default is 3.0. A speed of 3.8 mm/ms is recommended, derived from an atlas of axonal and synaptic delays estimated from cortico-cortical evoked potentials [@lemarechal2022].

(metadata)=
### Centres, labels, hemispheres, cortical flag

`centres` is $(l, 3)$ in millimetres, in whatever coordinate space the atlas
uses. It is optional for a bare regional simulation, but required if geometry matters: fallback for tract lengths, {term}`lead field` projections for EEG/MEG, different visualisations. Usually you won't need it.

`region_labels` are labels for the individual regions. Their ordering is the same as every other attribute of connectivity (weights, tract lengths, centres...)

`hemispheres` is a boolean vector with `True` meaning right.
If unset, `configure()` infers it from the first letter of each
label (`L/R`), and falls back to "second half of the indices
is right" when labels carry no prefix.

`cortical` marks which regions are cortex. If you wish to add
subcortical structures, you need to set these labels yourself. 
`subcortical_indices` is derived from it. `areas` and 
`orientations` are optional and may be zeros where unknown; 
zeros are the documented convention for "not measured", not a
physical value.

`number_of_regions` and `number_of_connections` are both computed in
`configure()`. Note that `number_of_connections` counts non-zero entries, so a
symmetric matrix counts every edge twice.

---

#### How delays are computed

$$
\tau_{kj} = \frac{\ell_{kj}}{v_{kj}}
\quad\text{(ms)},
\qquad
\texttt{idelays}_{kj} = \operatorname{round}\!\left(\frac{\tau_{kj}}{\Delta t}\right).
$$

`configure()` computes `delays` unconditionally as `tract_lengths / speed`, so
changing `speed` takes effect on the next `configure()`. `set_idelays(dt)` then
converts those into whole integration steps, and that integer matrix is what the
solver indexes into its **history** buffer.

:::{warning}
**Delays are quantised, and $\Delta t$ sets the resolution.**

A delay shorter than half a step rounds to zero. That tract is then
instantaneous, not short. Raising $\Delta t$ to make a run faster therefore
coarsens the whole delay structure. If a result depends on short-range timing, check
$\tau_{\min} / \Delta t$.
:::

The **history** buffer scales with $\max(\tau) / \Delta t$. Long tracts and small
steps both cost memory, and this is usually the limit on how long a delay a
simulation can carry.

#### Causality at the two scales

:::{caution}
**replaced in TVB 3.0.** This subsection documents how TVB used to treat
causality across scales. It is kept for reference only: TVB 3.0 supersedes it.
:::

Short-range connections on a cortical surface are treated as instantaneous within one integration step. Their
influence spreads one step at a time. See [local connectivity
page](bb-local-connectivity.md) for more information.

---

(setup-guide)=
## Setup guide

### 1. Obtain a connectome

The shortest path is the default file:

```python
from tvb.simulator.lab import connectivity

conn = connectivity.Connectivity.from_file("my_connectivity.zip")
```

A zip must contain 
- `weights.txt` 
- `tract_lengths.txt`
- `centres.txt` first column holds the region labels and the remaining three columns are coordinates.

Optional files: `average_orientations.txt`, `cortical.txt`, `hemispheres.txt`, `areas.txt`.

Alternatively, use you own arrays and assign the fields directly:

```python
conn = connectivity.Connectivity()
conn.weights = weights          # (l, l), rows are targets
conn.tract_lengths = lengths    # (l, l), mm
conn.centres = centres          # (l, 3), mm
conn.region_labels = labels     # (l,), strings
conn.configure()
```

Bring-your-own-data specifics - validation, units, hemisphere handling - are in
[using your own connectivity](../demos/using_your_own_connectivity.ipynb).

### 2. Set the conduction speed

```python
conn.speed = np.array([3.0])          # mm/ms, whole network. This is the default, here explicitly for completenes
# OR
conn.speed = np.inf                   # effectively no delays
```

### 4. Attach it to a simulation

```python
from tvb.simulator.lab import coupling, models, integrators, monitors, simulator

sim = simulator.Simulator(
    connectivity=conn,
    coupling=coupling.Linear(a=np.array([0.004])),
    model=models.JansenRit(),
    integrator=integrators.HeunDeterministic(dt=0.1),
    monitors=[monitors.Raw()],
)
sim.configure()
results = sim.run()
```

Do not call `configure()` or `set_idelays()` yourself. `Simulator.configure()` does it for you.

---

(api-reference)=
## API reference

:::{note}
**To do:** link to the generated API reference for
`tvb.datatypes.connectivity.Connectivity`. Until it exists, this section carries
the guidance.
:::
