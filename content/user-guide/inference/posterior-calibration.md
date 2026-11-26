---
title: "How-to: check that an amortised posterior can be trusted"
kernelspec:
  name: python3
  display_name: Python 3
  language: python
bibliography:
  - ../../references.bib
---

# How-to: check that an amortised posterior can be trusted

:::{tip} Run interactively
- **[Open in JupyterLite Lab](/lite/lab/index.html?path=user-guide/inference/posterior-calibration.ipynb)**
- **[Download Notebook](/notebooks/user-guide/inference/posterior-calibration.ipynb)**
:::

**Goal:** decide whether a posterior estimated by simulation-based inference
is accurate enough to use, before applying it to real data.

A posterior that looks plausible for one or two test observations can still be
systematically overconfident, biased, or no better than the prior. Because an
amortised estimator is cheap to evaluate, you can test it on hundreds of
simulated observations whose true parameters you know, and measure how it
behaves across the whole prior. This guide shows four complementary checks:
parameter recovery, shrinkage against z-score, simulation-based calibration
ranks, and expected coverage.

To make the checks concrete, we apply them to two estimators for the same
problem. One is trained properly. The other is deliberately overfitted on a
few hundred simulations, so you can see what failure looks like. The setting
follows the [tutorial](npe-montbrio.md), with one change: noise now drives the
dynamics, and its amplitude $\sigma$ is a fourth unknown, as in the stochastic
version of the problem studied by @baldy2024.

```{code-cell} ipython3
:tags: [remove-cell]

import sys, pathlib

_root = pathlib.Path.cwd()
while not (_root / "myst.yml").exists() and _root != _root.parent:
    _root = _root.parent
sys.path.insert(0, str(_root / "content" / "_code"))

import matplotlib.pyplot as plt

plt.rcParams.update({
    "figure.dpi": 110, "font.size": 9, "axes.titlesize": 9, "axes.labelsize": 9,
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
})
```

```{code-cell} ipython3
import numpy as np
import matplotlib.pyplot as plt
from scipy import stats
from scipy.signal import find_peaks

from tvbl.infer import (
    BoxUniform, NPE, central_coverage, hpd_coverage, sbc_histogram, sbc_ranks,
    shrinkage_zscore,
)
```

## Step 1: Simulate a training set and a separate test set

The simulator is the Montbrió model with additive noise on both variables,
integrated with the stochastic Heun scheme. The same noise draw enters the
predictor and corrector steps. The summary statistics are the 17 voltage
statistics from the tutorial.

```{code-cell} ipython3
def montbrio_sde(theta, rng, dt=0.01, t_end=100.0, t_on=30.0, t_off=60.0, i0=3.0, record_every=5):
    """Simulate each row of theta = (Delta, eta, J, sigma); return t, v(t)."""
    theta = np.atleast_2d(theta)
    delta, eta, j, sigma = theta.T
    n = theta.shape[0]
    r = np.full(n, 0.5)
    v = np.full(n, -3.0)

    def rhs(r, v, current):
        return delta / np.pi + 2 * r * v, v ** 2 - (np.pi * r) ** 2 + j * r + eta + current

    vs = []
    with np.errstate(over="ignore", invalid="ignore"):
        for step in range(int(round(t_end / dt))):
            current = i0 if t_on <= step * dt < t_off else 0.0
            zr = np.sqrt(dt) * sigma * rng.standard_normal(n)
            zv = np.sqrt(dt) * sigma * rng.standard_normal(n)
            dr1, dv1 = rhs(r, v, current)
            dr2, dv2 = rhs(r + dt * dr1 + zr, v + dt * dv1 + zv, current)
            r = r + 0.5 * dt * (dr1 + dr2) + zr
            v = v + 0.5 * dt * (dv1 + dv2) + zv
            if (step + 1) % record_every == 0:
                vs.append(v)
    t = dt * record_every * np.arange(1, len(vs) + 1)
    return t, np.array(vs)


def summary_statistics(t, trace, t_on=30.0, t_off=60.0):
    """Five moments in each of three windows, peak count and first peak time."""
    out = []
    for window in (t < t_on, (t > t_on) & (t < t_off), t > t_off):
        seg = trace[window]
        out += [seg.mean(0), seg.std(0), np.median(seg, 0), stats.skew(seg, 0), stats.kurtosis(seg, 0)]
    during = (t > t_on) & (t < t_off)
    min_gap = int(round(1.0 / (t[1] - t[0])))
    n_peaks = np.full(trace.shape[1], np.nan)
    first_peak = np.full(trace.shape[1], np.nan)
    for k in range(trace.shape[1]):
        if np.all(np.isfinite(trace[during, k])):
            peaks, _ = find_peaks(trace[during, k], height=0.2, distance=min_gap)
            n_peaks[k] = peaks.size
            first_peak[k] = t[during][peaks[0]] if peaks.size else 0.0
    return np.stack(out + [n_peaks, first_peak], axis=1)
```

The test set must be drawn from the same prior as the training set and
simulated independently of it. Every check below is an average over the prior,
and a test set chosen by hand would only probe the regions you happened to
pick.

```{code-cell} ipython3
names = ["Delta", "eta", "J", "sigma"]
labels = [r"$\Delta$", r"$\eta$", r"$J$", r"$\sigma$"]
prior = BoxUniform(low=[0.1, -10.0, 5.0, 0.0], high=[5.0, -3.0, 20.0, 1.0])

rng = np.random.default_rng(2)
theta_all = prior.sample(6300, rng)
t, v_all = montbrio_sde(theta_all, rng)
x_all = summary_statistics(t, v_all)

theta_train, x_train = theta_all[:6000], x_all[:6000]
finite = np.all(np.isfinite(x_all[6000:]), axis=1)
theta_test, x_test = theta_all[6000:][finite], x_all[6000:][finite]
print(f"{len(theta_train)} training and {len(theta_test)} test simulations")
```

## Step 2: Train the estimator, and a bad one for comparison

The good estimator uses all training simulations, minibatches and early
stopping on a validation split. The bad one sees only 300 simulations, uses no
validation data and trains long enough to memorise them, which is a common way
to get an overconfident posterior.

```{code-cell} ipython3
good = NPE(prior, n_flows=5, hidden_units=64)
good.train(theta_train, x_train, n_iter=6000, batch_size=256, learning_rate=1e-3, patience=20)

bad = NPE(prior, n_flows=5, hidden_units=64)
bad.train(theta_train[:300], x_train[:300], n_iter=3000, batch_size=None, validation_fraction=0.0, patience=None, learning_rate=1e-3)

estimators = {"well trained": good, "overfitted": bad}
n_post = 299
draws = {name: post.sample(x_test, n_post, np.random.RandomState(0)) for name, post in estimators.items()}
```

## Step 3: Check parameter recovery

Plot the posterior mean and 90% interval of every test observation against
its true value. Points should scatter around the diagonal, and the intervals
should cross it about nine times in ten.

```{code-cell} ipython3
fig, axes = plt.subplots(2, 4, figsize=(10, 4.8))
for row, (name, smp) in enumerate(draws.items()):
    mean = smp.mean(axis=1)
    lo, hi = np.percentile(smp, [5, 95], axis=1)
    for i, ax in enumerate(axes[row]):
        ax.errorbar(theta_test[:80, i], mean[:80, i], yerr=[mean[:80, i] - lo[:80, i], hi[:80, i] - mean[:80, i]], fmt=".", ms=3, lw=0.6, color=f"C{row}")
        ax.plot([prior.low[i], prior.high[i]], [prior.low[i], prior.high[i]], "k--", lw=0.8)
        ax.set_title(f"{labels[i]}, {name}")
        if row == 1:
            ax.set_xlabel("true value")
    axes[row, 0].set_ylabel("posterior mean")
plt.tight_layout()
plt.show()
```

This check is intuitive, but it is easy to misread. The well-trained estimator
recovers $\eta$, $J$ and $\sigma$ along the diagonal. For $\Delta$ the points
spread more and the intervals are wide, because the degeneracy described in
the tutorial makes it hard to identify from the voltage alone. The overfitted
estimator puts its means in roughly the right places too. What is wrong with
it is that its intervals are too narrow, and that is hard to see by eye.

## Step 4: Plot shrinkage against z-score

Two numbers summarise each posterior. The shrinkage $1 -
\sigma^2_\text{post}/\sigma^2_\text{prior}$ is near 1 when the data are much
more informative than the prior and near 0 when they add nothing. The z-score
$(\mu_\text{post} - \theta_\text{true})/\sigma_\text{post}$ measures how many
posterior standard deviations separate the estimate from the truth. An ideal
posterior has shrinkage close to 1 and z-scores spread like a standard normal
variable, mostly between $-2$ and $2$.

```{code-cell} ipython3
fig, axes = plt.subplots(1, 4, figsize=(10, 2.6), sharey=True)
for row, (name, smp) in enumerate(draws.items()):
    shrinkage, z = shrinkage_zscore(smp, theta_test, prior.std)
    for i, ax in enumerate(axes):
        ax.plot(shrinkage[:, i], z[:, i], ".", ms=3, alpha=0.6, color=f"C{row}", label=name)
        ax.set_xlabel(f"shrinkage {labels[i]}")
    print(f"{name:>12}: std of z-scores", np.round(z.std(axis=0), 2))
for ax in axes:
    ax.axhspan(-2, 2, color="0.9", zorder=0)
    ax.set_xlim(right=1.02)
axes[0].set_ylabel("z-score")
axes[0].set_ylim(-12, 12)
axes[0].legend(fontsize=8, markerscale=3)
plt.tight_layout()
plt.show()
```

The overfitted estimator claims as much shrinkage as the well-trained one, or
more, but only the well-trained one backs it up. Its z-scores stay in the band
and have a standard deviation close to 1. The overfitted estimator produces a
tail of z-scores far outside the band, mostly where its shrinkage is close to 1.
Those posteriors are very narrow and miss the truth, which is the signature of
overconfidence, and shrinkage on its own would never have revealed it. Note
also the negative shrinkage of some $\Delta$ posteriors. When a posterior keeps
weight near both ends of the prior range, its variance can exceed that of the
uniform prior.

## Step 5: Simulation-based calibration

If the posterior is exact, the true parameter of a test observation is just
one more draw from it. Its rank among the $L$ posterior samples is then equally
likely to take any value from 0 to $L$, and a histogram of ranks over the test
set is flat. This is simulation-based calibration [@modrak2025]. The shape of
a non-flat histogram tells you what is wrong: a U shape means the posterior is
too narrow, a dome means it is too wide, and a slope means it is biased. When
grouping ranks into bins, choose $L$ so that the $L + 1$ possible ranks divide
evenly among the bins. Otherwise some bins collect more ranks than others and
the histogram cannot be flat even for an exact posterior. Here $L = 299$ and
there are 10 bins of 30 ranks each.

```{code-cell} ipython3
ranks = {name: sbc_ranks(post, theta_test, x_test, n_post, np.random.RandomState(1)) for name, post in estimators.items()}

n_bins = 10
fig, axes = plt.subplots(2, 4, figsize=(10, 4.2), sharex=True, sharey=True)
for row, (name, rk) in enumerate(ranks.items()):
    counts, band = sbc_histogram(rk, n_post, n_bins)
    for i, ax in enumerate(axes[row]):
        ax.axhspan(*band, color="0.88", zorder=0)
        ax.bar(np.arange(n_bins), counts[:, i], width=0.9, color=f"C{row}")
        ax.set_title(f"{labels[i]}, {name}")
        ax.set_yticks([])
for ax in axes[1]:
    ax.set_xticks([0, n_bins - 1], ["lowest", "highest"])
    ax.set_xlabel("rank bin of true value")
plt.tight_layout()
plt.show()
```

The grey band is the range a flat histogram stays within 99% of the time with
this many test observations. The well-trained estimator's ranks stay close to
it. The overfitted estimator's ranks pile up at both ends: the truth falls
outside its posterior far too often, on either side.

## Step 6: Measure expected coverage

Coverage turns the same idea into a single curve. For each credibility level
$\alpha$, count how often the truth lies inside the $\alpha$ credible region.
For a calibrated posterior the answer is $\alpha$, so the curve lies on the
diagonal. A curve below the diagonal means overconfidence, and a curve above it
means the posterior is more cautious than it needs to be.

We compute it in two ways. Central intervals are per-parameter and follow
directly from the SBC ranks. Highest-density regions use the estimated density
and test all parameters jointly.

```{code-cell} ipython3
levels = np.linspace(0.05, 0.95, 19)
fig, axes = plt.subplots(1, 2, figsize=(8, 3.6), sharey=True)
for row, (name, post) in enumerate(estimators.items()):
    central = central_coverage(ranks[name], n_post, levels)
    for i in range(4):
        axes[0].plot(levels, central[:, i], color=f"C{row}", lw=1, label=name if i == 0 else None)
    joint = hpd_coverage(post, theta_test[:150], x_test[:150], n_post, np.random.RandomState(2), levels)
    axes[1].plot(levels, joint, "o-", ms=3, color=f"C{row}", label=name)
    print(f"{name:>12}: joint coverage of the 90% region = {joint[np.argmin(abs(levels - 0.9))]:.2f}")
for ax, title in zip(axes, ["central intervals (each parameter)", "highest-density regions (joint)"]):
    ax.plot([0, 1], [0, 1], "k--", lw=0.8)
    ax.set_xlabel("credibility level")
    ax.set_title(title, fontsize=9)
axes[0].set_ylabel("empirical coverage")
axes[0].legend(fontsize=8)
plt.tight_layout()
plt.show()
```

The well-trained estimator tracks the diagonal closely for every parameter. Its
joint curve follows the diagonal up to moderate credibility levels and then
falls slightly below it, which means its highest-density regions are a little
too small when you ask for high credibility. This is typical, because the
estimated density is least accurate in its tails, and it is worth keeping in
mind when interpreting 95% regions. The overfitted estimator falls far below the
diagonal everywhere, and the joint check is the most severe: its 90% region
contains the truth in well under half of the test cases.

## Interpreting the checks

No single diagnostic is enough. A posterior equal to the prior is perfectly
calibrated, and it passes the rank and coverage checks while telling you
nothing. That is why coverage should be read together with shrinkage.
Conversely, high shrinkage means little if the z-scores show the posterior is
in the wrong place. The combination used here answers the three questions that
matter: is the posterior informative (shrinkage), is it right (recovery and
z-scores), and are its uncertainties honest (ranks and coverage).

A few practical points:

- Calibration is an average over the prior. A calibrated estimator can still
  be poor for a particular kind of observation, such as the quiet traces in the
  tutorial. If your data occupy a narrow region, test there as well.
- A few hundred test simulations are enough to detect gross miscalibration.
  Subtle errors need more, and the binomial band in step 5 tells you what is
  distinguishable from noise.
- When a check fails, the usual remedies are more simulations, early stopping
  on a validation set, or more informative statistics. All of them are cheaper
  than drawing conclusions from an overconfident posterior.
- These checks test the estimator against the simulator. They say nothing
  about whether the simulator describes your data. That is the job of the
  posterior predictive check in the [tutorial](npe-montbrio.md).

## Related documentation

- [Inference overview](../inference.md): why calibration matters for amortised
  estimators, and how this compares with likelihood-based inference.
- [Tutorial: simulation-based inference on a neural mass model](npe-montbrio.md).
- [How-to: fit an ERP model with a likelihood](erp-likelihood.md): convergence
  diagnostics for MCMC, the likelihood-based counterpart of these checks.
