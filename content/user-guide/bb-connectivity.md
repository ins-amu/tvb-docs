---
title: Connectivity
bibliography:
  - ../references.bib
---

# Connectivity

The {term}`connectome` is the anatomical scaffold of a TVB simulation. The
dynamics live in the {term}`neural mass model` at each {term}`node`; the
connectome decides which nodes can influence each other, how strongly, and
with what delay.

This page covers three topics. Jump to whichever you need.

- **[What the connectome does in a simulation](#role)**.
- **[How to set up a connectome in your simulation](#setup-guide)**.
- **[API reference](#api-reference)**, with commentary and common pitfalls.

---

(role)=
## What the connectome does in a simulation

The connectome is a mathematical representation of how the individual brain regions are interconnected. It consist of two matrices. One representing connection strengths, and the second one representing the delay (or length) of those connections. While the individual **nodes** hold their state, the connectome holds the information on which nodes and when this state affects.

### Nodes come from a parcellation

A {term}`parcellation` or an **atlas** divides the brain into regions. Each region becomes one
{term}`node` with its own neural mass model, so the number of regions is the
size of the network. TVB places no constraint on how many regions you use.

### Edges come from tractography

The {term}`edges <Edge>` are inferred from {term}`Diffusion-weighted MRI`.
{term}`Tractography` algorithms follow directional bias through the volume, tracing candidate pathways called {term}`streamlines <Streamline>`, from one voxel to the next.

Streamlines are then assigned to the parcels their endpoints. Counting
them gives the edge weight: the number of streamlines between region $k$ and
region $j$ is the standard proxy for how much wiring connects them [TODO cite]. The
streamline path length gives the edge's physical distance, which becomes a
delay once a {term}`conduction speed`[TODO cite] is assumed.

#### Notes on tractography

Raw values of streamline counts are generally not useful, as they are strongly affected by acquisition methods and tractography settings. Normalization of  a connectome fixes this, but it's a complex task. For one subject you might wish to normalize to the largest value, or for a population study you may wish to pick a single normalization constant across all subjects. Log normalization is also an option.

Direction is not measured. Region-level tractography gives an undirected graph. The connectome says two regions are wired together, not which one drives which.

### What the simulator reads out of it [TODO RENAME]

The connection weights become the coupling term. For region $k$, the delayed
activity arriving from the rest of the network is

$$
u_{kj}\,\Gamma\!\left(\Psi_k(t),\,\Psi_j(t-\tau_{kj})\right),
\qquad
\tau_{kj} = \frac{\ell_{kj}}{v},
$$

where $u_{kj}$ is the weight from region $j$ to region $k$, $\ell_{kj}$ is the
**tract length**, $v$ the **conduction speed**, and $\Gamma$ the coupling function, see [coupling](bb-coupling.md).


(object)=
## What the object holds [TODO RENAME]

`tvb.datatypes.connectivity.Connectivity` is a collection of arrays, all indexed
by region. $l$ is the number of regions.

For a definitive API reference, see [TODO link api reference].

| Field | Required | Shape | Units | Set by | Notes |
|---|---|---|---|---|---|
| `weights` | yes | $(l, l)$ | arbitrary | you | Directed by default. Rows are targets. |
| `tract_lengths` | yes | $(l, l)$ | mm | you | Fallback: straight-line distance from `centres`. |
| `speed` | yes | $(1,)$ or $(l, l)$ | mm/ms | you | Default 3.0 if unset. Recommended 3.8 by [TODO charlotte paper]. |
| `delays` | — | $(l, l)$ | ms | derived | `tract_lengths / speed`, in `configure()`. |
| `idelays` | — | $(l, l)$ int | integration steps | `set_idelays(dt)` | What the solver actually uses. |
| `centres` | yes | $(l, 3)$ | mm | you | Required for surfaces and forward models. Can be approximated by the `centres_*()` methods. |
| `region_labels` | yes | $(l,)$ str | — | you | Fallback: `create_region_labels()`, which generates `region_000`, `region_001`, … |
| `cortical` | no | $(l,)$ bool | — | you | Cortex or not. |
| `hemispheres` | no | $(l,)$ bool | — | you | `True` is right. Fallback: label prefix. |
| `orientations` | no | $(l, 3)$ | unit vector | you | Zeros where unknown. |
| `areas` | no | $(l,)$ | mm² | you | Surface area per region. |
| `undirected` | — | bool | — | derived | Report, not a constraint. |
| `number_of_regions` | — | int | — | derived | $l$, from the shape of `weights`. |
| `number_of_connections` | — | int | — | derived | Non-zero entries. Counts both directions. |
| `parent_connectivity` | no | str | — | lesion tools | Source of an edited connectome. |
| `saved_selection` | no | list of int | — | lesion tools | Regions kept. |

Only `weights` has no fallback of any kind. Everything else either has one, a
default, or is computed — and every fallback is a change to your model that you
should notice rather than inherit.

:::{warning}
A fallback that fires silently is not neutral. If `tract_lengths` is missing,
straight-line distances are used — they are shorter than real fibre paths, so
all delays come out too small. If `speed` is missing, 3.0 mm/ms is assumed. Both
cases log at `INFO` or below, which is easy to miss.
:::

---

(weights-section)=
## Weights

`weights[k, j]` is the strength of the projection **from region $j$ onto region
$k$**. Rows index targets, columns index sources.

:::{warning}
This is the **inverse** of the convention used by the Brain Connectivity Toolbox
and most graph-theory code. A matrix exported from BCT and loaded without a
transpose will couple the network backwards. It will run, produce plausible
spectra, and be wrong. Transpose on import and check one known asymmetric edge
by hand.
:::

The matrix is directed unless it happens to be symmetric. `configure()` sets
`undirected` to `True` when it finds an exactly symmetric matrix, but that flag
is a report about the data, not a switch that suppresses asymmetry. Nothing in
the library requires symmetry; an asymmetric matrix is the physically honest
case, since tracer data and laterality are not symmetric.

Values are non-negative and arbitrary in scale. TVB imposes no grading scheme.
The reference dataset described in [@sanzleon2015] uses the CoCoMac convention
of integer grades — 0 no connection, 1 weak, 2 moderate, 3 strong — while
tractography-derived matrices are continuous and heavy-tailed. Both work. What
matters is what you do to them afterwards.

### The diagonal

Self-connections live on the diagonal, and the library does not remove them for
you. Because the diagonal tract length is zero, a diagonal weight contributes
the node's *current* state as extra input to itself — an implicit gain on the
node's own activity. `transform_remove_self_connections()` returns a copy with
the diagonal zeroed.

Know which case your matrix is in. A diagonal of ones added to a coupling gain
of 0.004 can shift a model across a bifurcation without anything looking wrong.

### Scaling

`scaled_weights(mode)` returns a scaled copy; it does not modify `self`.

| `mode` | Divisor |
|---|---|
| `'tract'`, `'edge'` | largest absolute weight |
| `'region'`, `'node'` | largest absolute row sum (in-strength) |
| `'none'`, `None` | 1.0 — no change |

Two warnings apply. First, the operation is lossy: two consecutive scalings
cannot be undone, because the divisor is not recorded anywhere. Second,
normalisation competes with the coupling gain for the same job. If the
{term}`global coupling` function already rescales input by a parameter $a$,
normalising the weights as well gives you two knobs for one quantity, and the
sweep you run over one will silently depend on the other. Pick one place to do
it. The [coupling page](bb-coupling.md) covers the gain side.

### What the graph structure does to your dynamics

Coarse parcellations have highly variable region sizes, often by one to two
orders of magnitude. Larger regions attract more streamlines, so they get larger
in-strength for purely geometric reasons. When each region is a single mass
model with no spatial extent, that artefact biases the dynamics — a few large
parcels dominate the network's behaviour. This is a property of the data, not a
bug you can configure away; it is worth checking your in-strength distribution
before drawing conclusions about which regions are "hubs" [@zalesky2010].

---

## Tract lengths, conduction speed and delays

`tract_lengths[k, j]` is the physical length of the fibre pathway between
regions $k$ and $j$, in millimetres. Tractography cannot tell direction, so
these matrices come out symmetric; nothing in TVB enforces that.

If you supply `centres` but not `tract_lengths`, `configure()` fills them with
Euclidean distances between region centres. That is a straight-line proxy.
Fibres curve, so the true path is longer — Euclidean lengths underestimate every
delay in the network. Treat them as a placeholder, not a model.

`speed` is one number for the whole network, or a full matrix if you want
heterogeneous conduction speeds. Its unit is mm/ms, and the default is 3.0.

### How delays are computed

You do not choose delays; they are derived.

$$
\tau_{kj} = \frac{\ell_{kj}}{v_{kj}}
\quad\text{(ms)},
\qquad
\texttt{idelays}_{kj} = \operatorname{round}\!\left(\frac{\tau_{kj}}{\Delta t}\right).
$$

`configure()` computes `delays` unconditionally as `tract_lengths / speed`, so
changing `speed` takes effect on the next `configure()`. `set_idelays(dt)` then
converts those into whole integration steps, and that integer matrix is what the
solver indexes into its history buffer.

:::{warning}
**Delays are quantised, and $\Delta t$ sets the resolution.**

A delay shorter than half a step rounds to zero. That tract is then
instantaneous, not short. Raising $\Delta t$ to make a run faster therefore
coarsens the whole delay structure — you have changed the network, not just the
numerical precision. If a result depends on short-range timing, check
$\tau_{\min} / \Delta t$ before trusting it.
:::

The history buffer scales with $\max(\tau) / \Delta t$. Long tracts and small
steps both cost memory, and this is usually the limit on how long a delay a
simulation can carry.

### Causality at the two scales

Long-range connections carry a real delay, because they are the ones with a
measured length. Short-range connections — the local kernel on a cortical
surface — are treated as instantaneous within one integration step. Their
influence spreads no faster than one step at a time, which is a resolution
statement rather than a physical one. The [local connectivity
page](bb-local-connectivity.md) handles that scale.

---

## Centres, labels, hemispheres, cortical flag

`centres` is $(l, 3)$ in millimetres, in whatever coordinate space the atlas
uses. It is optional for a bare regional simulation, but required as soon as
geometry matters: the Euclidean fallback for tract lengths, {term}`lead field`
projections for EEG/MEG, and any plot of the network in space.

`region_labels` are short strings, one per region, and their **order is the
identity of every index in the object**. Weights, tract lengths, centres,
`cortical`, and every `region_mapping` that refers to this connectome all use
the same ordering. Reordering the labels without reordering the matrices
silently relabels the brain.

`hemispheres` is a boolean vector with `True` meaning right. If you leave it
unset, `configure()` infers it from the first letter of each label, and falls
back to "second half of the indices is right" when labels carry no `L`/`R`
prefix. Plotting helpers use it: `ordered_weights`, `ordered_tracts`,
`ordered_labels` and `ordered_centres` return views with left-hemisphere
regions first, and `get_grouped_space_labels()` returns the labels split for a
side-by-side figure.

`cortical` marks which regions are cortex. A cortex-only connectome has this
all `True`; add subcortical structures and you set it yourself.
`subcortical_indices` is derived from it and returns nothing useful if the field
was never populated. `areas` and `orientations` are optional and may be zeros
where unknown; zeros are the documented convention for "not measured", not a
physical value.

`number_of_regions` and `number_of_connections` are both computed in
`configure()`. Note that `number_of_connections` counts non-zero entries, so a
symmetric matrix counts every edge twice.

---

(setup-guide)=
## Setup guide

### 1. Obtain a connectome

The shortest path is the default file:

```python
from tvb.simulator.lab import connectivity

white_matter = connectivity.Connectivity.from_file()          # ships with tvb-data
white_matter = connectivity.Connectivity.from_file("my_connectivity.zip")
white_matter = connectivity.Connectivity.from_file("my_connectivity.h5")
```

A zip must contain `weights.txt` and `tract_lengths.txt`, plus a
`centres.txt` (or `centers.txt`) whose first column holds the region labels and
whose remaining three columns are the coordinates. Optional files:
`average_orientations.txt`, `cortical.txt`, `hemispheres.txt`, `areas.txt`.

From your own arrays, assign the fields directly:

```python
white_matter = connectivity.Connectivity()
white_matter.weights = weights          # (l, l), rows are targets
white_matter.tract_lengths = lengths    # (l, l), mm
white_matter.centres = centres          # (l, 3), mm
white_matter.region_labels = labels     # (l,), strings
white_matter.configure()
```

Bring-your-own-data specifics — validation, units, hemisphere handling — are in
[using your own connectivity](../demos/using_your_own_connectivity.ipynb).

### 2. Verify it

Do this before anything else, every time. The failure modes are quiet.

```python
import numpy as np

w, ell = white_matter.weights, white_matter.tract_lengths
assert w.shape[0] == w.shape[1] == len(white_matter.region_labels)
assert w.shape == ell.shape
assert np.isfinite(w).all() and np.isfinite(ell).all()
assert (w >= 0).all() and (ell >= 0).all()

print("symmetric:", np.allclose(w, w.T))
print("non-zero edges:", np.count_nonzero(w))
print("tract length range:", ell[ell > 0].min(), ell.max(), "mm")
print("self-connections:", np.count_nonzero(np.diag(w)))
```

The length range is the check that catches unit errors. Millimetres against a
3.0 mm/ms speed gives delays of a few to a few hundred milliseconds, which is
what white matter does. Metres give delays a thousand times too small, and a
network that looks like it has no delays at all.

### 3. Set the conduction speed

```python
white_matter.speed = np.array([3.0])          # mm/ms, whole network
```

A single-element array broadcasts to every edge. A full $(l, l)$ matrix is
allowed when you have per-tract estimates. The value enters every delay, so it
is a physiological parameter, not a numerical knob — see the [coupling
page](bb-coupling.md) for the joint effect of speed and coupling gain on which
rhythms survive.

### 4. Attach it to a simulation

```python
from tvb.simulator.lab import coupling, models, integrators, monitors, simulator

sim = simulator.Simulator(
    connectivity=white_matter,
    coupling=coupling.Linear(a=np.array([0.004])),
    model=models.JansenRit(),
    integrator=integrators.HeunDeterministic(dt=0.1),
    monitors=[monitors.Raw()],
)
```

You do not call `configure()` or `set_idelays()` yourself here.
`Simulator.configure()` does it in the right order: the connectome first, then
`set_idelays(dt)` once the integrator's step size is known. That order is the
reason delays and step size cannot be set independently.

### 5. When it breaks

| Symptom | Cause | Fix |
|---|---|---|
| All delays zero | lengths in wrong units, or `speed` huge | check `tract_lengths` range |
| Delays stale after a change | `configure()` not re-run | rebuild the simulator, or call `configure()` then `set_idelays(dt)` |
| Network couples backwards | matrix transposed on import | transpose; rows are targets |
| `ValidationException` on configure | region count mismatch between fields | check every field's length equals $l$ |
| Cannot allocate history | $\max(\tau)/\Delta t$ too large | raise $\Delta t$ (coarsens delays) or shorten tracts |
| Surface simulation errors on regions | `region_mapping` refers to absent regions | `unmapped_indices(region_mapping)` |

---

(api-reference)=
## API reference

:::{note}
**To do:** link to the generated API reference for
`tvb.datatypes.connectivity.Connectivity`. Until it exists, this section carries
the guidance.
:::

### Loading and writing

`from_file(source_file="connectivity_76.zip")` reads a zip or an `.h5` file and
returns a new object; it does **not** call `configure()`. Call it yourself, or
let the simulator do it. `from_bytes_stream(bytes_stream, content_type='.zip')`
does the same for uploaded data. Both accept `centres.txt` and `centers.txt`,
which is why some files in the wild have American spelling.

### Validation and derived quantities

`configure()` is the one method that matters. In order, it:

1. sets `number_of_regions` from the shape of `weights` and counts non-zero
   entries into `number_of_connections`;
2. computes `tract_lengths` from `centres` if absent;
3. generates `region_labels` if absent;
4. infers `hemispheres` from label prefixes if absent;
5. warns and sets `speed = 3.0` if unset;
6. **recomputes `delays = tract_lengths / speed` unconditionally**;
7. sets `undirected = True` if the weights are exactly symmetric;
8. validates the result.

Step 6 is worth remembering. `delays` is recomputed every time, so a value you
assign by hand is overwritten. Set `speed` and `tract_lengths`; never set
`delays`.

`set_idelays(dt)` converts `delays` into integration steps and prepares what the
solver needs: `idelays`, `has_delays`, `horizon` (maximum delay in steps, plus
one), and the flat index arrays `inodes` and `delay_indices`. `horizon` is only
valid after this call — reading it earlier raises. It is also the buffer length
the simulation must allocate.

`summary_info()` returns a dictionary of counts and per-array statistics,
including the non-zero subsets. It is the quickest way to eyeball an unfamiliar
file.

The `set_*` methods — `set_weights`, `set_tract_lengths`, `set_centres`,
`set_region_labels`, `set_orientations`, `set_areas`, `set_cortical`,
`set_hemispheres` — all take an `expected_number_of_nodes` argument and raise
`ValidationException` on a mismatch, or on fewer than two nodes. Prefer them to
raw assignment when the data comes from outside your own code.

### Transforms

All of these return a new array and leave `self` alone:

- `transform_remove_self_connections()` — zero the diagonal;
- `transform_binarize_matrix()` — 1 where weight > 0;
- `binarized_weights` — the same thing as a property;
- `scaled_weights(mode='tract')` — see [Scaling](#weights-section).

Assign the result back yourself if that is what you want. This is a feature:
transforms are cheap, reversible in the sense that the original is still there,
and safely chainable.

### Reordering and selection

These are read-only views built for plotting and for sub-setting, not for
changing the model: `hemisphere_order_indices`, `ordered_weights`,
`ordered_tracts`, `ordered_labels`, `ordered_centres`,
`get_grouped_space_labels()`, `is_right_hemisphere(idx)`,
`get_default_selection()`, `subcortical_indices`, `unmapped_indices(region_mapping)`.

`unmapped_indices(region_mapping)` is the one to reach for when a surface
simulation and a regional connectome disagree: it returns the region indices
that the mapping never touches. Those regions will contribute nothing and
receive nothing, which is usually an error rather than an intention.

### Surrogate generators

For testing and for null models: `motif_linear_directed`,
`motif_linear_undirected`, `motif_chain_directed`, `motif_chain_undirected`,
`motif_all_to_all`, with `create_region_labels(mode)` (`'numeric'` or
`'alphabetic'`), and the geometry helpers `centres_spherical`,
`centres_toroidal`, `centres_annular`, `centres_cubic`. The wrapper is
`generate_surrogate_connectivity(number_of_regions, motif='chain',
undirected=True, these_centres='spherical')`.

These **mutate the object in place and overwrite whatever was loaded**. They are
for building a synthetic network from nothing, or for generating a null model to
compare against real data — not for editing a real connectome.

### Lesion bookkeeping

`parent_connectivity` records where an edited connectome came from,
`saved_selection` holds the region indices that survived, and
`saved_selection_labels` turns those back into names for a report. These fields
are populated by the framework's lesion tools. Surgical-resection workflows are
demonstrated in [resting state in epilepsy](../demos/exploring_resting_state_in_epilepsy.ipynb).

### Pitfalls, collected

- Rows are targets; BCT matrices need transposing.
- The diagonal is not removed for you, and it acts as self-gain.
- `delays` is derived; setting it by hand does nothing.
- `idelays` are quantised to $\Delta t$; delays below $\Delta t/2$ vanish.
- Changing `speed` after `configure()` has no effect until you configure again.
- Normalising weights and tuning the coupling gain are two knobs for one job.
- Euclidean tract lengths are a placeholder, and they underestimate delays.
- `undirected` describes the data; it does not constrain the model.
- Region order is the identity of every index in the object, everywhere.
