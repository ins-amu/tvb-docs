# Explanation

**Explanation is conceptual background: understanding-oriented discussion.** An
explanation page steps back to explain *why* things are the way they are — the
dynamics behind the models, the design of the documentation and tooling, and
the trade-offs involved.

Explanation pages are essays: they clarify, discuss, and put choices in
context. For hands-on learning see [Tutorials](../tutorials/index.md), for
practical recipes see [How-to guides](../howtos/index.md), and for precise
facts see [Reference](../reference/index.md).

## Foundational Concepts

- **[The connectome](connectome.md)** — Structural connectivity matrices, tract lengths, signal propagation delays, and graph properties.
- **[Functional connectivity](functional-connectivity.md)** — Emergent statistical correlations, sliding-window dynamic FC, and empirical benchmarks.
- **[Forward models](forward-models.md)** — Biophysical mapping from cortical sources to scalp sensors (EEG, MEG) and intracerebral electrodes (SEEG).
- **[Dynamical systems theory](dynamical-systems-theory.md)** — Phase space, vector fields, fixed points, attractors, and stability analysis.
- **[Bifurcation analysis](bifurcation-analysis.md)** — Qualitative shifts in dynamics, Hopf bifurcations, bistability, and parameter sensitivity.
- **[Excitation–inhibition balance](excitation-inhibition-balance.md)** — Feedback inhibition control (FIC), criticality, and stable operating regimes.
- **[Neural mass models](neural-mass-models.md)** — Mesoscopic approximations of neuronal populations: derivation, assumptions, and limits.
- **[Phase planes](phase-plane-explanation.md)** — Geometric analysis of 2D dynamical systems: nullclines, eigenvalues, and limit cycles.
- **[From simulation to inference](tvbl-sim-to-inference.md)** — Closing the loop: simulation-based inference (SBI) and parameter recovery in TVB-Lite.

## Numerical & Paper Studies

Notebooks that explore numerical methods, benchmark simulation techniques, or reproduce figures from published research:

- **[Integrators Presentation](../demos/integrators_presentation.ipynb)** — Overview of deterministic and stochastic numerical integration algorithms in TVB.
- **[Integrators Comparison](../demos/integrators_comparison.ipynb)** — Quantitative accuracy and convergence comparison across Euler, Heun, and Runge-Kutta schemes.
- **[Compare Connectivity Normalization](../demos/compare_connectivity_normalization.ipynb)** — Impact of tract weight normalization strategies on emergent network activity.
- **[Exploring Resting State in Epilepsy](../demos/exploring_resting_state_in_epilepsy.ipynb)** — Mechanisms of epileptogenic zone propagation and network synchronization.
- **[Simulate for Mouse](../demos/simulate_for_mouse.ipynb)** — Whole-brain dynamics on high-resolution rodent tractography and parcellation.
- **[Skewed Functional Connectivity](../demos/skewed_fc.ipynb)** — Analysis of heavy-tailed, non-Gaussian distribution regimes in functional connectivity.
- **[Remake Wilson–Cowan Figure](../demos/remake_figure_WilsonCowan.ipynb)** — Reproduction of classical limit cycles and hysteresis from Wilson & Cowan (1972/1973).
- **[Reproduce Figure 2 (Gast et al., 2024 PNAS)](../demos/reproduce_figure_Gast_2024_PNAS.ipynb)** — Computational reproduction of neural mass transitions under synaptic depression.
- **[Gast–Solla–Kennedy Resting State](../demos/simulate_gast_solla_kennedy_resting_state.ipynb)** — Resting-state simulations using the Gast-Solla-Kennedy cortical population equations.
- **[Theta Neuron Models](../demos/theta_neuron_models.ipynb)** — Microscopic-to-macroscopic mapping of coupled theta neuron populations.
- **[AdEx Mean-Field Model](../demos/adex_meanfied/adex_meanfield.ipynb)** — Adaptive Exponential (AdEx) integrate-and-fire mean-field formulation.
- **[Goldman et al. (2020) Spontaneous Activity](../demos/adex_meanfied/goldman_2020_spontaneous_activity.ipynb)** — Simulating state transitions and spontaneous activity in AdEx cortical networks.
