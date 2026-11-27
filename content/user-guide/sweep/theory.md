---
title: Sweep Theory
bibliography:
  - ../../references.bib
---

# Sweep Theory

A single whole-brain simulation tells you what a model produces at one point in parameter space. Because neural mass networks are nonlinear, coupled, and delayed, small shifts in excitability, {term}`global coupling`, or synaptic time constants can push a brain network across a {term}`bifurcation` from quiet rest into limit-cycle oscillations, bistability, or synchronized fluctuations. A {term}`parameter sweep` systematically maps how model behaviour and summary observables change across a controlled set of parameter vectors $\theta \in \mathbb{R}^D$.

This page covers the scientific, statistical, and numerical principles behind effective parameter sweeps, including how to chain {term}`monitors <Monitor>` with online and post-processing data features. For the systems architecture of the compiled C++ execution engine, see [C++ Hybrid Backend](../hpc/cpp-hybrid-backend.md).

---

## Why run parameter sweeps?

Whole-brain modelers use parameter sweeps for four complementary tasks:

1. **Mapping dynamical regimes and working points.** Resting-state brain models typically operate near a {term}`criticality <Criticality>` boundary or Hopf threshold where noise-driven fluctuations explore the structural {term}`connectome` without locking into global hyper-synchrony [@deco2017]. Sweeping excitability and coupling locates that working point before running longer experiments.
2. **Fitting empirical observables.** Comparing simulated {term}`functional connectivity` (FC), {term}`power spectral density` (PSD), or metastability against empirical neuroimaging requires evaluating how summary features vary across parameters [@sanzleon2013; @deco2014].
3. **Sensitivity and degeneracy analysis.** Sweeps reveal which parameters strongly move an observable and which trade off along ridges of near-identical behaviour ({term}`degeneracy <Degeneracy>`).
4. **Scoping priors for Bayesian inference.** Before running {term}`simulation-based inference` [@cranmer2020; @hashemi2024], an exploratory sweep verifies that the chosen {term}`prior` spans biologically plausible activity without numerical instability (see [Inference](../inference.md)).

---

## Anatomy of a parameter sweep

Every sweep evaluates a map from a $D$-dimensional control-parameter vector $\theta^{(k)}$ to reduced observables:

$$
\theta^{(k)} \;\xrightarrow{\;\text{integrate}\;}\; x(t; \theta^{(k)}) \;\xrightarrow{\;\text{monitor}\;}\; y(t; \theta^{(k)}) \;\xrightarrow{\;\text{summarise}\;}\; S\!\left(y(\cdot\,;\theta^{(k)})\right),
\qquad k = 0, \dots, K - 1.
$$

Separating **control parameters** ($\theta$), **monitored signals** ($y$), and **summary statistics** ($S$) clarifies three choices:

- **Control parameters ($\theta$):** Coupling gains and sigmoidal transfer parameters on projections, local excitabilities or time constants on subnetworks, or random seeds across stochastic replicates.
- **Monitors ($y$):** Neural state variables (`TemporalAverage`, `Raw`), or biophysical hemodynamic BOLD via the nonlinear {term}`Balloon–Windkessel model` (`BalloonWindkessel`, passed via `bw={...}`).
- **Summary features ($S$):** Envelopes ($\min, \max, \text{std}$), spectral peak frequencies and band power, spatial correlations (FC matrices), or compact statistical tables.

---

## Sampling geometry and the curse of dimensionality

How you choose the $K$ parameter points $\{\theta^{(k)}\}_{k=0}^{K-1}$ depends on the dimension $D$:

| Geometry | Points $K$ | Best for | API pattern |
|---|---|---|---|
| **1D sequence** | $N$ | Bifurcation profiles, dose-response curves, excitability scans | `nb.sweep(ns, nstep, **{"A.eta": vals})` |
| **2D Cartesian grid** | $N_1 \times N_2$ | Regime maps and 2-parameter phase diagrams [@kuznetsov2004] | `nb.sweep(ns, nstep, grid=True, **{"A.eta": a, "coupling_scale": g})` |
| **Monte Carlo / QMC** | $N$ (independent of $D$) | $D \ge 3$ sensitivity analysis, global exploration, SBI training sets | `nb.sweep(ns, nstep, grid=False, **params)` (lockstep zip) |

A Cartesian grid grows as $N^D$: ten points per axis across five parameters already requires $10^5$ simulations, most of which repeat identical marginal coordinates. In $D \ge 3$ dimensions, space-filling designs such as **Latin Hypercube Sampling (LHS)** or low-discrepancy **Sobol sequences** distribute $K$ evaluations evenly across every marginal projection and interior volume, and feed directly into `nb.sweep(..., grid=False)` as matched 1D arrays.

---

## Numerical and statistical pitfalls

### 1. Discard the initial transient (burn-in)

Simulations rarely start on an {term}`attractor <Attractor>`. Computing means, variance, spectra, or FC over the full trajectory mixes initial relaxation ({term}`transient <Transient>`) with steady-state dynamics—and for slow hemodynamic states in the `BalloonWindkessel` model, equilibration spans roughly $10\text{--}15\text{ s}$. Always slice away a burn-in prefix before extracting steady-state envelopes, PSDs, or BOLD FC matrices.

### 2. Check initial conditions for multistability

In models with {term}`bistability` (such as `MontbrioPazoRoxin` [@montbrio2015] or `JansenRit` [@jansenRit1995; @grimbertFaugeras2006]), two stable attractors coexist over an interval of a control parameter. Sweeping from a single fixed initial state samples only whichever {term}`basin of attraction <Basin of attraction>` contains that state. Running the sweep from both low-activity and high-activity initial conditions exposes hysteresis and coexisting branches.

### 3. Reduce Monte Carlo noise with common random numbers

When comparing parameters in a stochastic {term}`SDE <Stochastic differential equation>` model, drawing independent noise realizations at every parameter value adds Monte Carlo jitter to differences $S(\theta_2) - S(\theta_1)$. Passing `shared_noise=True` applies **common random numbers** (the same noise realization across sweep points) so smooth parameter trends emerge cleanly, while explicit `noise_seeds` quantify trial-to-trial variability across independent replicates.

### 4. Hemodynamic BOLD readout: `BalloonWindkessel`

For fMRI-scale observables in hybrid sweeps, prefer the biophysical `BalloonWindkessel` monitor (`bw={"global": BalloonWindkessel(...)}` or `bw={"local": {"subnet": ...}}`). It averages neural observations over complete $10\text{ ms}$ windows, integrates the nonlinear balloon-model ODEs per region, and returns midpoint-stamped fractional BOLD changes $\Delta S / S$ with no incomplete trailing partial window. *(For compatibility with classic TVB pipelines, linear HRF convolution remains available via `monitor="bold"`.)*

---

## Online vs. post-processing features and monitor chaining

Storing full time series for $K = 1{,}000$ sweep points across $100$ regions and $10{,}000$ steps requires gigabytes of RAM just for the output buffer. Computing summary features **online** during integration reduces output memory from $O(K \cdot T \cdot N_\text{voi} \cdot N_\text{node})$ to $O(K \cdot N_\text{voi} \cdot N_\text{node})$, at the cost of restricting which features are eligible.

### Which features can run online vs. in post-processing?

- **Available online (`monitor="features"`):** The 16 single-pass streaming statistics that require only running accumulators over the **neural VOI stream**:
  - *Moments & distribution shape:* `mean`, `var`, `std`, `moments`, `skewness`, `kurtosis`
  - *Amplitude & energy:* `min`, `max`, `rms`, `abs_energy`, `average_power`, `auc`, `auc_trapz`
  - *Temporal structure:* `zero_crossing`, `burstiness`, `centroid`
  - *Important limits:* Online accumulation runs over the **full simulated window from step 1** (no burn-in exclusion) and operates on the neural VOI stream, not on `BalloonWindkessel` BOLD output.

- **Must be computed in post-processing (`features.compute_features` / custom NumPy):** Any statistic requiring multi-pass sorting, histogram binning, Fourier transforms, burn-in trimming, or cross-region pairing:
  - *Order statistics & entropy:* `median`, `iqr`, `mad`, `median_abs_dev`, `entropy`
  - *Spectral (Welch PSD):* `psd_raw`, `spectrum_stats` (mean frequency, peak frequency, total power), `spectrum_auc` (band power), `spectrum_moments`
  - *Cross-region & trimmed observables:* **Functional connectivity (FC)**, dynamic FC, phase synchrony, or *any* feature after discarding an initial burn-in transient.

### How to chain monitors and features

`features.compute_features(ts, ...)` works on **any** time-first array `(n_time, ...)`, whether it came from a neural monitor (`TemporalAverage`, `Raw`, `SubSample`) or a hemodynamic monitor (`BalloonWindkessel`):

| Workflow | Monitor configuration | Post-processing step | Output |
|---|---|---|---|
| **Zero-storage neural summary** | `monitor="features", features=[...]` | None (call `res.features(...)` or `res.to_dataframe()`) | 16 single-pass neural stats, zero trajectory RAM |
| **Trimmed neural stats / PSD** | `monitor="tavg", chunk_size=k, monitor_period=k` | Slice burn-in `[:, T0:, ...]`, demean if needed, call `features.compute_features(...)` | Welch PSD, peak freq, band AUC, `entropy`, `iqr` |
| **Biophysical BOLD FC & BOLD stats** | `monitor="none", bw={"global": BalloonWindkessel(...)}` | Slice hemodynamic burn-in (e.g., `[:, 15:, 0, :, 0]`), compute `np.corrcoef` and/or `features.compute_features(...)` | Regional BOLD FC matrices, FC–SC correlation, BOLD `std` / low-freq power |

---

## Where to go next

Work through the four interactive notebooks in this section:

- [Parameter Types and Querying Sweepable Parameters](parameter-types.ipynb) — discover and validate sweepable projection, model, and noise parameters via the API.
- [Bifurcation Sweeps](bifurcation.ipynb) — run 1D transitions, 2D `grid=True` regime maps, and hysteresis sweeps with `initial_conditions`.
- [Monte Carlo and Quasi-Monte Carlo Sweeps](mc-sampling.ipynb) — compare LHS/Sobol designs, common random numbers vs. independent seeds, and zero-storage `monitor="features"` tables.
- [Hybrid Sweep Workflows and Performance](backends.ipynb) — end-to-end hybrid workflows spanning 1D transitions, excitability-to-PSD shifts, excitability-to-Balloon–Windkessel BOLD FC, and 3D Monte Carlo sweeps.

For the compiled C++ execution architecture, see [C++ Hybrid Backend](../hpc/cpp-hybrid-backend.md); for conceptual background on bifurcations and hybrid ownership, see [Bifurcation analysis](../../explanation/bifurcation-analysis.md) and [Hybrid Conceptual Model](../hybrid/hybrid-concepts.md).
