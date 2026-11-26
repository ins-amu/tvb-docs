---
title: Bifurcation analysis
bibliography:
  - ../references.bib
---
# Bifurcation analysis

*Explanation — what a bifurcation diagram shows, which bifurcations matter for
neural mass models, and why mapping them is part of using a model well.*

A **bifurcation** is a qualitative change in a system's behaviour caused by a
smooth change in a parameter: a resting state that suddenly starts oscillating, or
a second resting level that appears out of nowhere. **Bifurcation analysis** is
the systematic sweep of a parameter to find where those changes happen and what
the system does on either side of them.

The reason it matters here is that neural mass models are nonlinear, and nonlinear
systems do not respond proportionally. Small parameter changes can leave the
behaviour untouched for a long stretch and then change it completely. A time
series at one parameter value tells you about that value only; the bifurcation
diagram tells you what the model is *capable* of.

## Control parameters versus state

The first distinction to get straight is between the two kinds of variable:

- **State variables** ($E$, $I$, membrane potentials, synaptic variables) change
  because of the dynamics. They are what the simulation integrates.
- **Control parameters** (drive $P$, coupling coefficients, time constants, global
  coupling $\kappa$, conduction speed) are fixed during a run. They select *which*
  dynamics the equations have.

A bifurcation diagram plots one control parameter on the horizontal axis and a
feature of the attractor on the vertical axis — the value of a fixed point, the
amplitude and period of a limit cycle, the number of coexisting attractors. Stable
branches are drawn solid, unstable ones dashed, and the points where branches
appear, disappear, or change stability are the bifurcations. Reading such a
diagram is the fastest way to learn a model: it compresses every possible time
series into one picture.

## The bifurcations that show up most often

**Saddle-node.** A stable fixed point and a saddle collide and annihilate as the
parameter crosses a critical value. The local normal form is

$$
\dot{x} = r - x^2 ,
$$

which has two fixed points for $r > 0$ and none for $r < 0$. In a mass model this
is where a *second*, high-activity resting level appears, giving bistability: two
stable states separated by the saddle's separatrix, with hysteresis if the
parameter is swept back and forth. Threshold-like "all-or-none" responses come
from the same geometry.

**Supercritical Hopf.** A stable fixed point loses stability when a
conjugate pair of Jacobian eigenvalues crosses the imaginary axis, and a stable
limit cycle appears around it. The amplitude grows continuously from zero, so the
onset of rhythm is smooth:

$$
\dot{r} = r(\mu - r^2), \qquad \dot{\theta} = \omega .
$$

This is the standard account of how a brain region begins to oscillate, and the
frequency just past the bifurcation is set by the imaginary part $\omega$ — in a
mass model, by the synaptic and population time constants.

**Subcritical Hopf.** The unstable branch lies on the side where the fixed point
is still stable, so a stable limit cycle of *finite* amplitude coexists with rest
before the fixed point loses stability. The transition is abrupt, with a jump and
hysteresis. This is the geometry behind sudden-onset phenomena — a seizure-like
transition, for instance — where the system can sit comfortably at rest and then
leave it discontinuously under a perturbation large enough to cross the separatrix.

**Infinite-period (SNIC-type) transitions.** A saddle-node occurring on a closed
orbit creates oscillation whose period diverges as the bifurcation is approached:
the frequency can be arbitrarily low. Models with this structure can oscillate
slowly or fast; Hopf-based models instead have a minimum frequency at onset. The
difference shows up immediately in what a parameter sweep produces.

(jansen-rit-diagram)=
## A worked example: the Jansen–Rit column

The [Jansen–Rit model](../reference/model-cards/jansen-rit.md) shows several
of these bifurcations along a single control parameter, the extrinsic input
$p$. Grimbert & Faugeras mapped its diagram with the published parameters
($v_0 = 6$ mV) [@grimbertFaugeras2006]. Computing the equilibria of TVB's
`JansenRit` and the eigenvalues of its Jacobian recovers their Hopf and
saddle-node points to within 0.01 pulses/s. The fold of limit cycles is taken
from the paper.

| $p$ [pulses/s] | bifurcation | consequence |
|---|---|---|
| 89.83 | supercritical Hopf on the upper branch of equilibria | a ~10 Hz limit cycle (alpha) appears |
| 113.58 | saddle-node with a homoclinic orbit on the lower branch | the lower resting state vanishes; slow, large "spike" cycles appear |
| 137.38 | fold of limit cycles | the spike cycles vanish |
| 315.70 | second Hopf | the alpha cycle shrinks to zero; the upper equilibrium is stable again |

The diagram explains the original simulations. Jansen & Rit drove the column
with noise spread uniformly over 120–320 pulses/s [@jansenRit1995]. Most of
that range lies between 137.38 and 315.70 pulses/s, where the alpha cycle is
the only attractor, so the trajectory keeps winding around the cycle that
belongs to the current input. Wendling and colleagues produced epileptic
spikes with the same equations driven by Gaussian noise of mean 90 and
standard deviation 30 pulses/s. As Grimbert & Faugeras point out, that input
spends most of its time in the bistable rest region and the spike window
[@grimbertFaugeras2006].

The diagram is also fragile. Grimbert & Faugeras found that changing the
parameters by as little as 5 % gives fairly different behaviour. TVB's default
threshold, $v_0 = 5.52$ mV instead of 6, is an 8 % change. It leaves
the lower saddle-node almost in place (about 112 pulses/s) but moves the
upper Hopf to about 516 pulses/s. At the default input of 220 pulses/s the
column then sits on a large ~7 Hz cycle rather than on the alpha cycle.
Before reusing a published operating point, check which branch the defaults
put the model on.

(coupling-and-network-rest)=
## Coupling decides what a network's resting state does

The node's diagram is only half the story in a network, because the coupling
function decides how neighbours perturb each node. The
[SupHopf (Stuart–Landau) model](../reference/model-cards/suphopf.md) makes this
explicit. Linearised around the all-quiet state, a network of $N$ identical
nodes with weights $W$ and global coupling $G$ has growth rates

- $a - G\,\ell_k$ with **diffusive** coupling, $G\sum_j w_{ij}(x_j - x_i)$,
  where the $\ell_k$ are the eigenvalues of the graph Laplacian
  $\mathrm{diag}(W\mathbf{1}) - W$;
- $a + G\,\lambda_k(W)$ with **additive** coupling, $G\sum_j w_{ij}x_j$,

where, for non-symmetric weights, the real parts of the eigenvalues count.
The Laplacian eigenvalues have non-negative real parts, so around rest
diffusive coupling can only add damping. Without delays and noise, a network
of nodes with $a < 0$ stays at rest for any $G$. Deco et al. use diffusive
coupling with their nodes at or near $a = 0$ [@deco2017]. In their model, the
connectome mainly shapes how noise-driven fluctuations spread and synchronise.
Additive coupling instead shifts the effective bifurcation parameter: once
$G\,\lambda_{max}(W) > -a$, the network oscillates although no node would
alone. Conduction delays change both cases, because a delayed neighbour is
no longer in the same state.

## Why TVB modelers map the structure

- **To choose an operating point.** A model near a bifurcation is sensitive and
  easily driven into oscillation; one far from it is damped and sluggish. Where a
  simulation sits relative to the diagram determines what perturbations, stimuli,
  and coupling will do — and global coupling $\kappa$ is itself a control
  parameter for the network.
- **To know what a model can do at all.** Two parameter sets that fit the same
  data can sit in different regimes. Regime membership is usually more
  trustworthy than a fitted number, because parameters are degenerate
  ([neural mass models](neural-mass-models.md) discusses this).
- **To read pathological transitions as bifurcations.** In seizure-oriented models
  the transition *is* the phenomenon being modelled, and the diagram — not a
  single trajectory — is the object of interest.
- **To transfer insight from node to network.** A whole-brain model is high
  dimensional and hard to analyse directly, so its behaviour is usually
  interpreted through the bifurcation structure of the *uncoupled* node plus the
  effect of coupling and delays.

For a two-dimensional model the whole story is visible geometrically: fixed points
are nullcline crossings, stability is the Jacobian's eigenvalues, and a bifurcation
is a crossing appearing, disappearing, or changing type. That is the content of the
[phase-plane explanation](phase-plane-explanation.md), and it is directly
explorable in the [phase-plane tutorial](../tutorials/phase-plane.md) — drag the
drive $P$ and watch a single fixed point become three, then become a limit cycle.
The [Wilson–Cowan model card](../reference/model-cards/wilson-cowan.md) names the
control parameters the original analysis used — the excitatory self-coupling
$c_{ee}$ and the drive $P$ [@wilsonCowan1972] — and the theory behind the
eigenvalue bookkeeping is on the
[dynamical systems theory page](dynamical-systems-theory.md).
