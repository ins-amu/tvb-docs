---
title: "Tutorial: simulation-based inference on a neural mass model"
kernelspec:
  name: python3
  display_name: Python 3
  language: python
bibliography:
  - ../../references.bib
---

# Tutorial: simulation-based inference on a neural mass model

:::{tip} Run interactively
- **[Open in JupyterLite Lab](/lite/lab/index.html?path=user-guide/inference/npe-montbrio.ipynb)**
- **[Download Notebook](/notebooks/user-guide/inference/npe-montbrio.ipynb)**
:::

In this tutorial you recover the parameters of a neural mass model from its
simulated membrane potential. You will write a simulator, reduce its output to
a handful of summary statistics, train a neural density estimator on ten
thousand simulations, and then read off posterior distributions for several
observations without retraining. Along the way the posterior will expose a
degeneracy among the parameters, and you will reduce it by measuring one more
variable.

The model is the mean-field description of quadratic integrate-and-fire
neurons derived by @montbrio2015. The problem, prior and summary statistics are
those of @baldy2024, and the method is neural posterior estimation as used by
@goncalves2020. Where @baldy2024 train on a hundred thousand simulations, we use
ten thousand, so the tutorial runs in about fifteen seconds, in a browser if you
like. The [inference overview](../inference.md) explains the ideas behind each
step.

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

from tvbl.infer import BoxUniform, NPE, pairplot, shrinkage_zscore
```

## 1. Write the simulator

The model tracks the mean firing rate $r$ and mean membrane potential $v$ of a
population of neurons whose excitabilities follow a Lorentzian distribution
with centre $\eta$ and half-width $\Delta$, coupled with synaptic weight $J$.
With time measured in units of the membrane time constant [@montbrio2015],

$$
\dot r = \frac{\Delta}{\pi} + 2 r v, \qquad
\dot v = v^2 - \pi^2 r^2 + J r + \eta + I(t).
$$

The input $I(t)$ is a current step of amplitude 3 between $t = 30$ and
$t = 60$. Depending on $(\Delta, \eta, J)$ the population ignores the step,
follows it, or is switched into a lasting high-activity state. These are the
three parameters we want to infer.

The simulator below integrates every row of a parameter array at once. Batching
over parameter sets matters more than any other optimisation here, because the
cost of a NumPy time loop is dominated by per-step overhead, not by array size.
We use Heun's method, the default scheme in TVB, with a step of 0.01. Its count
of oscillation peaks agrees with an Euler reference run at a step a hundred
times smaller, whereas Euler at a step of 0.001 still miscounts by one.

```{code-cell} ipython3
def montbrio(theta, dt=0.01, t_end=100.0, t_on=30.0, t_off=60.0, i0=3.0, record_every=5):
    """Simulate each row of theta = (Delta, eta, J); return t, r(t), v(t)."""
    theta = np.atleast_2d(theta)
    delta, eta, j = theta.T
    r = np.full(theta.shape[0], 0.5)
    v = np.full(theta.shape[0], -3.0)

    def rhs(r, v, current):
        return delta / np.pi + 2 * r * v, v ** 2 - (np.pi * r) ** 2 + j * r + eta + current

    rs, vs = [], []
    with np.errstate(over="ignore", invalid="ignore"):
        for step in range(int(round(t_end / dt))):
            current = i0 if t_on <= step * dt < t_off else 0.0
            dr1, dv1 = rhs(r, v, current)
            dr2, dv2 = rhs(r + dt * dr1, v + dt * dv1, current)
            r = r + 0.5 * dt * (dr1 + dr2)
            v = v + 0.5 * dt * (dv1 + dv2)
            if (step + 1) % record_every == 0:
                rs.append(r)
                vs.append(v)
    t = dt * record_every * np.arange(1, len(vs) + 1)
    return t, np.array(rs), np.array(vs)
```

Run it once with $\Delta = 0.7$, $\eta = -4.6$ and $J = 14.5$. These values will
serve as the ground truth of our first observation.

```{code-cell} ipython3
theta_true = np.array([0.7, -4.6, 14.5])
t, r, v = montbrio(theta_true)

fig, axes = plt.subplots(2, 1, figsize=(6.5, 3.4), sharex=True)
axes[0].plot(t, v[:, 0], color="k", lw=1)
axes[0].set_ylabel("membrane potential $v$")
axes[1].plot(t, r[:, 0], color="k", lw=1)
axes[1].set_ylabel("firing rate $r$")
axes[1].set_xlabel("time")
for ax in axes:
    ax.axvspan(30, 60, color="0.92", zorder=0)
axes[0].text(45, axes[0].get_ylim()[1], "stimulus", ha="center", va="top", color="0.4")
plt.show()
```

Before the stimulus the population sits in a low-activity state. The step
drives it into damped oscillations that settle onto a high-activity state. The
oscillations reflect a transient synchronisation of the neurons' firing
[@montbrio2015]. When the current is removed the population drops back only part
of the way and stays active: with these parameters the model is bistable, and
the stimulus has switched it from one stable state to the other.

## 2. Reduce each simulation to summary statistics

A density estimator could in principle read the raw trace, but it would need
far more simulations to learn which of its thousands of samples matter. Instead
we describe each trace with the 17 numbers used by @baldy2024: the mean,
standard deviation, median, skewness and kurtosis of $v$ before, during and
after the stimulus, plus the number of oscillation peaks during the stimulus
and the time of the first one.

We only use $v$, as if the membrane potential were the only quantity we could
record. The firing rate stays hidden for now.

```{code-cell} ipython3
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


x_true = summary_statistics(t, v)[0]
print(f"{x_true.size} features; {x_true[15]:.0f} peaks, the first at t = {x_true[16]:.2f}")
```

## 3. Choose a prior

The prior states which parameter values we consider plausible before seeing
data. We use independent uniform distributions over the ranges of @baldy2024.
$\Delta$ and $J$ must be positive, and a negative $\eta$ makes most neurons
excitable rather than spontaneously firing.

```{code-cell} ipython3
labels = [r"$\Delta$", r"$\eta$", r"$J$"]
prior = BoxUniform(low=[0.1, -10.0, 5.0], high=[5.0, -3.0, 20.0])
limits = list(zip(prior.low, prior.high))
```

## 4. Simulate the training set

Draw parameters from the prior and simulate each draw. If some parameter
combination makes the model diverge, its statistics come out as NaN and the
training step discards it.

```{code-cell} ipython3
rng = np.random.default_rng(1)
theta_train = prior.sample(10_000, rng)
t, r_train, v_train = montbrio(theta_train)
x_train = summary_statistics(t, v_train)
print(f"{np.isfinite(x_train).all(axis=1).sum()} of {len(x_train)} simulations are usable")
```

The simulations are usually the expensive part of the workflow. In real
applications you would save `theta_train` and `x_train` to disk (with
`np.savez`, for example) and reuse them while you experiment with features and
estimators. None of what follows needs new simulations.

## 5. Train the neural posterior estimator

`NPE` wraps a masked autoregressive flow, a density estimator that learns
$q(\theta \mid x)$ from the simulated pairs. Before training, it rescales the
statistics and the parameters to zero mean and unit variance, and maps each
parameter through a logit transform so that the learned density cannot leak
outside the prior box. Ten per cent of the simulations are held out to monitor
overfitting.

```{code-cell} ipython3
posterior = NPE(prior, n_flows=5, hidden_units=64)
posterior.train(theta_train, x_train, n_iter=6000, batch_size=256, learning_rate=1e-3, patience=20)

fig, ax = plt.subplots(figsize=(6.5, 2.4))
steps_per_check = len(posterior.loss_history) / len(posterior.val_loss_history)
ax.plot(posterior.loss_history, color="0.75", lw=0.5, label="training minibatch")
ax.plot(steps_per_check * np.arange(1, len(posterior.val_loss_history) + 1), posterior.val_loss_history, color="k", lw=1.2, label="validation set")
ax.set_xlabel("gradient step")
ax.set_ylabel("negative log-density")
ax.set_ylim(top=np.percentile(posterior.loss_history, 99))
ax.legend()
plt.show()
```

The loss is the average negative log-density of the true parameters under the
estimated posterior, so lower is better. Watch the validation curve. If it
turned upwards while the training loss kept falling, the network would be
memorising its training set. `NPE` keeps the weights with the lowest validation
loss and stops once it has not improved for `patience` consecutive checks. Here
both curves are still falling slowly when the step budget runs out, which is
acceptable for this tutorial.

## 6. Infer the parameters of an observation

Conditioning the trained estimator on the statistics of our observation gives
the posterior. Sampling it takes milliseconds.

```{code-cell} ipython3
samples = posterior.sample(x_true, 5000, np.random.RandomState(0))

fig, axes = plt.subplots(1, 3, figsize=(6.5, 2.0))
for i, ax in enumerate(axes):
    ax.hist(samples[:, i], bins=60, range=limits[i], density=True, color="C0")
    ax.axvline(theta_true[i], color="C3", lw=1.2)
    ax.set_xlim(limits[i])
    ax.set_xlabel(labels[i])
    ax.set_yticks([])
plt.tight_layout()
plt.show()

lo, hi = np.percentile(samples, [5, 95], axis=0)
for name, a, b, true in zip(["Delta", "eta", "J"], lo, hi, theta_true):
    print(f"{name:>5}: 90% interval [{a:6.2f}, {b:6.2f}], true value {true}")
```

The x-axes span the whole prior, so the width of each histogram shows how much
the observation has narrowed it down: each 90% interval covers only a few per
cent of its prior range. Compare the intervals with the true values (red). A
true value outside one of three 90% intervals would not be unusual for a single
observation, and the [calibration guide](posterior-calibration.md) tests the
estimator over hundreds of them. More telling is that the true values sit
towards the edge of the posterior for all three parameters, for a reason that
becomes clear in step 9.

## 7. Reuse the estimator for new observations

Nothing in the training step referred to our observation. The estimator learned
the posterior for *any* statistics the simulator can produce, so inference on a
new recording costs only a forward pass. This is what is meant by amortised
inference. Here are two more observations, generated from different parameters.

```{code-cell} ipython3
new_truths = np.array([[0.4, -4.0, 18.5], [1.5, -5.0, 10.0]])
t, _, v_new = montbrio(new_truths)
x_new = summary_statistics(t, v_new)
new_samples = posterior.sample(x_new, 5000, np.random.RandomState(1))

fig, axes = plt.subplots(2, 3, figsize=(6.5, 3.6))
for row, (truth, smp) in enumerate(zip(new_truths, new_samples)):
    for i in range(3):
        ax = axes[row, i]
        ax.hist(smp[:, i], bins=60, range=limits[i], density=True, color=f"C{row + 1}")
        ax.axvline(truth[i], color="C3", lw=1.2)
        ax.set_xlim(limits[i])
        ax.set_yticks([])
        if row == 1:
            ax.set_xlabel(labels[i])
    axes[row, 0].set_ylabel(f"observation {row + 2}")
plt.tight_layout()
plt.show()
```

All these posteriors are narrow, and each contains its true value, but their
shapes differ from the first one and from each other. For observation 2, $J$ is
the least certain parameter, with a long tail towards weaker coupling. For
observation 3, $\Delta$ has a tail towards larger values. How much the data
reveal depends on the observation as well as on the model, and a single best-fit
value would hide that.

## 8. Check the posterior against the data

A posterior predictive check closes the loop. Take parameter draws from the
posterior, simulate them, and see whether the simulations resemble the
observation. Here we can also compare the firing rate, which the estimator
never saw.

```{code-cell} ipython3
t, r_pred, v_pred = montbrio(samples[:200])
_, r_obs, v_obs = montbrio(theta_true)

fig, axes = plt.subplots(2, 1, figsize=(6.5, 3.4), sharex=True)
for ax, pred, obs, name in [(axes[0], v_pred, v_obs, "$v$"), (axes[1], r_pred, r_obs, "$r$ (hidden)")]:
    lo, mid, hi = np.nanpercentile(pred, [5, 50, 95], axis=1)
    ax.fill_between(t, lo, hi, color="C0", alpha=0.3, lw=0, label="90% of posterior simulations")
    ax.plot(t, mid, color="C0", lw=1, label="median")
    ax.plot(t, obs[:, 0], color="k", lw=0.8, label="observation")
    ax.set_ylabel(name)
axes[1].legend(loc="upper left", fontsize=8)
axes[1].set_xlabel("time")
plt.show()
```

The simulated membrane potential follows the observation closely, oscillation
by oscillation. The hidden firing rate tells a different story. After the
stimulus, most posterior simulations settle at a higher rate than the true
one. The parameters agree with everything the voltage statistics measure, yet
they disagree about a quantity those statistics do not see.

## 9. Look at the joint posterior

The marginal histograms hide how parameters relate to one another. A pairwise
plot shows them.

```{code-cell} ipython3
pairplot(samples, labels, truth=theta_true)
plt.show()
print("posterior correlation matrix:")
print(np.round(np.corrcoef(samples.T), 2))
```

The posterior is not a cloud but a thin, curved ridge through all three
parameters: as $\Delta$ grows, $\eta$ falls and $J$ rises, and every point
along the ridge produces nearly the same membrane potential. The true
parameters lie at the edge of the ridge, which is why they sat off-centre in
the marginal histograms. Parameters that compensate for one another like this
are called degenerate, and degeneracies are common in neural models. They are
also why the predictive check of the hidden firing rate went astray. Points
along the ridge agree on $v$ but not on $r$.

The same structure comes out of an active-subspace sensitivity analysis
[@constantine2014]. Average the outer product of the gradient of
$\log q(\theta \mid x)$ over posterior samples, and take the eigenvectors of the
result. They point along the directions in which the posterior density changes
fastest (large eigenvalue) and slowest (small eigenvalue). We measure the
gradients in units of prior standard deviation so that the three parameters are
comparable.

```{code-cell} ipython3
def log_prob_gradients(posterior, theta, x, scale, h=1e-3):
    grads = np.empty_like(theta)
    for i in range(theta.shape[1]):
        step = np.zeros(theta.shape[1])
        step[i] = h * scale[i]
        up = posterior.log_prob(theta + step, x)
        down = posterior.log_prob(theta - step, x)
        grads[:, i] = (up - down) / (2 * h)
    return grads


grads = log_prob_gradients(posterior, samples[:2000], x_true, prior.std)
grads = grads[np.all(np.isfinite(grads), axis=1)]
eigvals, eigvecs = np.linalg.eigh(grads.T @ grads / len(grads))
for k in (2, 0):
    weights = ", ".join(f"{name} {w:+.2f}" for name, w in zip(["Delta", "eta", "J"], eigvecs[:, k]))
    print(f"eigenvalue {eigvals[k]:9.1f}: {weights}")
```

The stiffest direction is a combination of all three parameters that the
voltage statistics pin down tightly. The sloppiest, whose eigenvalue is smaller
by well over an order of magnitude, moves mainly $J$, with $\Delta$ changing in
the same sense and $\eta$ in the opposite one. That is the direction of the
ridge.

## 10. Break the degeneracy with a second measurement

If the firing rate can be recorded too, its statistics carry information that
the voltage lacks. We concatenate them with the voltage statistics, retrain on
the same simulations, and compare.

```{code-cell} ipython3
x_train_rv = np.hstack([x_train, summary_statistics(t, r_train)])
x_true_rv = np.hstack([x_true, summary_statistics(t, r_obs)[0]])

posterior_rv = NPE(prior, n_flows=5, hidden_units=64)
posterior_rv.train(theta_train, x_train_rv, n_iter=6000, batch_size=256, learning_rate=1e-3, patience=20)
samples_rv = posterior_rv.sample(x_true_rv, 5000, np.random.RandomState(0))

fig = pairplot(samples, labels, truth=theta_true, color="C0")
pairplot(samples_rv, labels, color="C1", fig=fig)
fig.legend([plt.Line2D([], [], color="C0"), plt.Line2D([], [], color="C1")], ["$v$ only", "$v$ and $r$"], loc="upper right")
plt.show()

shrink_v, _ = shrinkage_zscore(samples, theta_true, prior.std)
shrink_rv, _ = shrinkage_zscore(samples_rv, theta_true, prior.std)
print("posterior standard deviation, v only: ", np.round(samples.std(axis=0), 3))
print("posterior standard deviation, v and r:", np.round(samples_rv.std(axis=0), 3))
print("shrinkage, v only: ", np.round(shrink_v, 3))
print("shrinkage, v and r:", np.round(shrink_rv, 3))
```

With both variables (orange), the ridge collapses onto a small region around
the true parameters, and the posterior standard deviations drop for every
parameter, most of all for $J$. The shrinkage, one minus the ratio of posterior
to prior variance, was already high because the prior is broad, and moves closer
still to 1. The ridge came mainly from what we measured: the voltage statistics
do not contain the information that separates the parameters, and more
simulations would not have supplied it. @baldy2024 observe the same effect,
and also note that density estimators of this kind can exaggerate correlations
between parameters, so the voltage-only ridge may be somewhat longer than the
exact posterior would be.

## What you have done

You built the full simulation-based inference loop for a neural mass model:
simulator, summary statistics, prior, training set, amortised posterior,
predictive check, and an analysis of what the data can and cannot identify. The
same steps apply to any model you can simulate. The parameters do not even have
to be biophysical: moving the stimulus amplitude or frequency into $\theta$
turns the same pipeline into an estimator of the input.

Before trusting an amortised posterior on real data, check that it is
calibrated across the whole prior, not only for a few hand-picked observations.
[Checking an amortised posterior](posterior-calibration.md) shows how. If the
likelihood of your model can be written down, the
[likelihood-based route](erp-likelihood.md) is an alternative.
