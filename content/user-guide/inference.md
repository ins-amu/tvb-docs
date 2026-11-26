---
title: Inference
bibliography:
  - ../references.bib
---

# Inference

A simulation tells you what a model does for the parameters you chose. Inference
runs the question the other way round: given a recording, which parameters could
have produced it, and how sure can we be? This matters wherever model parameters
carry meaning, such as the excitability of a region, the strength of a
connection or the global coupling of a network, and wherever you want to
compare a patient's brain model with a control's.

This page explains the ideas behind the inference tools in TVB. The
[tutorial](inference/npe-montbrio.md) and the how-to guides linked at the end
put them to work.

## Inference means a distribution, not a number

Fitting a model by minimising an error returns a single parameter set. That is
not necessarily representative of the expected parameter values, because many
different parameter sets can fit the same data
equally well. Bayesian inference returns all of them, weighted by plausibility.
It combines three ingredients:

- the {term}`prior`, which states what parameter values are plausible before
  looking at the data, for example that time constants are positive and
  typically a few milliseconds;
- the {term}`likelihood`, which says how probable the observed data are for a
  given parameter set, and is where the model enters;
- the {term}`posterior`, which is their normalised product: the distribution of
  parameters that are consistent with both prior knowledge and data.

A narrow posterior means the data pin a parameter down. A broad one means they
do not, and a posterior that stretches along a curve in several parameters
reveals a {term}`degeneracy <Identifiability>`, a trade-off the data cannot
resolve. The posterior therefore reports not only an estimate but also what can
and cannot be learned from the data.

## Two routes to the posterior

Which route to take depends on whether the likelihood can be evaluated.

**Likelihood-based inference** applies when the model is deterministic and the
measurement noise has a known form, so the likelihood is a formula. Then you can
optimise it, approximate the posterior as a Gaussian around its peak (the
Laplace approximation), or draw samples from it with
{term}`Markov chain Monte Carlo` (MCMC). The samples are asymptotically exact,
but each one needs a model simulation, and chains can fail to converge, so
convergence must be checked. Stochastic models can be treated the same way by
sampling the unobserved noise-driven trajectory together with the parameters,
as @baldy2024 do with Hamiltonian Monte Carlo, but the number of unknowns then
grows with the length of the recording. The
[ERP how-to](inference/erp-likelihood.md) follows this route.

**{term}`Simulation-based inference <Simulation-based inference>`** (SBI)
applies when the likelihood cannot be written down or evaluated at an
affordable cost [@cranmer2020]. This is typical for TVB models. When noise
drives the dynamics, the probability of an observation requires integrating
over every trajectory the unobserved states could have taken. When the data
are summarised by features such as functional connectivity or spectra, the
distribution of those features has no closed form at all.
SBI needs only the ability to simulate. It draws parameters from the prior,
simulates each one, and trains a neural network to approximate the posterior
from the pairs of parameters and simulated data. The
[tutorial](inference/npe-montbrio.md) follows this route.

| | Likelihood-based | Simulation-based |
|---|---|---|
| Requires | A likelihood you can evaluate | A simulator you can run |
| Suited to | Deterministic models, known measurement noise | Stochastic models, summary features |
| Cost | Simulations for every posterior | Simulations once, then fast |
| Main risk | Non-convergence of the sampler | Poor or overconfident approximation |
| Check with | R-hat, effective sample size | Calibration, coverage |

## How simulation-based inference works

The workflow has five steps, and the tutorial walks through each.

1. **Simulator.** A function mapping parameters to data. For speed, it should
   process many parameter sets in one call.
2. **Prior.** A distribution to draw parameters from.
3. **Summary statistics.** A short vector describing each simulation, such as
   moments, spectral peaks or functional connectivity. The network has to learn
   from a limited number of simulations, so a compact, informative description
   helps. What you include also determines what you can infer, as the tutorial
   demonstrates.
4. **Training.** A conditional density estimator learns the posterior $q(\theta
   \mid x)$ from the simulated pairs. The method used here, neural posterior
   estimation, fits a {term}`masked autoregressive flow <Masked autoregressive flow>`,
   an invertible neural network that can represent correlated, skewed or curved
   densities and not only Gaussians. Parameters and statistics are standardised
   first, and the parameters are mapped to an unbounded space so the learned
   density respects the prior's limits.
5. **Inference.** Evaluate the trained network on the statistics of the
   observation. Because training did not depend on any particular observation,
   this takes milliseconds and works for any number of new observations. This
   property is called {term}`amortised inference <Amortised inference>`
   [@goncalves2020; @hashemi2023].

## Trusting the answer

A trained network will always return a posterior, whether or not it is any good.
Two kinds of check are needed.

First, **does the estimator work?** Test it on simulated observations whose
parameters are known. The posterior should contain the truth at its stated
rate, which is what calibration and coverage checks measure. This catches
overfitting, too few simulations and uninformative statistics. Even a
well-trained estimator is an approximation: on the model used in the tutorial,
@baldy2024 found that neural posterior estimates can overstate uncertainty and
correlations between parameters. The
[calibration guide](inference/posterior-calibration.md) shows how to check.

Second, **does the model describe the data?** A posterior is conditional on the
model being right. A {term}`posterior predictive check <Posterior predictive check>`
simulates from posterior draws and compares the result with the
recording. If they differ, the problem is the model or the statistics, not the
inference.

For MCMC the first question becomes whether the chains have converged, which is
what R-hat and the effective sample size measure [@vehtari2021].

## What is available

The examples in this section use a self-contained NumPy implementation,
`tvbl.infer`, so that they run quickly and in the browser lab without extra
installation. It provides prior distributions, a posterior estimator built on
the flows in `tvbl.cde`, calibration checks, and the pieces needed for
likelihood-based inference: a log-posterior in unconstrained coordinates, a
Laplace approximation, information criteria and convergence diagnostics.

It is deliberately small. It trains on the CPU in NumPy, uses
one network architecture, and supports only single-round estimation. For larger
problems, with many parameters, long recordings or millions of simulations, the
`sbi` toolbox [@tejerocantero2020] offers more architectures, GPU training and
sequential methods, and applications to whole-brain models such as
@hashemi2024 use it at scale. The workflow and checks described here carry over
unchanged.

## Where to go next

- [Tutorial: simulation-based inference on a neural mass model](inference/npe-montbrio.md)
  builds the full workflow on a small model and shows how a degeneracy appears
  and disappears.
- [How-to: check that an amortised posterior can be trusted](inference/posterior-calibration.md)
  covers parameter recovery, simulation-based calibration and coverage.
- [How-to: fit an evoked-response model with a likelihood](inference/erp-likelihood.md)
  covers optimisation, MCMC, the Laplace approximation and model comparison for
  an ERP model.
- [Parameter sweeps](sweep/theory.md) explore how a model's behaviour changes
  across parameter space, which is a useful first step before choosing priors.
