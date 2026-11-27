# Glossary

[Search glossary terms and definitions](#search-glossary), or browse the entries below. Hover over a green link to preview its definition.

## A–B

:::{glossary}
Additive noise
: Noise added during integration with an amplitude independent of the current state.

Adjacency matrix
: A matrix whose entries indicate or weight edges between pairs of network nodes.

Alpha kernel
: A synaptic response proportional to time multiplied by an exponential decay, rising from zero to one peak.

Amortised inference
: Training an estimator once so that the posterior for any new observation is obtained from a single fast evaluation, without retraining.

  [Tutorial: simulation-based inference](user-guide/inference/npe-montbrio.md)

Attractor
: A set of states that nearby trajectories approach over time.

Backend
: An implementation that runs a simulation on a particular execution platform, such as a CPU or GPU.

Balloon–Windkessel model
: A haemodynamic model that relates neural activity to blood flow, blood volume, and deoxyhaemoglobin to predict the {term}`BOLD` signal.

Basin of attraction
: The set of initial states whose trajectories approach the same {term}`attractor <Attractor>`.

Bifurcation
: A qualitative change in a dynamical system’s behaviour as a parameter passes a critical value.

  [Explanation: Bifurcation analysis](explanation/bifurcation-analysis.md)

Bifurcation analysis
: The study of how equilibria, oscillations, or other solutions appear, disappear, or change stability as parameters vary.

  [Explanation: Bifurcation analysis](explanation/bifurcation-analysis.md)

Biophysical model
: A model whose equations represent specified physiological mechanisms, such as membrane currents or ion exchange.

Bistability
: Coexistence of two stable {term}`attractors <Attractor>` under the same parameter values.

BOLD
: Blood oxygenation level-dependent contrast in fMRI, sensitive to changes in deoxyhaemoglobin.

Brain atlas
: A spatial reference that maps anatomical or functional labels onto brain locations.

:::

## C–D

:::{glossary}
Coloured noise
: Temporally correlated noise; TVB generates exponentially correlated noise when `ntau` is positive.

Conduction speed
: The assumed speed of signal propagation along a tract, used with {term}`tract length <Tract length>` to calculate a delay.

Connectome
: A network representation of anatomical connections. In TVB, a regional connectome typically supplies connection weights and tract lengths.

  [Building Blocks: Connectivity](user-guide/bb-connectivity.md)

Control parameter
: A parameter varied to examine how a model’s dynamics change.

Cortical surface
: A mesh approximating a cortical sheet, used to represent sources or simulate spatially distributed cortical activity.

Coupling
: The rule that turns activity from other nodes or populations into input to a node’s local dynamics.

Coupling function
: A transformation of activity arriving from connected nodes, applied before or after weighted summation and passed to the local model.

Covariance
: A measure of how two variables vary together around their means.

Criticality
: A regime near a transition where small parameter changes can qualitatively alter collective dynamics.

Diffusion MRI
: MRI methods that measure water diffusion in tissue and support tractography of {term}`white-matter <White matter>` pathways.

Delay
: The lag between activity at one node and its arrival at another. Delays give a network simulation a {term}`history <History>`.

Diffusion-weighted MRI
: MRI sensitive to water diffusion, used by {term}`tractography <Tractography>` to estimate possible white-matter pathways.

Degeneracy
: A posterior pathology where parameters trade off or couple tightly, forming ridges, symmetries, or funnels that blur inference and impede optimization and MCMC exploration.

Directional bias
: The preference of a {term}`tractography <Tractography>` algorithm to extend a {term}`streamline <Streamline>` along the locally dominant diffusion orientation, inferred from anisotropic water diffusion in white-matter fibre bundles.

Dynamic functional connectivity
: Variation in estimated {term}`functional connectivity <Functional connectivity>` over time, often assessed using sliding windows.

Dynamical noise
: A noise term $g(\psi_i)\xi_i(t)$ applied during integration; $g$ sets its amplitude and can depend on the node's state.

Dynamical system
: A set of states together with a rule specifying how the state evolves over time.

:::

## E–H

:::{glossary}
Edge
: A connection between two network nodes, optionally associated with a direction, weight, or delay.

EEG
: Electroencephalography measures electrical potential differences at electrodes, usually on the scalp.

Effective sample size
: (ESS) the number of independent draws with the same estimation power as autocorrelated MCMC samples, estimated from multi-chain autocorrelations to quantify Monte Carlo error.

Eigenvalue
: A scalar associated with a matrix mode. For a {term}`Jacobian`, its real part determines the mode’s local growth or decay.

Epileptogenic zone
: The brain tissue or regions necessary for seizure generation, often represented in seizure models by highly excitable regions.

Euler method
: A first-order integrator that advances the state using the derivative at the beginning of each step.

Excitability
: How readily a neuron or model responds strongly to input or crosses into a different dynamical regime.

Excitation–inhibition balance
: The interplay of excitatory and inhibitory inputs and feedback that shapes the activity and stability of neural populations.

  [Explanation: Excitation–inhibition balance](explanation/excitation-inhibition-balance.md)

Feedback inhibition control
: Adjustment of local inhibitory feedback to bring a simulated neural population toward a target firing rate.

Firing rate
: The number of spikes per unit time, often averaged per neuron over a population.

Fixed point
: A state that remains unchanged under the dynamics. In continuous time, its time derivatives vanish.

fMRI
: Functional magnetic resonance imaging maps changes related to brain activity, most commonly using {term}`BOLD` contrast.

Forward model
: A mapping from simulated neural activity to predicted measurements, such as sensor voltages, magnetic fields, or BOLD signals.

  [Explanation: Forward models](explanation/forward-models.md)

Functional connectivity
: Statistical dependence between activity signals from different locations, commonly estimated with correlations.

  [Explanation: Functional connectivity](explanation/functional-connectivity.md)

Global coupling
: A shared scale factor controlling the overall strength of long-range input in a network simulation.

Haemodynamic response
: The changes in blood flow, volume, and oxygenation that follow neural activity.

Heterogeneous connectivity
: Coupling that varies by source and target, as with long-range white-matter pathways linking different brain regions.

Heun method
: A predictor–corrector integrator that averages derivatives evaluated at the initial state and an Euler prediction.

Homogeneous connectivity
: A connectivity rule whose coupling depends on spatial separation and is invariant under translation across the cortical sheet.

History
: The record of a node's past states over its {term}`delay <Delay>`, allowing states from previous integration steps to influence neighbouring nodes.

Hopf bifurcation
: A {term}`bifurcation <Bifurcation>` in which a fixed point changes stability and a nearby periodic orbit appears or disappears.

Hybrid simulation
: A TVB simulation that combines different local models within one coupled network.

:::

## I–M

:::{glossary}
Identifiability
: The extent to which available observations can distinguish model parameters or parameter combinations.

Initial condition
: The state from which integration starts. A delayed system generally also needs a history before the start time.

Integrator
: A numerical method for solving a model's differential equations using finite time steps.

Isotropic material
: A material that is isotropic behaves in precisely the same way regardless of how it is oriented with respect to sources, fields, and other materials.

Jacobian
: The matrix of first partial derivatives of a vector-valued function, used to linearise dynamics near a state.

Lead field
: The sensor pattern produced by a unit source. A lead-field matrix collects these patterns to project source activity to sensors.

Likelihood
: The probability of the observed data as a function of the model parameters, usually written as the density of the data given the parameters.

Limit cycle
: An isolated periodic orbit in state space, which may be attracting, repelling, or neither.

Linear material
: A material is said to be linear if its properties do not depend on the sources and fields applied to the material.

Local coupling
: Interactions among nearby sites or populations, distinguished in TVB surface simulations from long-range connections between regions.

Markov chain Monte Carlo
: A family of algorithms that draw correlated samples from a distribution by simulating a Markov chain whose long-run distribution is the target.

Masked autoregressive flow
: An invertible density model built from autoregressive transformations, used in the inference tutorials to estimate a conditional posterior.

Mean-field model
: A model that represents interactions through aggregate quantities, such as mean synaptic input, rather than tracking every individual interaction.

MEG
: Magnetoencephalography measures magnetic fields generated by neural currents.

Monitor
: A TVB component that samples, aggregates, or transforms simulation states into outputs.

Mode
: An index for parallel components of a local model at each node; reduced-set models use several modes to represent population heterogeneity.

  [Building Blocks: Simulator](user-guide/bb-simulator.md)

Multiplicative noise
: Noise added during integration with an amplitude that depends on the current state.

:::

## N–P

:::{glossary}
Neural field model
: A continuous spatial model of neural activity, often a PDE. TVB approximates it with discrete neural masses; see [High Resolution](user-guide/hr/classic.md).

Neural mass model
: A dynamical model of aggregate neuronal population activity, typically using variables such as mean firing rate or mean membrane potential.

  [Explanation: Neural mass models](explanation/neural-mass-models.md)

Node
: A unit in a network; in regional TVB simulations it commonly corresponds to a brain parcel.

Nullcline
: A set of states where the time derivative of one {term}`state variable <State variable>` vanishes.

Observer model
: A model mapping simulated neural activity to observable signals such as EEG, MEG, or BOLD, possibly including spatial projection, haemodynamics, and measurement noise.

Ordinary differential equation
: An equation relating a function of one independent variable, usually time here, to its derivatives.

Parameter sweep
: A series of simulations run across a range of parameter values to compare outcomes.

Parcellation
: A division of the brain into labelled regions used as units of analysis or as network nodes.

Perturbation
: A deliberate or incidental change to a system’s state or input, used to examine its response.

Phenomenological model
: A model formulated to reproduce observed dynamics without explicitly representing all the physiological mechanisms that generate them.

Phase plane
: A two-dimensional {term}`state space <State space>` used to visualise dynamics.

  [Explanation: Phase planes](explanation/phase-plane-explanation.md)

Phase portrait
: A visualisation of representative trajectories or flow in {term}`state space <State space>`.

Posterior
: The probability distribution of parameters after conditioning on observed data or summaries.

Posterior predictive check
: A comparison of data simulated from posterior parameter draws with the observation, to test whether the fitted model reproduces it.

Postsynaptic potential
: A change in membrane potential caused by synaptic input, averaged over a population in a neural mass model.

Postsynaptic transformation
: In network coupling, $Z^{(a)}$ acts on the weighted sum of incoming contributions at the receiving node.

Power spectral density
: Signal power per unit frequency, describing how variance is distributed across frequencies.

Presynaptic transformation
: In network coupling, $S^{(a)}$ transforms each source-to-target contribution before connection weights are summed.

Prior
: A probability distribution representing parameter uncertainty before conditioning on the current observations.

Projection matrix
: A matrix that maps simulated source activity to sensor-space signals, such as EEG or MEG.

Propagation delay
: The travel time assigned to a network connection, commonly calculated as {term}`tract length <Tract length>` divided by {term}`conduction speed <Conduction speed>`.

Pulse density
: The average rate of action potentials across a neuronal population.

Pulse-to-wave transform
: Synaptic filtering that converts incoming {term}`pulse density <Pulse density>` into an average {term}`postsynaptic potential <Postsynaptic potential>`.

:::

## R–Q

:::{glossary}
R-hat
: (R) Convergence diagnostic comparing between- and within-chain variance across split, rank-normalized chains; values near 1 indicate mixing, while higher values signal non-convergence.

Reduced model
: A simplified model that retains selected behaviour while using fewer variables, parameters, or mechanisms.

Reduced-set model
: A low-dimensional approximation of a heterogeneous neuronal population obtained by projecting its dynamics onto a small set of modes.

Resting state
: Brain activity without an instructed task. In dynamical-system discussions, the phrase can also refer to a stable baseline regime.

Runge–Kutta method
: A family of integrators that combine derivative estimates at one or more points within each time step.

Saddle
: A fixed point with attracting directions and repelling directions in its local dynamics.

Saddle-node bifurcation
: A local {term}`bifurcation <Bifurcation>` where two fixed points collide and appear or disappear together.

Sampling period
: The simulated time between successive recorded samples, which can differ from the {term}`time step <Time step>`.

SEEG
: Stereoelectroencephalography records intracranial electrical potentials using implanted depth electrodes.

Separatrix
: An invariant boundary separating regions of state space with different trajectories or long-term outcomes.

Sigmoid
: An S-shaped nonlinear function that smoothly transitions between lower and upper saturation levels.

Simulation-based inference
: Inference that uses simulations to learn about unknown parameters when evaluating the likelihood directly is difficult.

  [Inference overview](user-guide/inference.md)

Simulator
: TVB component that coordinates connectivity, local dynamics, coupling, integration, delayed history, and monitors to generate activity over time.

  [Building Blocks: Simulator](user-guide/bb-simulator.md)

Sparse coupling
: A representation or computation that stores or evaluates only the connections present in the network.

Stability
: The tendency of a solution to resist small perturbations. Asymptotic stability also requires trajectories to return toward it.

State space
: The space of all possible model states, with coordinates given by the state variables in a finite-dimensional model.

  [Explanation: Dynamical systems theory](explanation/dynamical-systems-theory.md)

State variable
: A quantity that changes according to the model dynamics and helps specify its current state.

Stationarity
: Invariance of a process’s statistical properties under shifts in time, with the precise requirements depending on the definition used.

Stimulus
: An external input prescribed in space, time, or both to drive part of a simulation.

Stochastic differential equation
: A differential equation with a random driving term, used to model noisy evolution in continuous time.

Streamline
: A reconstructed path following estimated local fibre orientations in {term}`tractography <Tractography>`.

Structural connectivity
: The pattern or strength of anatomical connections between brain areas.

Summary statistic
: A quantity calculated from data or simulations to capture features used in comparison or inference.

Synaptic time constant
: A characteristic timescale controlling the rise, decay, or filtering of a synaptic response.

Quadratic integrate-and-fire neurons
: neuron model with quadratic function describing the evolution of membrane voltage $V$. Spike occurs at threshold $V_t$, followed by a reset to $V_r$.
 
:::

## T–W

:::{glossary}
Time series
: A sequence of measurements or simulated values indexed by time.

Time step
: The increment of simulated time used by an {term}`integrator <Integrator>` to advance the state.

Tract length
: The estimated path length associated with a connection between brain regions.

Tractography
: Reconstruction of candidate white-matter pathways from local fibre orientations estimated using diffusion MRI.

Trajectory
: The path a model state follows through {term}`state space <State space>` over time.

Transfer function
: In neural population models, a mapping from input statistics to a population response, such as its mean firing rate.

Transient
: An initial or temporary phase of dynamics before the behaviour of interest, such as a steady state, is reached.

Vector field
: A function assigning a direction and rate of motion to each state in a continuous-time dynamical system.

Wave-to-pulse transform
: A nonlinear mapping from mean {term}`postsynaptic potential <Postsynaptic potential>` to population {term}`pulse density <Pulse density>`, commonly a sigmoid.

Weight normalisation
: Rescaling connection weights according to a rule, such as dividing each row by its sum.

White matter
: Brain tissue composed predominantly of myelinated axons that connect different regions of the central nervous system, facilitating communication between them.

White noise
: Noise with no temporal correlation and a flat power spectrum in the idealised continuous-time limit.

:::
