---
title: Mathematical Framework
bibliography:
  - ../references.bib
---

# Mathematical Framework

The Virtual Brain (TVB) represents the mesoscopic activity of neuronal populations (e.g. brain regions), and interactions between them. The evolution of the state of each node in time is governed by a neural mass model, and the connections within cortical tissue and through white matter couple these dynamics over different spatial scales. Overall, in the most generic case, TVB is formulated as a coupled set of (non-)linear stochastic delay differential equations described in detail below [@wang2024; @sanzleon2015].

## Network dynamics

Let $\psi_i(t)$ denote the state vector of the neural population at node $i$
and time $t$. The Jirsa–Haken formulation distinguishes local dynamics from
interactions within nearby tissue and through long-range connections
[@jirsaHaken1996; @jirsaHaken1997; @sanzleon2015;@wang2024;@hashemi2025]. General form of TVB equations for $M$ connectivity pathways can be written as,

$$
\begin{aligned}
c_i^{(a)}(t)
&=Z^{(a)}\!\left(\sum_{j\in\mathcal N_i^{(a)}}W_{ij}^{(a)}S^{(a)}\!\left(\psi_i,\psi_j(t-\tau_{ij}^{(a)})\right)\right),\qquad a=1,\ldots,M,\\
\dot{\psi}_i(t)
&=L_i\!\left(\psi_i(t),\boldsymbol\nu_{1,i}\mathbf c_i(t)\right)+\boldsymbol\nu_{2,i}\mathbf c_i(t)+g(\psi_i)\xi_i(t).
\end{aligned}
$$

The quantity $c_i^{(a)}$ measures the input arriving through pathway $a$.
For each connected source node $j$, activity delayed by $\tau_{ij}^{(a)}$
is transformed by $S^{(a)}$ and weighted by $W_{ij}^{(a)}$.
The receiving-side function $Z^{(a)}$ acts on the resulting sum. These
transformations can be nonlinear [@sanzleon2015]. We write the pathway
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

Several pathways can therefore contribute to the same component. The first
map passes weighted inputs into the local dynamics $L_i$, while the second
adds them directly to the state derivative. This lets the local equations and the
coupling arrangement vary between nodes. The formal
{term}`noise term <Dynamical noise>` $g(\psi_i)\xi_i(t)$ is added outside the pathway
transformations and is allowed to be state dependent (i.e., multiplicative) through the function $g(\psi_i)$. TVB's
[coupling functions](https://docs.thevirtualbrain.org/api/tvb.simulator.coupling.html)
apply the source and receiving transformations [@sanzleon2015].

The familiar additive form is obtained by taking two pathways: local cortical
coupling $\ell$ and long-range white-matter coupling $g$. For a single
receiving activity variable, set $\boldsymbol\nu_{1,i}=\mathbf 0$ and
$\boldsymbol\nu_{2,i}=(1,1)$, so the additive input is
$c_i^{(\ell)}+c_i^{(g)}$. If both $Z^{(a)}$ are the identity, both source
transformations are $S$, and their weights are written
$W_{ij}^{(\ell)}=w_{ij}$ and $W_{ij}^{(g)}=W_{ij}$, the equation becomes
(we omit explicit time-dependence of the variables for the sake of clarity, )
$$
\begin{aligned}
\dot{\psi}_i={}&L_i\!\left(\psi_i\right)\\
&+\sum_{k\in\mathcal N_i^{(\ell)}}w_{ik}S\!\left(\psi_i, \psi_k(t-\tau_{ik})\right)\\
&+\sum_{j\in\mathcal N_i^{(g)}}W_{ij}S\!\left(\psi_i,\psi_j(t-\tau_{ij})\right)+g(\psi_i)\xi_i(t).
\end{aligned}
$$

Here $L_i(\psi)=L_i(\psi,\mathbf 0)$, and $\tau_{ij}$ denotes the propagation (axonal) delay on
the relevant pathway [@wang2024]. The relevant
[model card](../reference/index.md) describes how coupling enters when a model
does not follow this additive form.

## Neural mass models

A neural mass represents a population through a small set of state variables,
such as mean firing rate or mean membrane potential. Mean-field averaging is
one way to obtain such a description. Its equations define $L_i$ at node $i$,
and different nodes may use different neural mass models. In a regional
simulation, each brain region has a neural mass; the chosen connectivity
pathways supply coupling between regions.

At finer cortical resolution, TVB places neural masses at the vertices of a
surface mesh and couples nearby vertices. Their activity still forms a
discrete system, approximating a continuous {term}`neural field <Neural field model>`
on the cortical sheet. Local coupling is evaluated as a sum over connected
vertices [@spieglerJirsa2013; @sanzleon2015]. The
[model cards](../reference/index.md) give the equations for individual TVB models.

## Neuroscientific basis

At each node, the neural mass can represent interactions between excitatory
and inhibitory populations or the effects of synaptic filtering, depending
on its equations. The effect of anatomy comes through coupling as nearby cortical vertices interact along the folded surface, while white-matter pathways link distant brain regions. A parcellation of brain regions defines the nodes; estimated tract weights and lengths inform the strength.
Together with conduction speed, tract length determines when activity from
one node reaches another. The interplay of local dynamics and delayed
structural input shapes the network's spatiotemporal activity
[@sanzleon2015; @wang2024]. These anatomical inputs are described in
[the connectome](../explanation/connectome.md).

Connectivity is selected according to the physiological interactions in the
model. Diffusion MRI estimates white-matter pathways and their relative
weights; their direction and transmitter identity require additional
anatomical evidence. Pathway-specific weights $W_{ij}^{(a)}$ can then
represent glutamatergic, GABAergic, dopaminergic, or serotonergic projections,
informed where possible by anatomical studies and receptor maps. Excitatory
and inhibitory projections contribute to synaptic drive, while
neuromodulatory projections may also change local excitability or the
efficacy of other inputs [@preti2026; @dangelo2026].

Brain regions differ in their local circuitry as well. The equations $L_i$
can reflect the cell populations and synaptic organisation of each region.
A multi-region simulation may therefore assign different local models to
neocortical, cerebellar, and subcortical nodes. In one TVB application, a
cerebellar mean-field model was coupled to neural masses elsewhere in the
network [@lorenzi2025; @dangelo2026].

Neural populations fluctuate at rest, even without an imposed stimulus.
Processes unresolved by a neural mass can perturb its trajectory; local
dynamics and structural connections shape the resulting activity
[@ghosh2008]. In TVB's usual stochastic integration,
{term}`additive noise <Additive noise>` and
{term}`multiplicative noise <Multiplicative noise>` act as
stochastic forcing of the state equations. The integrator applies the noise
increment to the state update. An {term}`observer model <Observer model>` maps simulated neural activity to EEG, MEG, or fMRI measurements. [@sanzleon2013].

## Mathematical nomenclature

In the equation, $i$ indexes the receiving brain region and $j$ a contributing
brain region. For a cortical surface model, they index vertices. Each
connectivity pathway has its own weights, delays, and coupling transformations.

| Symbol | Meaning |
| --- | --- |
| $i$ | Brain region represented by node $i$, or a cortical vertex in a surface model. |
| $\psi(t)$ | State vector of the neural population at sampled position $x_i$ and time $t$. |
| $k$ | Index of a component of the state vector at node $i$. |
| $L_i$ | Local neural mass dynamics at node $i$, which may depend on the coupling contributions; the model may vary between nodes. |
| $M$, $a$ | Number of connectivity pathways and the index of one pathway. |
| $\mathbf c_i(t)$ | Vector of pathway inputs $(c_i^{(1)}(t),\ldots,c_i^{(M)}(t))^{\mathsf T}$ at node $i$. |
| $\boldsymbol\nu_i=(\boldsymbol\nu_{1,i},\boldsymbol\nu_{2,i})$ | Pair of weighted routing maps for coupling within $L_i$ and for direct additive coupling. |
| $(\boldsymbol\nu_{r,i})_{ka}$ | Weight of pathway $a$ at state component $k$ in routing map $r$ ($r=1$ for local dynamics, $r=2$ for direct addition). |
| $\mathcal N_i^{(a)}$ | Nodes contributing to node $i$ through pathway $a$. |
| $W_{ij}^{(a)}$ | Weight from node $j$ to node $i$ in pathway $a$. |
| $\tau_{ij}^{(a)}$ | Transmission delay from node $j$ to node $i$ in pathway $a$. |
| $S^{(a)}$ | Transformation of delayed source activity in pathway $a$. |
| $Z^{(a)}$ | Receiving-side transformation of the weighted signal from pathway $a$. |
| $c_i^{(a)}(t)$ | Coupling contribution from pathway $a$ to node $i$ at time $t$. |
| $\ell$, $g$ | Local cortical and long-range pathways in the expanded equation. |
| $w_{ij}$, $W_{ij}$ | Local cortical and long-range connection weights in the expanded equation. |
| $g_i$ | Function for the state-dependency of the noise at node $i$. |
| $\xi_i(t)$ | Formal stochastic forcing added to the state dynamics at node $i$. |
