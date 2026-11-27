# Tutorials

**Tutorials are lessons: learning by doing.** A tutorial takes you by the hand
through a worked example, start to finish, so that you can learn by doing and
achieve a concrete result.

In this section you will run TVB simulations step by step — from a first
simulation to exploring the phase-plane — and see how the pieces fit together.
Tutorials are aimed at learners: they are opinionated, minimal, and guaranteed
to work as written.

## Presenting TVB

Use the introductory tutorial deck for events:
[HTML presentation](https://ins-amu.github.io/tvb-docs/slides/tvb-tutorial.html),
[PDF](https://ins-amu.github.io/tvb-docs/slides/tvb-tutorial.pdf), or
[PowerPoint](https://ins-amu.github.io/tvb-docs/slides/tvb-tutorial.pptx).
The HTML and PowerPoint versions include presenter notes.

:::{tip} Open in JupyterLite Lab
Want to run tutorials live in your browser with zero installation?
[Open in JupyterLite Lab](/lite/lab/index.html) or launch [Your first simulation in Lab](/lite/lab/index.html?path=tutorials/first-simulation.ipynb).
:::

## Core Tutorials

- **[Getting started](getting-started.md)** — Core TVB concepts, simulator anatomy, and architecture overview.
- **[Your first simulation](first-simulation.md)** — Complete runnable TVB pipeline: connectome, neural mass, coupling, integrator, and monitors.
- **[Interactive phase planes](phase-plane.md)** — Dynamic phase-plane exploration with the interactive anywidget.
- **[Your first tvb-lite simulation](tvbl-quickstart.md)** — Browser-native TVB simulation with Pyodide and WebAssembly.

## Simulation Tutorials

Step-by-step demonstrations walking through fundamental simulation setups:

- **[Simulate Region Jansen-Rit](../demos/simulate_region_jansen_rit.ipynb)** — Simulating the classic Jansen-Rit visual cortex model at the region level.
- **[Simulate Reduced Wong-Wang](../demos/simulate_reduced_wong_wang.ipynb)** — Simulating the Reduced Wong-Wang model for resting-state dynamics.
- **[Simulate Hybrid Getting Started](../demos/simulate_hybrid_getting_started.ipynb)** — Getting started with hybrid multiscale modeling in TVB.
- **[Exploring Longer Time Series](../demos/exploring_longer_time_series.ipynb)** — Managing memory and analyzing long-duration recordings.
- **[Exploring the BOLD Monitor](../demos/exploring_the_bold_monitor.ipynb)** — Modeling the hemodynamic response function (HRF) to compute fMRI BOLD signals.
- **[Exploring a Surface Mesh](../demos/exploring_a_surface_mesh.ipynb)** — Working with high-resolution triangular cortical meshes.

## Structural Lesion Studies

A three-part tutorial series investigating the structural and functional consequences of brain lesions:

- **[Structural Lesions Part 1](../demos/sandbox/tutorial_s7_ModelingTheImpactOfStructuralLesionsPart1.ipynb)** — Modeling structural connectivity damage and lesion masks.
- **[Structural Lesions Part 2](../demos/sandbox/tutorial_s8_ModelingTheImpactOfStructuralLesionsPart2.ipynb)** — Assessing changes in network dynamics and functional connectivity post-lesion.
- **[Structural Lesions Part 3](../demos/sandbox/tutorial_s9_ModelingTheImpactOfStructuralLesionsPart3.ipynb)** — Modeling compensatory reorganization and structural recovery.

---

For task-oriented recipes see [How-to guides](../howtos/index.md),
for precise facts see [Reference](../reference/index.md), and for background
concepts see [Explanation](../explanation/index.md).
