# Demos & Sandbox

This section collects interactive demonstrations, specialized workflow notebooks, and experimental prototypes from The Virtual Brain (TVB) and TVB-Lite.

:::{tip} Open in JupyterLite Lab
Want to run, modify, and experiment with these notebooks directly in your browser without installing anything locally?

[Open in JupyterLite Lab](/lite/lab/index.html)
:::

## Overview of Demos

TVB provides a wide collection of demonstration notebooks that illustrate how to configure and execute whole-brain simulations, analyze synthetic signals, explore mathematical models, and integrate with external frameworks.

Most domain-specific demonstration notebooks have been organized into the four [Diátaxis](https://diataxis.fr) documentation quadrants:

- **[Tutorials](../tutorials/index.md)**: Guided walkthroughs including regional simulation with Jansen-Rit and Reduced Wong-Wang, hybrid modeling, surface mesh exploration, and structural lesion studies.
- **[How-to guides](../howtos/index.md)**: Practical task recipes for connectivity manipulation, stimuli definition, forward models (EEG, MEG, SEEG), HPC/GPU backends, RateML DSL, and framework REST APIs.
- **[Reference](../reference/index.md)**: Detailed model cards and interactive explorers for model phase planes, power spectra, and state variables.
- **[Explanation](../explanation/index.md)**: Deep dives into numerical integrators, resting-state dynamics in epilepsy, mouse brain simulations, and reproductions of published papers.

Below are the specialized **TVB-Lite** in-browser notebooks and the **Sandbox** experimental prototypes.

---

## TVB-Lite Demos

TVB-Lite is a lightweight, browser-based TVB environment running in JupyterLite with `xeus-python` and WebAssembly:

- **[CDE Jansen-Rit](cde_jr.ipynb)**: Jansen-Rit simulation and parameter inference using Conditional Density Estimation.
- **[MHSA](mhsa.ipynb)**: Multi-Head Self-Attention mechanisms applied to brain network dynamics.
- **[TVB-Lite Simulation & Inference](demo.ipynb)**: Complete end-to-end workflow demonstrating simulation on a connectome followed by posterior parameter inference.

---

## Sandbox & Experimental Prototypes

The sandbox contains experimental prototypes, advanced research tests, and legacy exploratory workflows:

- **Surface & Parcellation**:
  - [Display Surface Parcellation](sandbox/display_surface_parcellation.ipynb) — Visualizing cortical surface parcel divisions.
  - [Surface Deterministic with Custom Local Connectivity](sandbox/surface_deterministic_custom_local_connectivity.ipynb) — Modeling localized spatial kernels on triangular surface meshes.
  - [Surface Stimuli](sandbox/surface_stimuli.ipynb) — Injecting spatio-temporal stimuli onto surface vertices.
  - [Surface Stochastic](sandbox/surface_stochastic.ipynb) — Surface simulation driven by spatial noise processes.
- **SEEG & Sensor Projections**:
  - [SEEG Region Deterministic](sandbox/seeg_region_deterministic.ipynb) — Forward projection of regional dynamics to stereo-EEG electrode contacts.
  - [SEEG Surface Deterministic](sandbox/seeg_surface_deterministic.ipynb) — Forward projection of folded cortical surface dynamics to stereo-EEG electrode contacts.
- **Signal Analysis & Dimensionality Reduction**:
  - [MSE Analyse Region](sandbox/mse_analyse_region.ipynb) — Multiscale Entropy analysis on regional time series.
  - [PCA Analyse View Region](sandbox/pca_analyse_view_region.ipynb) — Principal Component Analysis and state-space trajectory projection.
- **Model Explorations & Parameter Variations**:
  - [Exploring Hopfield-based Models](sandbox/exploring_hopfield_based_models.ipynb) — Hopfield associative memory networks embedded in connectome dynamics.
  - [Exploring Reduced Wong-Wang Model](sandbox/exploring_a_model_reducedWongWang.ipynb) — Dynamic regimes of the Reduced Wong-Wang neural mass.
  - [Region Deterministic Larter-Breakspear](sandbox/region_deterministic_larterbreakspear.ipynb) — Simulating the Larter-Breakspear nonlinear neural mass model on a connectome.
  - [Smooth Parameter Variation](sandbox/smooth_parameter_variation.ipynb) — Varying model parameters continuously during simulation run-time.
  - [Stochastic Simulation](sandbox/stochastic_simulation.ipynb) — Integration schemes under additive and multiplicative noise.
