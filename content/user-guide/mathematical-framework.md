---
title: Mathematical Framework
bibliography:
  - ../references.bib
---

# Mathematical Framework

The Virtual Brain (TVB) relies on the mathematical framework of graph theory
and nonlinear dynamics. It represents the activity of different brain regions and interaction between them grounded in biological principles. Brain regions form the nodes of a structural network, and a population model specifies the dynamics at each node. Connections within cortical tissue and through white matter couple these dynamics over different spatial scales. The foundation is based on Jirsa-Haken equation [@wang2024; @sanzleon2015].

## Jirsa–Haken equation

Let $\psi(x_i,t)$ denote the activity of the neural population in brain region
$i$ at time $t$. Local dynamics and input from other populations determine its
evolution [@wang2024; @sanzleon2015]:

$$
\begin{aligned}
\dot{\psi}(x_i,t)
={}& L\bigl(\psi(x_i,t)\bigr) \\
&+ \int_{\Gamma_l} g_{ij}
   S\bigl(\psi(x_j,t-\tau_{ij})\bigr)\,\mathrm{d}x_j \\
&+ G\int_{\Gamma_g} W_{ij}
   S\bigl(\psi(x_j,t-\tau_{ij})\bigr)\,\mathrm{d}x_j
   + w(t).
\end{aligned}
$$

The term $L$ describes the local population dynamics. Input from the nearby
cortical domain $\Gamma_l$ is weighted by $g_{ij}$, while input carried by
long-range white-matter pathways is weighted by $W_{ij}$ and scaled by the
global coupling constant $G$. Activity from one region reaches the receiving
population after a delay $\tau_{ij}$ and get transformed through the nonlinear response
$S$. The term $w(t)$ denotes {term}`dynamical noise <Dynamical noise>`
[@wang2024].

## Neural mass models

A neural mass describes a neural population with a small set of state variables, such as mean firing rate or mean membrane potential. Statistical methods like mean-field averaging is generally used in this process. Its equations define $L$. At regional resolution, each brain region is assigned a neural mass, with local cortical interactions included in its dynamics. The explicit local coupling term is then set to $g_{ij}=0$, and interregional input enters through $W_{ij}$.

At finer spatial resolution, a {term}`neural field <Neural field model>` assigns
activity to cortical surface vertices and retains the local interaction term
[@wang2024]. The [model cards](../reference/index.md) give the equations for
individual TVB models.

Neural mass formulations often relate mean postsynaptic potential and
population firing rate through two transformations. The
{term}`wave-to-pulse transform <Wave-to-pulse transform>` gives the firing
response to a mean postsynaptic potential, commonly through a sigmoid. The
{term}`pulse-to-wave transform <Pulse-to-wave transform>` describes the
synaptic filtering of incoming firing activity into a postsynaptic potential
[@sanzleon2015].

## Neuroscientific basis

At the cortical surface, local connectivity $g_{ij}$ describes interactions
along the folded cortical sheet. At regional resolution, the anatomical
parcellation defines the nodes, and white-matter pathways inform $W_{ij}$.
Pathway length and conduction speed determine the propagation delay
$\tau_{ij}$. These anatomical inputs are described in
[the connectome](../explanation/connectome.md). The global coupling constant
$G$ sets the strength of interregional input [@sanzleon2015]. A
[forward model](../explanation/forward-models.md) projects simulated neural
activity to EEG, MEG, or fMRI measurements.

Neural populations fluctuate at rest, even in the absence of an imposed
stimulus. At regional scale, $w(t)$ represents fluctuating drive unresolved by
the chosen neural mass. A fluctuation displaces a population from its resting
state, and its local dynamics govern the subsequent transient. Across the
network, structural connections and conduction delays shape the modes that
respond most strongly. TVB introduces noise through stochastic integration. {term}`Additive noise <Additive noise>` provides a fluctuating input independent of the current state; for {term}`multiplicative noise <Multiplicative noise>`, its amplitude depends on the state. [@ghosh2008].

## Mathematical nomenclature

In the equation, $i$ indexes the receiving brain region and $j$ a contributing
brain region. For a cortical surface model, they index vertices. We use
$W_{ij}$ for structural weights and $G$ for global coupling
[@wang2024; @sanzleon2015].

| Symbol | Meaning |
| --- | --- |
| $x_i$ | Brain region represented by node $i$, or a cortical vertex in a surface model. |
| $\psi(x_i,t)$ | Neural activity of brain region $i$ at time $t$. |
| $L$ | Local node dynamics in the Jirsa–Haken equation. |
| $\Gamma_l$, $\Gamma_g$ | Local and global spatial domains of interaction. |
| $g_{ij}$ | Local connectivity between nearby cortical vertices. |
| $W_{ij}$ | Structural connectivity weight associated with a white-matter connection. |
| $G$ | Global coupling constant scaling long-range input. |
| $S$ | Nonlinear function of delayed neural activity. |
| $\tau_{ij}$ | Transmission delay between connected brain regions. |
| $w(t)$ | Dynamical noise. |
