---
title: Non-invasive brain stimulation
bibliography:
  - content/references.bib
---

# Introduction

Non-invasive brain stimulation (or NIBS for short) is a very important neuromodulation technique that has gained traction in the last decades. It has applications both in basic neuroscientific research, as well as in clinical practice. In the latter case, NIBS techniques are applied or are currently under investigation in neuropsychiatric disorders as diverse as depression, obsessive-compulsive disorder (OCD), schizophrenia, dementia, ADHD and many others.

In this document we are going to focus mainly on electromagnetic NIBS techniques, which can be brooadly split in the following (non-exhaustive) subcategories:
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

The main physical quantity which mediates the effect of the stimulation is either the *externally induced* electric or magnetic field in TES/TMS respectively. We must emphasize that this field must not be confused with the *intrinsic* electromagnetic field of the brain, which is produced by its internal neuronal activity. The external field has as its source the stimulation apparatus (e.g. an externally injected current via scalp electrodes in TES or an externally generated magnetic field by the coils of the TMS device).

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
* $\vec{B}$: is the magnetic induction field
* $\vec{J}$: is the electric current density. 
(magnetic flux density)

In ***linear isotropic*** media also satisfy the following constitutive relations between the pairs $(\vec{E},\vec{D})$ and $(\vec{H},\vec{B})$:

\begin{align*}
\vec{D}=\varepsilon\vec{E}\\
\vec{B}=\mu\vec{H{}}
\end{align*}

where $\varepsilon$ is the dielectric permittivity and $\mu$ is the magnetic permeability of the medium.

It is crucial to understand that the electric current density $\vec{J}$ is actually composed of two components:

\begin{equation}
\vec{J}=\vec{J}_s+\vec{J}_r
\end{equation}

* $\vec{J}_s$ is the *source* current (sometimes also called *imprinted* current), which is the actual and only source of the electromagnetic fields.
* $\vec{J}_r$ is the *induced* or *ohmic* current that flows through imperfect conductors and follows Ohm's law (in point form), which in case of linear, isotropic media takes the form:

\begin{equation}
\vec{J}=\sigma \vec{E}
\end{equation}

where $\sigma$ is the conductivity of the medium.

Although brain tissue is, strictly speaking, neither linear nor isotropic, many CEM solvers make this assumption as a first approximation (although, some solvers and many papers in the literature take into account the anisotropy of *white matter* by replacing the scalars $\varepsilon, \sigma$ by *tensors* $\bar{\bar\varepsilon}, \bar{\bar\sigma}$).

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

**Note**: For TMS, a related, but slightly different form of approximation is used, which does not neglect induction. It is called the magneto-quasistatic approximatoin (MQS) and has the form

\begin{equation*}
\nabla\cdot(\sigma\nabla v)=-\nabla\cdot\left(\sigma\frac{\partial\vec{A}}{\partial t}\right)
\end{equation*}

where $\vec{A}$ is the vector magnetic potential generated by the TMS coils (i.e. a given source quantity). Sometimes a further approximation, called MQS $\phi$-formlatoin for TMS is used, see @perez2023review.

Most CEM solvers calculate the potential function $v$ and derive the electric field $\vec{E}$ from its gradient. However, it is imporant to note here that **the potential $v$ has no intrinsic physical meaning**, since it is arbitrary up to additive constant $c$ (i.e. any potential function $v+c$ yields the same E-field). Only the **potential difference** $\Delta v$ has a well-defined, (bio-)physical meaning.

**Warning**: The quasi-static approximation is only valid under certain conditions, and only in the low frequency regime (the physiological activity of the brain and stimulaion frequencies up to the lower kHz regime are usually considered valid for this approximation). If the stimulation fields exceed this frequency range, the results of the solvers that rely on this approximation maybe too inaccurate.

## Spatiotemporal separation

One very important aspect of the EQS approximation is that it effectively separates the spatial from the temporal variation of the fields. As you will notice, the equation satisfied by the electric potential in biological tissues (\nabla\cdot(\sigma\nabla v)=-\nabla\cdot\vec{J}_s
) does not involve any temporal derivatives. Let us assume that the source current has a separable form

$$
\vec{J}_s(\vec{r},t)=\vec{J}_0(\vec{r})s(t)
$$
where $\vec{J}_0(\vec{r})$ is a static (or *DC* current) and $s(t)$ is an arbitrary signal that modulates its amplitude in time, then the solution to the Poisson equatoin is
$$
u(\vec{r},t)=u_0(\vec{r})s(t)
$$
where $u_0(\vec{r})$ is the static (or *DC*) solution to the time-independent boundary value problem

\begin{equation*}
\nabla\cdot(\sigma\nabla v_0)=-\nabla\cdot\vec{J}_0
\end{equation*}

Most of the CEM solvers compute actually the static solution $v_0$ (and the derived static E-field $\vec{E}_0=-\nabla u_0$), and the temporal variability of the field is just a multiplication with a scalar signal $s(t)$:

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

* FEM:
  * Discretization of the volume of the solution domain with finite volume elements (e.g. tetrahedra)
  * Reduces the problem to the solution of a very large sparse linear system.
  * If the solution domain is unbounded, it needs to be truncated and termination boundary conditions must be applied.
  * It can handle inhomogeneous material properties.
  * It can give the values of the potentials and electric fields at any point almost instantaneously.

* BEM:
  * Discretization of the boundaries of the soluton domains with finite surface elements (e.g. triangles)
  * Reduces the problem to the solution of a relatively smaller dense linear system.
  * It can handle uncounded solution domains out-of-the-box, without any special termination boundary conditions.
  * It assumes that the solution domain is homogeneous or piecewise homogeneous.
  * The field values inside the solution domain need to be calculated in post-processing by integrating the boundary values.

