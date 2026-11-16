# Reference

**Reference is accurate, complete information: description, not instruction.**
A reference page records the facts about the system — model equations,
parameter names and units, configuration keys, and API surfaces — organised so
that you can look things up quickly.

Reference material must be accurate and consistent, like a dictionary or a
datasheet; it should not try to teach or tell stories. For guided learning see
[Tutorials](../tutorials/index.md), for task recipes see
[How-to guides](../howtos/index.md), and for conceptual background see
[Explanation](../explanation/index.md).

## Neural Mass Model Cards

Each model card specifies state variables, parameters, differential equations, default configurations, and literature references:

| Model | Classification | Description |
| --- | --- | --- |
| [Wilson–Cowan](model-cards/wilson-cowan.md) | Population rate | Excitatory-inhibitory interacting populations |
| [FitzHugh–Nagumo](model-cards/fitzhugh-nagumo.md) | Relaxation oscillator | Classical 2D excitable system |
| [Jansen–Rit](model-cards/jansen-rit.md) | Cortical column | 3-population pyramidal, excitatory, and inhibitory interneurons |
| [Zetterberg–Jansen](model-cards/zetterberg-jansen.md) | Cortical column | Extended column model with fast and slow inhibition |
| [Larter–Breakspear](model-cards/larter-breakspear.md) | Conductance-based | Ion channel dynamics with voltage-gated ion conductances |
| [Dumont–Gutkin](model-cards/dumont-gutkin.md) | Mean-field | Exact mean-field macroscopic model of spiking neurons |
| [K-Ion Exchange](model-cards/k-ion-ex.md) | Ionic dynamics | Extracellular potassium dynamics and spreading depression |
| [Generic 2D Oscillator](model-cards/generic-2d-oscillator.md) | Phenomenological | Canonical 2D excitable limit-cycle oscillator |
| [Epileptor](model-cards/epileptor.md) | Phenomenological | 5D model of epileptic seizure transitions and interictal spikes |
| [Epileptor 2D](model-cards/epileptor-2d.md) | Phenomenological | Reduced planar 2D seizure transition model |
| [Montbrió–Pazó–Roxin](model-cards/montbrio-pazo-roxin.md) | Exact mean-field | Quadratic integrate-and-fire microscopic ensemble |
| [Coombes–Byrne](model-cards/coombes-byrne.md) | Exact mean-field | Theta neuron network with gap junctions and synaptic kinetics |
| [Coombes–Byrne 2D](model-cards/coombes-byrne-2d.md) | Exact mean-field | Planar reduction of the Coombes-Byrne model |
| [Gast–Smidt–Knösche (SD)](model-cards/gast-smidt-knosche-sd.md) | Spiking population | Synaptic depression in cortical networks |
| [Gast–Smidt–Knösche (SF)](model-cards/gast-smidt-knosche-sf.md) | Spiking population | Synaptic facilitation in cortical networks |
| [Kuramoto](model-cards/kuramoto.md) | Phase oscillator | Canonical phase synchronization model |
| [SupHopf](model-cards/suphopf.md) | Normal form | Supercritical Hopf bifurcation normal form |
| [Linear](model-cards/linear.md) | Linear dynamics | Coupled multivariate Ornstein-Uhlenbeck process |
| [Reduced Set FitzHugh–Nagumo](model-cards/reduced-set-fitzhugh-nagumo.md) | Relaxation oscillator | Parameter-reduced FitzHugh-Nagumo formulation |
| [Reduced Wong–Wang](model-cards/reduced-wong-wang.md) | Population rate | 1D NMDA-mediated attractor dynamics |
| [Reduced Wong–Wang (Exc-Inh)](model-cards/reduced-wong-wang-exc-inh.md) | Population rate | 2D excitatory and inhibitory feedback loops |
| [Deco Balanced (Exc-Inh)](model-cards/deco-balanced-exc-inh.md) | Population rate | Feedback inhibition control for whole-brain resting state |
| [Reduced Set Hindmarsh–Rose](model-cards/reduced-set-hindmarsh-rose.md) | Bursting neuron | 3D neuronal bursting and spiking model |

## Model & Interactive Explorers

Notebooks demonstrating model equations, phase portraits, and interactive parameter widgets:

- **[Exploring K-Ion Exchange Model](../demos/exploring_K_ION_Exchange_model.ipynb)** — Phase portraits and ion concentration dynamics in the K-ion model.
- **[Exploring Epileptor 2D](../demos/exploring_epileptor_2d.ipynb)** — Fast-slow planar dynamics of epileptic discharges and seizure onset.
- **[Exploring Epileptor 3D (Codim-3)](../demos/exploring_the_epileptor_codim_3_model.ipynb)** — Unfolding and bifurcations of the codimension-3 Epileptor system.
- **[Exploring SupHopf Model](../demos/exploring_supHopf_model.ipynb)** — Subcritical and supercritical regime transitions in the Hopf model.
- **[Interactive Phase Plane Tool](../demos/exploring_phase_plane_interactive.ipynb)** — Interactive nullclines, vector fields, and trajectories.
- **[Interactive Power Spectra](../demos/exploring_power_spectra_interactive.ipynb)** — Live interactive frequency spectrum and power spectral density visualizer.
- **[Interactive Time Series](../demos/exploring_time_series_interactive.ipynb)** — Interactive signal inspection across multiple simulated channels.

## Site & Architecture

- **[About this documentation](about-this-site.md)** — Diátaxis architecture, MyST configuration, marimo islands, and build pipeline.
