---
title: Mathematical Framework
bibliography:
  - ../references.bib
---

# Mathematical Framework

The Virtual Brain (TVB) represents the mesoscopic activity of neuronal populations (e.g. brain regions), and interactions between them. The evolution of the state of each node in time is governed by a neural mass model, and the connections within cortical tissue and through {term}`white matter <White matter>` couple these dynamics over different spatial scales. TVB formulates their evolution as coupled differential equations, with delays and stochastic forcing included where specified [@sanzleon2015; @schirner2022; @hashemi2025].

## Network dynamics

Let $\psi_i(t)$ denote the state vector of the neural population at node $i$
and time $t$. The Jirsa–Haken formulation distinguishes local dynamics from
interactions within nearby tissue local connectivity and distant brain regions through long-range connections
[@jirsaHaken1996; @jirsaHaken1997; @sanzleon2015; @wang2024; @hashemi2025]. The general form of the TVB equations for $M$ connectivity pathways is

$$
\begin{aligned}
c_i^{(a)}(t)
&=Z^{(a)}\!\left(\sum_{j\in\mathcal N_i^{(a)}}W_{ij}^{(a)}S^{(a)}\!\left(\psi_i(t),\psi_j(t-\tau_{ij}^{(a)})\right)\right),\qquad a=1,\ldots,M,\\
\dot{\psi}_i(t)
&=L_i\!\left(\psi_i(t),\boldsymbol\nu_{1,i}\mathbf c_i(t)\right)+\boldsymbol\nu_{2,i}\mathbf c_i(t)+g\!\left(\psi_i(t)\right)\xi_i(t).
\end{aligned}
$$

The quantity $c_i^{(a)}$ measures the input arriving through pathway $a$.
For each connected source node $j$, the {term}`presynaptic transformation`
$S^{(a)}$ combines the current state
$\psi_i(t)$ at the receiving node with the source state delayed by
$\tau_{ij}^{(a)}$. The result is weighted by $W_{ij}^{(a)}$.
The {term}`postsynaptic transformation` $Z^{(a)}$ acts on the resulting sum. These
transformations include nonlinear responses [@sanzleon2015]. We write the pathway
inputs together as
$\mathbf c_i(t)=(c_i^{(1)}(t),\ldots,c_i^{(M)}(t))^{\mathsf T}$.

The pair $\boldsymbol\nu_i=(\boldsymbol\nu_{1,i},\boldsymbol\nu_{2,i})$
specifies how these inputs enter the equations at node $i$. Each map has a
column for every pathway and a row for every component of the state vector.
Its entry in row $k$, column $a$ sets how strongly the assembled pathway
input $c_i^{(a)}$ affects state component $k$. The matrix products in the
network equation sum over pathways at each state component:

$$
\bigl(\boldsymbol\nu_{r,i}\mathbf c_i(t)\bigr)_k
=\sum_{a=1}^{M}(\boldsymbol\nu_{r,i})_{ka}c_i^{(a)}(t).
$$

A state component receives the sum of its selected pathway contributions. The first
map passes weighted inputs into the local dynamics $L_i$, while the second
adds them directly to the state derivative. This lets the local equations and the
coupling arrangement vary between nodes. TVB's
[coupling functions](https://docs.thevirtualbrain.org/api/tvb.simulator.coupling.html)
apply the source and receiving transformations [@sanzleon2015].

Stochastic forcing $g(\psi_i)\xi_i(t)$ enters the state equation outside the
coupling contributions. When $g$ is constant, the noise is
{term}`additive noise <Additive noise>`; when it depends on $\psi_i$, it is
{term}`multiplicative noise <Multiplicative noise>`.

The familiar additive form is obtained by taking two pathways: local cortical
coupling $\ell$ and long-range white-matter coupling $g$. In the
{term}`homogeneous connectivity` approximation, local weights $w_{ik}$ depend
on cortical distance. The long-range weights $W_{ij}$ vary across pairs of
brain regions, as in {term}`heterogeneous connectivity` [@hashemi2025]. For a single
receiving activity variable, we set $\boldsymbol\nu_{1,i}=\mathbf 0$ and
$\boldsymbol\nu_{2,i}=(1,1)$, so the additive input is
$c_i^{(\ell)}+c_i^{(g)}$. If both $Z^{(a)}$ are the identity, both
$S^{(a)}$ are the same pairwise function $S$, and the weights are written
$W_{ik}^{(\ell)}=w_{ik}$ and $W_{ij}^{(g)}=W_{ij}$, the equation becomes

$$
\begin{aligned}
\dot{\psi}_i={}&L_i\!\left(\psi_i\right)\\
&+\sum_{k\in\mathcal N_i^{(\ell)}}w_{ik}S\!\left(\psi_i, \psi_k(t-\tau_{ik})\right)\\
&+\sum_{j\in\mathcal N_i^{(g)}}W_{ij}S\!\left(\psi_i,\psi_j(t-\tau_{ij})\right)+g(\psi_i)\xi_i(t).
\end{aligned}
$$

In the expanded equation, undelayed states omit the time argument.
Here $L_i(\psi)=L_i(\psi,\mathbf 0)$, and $\tau_{ij}$ denotes the propagation delay on the relevant pathway
[@wang2024; @hashemi2025]. For models with other coupling forms, see the
[Model Zoo](../model-zoo/intro.md).

## Neural mass models

A neural mass represents a population through a small set of state variables,
such as mean firing rate or mean membrane potential. Mean-field averaging is
one way to obtain such a description. Its equations define the local dynamics
$L_i$ at node $i$. In a regional
simulation, each brain region has a neural mass; the chosen connectivity
pathways supply coupling between regions.

At [finer cortical resolution](hr/classic.md), TVB places neural masses at the vertices of a
surface mesh and couples nearby vertices. Their activity still forms a
discrete system, approximating a continuous {term}`neural field <Neural field model>`
on the cortical sheet. Local coupling is evaluated as a sum over connected
vertices [@spieglerJirsa2013; @sanzleon2015]. See the
[Model Zoo](../model-zoo/intro.md) for details on the neural mass models
implemented in TVB.

## Neuroscientific basis

At each node, $L_i$ describes excitatory–inhibitory interactions, synaptic
filtering, or other local population processes according to the chosen model.
Anatomical constraints enter through coupling: nearby
cortical vertices interact along the folded surface, and white-matter
pathways link distant brain regions. A parcellation defines the brain regions
used as nodes. Estimated tract weights inform coupling strength, while tract
lengths and conduction speed determine propagation delays. Local dynamics
and delayed structural input together shape the network's spatiotemporal activity
[@sanzleon2015; @wang2024]. These anatomical inputs are described in
[connectivity](bb-connectivity.md).

The choice of additional connectivity pathways follows the physiology under
study. {term}`Diffusion MRI` estimates white-matter pathways and their relative
weights. In models that distinguish excitation and inhibition, their
projection patterns supply separate synaptic inputs. Neuromodulatory effects
alter local excitability or the gain of those inputs and it can be informed by receptor maps inform [@preti2026; @dangelo2026].

Local circuitry varies across brain regions. For a simulation spanning cortical and subcortical regions, $L_i$ specifies the population model
assigned to each node. In one TVB application, a
cerebellar mean-field model was coupled to neural masses elsewhere in the
network [@lorenzi2025; @dangelo2026].

Neural populations fluctuate at rest, even without an imposed stimulus. Neural mass does not explicitly describe all the processes and hence, the rest are approximated via noise. In TVB's usual stochastic integration,
{term}`additive noise <Additive noise>` and
{term}`multiplicative noise <Multiplicative noise>` act as
stochastic forcing of the state equations. The integrator applies the noise
increment to the state update [@sanzleon2013].

An {term}`observer model <Observer model>` maps simulated neural activity to
EEG, MEG, or fMRI measurements.

## Mathematical nomenclature

In the equation, $i$ indexes the receiving brain region and $j$ a contributing
brain region. For a cortical surface model, they index vertices. Each
connectivity pathway has its own weights, delays, and coupling transformations.

| Symbol | Meaning |
| --- | --- |
| $i$ | Brain region represented by node $i$, or a cortical vertex in a surface model. |
| $\psi_i(t)$ | State vector of the neural population at node $i$ and time $t$. |
| $k$ | Index of a component of the state vector at node $i$. |
| $L_i$ | Local neural mass dynamics at node $i$, with coupling contributions as arguments; $L_i$ varies across nodes when local models differ. |
| $M$, $a$ | Number of connectivity pathways and the index of one pathway. |
| $\mathbf c_i(t)$ | Vector of pathway inputs $(c_i^{(1)}(t),\ldots,c_i^{(M)}(t))^{\mathsf T}$ at node $i$. |
| $\boldsymbol\nu_i=(\boldsymbol\nu_{1,i},\boldsymbol\nu_{2,i})$ | Pair of weighted routing maps for coupling within $L_i$ and for direct additive coupling. |
| $(\boldsymbol\nu_{r,i})_{ka}$ | Weight of pathway $a$ at state component $k$ in routing map $r$ ($r=1$ for local dynamics, $r=2$ for direct addition). |
| $\mathcal N_i^{(a)}$ | Nodes contributing to node $i$ through pathway $a$. |
| $W_{ij}^{(a)}$ | Weight from node $j$ to node $i$ in pathway $a$. |
| $\tau_{ij}^{(a)}$ | Transmission delay from node $j$ to node $i$ in pathway $a$. |
| $S^{(a)}$ | Presynaptic transformation of each source-to-target contribution before weighted summation in pathway $a$. |
| $Z^{(a)}$ | Postsynaptic transformation of the summed incoming activity in pathway $a$. |
| $c_i^{(a)}(t)$ | Coupling contribution from pathway $a$ to node $i$ at time $t$. |
| $\ell$, $g$ | Local cortical and long-range pathway labels; the superscript $g$ is separate from the noise amplitude $g(\psi_i)$. |
| $w_{ik}$, $W_{ij}$ | Local cortical and long-range connection weights in the expanded equation. |
| $g(\psi_i)$ | Noise amplitude; constant for additive noise and state dependent for multiplicative noise. |
| $\xi_i(t)$ | Stochastic forcing of the state dynamics at node $i$. |
