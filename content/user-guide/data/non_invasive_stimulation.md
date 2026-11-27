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
- Determine the way the electric field distribution inside the volume represented by a neural mass maps onto the stimulus terms on the r.h.s. of he state equations.

## How to identify and set which state equations can be stimulated

### Classic `Simulator`: you target the equation directly

In the classic framework, the model itself declares which state variables receive external input through the `stvar` attribute. It holds indices into `state_variables`, and if you leave it unset the model falls back to `cvar` during configuration:

```python
if self.stvar is None:
    self.stvar = self.cvar.copy()
```

To choose a target, assign the attribute before calling `run()`. Note that `stvar` is a plain class attribute rather than a validated trait, so nothing checks your indices until the simulation actually indexes the array:

```python
model.stvar = numpy.r_[4]        # stimulus is added to d(y4)/dt
```

The simulator then writes the stimulus into the derivative array at those rows, and the integrator adds it to the state update:

```python
stimulus[self.model.stvar, :, :] = self.stimulus(stim_step).reshape((1, -1, 1))
...
X_next = X + self.dt * (self.dX + stimulus)
```

Because the stimulus is injected at the derivative level, you can reach **any** state variable in the range `0 .. nvar-1`. An out-of-range index raises an `IndexError` at runtime, so mistakes are loud rather than silent.

---

### Hybrid `Subnetwork`: you target a coupling slot

In the hybrid framework the situation is different, because the integrator's stimulus channel is not used at all. Instead, stimuli are added to the subnetwork's coupling buffer, and the model's `dfun` decides which equation that buffer row feeds.

To identify what you can stimulate, inspect the model's `dfun` and look for the coupling rows it actually reads (for example `coupling[0, :]`). The number of allocated slots equals `len(model.cvar)`, but the number of *usable* slots equals `len(coupling_terms)`, and these two counts do not always agree.

To choose a target, set `Stim.target_cvar`, or pass `stimulus_cvar=` to `add_stimulus()`. The value is a coupling slot index, not a state variable index:

```python
subnet.add_stimulus(stimulus=pat, stimulus_cvar=np.r_[0])   # slot 0, not state 0
```

The subnetwork adds the stimulus into the coupling buffer and then hands the combined coupling to `dfun`. Note that the final two arguments of the integrator call are hardcoded to zero, which is why `stvar` has no effect here:

```python
internal_c[stim.target_cvar] += stim_coupling
nx = self.scheme.scheme(x, self.model.dfun, total_c, 0.0, 0.0)   # stimulus=0.0
```

Consequently, you can only stimulate equations that the model already wires to a coupling slot. I checked every hybrid module and backend, and `stvar` appears zero times, so setting it in a hybrid simulation has no effect whatsoever.

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

If you need to hit a specific ordinary differential equation in any model, use the classic `stvar`, because it gives you direct access to every state variable. If the model already exposes the pathway you need as a coupling slot, the hybrid `target_cvar` is the natural choice and keeps you inside the hybrid architecture. If the equation you want is not wired to any slot, you have two options: extend `cvar` and make `dfun` read the new slot, or fall back to the classic simulator.

One caveat is worth repeating. For seven shipped models (`JansenRit`, `WilsonCowan`, `CoombesByrne`, `DumontGutkin`, `GastSchmidtKnosche_SD` and `_SF`), `len(cvar)` is larger than `len(coupling_terms)`. The hybrid validator only checks that the index is below `len(cvar)`, so `target_cvar=1` on `JansenRit` passes validation and then does nothing at all.

## Determining the influence of the E-field

Let us assume for now that we have chosen a neural mass model with at least one state equation that accepts an external input (e.g. Montbrió–Pazó–Roxin or MPR for short). Depending on the model, we are still **not allowed** to identify that input directly with the ohmic current induced by the stimulation, whose density is given by $\vec{J}=\sigma\vec{E}$. The user must define a biophysical model that converts the electric field distribution $\vec{E}(\vec{r})$ into a stimulation term in each parcel $i$. That is, we need a functional $\mathcal{F}$ that maps the field $\vec{E}(\vec{r})$ defined on the parcel $i$ ($\vec{r}\in V_i$) onto a single scalar $w_i$:
$$
\mathcal{F}:L^2(V_i;\mathbb{R}^3)\to\mathbb{R}
$$
such that
$$
\mathcal{F}[\vec{E}]=w_i
$$

We call $w_i$ the **stimulation weight** of parcel $i$. It is not necessarily a current: depending on the model it may be a membrane-potential offset, an additive current, a shift of the mean drive, or a modulation of a gating variable. It is also not necessarily positive, because the polarity of the field relative to the neuronal axis carries the sign of the effect. Its units are therefore model-dependent, and what the state equations do with $w_i$ is a separate modelling choice, discussed further below.

The rest of this section surveys the functionals $\mathcal{F}$ that have actually been used in the literature. Every row of the table below produces the same object, a scalar $w_i$ attached to parcel $i$; the rows differ only in how the field distribution over $V_i$ is reduced to that scalar.

### Functionals used in the literature

The temporal part of the coupling is rarely controversial: under the quasi-static approximation the field separates as $\vec{E}(\vec{r},t)=\vec{E}_0(\vec{r})s(t)$, so a functional acts on the static field and the time course $s(t)$ is carried through unchanged. Almost all disagreement in the literature concerns the choice of $\mathcal{F}$.

| # | Functional | Form | Neural mass model | Modality | Where the result enters | Representative work |
|---|---|---|---|---|---|---|
| F1 | Signed normal projection, membrane offset ($\lambda$-$E$) | $w_i=\lambda\,\langle\hat{\mathbf{n}}\cdot\vec{E}_0\rangle_{V_i}$ | Jansen–Rit, Wendling | tDCS, tACS | voltage offset added to the mean membrane potential, inside the sigmoid | [@ruffini2013tcs; @merlet2013oscillatory; @molaeeardekani2013tdcs; @dong2025tdcs] |
| F2 | Signed normal projection, firing-rate shift | $w_i=\dfrac{\lambda}{A h_e}\,\langle\hat{\mathbf{n}}\cdot\vec{E}_0\rangle_{V_i}$ | Jansen–Rit | tDCS | additive mean firing rate entering the pyramidal population via the excitatory interneuron path | [@kunze2016tdcs] |
| F3 | Vector dipole projection | $w_i=\boldsymbol{\lambda}_i\cdot\langle\vec{E}_0\rangle_{V_i}$ | MPR / NMM2 | tACS, tDCS | additive current or voltage in the mean-potential equation | [@ruffini2022exact; @clusella2023comparison] |
| F4 | Spherical-harmonic response function | $w_i=\sum_{\ell m}c_{\ell m}^{(i)}\,\langle Y_\ell^m(\theta,\varphi)\rangle_{V_i}$ | any (response function) | tDCS | orientation-resolved coupling; the $\ell=1$ term recovers F3 | [@galan2023spherical] |
| F5 | Frequency-dependent transfer | $w_i(f)=\hat{Z}_i(f)\,\tilde{E}_i(f)$ from a ball-and-stick cable | AdEx / EIF mean field | tACS | additive current to an AdEx/EIF mean field | [@aspart2016extending; @cakan2020biophysically] |
| F6 | Axonal activation function | $w_i\propto\big\langle\partial^2V_e/\partial s^2\big\rangle_{V_i}$ along the fibre, thresholded | L2/3 → L5 cortical circuit | TMS | input-rate pulse to a presynaptic mass | [@weise2023directional; @miller2026coupling] |
| F7 | Distribution-aware functional | $w_i=\big\langle f(\boldsymbol{\lambda}\cdot\vec{E}_0)\big\rangle_{V_i}$ over an orientation distribution, absorbed into the quenched noise $(\eta,\Delta)$ | MPR / NMM2 | tACS, tDCS | renormalises $\eta$ and $\Delta$ of the Lorentzian | [@ruffini2022exact; @clusella2023comparison] |

### Where the term enters the state equations

The six insertion points below are genuinely different, and a functional from the table above is only meaningful together with the insertion point it was designed for. In each case the stimulation term is $w_i\,s(t)$, i.e. the weight $w_i$ computed from the static field $\vec{E}_0$ multiplied by the temporal profile $s(t)$.

1. **Additive current in the mean-potential equation (exact mean field).** In the Montbrió–Pazó–Roxin (MPR) reduction and its second-order-synapse extension NMM2, the field enters as a *common* input $I_E(t)=w_i\,s(t)$ in
   $$
   \tau_m\dot{v}=\eta-(\pi r\tau_m)^2+v^2+\tau_m Js+I_E(t),
   $$
   with $w_i=\boldsymbol{\lambda}_i\cdot\langle\vec{E}_0\rangle_{V_i}$ (F3), where $\boldsymbol{\lambda}_i$ is the dipole coupling vector of the population (written $\tilde{P}$ in some of the original derivations). Because $I_E$ is identical for every neuron in the population, the Lorentzian ansatz remains exact: the field shifts the centre $v$ of the distribution but does not change its half-width. This is the cleanest case, and the one the `stvar`/`cvar` discussion above targets [@montbrio2015; @ruffini2022exact; @clusella2023comparison].
2. **Voltage offset inside the sigmoid (classical NMM).** The field appears as $S\!\left(\sum_s v_s+w_i\,s(t)\right)$ in a Jansen–Rit or Wendling-type model, with $w_i$ given by F1. This is not exact; the offset is a lumped, semi-empirical quantity [@jansenRit1995; @molaeeardekani2013tdcs; @merlet2013oscillatory]. The laminar NMM (LaNMM) extends this to a layered cortical column with an explicit physical layer for field application and for forward modelling of the resulting electrophysiology [@sanchez-todo2023physical].
3. **Additive mean firing rate (classical NMM, alternative).** Rather than offsetting the membrane potential, the field can be converted into an equivalent additive mean firing rate that enters the pyramidal population through the excitatory interneuron path. This is the route taken by the large-scale tDCS model of [@kunze2016tdcs]. The functional is still the signed normal projection, but the coupling constant carries an extra factor $1/(A h_e)$, where $A$ is the excitatory synaptic gain and $h_e$ the maximum excitatory postsynaptic potential. The authors do compute an intermediate voltage offset $\hat{u}_{\text{tDCS}}\,\zeta_i$ (capped at $|4|\ \text{mV}$, corresponding to 30 mV/mm), but that offset never enters the state equations: it is immediately divided by $A h_e$ to give the rate $\hat{p}_{\text{tDCS}}\,\zeta_i$, which is then added to the input firing rate $p_{\text{in}}=p_0+m_{\text{tDCS}}+\gamma W_{\text{het}}S(Ju_{\text{Py}})$. The two classical routes are therefore not interchangeable: an offset inside the sigmoid acts on the sigmoid's argument, whereas an additive rate acts on the input to the excitatory interneuron mass, and $A h_e$ is the conversion factor between them.
4. **Shift of the mean drive in a linear–nonlinear cascade.** For AdEx/EIF populations the field is first converted to an equivalent somatic current through the cable transfer function, giving $w_i$ from F5, and then shifts $\mu_E^{\text{ext}}(t)\to\mu_E^{\text{ext}}(t)+w_i\,s(t)$ [@aspart2016extending; @cakan2020biophysically].
5. **Modulation of a gating variable.** The field is mapped to a bias voltage $w_i=\lambda\vec{E}_{\text{normal}}(i)$ (F1) and then to a modulation term $\theta(i)=k\,w_i\,s(t)$ added to the synaptic gating dynamics. This is heuristic but explicit, and it is the route used to embed tDCS into a dynamic mean-field whole-brain model [@dong2025tdcs].
6. **Input-rate pulse (TMS).** The field is converted into a spike-rate pulse on layer 2/3 axons, with $w_i$ from F6 setting the pulse amplitude, which then propagates synaptically to layer 5. This is currently the only fully biophysical TMS-to-NMM coupling [@miller2026coupling].

### Magnitudes

The coupling constant $\lambda$ has units of length, and is best read as a membrane displacement per unit field. Direct measurements in rat hippocampal slices give $0.12\pm0.05\ \text{mV}$ per $\text{mV/mm}$ at the soma [@bikson2004uniform]. Compartment-model reconstructions of neocortical cells give $0.14\ \text{mV}$ per $\text{V/m}$ for layer 5 thick-tufted pyramidal cells, $0.10$ for layer 6 tufted cells and $0.07$ for untufted cells [@galan2023spherical]. Whole-brain tDCS models typically adopt $\lambda\approx 0.13$ together with the normal field component, and cap the resulting polarization at $|4|\ \text{mV}$ [@dong2025tdcs].

With typical tES field strengths of $0.2$–$2\ \text{V/m}$ [@ruffini2013tcs], the resulting weight $w_i$ corresponds to a membrane perturbation of order $0.02$–$0.4\ \text{mV}$, i.e. genuinely subthreshold. This is why the network-amplification argument matters: in the exact mean-field description the resonant response to a weak alternating field grows with self-connectivity and with slow synapses, so a population can respond measurably to a field that barely moves a single neuron [@clusella2023comparison].

### Two distinct averaging problems

Averaging a field over a parcel is often described as if it were a single problem, but there are two, and they call for different remedies.

- **Geometric cancellation.** The surface normal $\hat{\mathbf{n}}(\mathbf{r})$ reverses between gyral crowns and sulcal walls. A *signed* average of $\hat{\mathbf{n}}\cdot\vec{E}_0$ over a parcel that spans both can therefore cancel, even when the local field is large everywhere. Remedies are finer parcellation, sub-parcel orientation binning, or a fibre-aligned projection that does not rely on the cortical normal [@colella2025effective].
- **Rectification.** Because the map from field to membrane displacement is rectifying, $\langle f(E_n)\rangle_{V_i}\neq f(\langle E_n\rangle_{V_i})$. A vanishing mean field therefore does not imply a vanishing $w_i$. The correct procedure is to average the *response*, not the field, which is what the spherical-harmonic representation makes explicit [@galan2023spherical].

Note also that orientation dispersion does not break the Lorentzian ansatz. In the exact mean-field formulation, variations in orientation can be absorbed into the quenched-noise term, so dispersion renormalises $\eta$ and $\Delta$ rather than requiring a modified distribution [@ruffini2022exact].

### Consequences for TVB

`StimuliRegion` accepts one scalar weight per region, so every functional above has to collapse to a scalar $w_i$. F1, F2, F3 and F4 do so directly. F5 and F6 do not, because they are frequency- or fibre-resolved; they require either a pre-computed effective weight or a custom `StimuliRegion` subclass.

Two conventions deserve to be fixed explicitly in any implementation:

- **Polarity.** A functional that takes the field magnitude rather than a signed projection discards the sign, so $w_i\ge 0$ by construction. That is fatal for tDCS, where the anodal/cathodal distinction is the entire effect.
- **Normal orientation.** The sign convention of $\hat{\mathbf{n}}$ must be stated, since surface-inward is depolarizing. This is the most common source of inverted results across the papers cited above.
