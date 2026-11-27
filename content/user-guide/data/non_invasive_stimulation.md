---
title: Non-invasive brain stimulation
bibliography:
  - content/references.bib
---

# Introduction

Non-invasive brain stimulation (or NIBS for short) is a very important neuromodulation technique that has gained traction in recent decades. It has applications both in basic neuroscientific research, as well as in clinical practice. In the latter case, NIBS techniques are applied or are currently under investigation in neuropsychiatric disorders as diverse as depression, obsessive-compulsive disorder (OCD), schizophrenia, dementia, ADHD and many others.

In this document we are going to focus mainly on electromagnetic NIBS techniques, which can be broadly split into the following (non-exhaustive) subcategories:
* Transcranial Electric Stimulation (TES)
  * tDCS (transcranial direct current stimulation)
  * tACS (transcranial alternating current stimulation)
  * tTIS (transcranial temporal interference stimulation)
  * tRNS (transcranial random noise stimulation)
  * tPCS (transcranial pulsed current stimulation)
* Transcranial Magnetic Stimulation (TMS)
  * spTMS / ppTMS (single /paired pulse TMS)
  * rTMS (repetitive TMS)
  * TBS (Theta-burst stimulation)

In the context of NIBS therapies, one could also mention Electroconvulsive Therapy (ECT), which is technically non-invasive, since it is applied via scalp electrodes, but it has a much larger field amplitude than the aformentioned techniques, therefore working on completely different principle.

The main physical quantity which mediates the effect of the stimulation is the *externally induced* electric/magnetic field in TES/TMS respectively. We must emphasize that this field must not be confused with the *intrinsic* electromagnetic field of the brain, which is produced by its internal neuronal activity. The external field has as its source the stimulation apparatus (e.g. an externally injected current via scalp electrodes in TES or an externally generated magnetic field by the coils of the TMS device).

In order to simulate the effects of NIBS on the intrinsic neuronal activity of the brain, one can apply simulated external stimuli to the virtual brain network of TVB. For this purpose one needs to calculate the external electromagnetic field applied by the stimulation device. These types of calculations fall into the domain of Computational Electromagnetics (CEM), which is an entire scientific field on its own. Here we will just mention the very basic tools that are required for a standard user to calculate the stimulation fields, and we will show how to apply them to the TVB simulation framework.

# Electromagnetic solvers for brain stimulation

## Physicomathematical background
Electromagnetic fields are described in general by Maxwell's equations:

\begin{align*}
\nabla\times\vec{H}&=\vec{J}+\frac{\partial\vec{D}}{\partial t}\\
\nabla\times\vec{E}&=-\frac{\partial\vec{B}}{\partial t}\\
\nabla\cdot\vec{D}&=\rho\\
\nabla\cdot\vec{B}&=0
\end{align*}

where
* $\vec{E}$: is the electric field
* $\vec{D}$: is the dielectric displacement field (or electric flux density)
* $\vec{H}$: is the magnetic field
* $\vec{B}$: is the magnetic induction field (magnetic flux density)
* $\vec{J}$: is the electric current density
* $\rho$: is the electric charge density


In {term}`linear <Linear material>` {term}`isotropic <Isotropic material>` media we also have the following constitutive relations between the pairs $(\vec{E},\vec{D})$ and $(\vec{H},\vec{B})$:

\begin{align*}
\vec{D}=\varepsilon\vec{E}\\
\vec{B}=\mu\vec{H{}}
\end{align*}

where $\varepsilon$ is the dielectric permittivity and $\mu$ is the magnetic permeability of the medium.

It is crucial to understand that the electric current density $\vec{J}$ inside a given medium is actually composed of two components:

\begin{equation}
\vec{J}=\vec{J}_s+\vec{J}_r
\end{equation}

* $\vec{J}_s$ is the *source* current (sometimes also called *imprinted* current), which is the actual and only source of the electromagnetic fields.
* $\vec{J}_r$ is the *induced* or *ohmic* current that flows through imperfect conductors and follows Ohm's law (in point form), which in case of {term}`linear <Linear material>` {term}`isotropic <Isotropic material>` media takes the form:

\begin{equation}
\vec{J}=\sigma \vec{E}
\end{equation}

where $\sigma$ is the conductivity of the medium.

Although brain tissue is, strictly speaking, neither linear nor isotropic, many CEM solvers make this assumption as a first approximation (although, some solvers and many papers in the literature take into account the anisotropy of {term}`white matter <White matter>` by replacing the scalars $\varepsilon, \sigma$ by *tensors* $\bar{\bar\varepsilon}, \bar{\bar\sigma}$).

## The quasi-static approximation

The most important approximation that most of the literature and CEM solvers make for studying/calculating EM fields in brain tissue is the so-called electro-quasistatic (EQS) approximation. In summary, what this approximation does is to effectively *decouple* the electric from the magnetic field, which in the general and exact form of the first two Maxwell's equations are coupled. The main biophysical rationale behind this approximation is that at **low frequencies** one can ignore inductive and capacitive effects (i.e. the time derivative terms in Maxwell's equation). A detailed exposition of this argument can be found in @plonsey1967considerations, for a more recent review of the various approximations of Maxwell's equations in brain stimulation see also @perez2023review. 

The most basic form of this approximation turns out to be

\begin{align*}
\nabla\times\vec{H}&=\vec{J}_s+\sigma\vec{E}\\
\nabla\times\vec{E}&=0\\
\nabla\cdot\vec{D}&=\rho\\
\nabla\cdot\vec{B}&=0
\end{align*}

The second equation tells us that in the EQS approximation the electric field is *irrotational* (another term is *conservative*), which means that although it is a vector, it can be purely derived from a scalar potential $v$, i.e.

$$
\vec{E}=-\nabla v
$$

Plugging this into the first equation and taking the divergence gives us the final form of the EQS approximation:

\begin{equation*}
\nabla\cdot(\sigma\nabla v)=-\nabla\cdot\vec{J}_s
\end{equation*}

This equation is sometimes called a generalized (or variable coefficient) non-homogeneous **Poisson equation**.

**Note**: For TMS, a related, but slightly different form of approximation is used, which does not neglect induction. It is called the magneto-quasistatic approximation (MQS) and has the form

\begin{equation*}
\nabla\cdot(\sigma\nabla v)=-\nabla\cdot\left(\sigma\frac{\partial\vec{A}}{\partial t}\right)
\end{equation*}

where $\vec{A}$ is the vector magnetic potential generated by the TMS coils (i.e. a given source quantity). Sometimes a further approximation, called MQS $\phi$-formlatoin for TMS is used, see @perez2023review.

Most CEM solvers calculate the potential function $v$ and derive the electric field $\vec{E}$ from its gradient. However, it is imporant to note here that **the potential $v$ has no intrinsic physical meaning**, since it is arbitrary up to an additive constant $c$ (i.e. any potential function $v+c$ yields the same E-field). Only the **potential difference** $\Delta v$ has a well-defined, (bio-)physical meaning.

**Warning**: The quasi-static approximation is only valid under certain conditions, and only in the low frequency regime (the physiological activity of the brain and stimulation frequencies up to the lower kHz regime are usually considered valid for this approximation). If the stimulation fields exceed this frequency range, the results of the solvers that rely on this approximation mabe too inaccurate.

## Spatiotemporal separation

One very important aspect of the EQS approximation is that it effectively separates the spatial from the temporal variation of the fields. As you will notice, the equation satisfied by the electric potential in biological tissues $(\nabla\cdot(\sigma\nabla v)=-\nabla\cdot\vec{J}_s)$ does not involve any temporal derivatives. Let us assume that the source current has a separable form

$$
\vec{J}_s(\vec{r},t)=\vec{J}_0(\vec{r})s(t)
$$
where $\vec{J}_0(\vec{r})$ is a static (or *DC* current) and $s(t)$ is an arbitrary signal that modulates its amplitude in time. Then the solution to the Poisson equatoin is
$$
u(\vec{r},t)=u_0(\vec{r})s(t)
$$
where $u_0(\vec{r})$ is the static (or *DC*) solution to the time-independent boundary value problem

\begin{equation*}
\nabla\cdot(\sigma\nabla v_0)=-\nabla\cdot\vec{J}_0
\end{equation*}

Most of the CEM solvers actually compute the static solution $v_0$ (and the derived static E-field $\vec{E}_0=-\nabla u_0$), and the temporal variability of the field is just a multiplication with a scalar signal $s(t)$:

$$
\vec{E}(\vec{r},t)=\vec{E}_0(\vec{r})s(t)
$$

## Numerical methods for calculating stimulation fields

Most CEM solvers for biophysical applications utilize one of the following numerical methods:
* The [Finite Element Method](https://en.wikipedia.org/wiki/Finite_element_method) (FEM)
* The [Boundary Element Method](https://en.wikipedia.org/wiki/Boundary_element_method) (BEM)
* The [Finite Difference Method](https://en.wikipedia.org/wiki/Finite_difference_method) (FDM)
* The [Finite-Difference Time-Domain method](https://en.wikipedia.org/wiki/Finite-difference_time-domain_method) (FDTD)

Since this tutorial is not about *CEM*, we will not describe the above methods in detail (see linked articles). For the quasi-static regime usually the FEM and BEM are common choices. The main properties, advantages and disadvantages of FEM vs BEM methods are listed below:


| Aspect | Finite Element Method (FEM) | Boundary Element Method (BEM) |
|---|---|---|
| **Discretization** | Discretizes the volume of the solution domain into volumetric finite elements (e.g., tetrahedra). | Discretizes the boundaries of the solution domain into finite surface elements (e.g., triangles). |
| **Resulting system** | Reduces the problem to a large, sparse linear system. | Reduces the problem to a comparatively smaller, dense linear system. |
| **Unbounded domains** | Requires truncation of the computational domain and the application of appropriate boundary conditions at the artificial boundaries. | Can handle unbounded domains naturally, without artificial domain truncation or termination boundary conditions. |
| **Material properties** | Can accommodate spatially varying and inhomogeneous material properties. | Typically assumes homogeneous or piecewise-homogeneous material properties within each subdomain. |
| **Field evaluation** | Provides potentials and electric fields throughout the discretized volume; field values at arbitrary points can be obtained through interpolation. | Field values inside the solution domain are obtained through post-processing, typically by evaluating integrals over the discretized boundaries. |

## Open source software for non-invasive brain stimulation

Currently the most popular, actively or partially maintained open source **CEM** solvers for **NIBS** are all using the FEM method. A list with the most important candidates is found below:

| Name | Main application domain | MRI-to-FEM geometry preprocessing included? | Underlying FEM library / method | Reference paper | Maintenance status |
|---|---|---|---|---|---|
| [SimNIBS](https://simnibs.github.io/simnibs/build/html/) | TES and TMS electric-field modelling and optimization | Yes. CHARM provides automated MRI segmentation and tetrahedral head meshing | Native FEM implementation; Gmsh for mesh generation. Older versions used getDP | @Windhoff2013; @saturnino2019simnibs | Actively maintained; SimNIBS 4.6.0 released in March 2026 |
| [ROAST](https://www.parralab.org/roast/) | TES/tDCS electric-field modelling and optimization | Yes. Automated MRI segmentation, electrode placement and tetrahedral meshing | getDP FEM solver; iso2mesh for mesh generation | @Huang2019 | Maintained; ROAST 4.0 released in September 2025 |
| [SCIRun / BrainStimulator](https://github.com/SCIInstitute/BrainStimulator) | TES/tDCS and TMS simulation workflows | Partially. Geometry preparation is supported through external tools such as Seg3D and BioMesh3D; not a fully automated MRI-to-head-model pipeline | SCIRun's native FEM modules and linear-system solvers | @Dannhauer2012 | Mixed: SCIRun remains actively developed, but maintenance of the BrainStimulator-specific package is unclear |

# Interfacing stimulation field data with TVB

The coupling between electromagnetic fields and neural mass models (i.e., the nodes of a TVB network) remains an active area of research. Several challenges contribute to this:

- **Population-level biophysical modelling:** The mechanisms by which externally applied electric fields interact with heterogeneous populations of neurons, and how these interactions should be represented at the neural-mass level, are not yet fully understood. Simplified approaches exist, but their assumptions and applicability across different neuronal populations remain open questions.
- **Spatial heterogeneity within network nodes:** Depending on the anatomical extent of each TVB node, the electric-field distribution may exhibit substantial spatial variations in both magnitude and direction. Consequently, reducing the field distribution to a single representative value or vector for each node may overlook relevant local variations.
- **Neuronal orientation:** The interaction between an external electric field and neuronal activity depends strongly on the orientation of the field relative to neuronal structures. In simplified models, membrane polarization is often assumed to be greatest when the field is aligned with the principal neuronal axis. However, defining a representative neuronal orientation can be challenging in anatomically heterogeneous regions, including many subcortical structures.
- **Tissue-specific effects:** Gray and white matter may exhibit different field–neuron coupling properties due to differences in cellular composition, neuronal and axonal organization, and electrical conductivity. In particular, the anisotropic conductivity and highly organized fibre architecture of white matter can influence both the local electric-field distribution and its interaction with neural structures.

As an entry point to applying stimulation fields on TVB simulations we will assume that the user has already obtained an electric field dataset in the form of a NIfTI file in the native T1-space of the subject, containing for each voxel the three components of the electric field $(E_x, E_y, E_z)$. This effectively means that we know the electric field vector $\vec{E}(\vec{r})$ in every point $\vec{r}$ in the white and gray matter.

The crucial steps for coupling the external E-field with the TVB are:

- Identify the equations of the **neural mass model** that accept a stimulation input
- Determine the way the electric field distribution inside the volume represented by a neural mass maps onto the stimulus terms on the r.h.s. of the state equations.

## How to identify and set which state equations can be stimulated

### Classic `Simulator`: you target the equation directly

In the classic framework, the model itself declares which state variables receive external input through the `stvar` attribute. It holds indices into `state_variables`, and if you leave it unset the model falls back to `cvar` during configuration:

```python
if self.stvar is None:
    self.stvar = self.cvar.copy()
```

To choose a target, assign the attribute before calling `run()`:

```python
model.stvar = numpy.r_[4]        # stimulus is added to d(y4)/dt
```

`stvar` is a plain class attribute, not a validated trait, so indices are only checked when the simulation indexes the array. You can reach **any** state variable in `0 .. nvar-1`; an out-of-range index raises `IndexError` at runtime.

---

### Hybrid `Subnetwork`: you target a coupling slot

In the hybrid framework the situation is different, because the integrator's stimulus channel is not used at all. Instead, stimuli are added to the subnetwork's coupling buffer, and the model's `dfun` decides which equation that buffer row feeds.

To identify what you can stimulate, inspect the model's `dfun` and look for the coupling rows it actually reads (for example `coupling[0, :]`). The number of allocated slots equals `len(model.cvar)`, but the number of *usable* slots equals `len(coupling_terms)`, and these two counts do not always agree.

To choose a target, set `Stim.target_cvar`, or pass `stimulus_cvar=` to `add_stimulus()`. The value is a coupling slot index, not a state variable index:

```python
subnet.add_stimulus(stimulus=pat, stimulus_cvar=np.r_[0])   # slot 0, not state 0
```

In a hybrid simulation `stvar` is ignored, silently. Use `target_cvar` instead, and note that you can only reach equations the model already wires to a coupling slot.

---

### Side-by-side comparison

| | Classic | Hybrid |
|---|---|---|
| Attribute to set | `Model.stvar` | `Stim.target_cvar` |
| Index space | state variables | coupling slots |
| Valid range | `0 .. nvar-1` | `0 .. len(cvar)-1` |
| Failure mode | `IndexError` (loud) | silent no-op if `dfun` ignores the slot |
| Granularity | any equation | only equations wired to a slot |

---

### Model cheat-sheet

| Model | `cvar` | `coupling_terms` | Slots `dfun` reads | Stimulable equations |
|---|---|---|---|---|
| `JansenRit` | `[1, 2]` | 1 | `0` | `y4` only |
| `WilsonCowan` | `[0, 1]` | 1 | `0` | `E` only |
| `Generic2dOscillator` | `[0]` | 1 | `0` | `V` |
| `ReducedWongWang` | `[0]` | 1 | `0` | `S` |
| `SupHopf` | `[0, 1]` | 2 | `0, 1` | `x`, `y` |
| `CerebellarMF` | `[0, 1]` | 2 | `0, 1` | mossy, parallel |
| `ReducedSetFitzHughNagumo` | `[0, 2]` | — | `0, 1` | 2 of 4 |

---

### How to decide

Use the classic `stvar` when you need to reach a specific equation, since it gives access to every state variable. Use the hybrid `target_cvar` when the model already exposes the pathway you need as a coupling slot.

Watch out for models where `len(cvar)` exceeds `len(coupling_terms)` — `JansenRit`, `WilsonCowan`, `CoombesByrne`, `DumontGutkin`, `GastSchmidtKnosche_SD` and `_SF`. The hybrid validator only checks the index against `len(cvar)`, so `target_cvar=1` on `JansenRit` passes validation and then does nothing.

## Determining the influence of the E-field

Let us assume for now that we have chosen a neural mass model with at least one state equation that accepts an external input (e.g. Montbrió–Pazó–Roxin or MPR for short). Depending on the model, we are still **not allowed** to identify that input directly with the ohmic current induced by the stimulation, whose density is given by $\vec{J}=\sigma\vec{E}$. The user must define a biophysical model that converts the electric field distribution $\vec{E}(\vec{r})$ into a stimulation term in each parcel $i$. That is, we need a functional $\mathcal{F}$ that maps the field $\vec{E}(\vec{r})$ defined on the parcel $i$ ($\vec{r}\in V_i$) onto a single scalar $w_i$:
$$
\mathcal{F}:L^2(V_i;\mathbb{R}^3)\to\mathbb{R}
$$
such that
$$
\mathcal{F}[\vec{E}]=w_i
$$

We call $w_i$ the **stimulation weight** of parcel $i$. It is not necessarily a current: depending on the model it may be a membrane-potential offset, an additive current, a shift of the mean drive, or a modulation of a gating variable. It is also not necessarily positive, because the polarity of the field relative to the neuronal axis carries the sign of the effect. Its units are therefore model-dependent, and what the state equations do with $w_i$ is a separate modelling choice, taken up under "Where the term enters the state equations" below.

The rest of this subsection surveys the functionals $\mathcal{F}$ that have actually been used in the literature. Every row of the table below produces the same object, a scalar $w_i$ attached to parcel $i$; the rows differ only in how the field distribution over $V_i$ is reduced to that scalar.

### Functionals used in the literature

The temporal part of the coupling is rarely controversial: under the quasi-static approximation the field separates as $\vec{E}(\vec{r},t)=\vec{E}_0(\vec{r})s(t)$, so a functional acts on the static field and the time course $s(t)$ is carried through unchanged. Almost all disagreement in the literature concerns the choice of $\mathcal{F}$.

| # | Functional | Form | Neural mass model | Modality | Where the result enters | Representative work |
|---|---|---|---|---|---|---|
| [F1](#insertion-1) | Signed normal projection, membrane offset ($\lambda$-$E$) | $w_i=\lambda\,\langle\hat{\mathbf{n}}\cdot\vec{E}_0\rangle_{V_i}$ | Jansen–Rit, Wendling | tDCS, tACS | voltage offset added to the mean membrane potential of each subpopulation, inside its sigmoid | [@ruffini2013tcs; @merlet2013oscillatory; @molaeeardekani2013tdcs] |
| [F2](#insertion-2) | Signed normal projection, firing-rate shift | $w_i=\dfrac{\lambda}{A h_e}\,\langle\hat{\mathbf{n}}\cdot\vec{E}_0\rangle_{V_i}$ | Jansen–Rit | tDCS | additive mean firing rate entering the pyramidal population via the excitatory interneuron path | [@kunze2016tdcs] |
| [F3](#insertion-3) | Vector dipole projection | $w_i=\big\langle\boldsymbol{\lambda}\cdot\vec{E}_0\big\rangle_{V_i}$ with $\boldsymbol{\lambda}=\lambda\,\hat{\mathbf{n}}$ | MPR / NMM2 | tACS, tDCS | additive current $I_E$ in the mean-potential equation | [@ruffini2022exact; @clusella2023comparison] |
| [F4](#insertion-4) | Frequency-dependent transfer | $w_i(f)=\hat{Z}_i(f)\,\tilde{E}_i(f)$ from a ball-and-stick cable | AdEx / EIF mean field | tACS | additive current to an AdEx/EIF mean field | [@aspart2016extending; @cakan2020biophysically] |
| [F5](#insertion-5) | Distribution-aware functional (proposed, not implemented) | $w_i=\big\langle f(\boldsymbol{\lambda}\cdot\vec{E}_0)\big\rangle_{V_i}$ over an orientation distribution | MPR / NMM2 | tACS, tDCS | not an additive drive: absorbed into the quenched-noise width $\Delta$ of the Lorentzian | [@ruffini2022exact; @clusella2023comparison] |
| [F6](#insertion-6) | Signed normal projection, gating modulation | $w_i=\lambda\,\langle\hat{\mathbf{n}}\cdot\vec{E}_0\rangle_{V_i}$ | Reduced Wong–Wang (Deco MFM) | tDCS | additive term $\theta(i)=k\,w_i\,s(t)$ in the synaptic gating equation | [@dong2025tdcs] |
| [F7](#insertion-7) | Spherical-harmonic response, per-population offset | $w_{i,p}=\lambda_p\,\langle\hat{\mathbf{n}}\cdot\vec{E}_0\rangle_{V_i}$ with $\lambda_p$ from $\Phi(\theta,\varphi)$ | Wendling / Lopez-Sola (162 VEP parcels) | tDCS | voltage offset added to each subpopulation's membrane potential, scaled by a calibrated gain $G_E$ | [@mercadal2026wholebrain] |

### Spatial resolution

The table above says nothing about the spatial resolution at which the functional is evaluated, and this matters for how the result can be used. Two resolutions have to be distinguished:

- **Field resolution.** The resolution of the mesh on which $\vec{E}_0$ is computed and on which $\mathcal{F}$ is evaluated. This is typically fine: FEM head models routinely use $10^5$–$10^6$ elements, and the surface meshes carry $10^4$–$10^5$ vertices.
- **Network resolution.** The resolution at which neural mass models are instantiated. In every work surveyed here this is a coarse anatomical parcellation, typically 66–74 regions.

In all the works listed, the pipeline is *fine field mesh → coarse parcellation → neural mass*, so the functional is evaluated at high resolution and then collapsed to one scalar per parcel before it reaches the state equations. [@merlet2013oscillatory] is explicit about this: the normal field component is computed on each of 189,494 triangles of the white/grey matter interface and then averaged over 66 macro-regions. [@kunze2016tdcs] likewise map the field onto 16,384 surface vertices and then collapse roughly 30,000 finite elements into each of 74 areas.

No work in this table places neural mass models on the vertices of the cortical surface. That regime, in which each vertex carries its own neural mass and receives its own $w_i$, is not represented in the literature surveyed here, and it is precisely the regime in which the parcel-averaging problems discussed below would disappear. Note that this is not merely a matter of accuracy: as [point 3](#insertion-3) explains, the exactness of the mean-field closure depends on the input being homogeneous across the population, which parcel-level reduction imposes by construction.

### Where the term enters the state equations

The seven insertion points below correspond one-to-one to the rows of the table: point $n$ implements F$n$, and each row number links to its point. In every case the stimulation term is $w_i\,s(t)$. What differs is which equation receives it, and in what form.

(insertion-1)=
1. **Voltage offset inside the sigmoid (F1).** Add $w_i\,s(t)$ to the membrane potential of the target subpopulation before the sigmoid, so that it reads $S\!\left(\sum_s v_s+w_i\,s(t)\right)$. In TVB, `JansenRit` exposes only `y4`; to offset a different subpopulation you must extend `cvar`. The offset is a lumped, semi-empirical quantity. It can be applied to more than one subpopulation: [@molaeeardekani2013tdcs] add a separate term to each of the three subpopulations $X\in\{P,I,I'\}$ (pyramidal, fast and slow interneurons) with independent coefficients, whereas [@merlet2013oscillatory] restrict it to pyramidal cells. The laminar NMM (LaNMM) extends this to a layered cortical column with an explicit physical layer for field application and forward modelling [@sanchez-todo2023physical].

(insertion-2)=
2. **Additive mean firing rate (F2).** Add $w_i\,s(t)$ to the input firing rate of the pyramidal population, entering through the excitatory interneuron path. The weight carries an extra factor $1/(A h_e)$, with $A$ the excitatory synaptic gain and $h_e$ the maximum excitatory postsynaptic potential, which converts a voltage offset into a rate. This is not interchangeable with point 1: an offset acts on the sigmoid's argument, whereas a rate acts on the input to the excitatory interneuron mass. The authors do compute an intermediate offset $\hat{u}_{\text{tDCS}}\,\zeta_i$, capped at $|4|\ \text{mV}$ (30 mV/mm), but it never enters the state equations: it is divided by $A h_e$ to give the rate, which is added to $p_{\text{in}}=p_0+m_{\text{tDCS}}+\gamma W_{\text{het}}S(Ju_{\text{Py}})$ [@kunze2016tdcs].

(insertion-3)=
3. **Additive current in the mean-potential equation (F3).** Add $I_E(t)=w_i\,s(t)$ to the voltage equation of MPR/NMM2:
   $$
   \tau_m\dot{v}=\eta-(\pi r\tau_m)^2+v^2+\tau_m Js+I_E(t),
   $$
   with
   $$
   w_i=\big\langle\boldsymbol{\lambda}(\vec{r})\cdot\vec{E}_0(\vec{r})\big\rangle_{V_i},
   \qquad \boldsymbol{\lambda}(\vec{r})=\lambda\,\hat{\mathbf{n}}(\vec{r}).
   $$
   $\boldsymbol{\lambda}$ is the **dipole coupling vector** of a neuron: its magnitude is the coupling constant $\lambda$ discussed under Magnitudes below, and its direction is the cell's preferred axis — for cortical pyramidal cells the somato-dendritic axis, close to the cortical surface normal. The average is over the **product**, because $\hat{\mathbf{n}}$ belongs to each neuron, not to the parcel.

   [@ruffini2022exact] and [@clusella2023comparison] assume that all neurons in a population are equally oriented, which makes $\boldsymbol{\lambda}$ constant and the field term independent of the neuron index — the condition the mean-field closure requires. Under that assumption the field merely translates the distribution of $\eta_j$ and leaves $\Delta$ unchanged, so the reduction is exact.

   For folded cortex the assumption fails, and collapsing the field to one scalar $w_i$ replaces the distribution of $\boldsymbol{\lambda}\cdot\vec{E}_0$ by its mean. That is an approximation, because the rate is a nonlinear function of the input; it becomes exact only if the distribution is Lorentzian, in which case the spread can be absorbed into $\Delta$ rather than discarded — that is [F5](#insertion-5). Separately, where $\hat{\mathbf{n}}$ reverses inside $V_i$ the signed average cancels, since opposite sulcal walls polarize in opposite directions; only a finer parcellation or sub-parcel orientation binning fixes that.

   In TVB, `MontbrioPazoRoxin` defaults to `stvar = [1]`, which is exactly this equation, so no change is needed [@montbrio2015; @ruffini2022exact; @clusella2023comparison].

(insertion-4)=
4. **Additive input current in a linear–nonlinear cascade (F4).** Convert the field to an equivalent somatic current through the cable transfer function, then add it to the input of the excitatory population. The transfer function is frequency-dependent, so $w_i$ is a function of the stimulation frequency, $w_i(f)$. For a single-frequency protocol this is still one number per parcel; for broadband or multi-frequency stimulation it is not, and you must either evaluate it per frequency component or precompute it on a grid. [@aspart2016extending] derive the equivalent current analytically from a ball-and-stick cable neuron model and show that its amplitude grows with field frequency while the somatic sensitivity decreases; [@cakan2020biophysically] propagate it to an AdEx mean field and apply it to the excitatory population only.

(insertion-5)=
5. **Widening of heterogeneity in the rate equation (F5).** Do not add a term; change a parameter. This row is a generalisation that the cited authors propose but do not carry out: both assume a single orientation for the whole population, which is what makes F3 valid. It applies once that assumption is dropped. Let $\boldsymbol{\lambda}$ be the dipole coupling vector of a neuron, so that $\boldsymbol{\lambda}\cdot\vec{E}_0$ is its field-induced input, and let $\Delta_\lambda$ be the half-width of the distribution of that input across the population. If that distribution is Lorentzian, the total input stays Lorentzian and its half-width becomes $\Delta+\Delta_\lambda$, since Lorentzian half-widths add under convolution. Set $\Delta\to\Delta+\Delta_\lambda$; $\eta$, the centre of the distribution, is unchanged. In TVB, either set `Delta` directly, which is the faithful option, or set `stvar = [0]` and inject $\Delta_\lambda/(\pi\tau^2)$ into the rate equation, which is algebraically equivalent. Note that the default `stvar = [1]` targets the wrong equation for this case. The location shift is a separate matter and is independent of $\Delta_\lambda$: it vanishes only if orientations are isotropically distributed, whereas $\Delta_\lambda$ can be large or small either way. Note that for a Lorentzian the location parameter is the median, not the mean, since the Cauchy distribution has no finite mean [@ruffini2022exact; @clusella2023comparison].

(insertion-6)=
6. **Modulation of a gating variable (F6).** Add $\theta(i)=k\,w_i\,s(t)$ to the gating ODE, $\dot{S}_i=-S_i/\tau_S+\gamma(1-S_i)H(x_i)+\sigma v_i(t)+\theta(i)$, with $w_i=\lambda\vec{E}_{\text{normal}}(i)$. In TVB, `ReducedWongWangExcInh` exposes `I_ext`, but that parameter enters the excitatory drive $x_{ek}$, not the gating equation, so setting `I_ext` does not reproduce this coupling. The bias voltage here is a derived quantity that never enters a membrane-potential equation, which is why this is a distinct insertion point from point 1 rather than a variant of it [@deco2013resting; @dong2025tdcs].

(insertion-7)=
7. **Per-subpopulation offset from a spherical-harmonic response (F7).** Reduce the field to one value per parcel by averaging the normal component over the mesh nodes of parcel $i$, then apply a separate offset to each subpopulation $p$:
   $$
   w_{i,p}=\langle\hat{\mathbf{n}}\cdot\vec{E}_0\rangle_{V_i}\,\lambda_p\,G_E,
   $$
   with $\lambda_p=1,\ 0.35,\ 0.25,\ 0.1$ for pyramidal, excitatory interneuron, SST and PV cells. One parcel therefore receives four perturbations from a single field value. $G_E$ is a calibrated gain, not a physical constant: it absorbs both the cancellation from signed averaging of $\hat{\mathbf{n}}\cdot\vec{E}_0$ over the folded cortex and the mesoscopic amplification from cell to population level, and is fixed per subject so that the hardest-to-influence parcel responds to 0.1 V/m. Expect the signed parcel average to be small — in a 12-patient cohort its median absolute value was 0.013 V/m against a raw cortical field of about 0.1 V/m [@galan2023spherical; @mercadal2026wholebrain].

### Magnitudes

The coupling constant $\lambda$ has units of length, and is best read as a membrane displacement per unit field. Direct measurements in rat hippocampal slices give $0.12\pm0.05\ \text{mV}$ per $\text{mV/mm}$ at the soma [@bikson2004uniform]. Compartment-model reconstructions of neocortical cells give $0.14\ \text{mV}$ per $\text{V/m}$ for layer 5 thick-tufted pyramidal cells, $0.10$ for layer 6 tufted cells and $0.07$ for untufted cells [@galan2023spherical]. Whole-brain tDCS models typically adopt $\lambda\approx 0.13$ together with the normal field component, and cap the resulting polarization at $|4|\ \text{mV}$ [@dong2025tdcs].

With typical tES field strengths of $0.2$–$2\ \text{V/m}$ [@ruffini2013tcs], the resulting weight $w_i$ corresponds to a membrane perturbation of order $0.02$–$0.4\ \text{mV}$, i.e. genuinely subthreshold. This is why the network-amplification argument matters. In the exact mean-field description the resonant response to a weak alternating field grows with two things: the strength of recurrent excitation *within* the population, i.e. the gain with which the population's own firing rate feeds back onto its input (the synaptic weight $J$ in the MPR equations), and the slowness of the synaptic kinetics, which gives that feedback loop memory and lets it integrate the perturbation over a longer window. A population can therefore respond measurably to a field that barely moves a single neuron [@clusella2023comparison].

### Two distinct averaging problems

Averaging a field over a parcel is often described as if it were a single problem, but there are two, and they call for different remedies.

- **Geometric cancellation.** The surface normal $\hat{\mathbf{n}}(\mathbf{r})$ reverses between gyral crowns and sulcal walls. A *signed* average of $\hat{\mathbf{n}}\cdot\vec{E}_0$ over a parcel that spans both can therefore cancel, even when the local field is large everywhere. Remedies are finer parcellation, sub-parcel orientation binning, or a fibre-aligned projection that does not rely on the cortical normal [@colella2025effective].
- **Rectification.** The map from field to membrane displacement is linear in $\vec{E}_0$, so $\lambda$ factors out and the averaging order is immaterial to first order (see [point 3](#insertion-3)). Once the map is genuinely nonlinear — as in the spherical-harmonic response, where the polarization is not proportional to the projected field — $\langle f(\hat{\mathbf{n}}\cdot\vec{E}_0)\rangle_{V_i}\neq f(\langle\hat{\mathbf{n}}\cdot\vec{E}_0\rangle_{V_i})$, and a vanishing mean field no longer implies a vanishing $w_i$. The response must then be averaged rather than the field, which is what the spherical-harmonic representation makes explicit [@galan2023spherical].

Orientation dispersion interacts with the mean-field closure in a way that is easy to overstate. Dispersion does not by itself break the Lorentzian ansatz, but it does not leave it untouched either: the closure survives only if the resulting distribution of $\boldsymbol{\lambda}\cdot\vec{E}_0$ across the population is itself Lorentzian, in which case it can be absorbed into the quenched-noise width as described under [F5](#insertion-5). For other orientation distributions — including the isotropic case, which produces a uniform rather than a Lorentzian distribution of the projected field — the closure is broken and the reduction no longer holds exactly [@ruffini2022exact; @clusella2023comparison].

### Consequences for TVB

`StimuliRegion` takes one scalar weight per region, so each functional has to collapse to a scalar $w_i$. F1, F2, F3 and F6 do so directly. F4 does so for a single-frequency protocol, where $w_i(f)$ is one number; for broadband stimulation, precompute an effective weight or subclass `StimuliRegion`. F5 is not an additive drive at all but a change to $\Delta$, so set `Delta` directly instead of using the stimulus channel.

F7 needs one weight per *subpopulation*, not per region. In the classic `Simulator` this is not expressible: `stvar` selects which equations receive the stimulus, but all of them receive the same value. In the hybrid framework, attach one stimulus per subpopulation — four `Subnetwork.add_stimulus` calls, each with its own `StimuliRegion` weight and its own `stimulus_cvar`. No subclassing is needed, and the contributions add.

Two conventions deserve to be fixed explicitly in any implementation:

- **Polarity.** A functional that takes the field magnitude rather than a signed projection discards the sign, so $w_i\ge 0$ by construction. That is fatal for tDCS, where the anodal/cathodal distinction is the entire effect.
- **Normal orientation.** The sign convention of $\hat{\mathbf{n}}$ must be stated explicitly. Reversing it flips the sign of the stimulation contribution, turning an intended depolarization into a hyperpolarization. This is the most common source of inverted results across the papers cited above.

## Worked example: F3 with the MPR model

This section walks through the full pipeline for F3 — the vector dipole projection into the mean-potential equation of MPR — starting from a NIfTI field map and ending with a configured `Simulator`. The case is tDCS, so the field is constant in time and the temporal profile is a constant.

### Inputs

Two NIfTI files in the same space, sharing header and affine:

- `E_field.nii.gz` — 4D, shape `(M, N, L, 3)`. The last axis holds the Cartesian components $(E_x, E_y, E_z)$ of the field in V/m.
- `parcellation.nii.gz` — 3D integer labels, one value per atlas parcel, `0` for background.

The parcellation must use the same label values as the region ordering of your TVB `Connectivity`. If your atlas is numbered 1..N and TVB expects 0..N-1, shift the labels.

### Step 1 — load the field and the parcellation

```python
import numpy as np
import nibabel as nib

efield_img = nib.load("E_field.nii.gz")
parc_img = nib.load("parcellation.nii.gz")

# (M, N, L, 3) float array, V/m
E = efield_img.get_fdata()
# (M, N, L) integer labels; get_fdata() always returns float64
labels = parc_img.get_fdata().astype(int)

assert E.shape[:3] == labels.shape, "field and parcellation must share a grid"
assert np.allclose(efield_img.affine, parc_img.affine), "affines must match"
```

The affine check matters: if the two files were resampled independently, the voxel indices no longer refer to the same anatomical location and every downstream average is silently wrong.

### Step 2 — load the cortical surface and its normals

F3 projects the field onto the dipole coupling vector of the population. For a cortical parcel the dominant direction is the cortical surface normal, so we take the normals from the FreeSurfer surface rather than estimating them from the parcellation.

The FreeSurfer pipeline produces, per hemisphere, a triangulated surface (`?h.white`, `?h.pial`) and a per-vertex annotation of the cortical parcellation (`?h.aparc.annot`). Vertex normals are not stored on disk. Rather than computing them by hand, read the surface with `pyvista`, which computes them from the mesh geometry:

```python
import pyvista as pv
from nibabel.freesurfer.io import read_annot

def load_surface(subject, hemi):
    """Surface mesh with vertex normals, plus per-vertex parcel labels."""
    mesh = pv.read(f"{subject}/surf/{hemi}.white")
    mesh.compute_normals(point_normals=True, cell_normals=False, inplace=True)

    labels, _, names = read_annot(f"{subject}/label/{hemi}.aparc.annot")
    return mesh, labels, names
```

`compute_normals` returns area-weighted vertex normals, which is what you want: each triangle contributes in proportion to its area, so large triangles count more than slivers. The result is available as `mesh.point_data["Normals"]`, and the vertex coordinates as `mesh.points`.

```python
mesh, labels, names = load_surface(subject, "lh")
coords = mesh.points                      # (n_vert, 3), mm, RAS
vn = mesh.point_data["Normals"]           # (n_vert, 3), unit length
```

The vertex coordinates are in FreeSurfer surface space (mm, RAS). They must be in the same space as the field, so check the transform before using them — see step 3.

### Step 3 — map the surface onto the field grid

The surface vertices and the field voxels live in different coordinate systems unless you have resampled one onto the other. The mapping is a voxel lookup: transform each vertex into voxel indices with the field's affine, round, and read the field there.

```python
def vertices_to_voxels(coords, img):
    """FreeSurfer surface coords -> nearest voxel indices in img."""
    # FreeSurfer surface space is RAS; nibabel affines are RAS too,
    # so the inverse affine maps world mm -> voxel indices directly.
    inv = np.linalg.inv(img.affine)
    homog = np.c_[coords, np.ones(len(coords))]
    vox = (inv @ homog.T).T[:, :3]
    return np.rint(vox).astype(int)
```

If your FreeSurfer subject was reconstructed from the same T1 that the field was computed on, this is exact up to rounding. If the two were processed separately, register them first — a mismatch here silently misassigns every vertex.

Guard against vertices that fall outside the field volume:

```python
vox = vertices_to_voxels(coords, efield_img)
inside = np.all((vox >= 0) & (vox < np.array(E.shape[:3])), axis=1)
```

Vertices outside the grid are usually a sign of a space mismatch rather than a genuinely out-of-brain vertex, so check the count before dropping them.

### Step 4 — project per vertex, then average over each parcel

The reduction is over the vertices belonging to each label. Project the field onto each vertex normal first, then average the resulting scalars:

```python
def parcel_projection(E, vox, vn, labels, n_parcels, inside):
    """Signed normal projection of the field, averaged per parcel."""
    E_vert = E[vox[inside, 0], vox[inside, 1], vox[inside, 2]]   # (n_vert, 3)
    n_vert = vn[inside]
    lab = labels[inside]

    w = np.zeros(n_parcels)
    for p in range(n_parcels):
        m = lab == p
        if not m.any():
            continue
        # project per vertex, then average the scalars
        w[p] = np.mean(np.einsum("vd,vd->v", E_vert[m], n_vert[m]))
    return w
```

This computes $\langle\hat{\mathbf{n}}\cdot\vec{E}_0\rangle_{V_i}$ directly. Because $\lambda$ is a scalar constant it factors out, and is applied in step 5.

What this step cannot fix is a parcel whose normals genuinely oppose each other. There the signed average cancels, because the underlying effect cancels: opposite walls of a sulcus are polarized in opposite directions. If that matters for your question, the remedy is a finer parcellation or sub-parcel orientation binning.

### Step 5 — apply the coupling constant

```python
LAMBDA = 0.13          # mV per (V/m); see the Magnitudes section
N_PARCELS = int(labels.max()) + 1

w = LAMBDA * parcel_projection(E, vox, vn, labels, N_PARCELS, inside)
```

At this point `w` is the stimulation weight per parcel, in mV. Two checks are worth running before going further:

```python
print("parcels with no vertices:", np.sum(w == 0))
print("w range (mV):", w.min(), w.max())
```

A large number of empty parcels usually means the annotation labels and the connectivity region ordering disagree. A `w` range far outside ±4 mV means `LAMBDA` is wrong for your units.

### Step 6 — fix the normal orientation

The sign of `w` determines whether a parcel is depolarized or hyperpolarized, so the normal convention must be pinned down. FreeSurfer surface normals are not consistently oriented outwards, so this step is not optional.

The physically motivated choice is that the normal points from white matter towards the cortical surface, so that a field along it depolarizes the pyramidal cells. `pyvista` can orient the mesh consistently for you:

```python
mesh = pv.read(f"{subject}/surf/{hemi}.white")
mesh.compute_normals(point_normals=True, cell_normals=False,
                     consistent_normals=True, auto_orient_normals=True,
                     inplace=True)
vn = mesh.point_data["Normals"]
```

`auto_orient_normals` orients the mesh so that normals point outwards from the enclosed volume, which is the convention we want. If you prefer to anchor the orientation to the white-to-pial direction instead, `pyvista` also exposes `mesh.flip_normals()` for a global flip, and you can select the vertices to flip yourself:

```python
pial = pv.read(f"{subject}/surf/{hemi}.pial")
outward = pial.points - mesh.points
flip = np.einsum("vd,vd->v", vn, outward) < 0
vn[flip] *= -1
```

The white-to-pial reference is more trustworthy than orienting relative to a brain centroid, which fails near the midline and in deep sulci.

State whichever convention you use, and check the sign of `w` in a parcel where you know the expected polarity.

### Step 7 — build the stimulus

tDCS is constant in time, so the temporal profile is a constant. `StimuliRegion` expects a weight of shape `(n_regions, 1)`:

```python
import numpy as np
from tvb.datatypes import patterns, equations
from tvb.simulator.lab import connectivity

conn = connectivity.Connectivity.from_file("connectivity_76.zip")
conn.configure()

assert conn.number_of_regions == N_PARCELS, (
    f"connectivity has {conn.number_of_regions} regions, "
    f"parcellation has {N_PARCELS}"
)

weights = w.reshape(-1, 1)          # (n_regions, 1)

stimulus = patterns.StimuliRegion(
    temporal=equations.Linear(parameters={"a": 0.0, "b": 1.0}),   # constant 1.0
    connectivity=conn,
    weight=weights,
)
```

`equations.Linear` with `a=0, b=1` evaluates to a constant `1.0` at every time step, which is what a DC field requires. The field magnitude is already folded into `w`, so the temporal factor must be unity; changing `b` rescales the whole stimulation.

### Step 8 — configure the simulator

MPR's `stvar` defaults to `[1]`, which is the mean-potential equation — exactly the target for F3. No change is needed:

```python
from tvb.simulator.lab import models, simulator, integrators, monitors

model = models.MontbrioPazoRoxin()
assert list(model.stvar) == [1], "F3 targets the V equation"

sim = simulator.Simulator(
    model=model,
    connectivity=conn,
    integrator=integrators.HeunDeterministic(dt=0.1),
    monitors=[monitors.TemporalAverage(period=1.0)],
    stimulus=stimulus,
).configure()

# the stimulus is now applied to dV/dt in every parcel
```

### What this pipeline does and does not do

It implements F3: a vector dipole projection, averaged over the parcel, entering the mean-potential equation as a common input. It does not resolve intra-parcel field variation, and it reduces each parcel to a single orientation — both are the approximations discussed in the preceding sections.

Three things to watch:

- **Units.** `LAMBDA` is in mV per (V/m). If your NIfTI stores V/mm, multiply by 1000 before step 5.
- **Sign.** The result is only as good as the normal convention in step 6. Verify against a montage with a known polarity before trusting the sign of any downstream effect.
- **Space.** Steps 3 and 6 both assume the FreeSurfer surface and the field share a coordinate system. If they were reconstructed or resampled independently, register them first; a mismatch misassigns every vertex without raising an error.
