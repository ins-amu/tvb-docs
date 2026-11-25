---
title: "How-to: fit an evoked-response model with a likelihood"
kernelspec:
  name: python3
  display_name: Python 3
  language: python
bibliography:
  - ../../references.bib
---

# How-to: fit an evoked-response model with a likelihood

:::{tip} Run interactively
- **[Open in JupyterLite Lab](/lite/lab/index.html?path=user-guide/inference/erp-likelihood.ipynb)**
- **[Download Notebook](/notebooks/user-guide/inference/erp-likelihood.ipynb)**
:::

**Goal:** estimate the parameters of a neural mass model from an event-related
potential (ERP) when the model is deterministic and the measurement noise is
Gaussian, so that the likelihood can be evaluated directly.

When the likelihood is available you do not need a density estimator. You can
optimise it, approximate the posterior around its peak, or sample the posterior
with Markov chain Monte Carlo (MCMC). This guide does all three for the ERP
model used in dynamic causal modelling [@david2006], and then compares model
variants. It follows the study of @baldy2025, with two substitutions that keep
everything in NumPy: gradient-free Metropolis-Hastings sampling with `emcee`
[@foremanmackey2013] instead of the No-U-Turn sampler, and finite differences
instead of automatic differentiation.

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
import emcee
import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import differential_evolution, minimize

from tvbl.infer import (
    Gamma, LogPosterior, aic, bic, ess_bulk, ess_tail, laplace_approximation,
    pairplot, rhat, shrinkage_zscore, student_t_proposal,
)
```

## Step 1: Simulate the model and an observation

The model describes a cortical source with three populations: spiny stellate
cells, which receive the input, pyramidal cells and inhibitory interneurons.
Each population turns the firing of its afferents into a postsynaptic potential
through a second-order synaptic kernel. Writing the equations as in
@baldy2025, with states $x_1$ to $x_9$,

$$
\begin{aligned}
\dot x_1 &= x_4, & \dot x_4 &= \frac{h_e}{\tau_e}\big(g_1 S(x_9) + u\big) - \frac{x_1}{\tau_e^2} - \frac{2 x_4}{\tau_e}, \\
\dot x_2 &= x_5, & \dot x_5 &= \frac{h_e}{\tau_e}\, g_2 S(x_1) - \frac{x_2}{\tau_e^2} - \frac{2 x_5}{\tau_e}, \\
\dot x_3 &= x_6, & \dot x_6 &= \frac{h_i}{\tau_i}\, g_4 S(x_7) - \frac{x_3}{\tau_i^2} - \frac{2 x_6}{\tau_i}, \\
\dot x_7 &= x_8, & \dot x_8 &= \frac{h_e}{\tau_e}\, g_3 S(x_9) - \frac{x_7}{\tau_e^2} - \frac{2 x_8}{\tau_e}, \\
\dot x_9 &= x_5 - x_6, & S(y) &= \frac{1}{1 + e^{-0.56\, y}} - \frac{1}{2}.
\end{aligned}
$$

$x_1$ is the stellate potential, $x_7$ the interneuron potential, and $x_9$, the
pyramidal potential, is the only observed variable. The gains $g_1$ to $g_4$ set
the strength of the four intrinsic connections, $h_e$ and $h_i$ the amplitude of
excitatory and inhibitory postsynaptic potentials, and $\tau_e$ and $\tau_i$
their time constants. Starting from rest, a constant input $u$ to the stellate
cells evokes a transient in $x_9$, the ERP. Each sigmoid is evaluated at a
potential delayed by $\delta$, using the first-order approximation
$y(t - \delta) \approx y(t) - \delta \dot y(t)$, which turns the delay equations
into ordinary ones.

@baldy2025 infer all ten parameters. Here we fix the two time constants and the
input at their true values and infer the remaining seven. The impulse response
of each synaptic kernel is $(h/\tau)\, t\, e^{-t/\tau}$, whose area is $h\tau$, so a
time constant can be partly traded against the corresponding amplitude. Fixing
them removes that trade-off and makes the example several times faster. It also
gives the simulator a convenient form. With the time constants fixed, the linear
part of the equations is the same for every parameter set, and an Euler step
becomes one matrix product plus the three sigmoids.

```{code-cell} ipython3
names = ["g1", "g2", "g3", "g4", "delta", "h_i", "h_e"]
labels = [r"$g_1$", r"$g_2$", r"$g_3$", r"$g_4$", r"$\delta$", r"$h_i$", r"$h_e$"]
tau_e, tau_i, u_input = 5.77, 7.77, 3.94


def erp_model(theta, dt=0.2, t_end=200.0, record_every=5):
    """Pyramidal potential x9 for each row of theta, sampled every millisecond."""
    theta = np.atleast_2d(theta)
    g1, g2, g3, g4, delta, h_i, h_e = theta.T
    # State order x1..x9 is stored in rows 0..8.
    linear = np.zeros((9, 9))
    for pos, vel, tau in ((0, 3, tau_e), (1, 4, tau_e), (2, 5, tau_i), (6, 7, tau_e)):
        linear[pos, vel] = 1.0
        linear[vel, pos] = -1.0 / tau ** 2
        linear[vel, vel] = -2.0 / tau
    linear[8, 4], linear[8, 5] = 1.0, -1.0
    euler = np.eye(9) + dt * linear
    # Rows 0-2 read x9, x1, x7; rows 3-5 read their derivatives for the delay.
    probe = np.zeros((6, 9))
    probe[0, 8] = probe[1, 0] = probe[2, 6] = 1.0
    probe[3, 4], probe[3, 5], probe[4, 3], probe[5, 7] = 1.0, -1.0, 1.0, 1.0
    gain = dt * np.stack([h_e * g1 / tau_e, h_e * g2 / tau_e, h_i * g4 / tau_i, h_e * g3 / tau_e])
    drive = np.zeros_like(gain)
    drive[0] = dt * h_e * u_input / tau_e
    x = np.zeros((9, theta.shape[0]))
    out = [x[8].copy()]
    with np.errstate(over="ignore", invalid="ignore"):
        for step in range(1, int(round(t_end / dt)) + 1):
            p = probe @ x
            s = 1.0 / (1.0 + np.exp(-0.56 * (p[:3] - delta * p[3:]))) - 0.5
            x = euler @ x
            x[[3, 4, 5, 7]] += gain * s[[0, 1, 2, 0]] + drive
            if step % record_every == 0:
                out.append(x[8].copy())
    return np.array(out).T
```

The observation is generated from the parameter values used by @baldy2025,
with Gaussian measurement noise of standard deviation 0.1, and sampled every
millisecond. @baldy2025 integrate with a step of 0.1 ms. We use 0.2 ms, which
changes the trace by less than a third of the noise level and halves the cost.

```{code-cell} ipython3
theta_true = np.array([0.42, 0.76, 0.15, 0.16, 12.13, 27.87, 1.63])
noise_sd = 0.1
t = np.arange(201.0)
rng = np.random.default_rng(1)
clean = erp_model(theta_true)[0]
y_obs = clean + noise_sd * rng.standard_normal(clean.size)

fig, ax = plt.subplots(figsize=(6.5, 2.4))
ax.plot(t, y_obs, ".", color="k", ms=2.5, label="observation")
ax.plot(t, clean, color="C3", lw=1.2, label="noise-free model")
ax.set_xlabel("time (ms)")
ax.set_ylabel(r"pyramidal potential $x_9$")
ax.legend()
plt.show()
```

## Step 2: Fit by optimisation, and see why it is not enough

The simplest approach searches for the parameters that minimise the mean
squared error between simulation and data. Differential evolution
[@storn1997] is a global optimiser that needs only bounds, and SciPy can
evaluate its whole population in a single call (`vectorized=True`). We run it
twice from different random seeds.

```{code-cell} ipython3
bounds = [(1e-3, 1.0)] * 4 + [(1.0, 20.0), (5.0, 50.0), (0.1, 5.0)]


def mse(population):
    err = np.mean((erp_model(population.T) - y_obs) ** 2, axis=1)
    return np.where(np.isfinite(err), err, 1e6)


fits = [
    differential_evolution(mse, bounds, popsize=10, maxiter=200, tol=1e-6, polish=False,
                           seed=seed, vectorized=True, updating="deferred")
    for seed in (0, 1)
]

print(f"{'':>8} {'true':>7} {'seed 0':>7} {'seed 1':>7}")
for i, name in enumerate(names):
    print(f"{name:>8} {theta_true[i]:7.2f} {fits[0].x[i]:7.2f} {fits[1].x[i]:7.2f}")
products = [theta_true[1] * theta_true[6]] + [fit.x[1] * fit.x[6] for fit in fits]
print(f"{'g2 * h_e':>8} {products[0]:7.2f} {products[1]:7.2f} {products[2]:7.2f}")
print(f"{'MSE':>8} {np.mean((clean - y_obs) ** 2):7.4f} {fits[0].fun:7.4f} {fits[1].fun:7.4f}")
```

Both runs fit the data as well as the true parameters do, with errors at the
level of the noise. Yet they disagree. One finds $g_2 \approx 0.3$ and
$h_e \approx 4.4$, the other $g_2 \approx 0.8$ and $h_e \approx 1.5$, and both
are far from the truth for $g_1$ and $h_i$. The products $g_2 h_e$, on the other
hand, agree with each other and with the true value: the connection from
stellate to pyramidal cells enters the ERP mainly through that product, so the
data fix the product but not its factors. The error surface has a long, flat
valley rather than a single minimum, and an optimiser returns one point in that
valley without saying how long it is. Bayesian inference describes the whole
valley.

## Step 3: Specify priors and check them

The parameters are positive and have typical ranges known from earlier
modelling work. We use the weakly informative Gamma priors of @baldy2025, which
are motivated by @sengupta2015. Before using them, simulate from the prior and
check that the resulting signals are plausible. This prior predictive check
catches priors that are too narrow to contain the data, or so wide that most of
their mass produces nonsense.

```{code-cell} ipython3
shape = np.array([18.16, 29.9, 29.14, 30.77, 22.87, 20.44, 24.17])
scale = np.array([0.03, 0.02, 0.005, 0.007, 0.51, 0.96, 0.07])
prior = Gamma(shape, 1 / scale)

prior_draws = prior.sample(300, np.random.default_rng(2))
prior_sims = erp_model(prior_draws)

fig, ax = plt.subplots(figsize=(6.5, 2.4))
lo, hi = np.percentile(prior_sims, [5, 95], axis=0)
ax.fill_between(t, lo, hi, color="0.6", alpha=0.35, lw=0, label="90% of prior simulations")
ax.plot(t, prior_sims[:15].T, color="0.45", lw=0.5)
ax.plot(t, y_obs, ".", color="k", ms=2.5, label="observation")
ax.set_xlabel("time (ms)")
ax.set_ylabel(r"$x_9$")
ax.legend()
plt.show()
```

All prior simulations are ERP-like transients, and the observation lies within
their range. The priors are informative but do not exclude the data.

## Step 4: Write down the log-posterior

With Gaussian measurement noise, the log-likelihood is a scaled sum of squared
residuals. `LogPosterior` combines it with the prior and works in the
unconstrained coordinates $\log\theta$, so that optimisers and samplers can move
freely without ever proposing a negative value. It adds the log-Jacobian of this
change of variables, without which the sampler would target the wrong density.
It accepts a batch of points and returns one value per point.

```{code-cell} ipython3
def log_likelihood(theta):
    resid = erp_model(theta) - y_obs
    ll = -0.5 * np.sum(resid ** 2, axis=1) / noise_sd ** 2 - y_obs.size * np.log(noise_sd * np.sqrt(2 * np.pi))
    return np.where(np.isfinite(ll), ll, -np.inf)


log_post = LogPosterior(prior, log_likelihood)
dim = len(names)
```

## Step 5: Find the posterior mode and a Laplace approximation

The mode of the posterior (the maximum a posteriori, or MAP, estimate) is found
with L-BFGS. Its gradient comes from central finite differences, again
evaluated in one batched call. Around the mode, the Laplace approximation
replaces the posterior with a Gaussian whose covariance is the inverse of the
negative Hessian of the log-posterior [@kass1995].

```{code-cell} ipython3
def value_and_grad(f, u, h=1e-5):
    points = np.vstack([u, u + h * np.eye(u.size), u - h * np.eye(u.size)])
    values = f(points)
    return values[0], (values[1:u.size + 1] - values[u.size + 1:]) / (2 * h)


def maximise(f, u0):
    res = minimize(lambda u: tuple(-a for a in value_and_grad(f, u)), u0, jac=True, method="L-BFGS-B")
    return res.x, -res.fun


u_map, _ = maximise(log_post, log_post.to_unbounded(fits[0].x)[0])
laplace_cov, log_evidence = laplace_approximation(log_post, u_map)
print("MAP estimate:", dict(zip(names, np.round(log_post.to_params(u_map), 3))))
```

The Laplace approximation is cheap and often good, but only as good as the
Gaussian assumption behind it. The variational methods compared by @baldy2025
make the same kind of assumption. MCMC does not.

## Step 6: Sample the posterior with MCMC

Each sampler in `emcee` runs an ensemble of walkers. Its default moves
[@goodman2010] need no tuning, but they mix slowly on this correlated
posterior, and each step costs two batched simulations. Instead we use
Metropolis-Hastings moves, for which every walker is an independent chain, in
two stages.

During a warm-up, the walkers take random-walk steps shaped by the Laplace
covariance and scaled by $2.38^2/d$, the optimal scaling for random-walk
Metropolis in $d$ dimensions [@roberts1997]. Halfway through, the covariance is
re-estimated from the chains, as in adaptive Metropolis [@haario2001]. The
proposal stops changing at the end of the warm-up, and the warm-up draws are
discarded, so the sampling stage is an ordinary Markov chain. In that stage
most moves are independence proposals [@tierney1994]. Each candidate is drawn
from a Student-t distribution fitted to the warm-up draws, regardless of the
current state, and accepted with the Metropolis-Hastings probability. When the
proposal resembles the posterior, as here, successive draws are nearly
independent. One move in twenty is still a random-walk step, so the chains can
explore locally if the proposal misses part of the posterior.

To test whether the chains reach the same distribution regardless of where they
start, half of them start around each of the two optimiser solutions from step
2.

```{code-cell} ipython3
def random_walk(cov):
    return emcee.moves.GaussianMove(cov * 2.38 ** 2 / dim)


def run(p0, moves, n_steps):
    sampler = emcee.EnsembleSampler(len(p0), dim, log_post, vectorize=True, moves=moves)
    sampler.run_mcmc(p0, n_steps, progress=False)
    return sampler


n_walkers, n_warmup, n_steps = 32, 400, 800
rng = np.random.default_rng(3)
starts = [log_post.to_unbounded(fit.x)[0] for fit in fits]
p0 = np.vstack([rng.multivariate_normal(s, laplace_cov, size=n_walkers // 2) for s in starts])

warm1 = run(p0, random_walk(laplace_cov), n_warmup // 2)
adapted_cov = np.cov(warm1.get_chain()[n_warmup // 4:].reshape(-1, dim).T)
warm2 = run(warm1.get_last_sample().coords, random_walk(adapted_cov), n_warmup // 2)
warm_draws = warm2.get_chain().reshape(-1, dim)

moves = [
    (emcee.moves.MHMove(student_t_proposal(warm_draws.mean(axis=0), np.cov(warm_draws.T))), 0.95),
    (random_walk(np.cov(warm_draws.T)), 0.05),
]
sampler = run(warm2.get_last_sample().coords, moves, n_steps)

chains_u = np.concatenate([warm1.get_chain(), warm2.get_chain(), sampler.get_chain()])
chains = log_post.to_params(chains_u.reshape(-1, dim)).reshape(chains_u.shape).transpose(1, 0, 2)
kept = chains[:, n_warmup:]
samples = kept.reshape(-1, dim)

print(f"acceptance rate {sampler.acceptance_fraction.mean():.2f}")
print(f"{'':>6} {'R-hat':>6} {'bulk ESS':>9} {'tail ESS':>9}")
for name, r, b, tl in zip(names, rhat(kept), ess_bulk(kept), ess_tail(kept)):
    print(f"{name:>6} {r:6.3f} {b:9.0f} {tl:9.0f}")
```

Two diagnostics decide whether the draws can be used [@vehtari2021]. The
rank-normalised R-hat compares the chains with each other and the halves of each
chain with each other, both in location and in spread. Values below 1.01 mean
the chains agree. The effective sample size (ESS) estimates how many independent
draws the correlated ones are worth, separately for the centre of the
distribution (bulk) and for its 5% and 95% quantiles (tail). A few hundred of
each is enough for means and 90% intervals. All parameters pass both checks.
The trace plots show the same thing.

```{code-cell} ipython3
fig, axes = plt.subplots(3, 1, figsize=(6.5, 4.2), sharex=True)
for ax, i in zip(axes, [1, 5, 6]):
    ax.plot(chains[:n_walkers // 2, :, i].T, color="C0", lw=0.3, alpha=0.4)
    ax.plot(chains[n_walkers // 2:, :, i].T, color="C1", lw=0.3, alpha=0.4)
    ax.axvline(n_warmup, color="k", ls="--", lw=0.8)
    ax.set_ylabel(labels[i])
axes[0].set_title("chains started at optimiser solution 1 (blue) and 2 (orange)")
axes[-1].set_xlabel("step (warm-up left of the dashed line)")
plt.show()
```

The two groups of chains leave their starting points within the first hundred
steps or so and then explore the same region. The two answers from step 2 were
two points of one posterior.

## Step 7: Read the posterior

Compare each marginal posterior with its prior, the Laplace approximation and
the true value.

```{code-cell} ipython3
prior_hist = prior.sample(20_000, np.random.default_rng(7))
laplace_draws = log_post.to_params(np.random.default_rng(4).multivariate_normal(u_map, laplace_cov, size=samples.shape[0]))

fig, axes = plt.subplots(1, dim, figsize=(10, 2.0))
for i, ax in enumerate(axes):
    lo, hi = np.percentile(np.concatenate([prior_hist[:, i], samples[:, i]]), [0.5, 99.5])
    bins = np.linspace(lo, hi, 45)
    ax.hist(prior_hist[:, i], bins=bins, density=True, color="0.6", alpha=0.45, label="prior")
    ax.hist(samples[:, i], bins=bins, density=True, color="C0", alpha=0.75, label="MCMC")
    ax.hist(laplace_draws[:, i], bins=bins, density=True, histtype="step", color="k", lw=0.8, label="Laplace")
    ax.axvline(theta_true[i], color="C3", lw=1.2)
    ax.set_xlabel(labels[i])
    ax.set_yticks([])
handles, names_legend = axes[0].get_legend_handles_labels()
fig.legend(handles + [plt.Line2D([], [], color="C3")], names_legend + ["true value"], loc="upper center", ncol=4, bbox_to_anchor=(0.5, 1.12))
plt.tight_layout()
plt.show()

shrinkage, z = shrinkage_zscore(samples, theta_true, prior.std)
for i, name in enumerate(names):
    print(f"{name:>6}: shrinkage {shrinkage[i]:5.2f}, z-score {z[i]:+5.2f}")
```

The shrinkage, one minus the ratio of posterior to prior variance, says how much
the data have narrowed each parameter. The z-score says how many posterior
standard deviations separate the posterior mean from the true value. Reading
them together with the histograms:

- The delay $\delta$ is pinned down almost exactly (shrinkage close to 1), and
  so is the product $g_2 h_e$, as the pair plot below shows.
- The data say little about $g_1$, whose posterior is barely narrower than its
  prior. $g_3$, $g_4$ and $h_i$ are only weakly constrained.
- The true value of $h_i$ lies in the lower tail of its posterior, about two and
  a half posterior standard deviations from the mean. The prior itself places
  most of its mass below the true value, and the data do not override it. This
  is how an informative prior shows up in practice, and a reminder to choose
  priors deliberately.
- The Laplace approximation matches MCMC closely on every marginal. For this
  nearly Gaussian posterior (in $\log\theta$) it would have been enough, at a
  fraction of the cost.

```{code-cell} ipython3
fig = pairplot(samples[:, [1, 6]], [labels[1], labels[6]], truth=theta_true[[1, 6]])
ax = fig.axes[2]
g2_grid = np.linspace(*ax.get_xlim(), 100)
ax.plot(g2_grid, products[0] / g2_grid, color="C3", lw=0.8, ls="--")
ax.set_ylim(np.percentile(samples[:, 6], [0.5, 99.5]))
plt.show()
print(f"correlation of log g2 and log h_e: {np.corrcoef(np.log(samples[:, [1, 6]]).T)[0, 1]:+.3f}")
```

The joint posterior of $g_2$ and $h_e$ lies along the curve $g_2 h_e =
\text{const}$ (dashed), the valley the two optimiser runs fell into. Each factor
is uncertain, while their product is not.

## Step 8: Check the fit

A posterior predictive check simulates the model at posterior draws, adds
measurement noise, and compares the spread with the data. The observation
should look like a typical member of that spread.

```{code-cell} ipython3
draws = samples[np.random.default_rng(5).choice(len(samples), 300, replace=False)]
predictive = erp_model(draws) + noise_sd * np.random.default_rng(6).standard_normal((300, t.size))

fig, ax = plt.subplots(figsize=(6.5, 2.4))
lo, hi = np.percentile(predictive, [5, 95], axis=0)
ax.fill_between(t, lo, hi, color="C0", alpha=0.3, lw=0, label="90% posterior predictive")
ax.plot(t, y_obs, ".", color="k", ms=2.5, label="observation")
ax.set_xlabel("time (ms)")
ax.set_ylabel(r"$x_9$")
ax.legend()
plt.show()
print(f"fraction of observed points inside the 90% band: {np.mean((y_obs >= lo) & (y_obs <= hi)):.2f}")
```

The band contains about 90% of the observed points, as it should if the model
with these parameters describes the data.

## Step 9: Compare model variants

Is every connection needed? Each variant below removes one intrinsic connection
by fixing its gain to zero. Three criteria are common. The Akaike and Bayesian
information criteria [@akaike1974; @schwarz1978] penalise the maximum
log-likelihood by the number of parameters, and lower values are better. The
Laplace approximation of the model evidence $p(y \mid M)$ integrates over the
prior instead, and higher values are better; differences in log evidence are
log Bayes factors [@kass1995].

```{code-cell} ipython3
def reduced_model(drop):
    keep = [k for k in range(dim) if k != drop]

    def log_lik(theta_k):
        full = np.zeros((theta_k.shape[0], dim))
        full[:, keep] = theta_k
        return log_likelihood(full)

    return keep, LogPosterior(Gamma(shape[keep], 1 / scale[keep]), log_lik)


rows = []
for drop in [None, 0, 1, 2, 3]:
    if drop is None:
        keep, model, label = list(range(dim)), log_post, "full model"
    else:
        keep, model = reduced_model(drop)
        label = f"{names[drop]} = 0"
    u_mode, _ = maximise(model, u_map[keep])
    _, log_ev = laplace_approximation(model, u_mode)
    _, max_ll = maximise(lambda u, m=model: m.log_likelihood(m.to_params(u)), u_mode)
    rows.append((label, len(keep), max_ll, aic(max_ll, len(keep)), bic(max_ll, len(keep), y_obs.size), log_ev))

print(f"{'model':>12} {'k':>3} {'max log-lik':>12} {'AIC':>10} {'BIC':>10} {'log evidence':>13}")
for label, k, ll, a, b, ev in rows:
    print(f"{label:>12} {k:3d} {ll:12.1f} {a:10.1f} {b:10.1f} {ev:13.1f}")
```

Each reduced model is fitted starting from the full-model solution, so its
numbers describe the best fit found from there. The verdicts below are not close
calls.

Dropping $g_1$ costs essentially nothing in likelihood, so AIC and BIC prefer
the smaller model. The log evidence of the two models differs by about 0.1, a
Bayes factor that @kass1995 would call not worth more than a bare mention: the
data cannot tell whether the connection is there. This is consistent with the
weak constraint on $g_1$ seen above, and @baldy2025 also rank the model without
$g_1$ first. Dropping $g_2$, $g_3$ or $g_4$ is catastrophic, with
log-likelihoods lower by thousands. Without $g_2$ the
stellate cells no longer drive the pyramidal cells. Zeroing either $g_3$ or $g_4$
cuts the inhibitory loop through the interneurons, which is why those two
variants give identical numbers. Whether a parameter is well identified and
whether the model needs it are different questions: $g_3$ and $g_4$ are needed
even though their values are uncertain, and $g_1$ is the reverse.

## Notes and pitfalls

- **Degeneracy belongs to the model and the data, not to the method.**
  Optimisation hides it and MCMC exposes it. Only more informative data cure it:
  other conditions, other recorded populations, or priors justified by
  independent knowledge.
- **Start chains from dispersed points.** Chains started at one point can agree
  with each other while all missing a second mode. @baldy2025 start their
  gradient-based chains in the tails of the prior. Random-walk proposals
  starting there need far more steps than this page affords, which is why we
  start from two different optimiser solutions instead.
- **Choice of sampler.** The proposals used here depend on the warm-up giving a
  reasonable picture of the posterior's shape. For multimodal or strongly
  curved posteriors, gradient-based samplers such as the No-U-Turn sampler in
  Stan or NumPyro are more robust, at the price of a differentiable simulator.
  When the likelihood is intractable, for example because noise enters the
  dynamics, use [simulation-based inference](npe-montbrio.md) instead.
- **Real data.** Recorded ERPs must first be brought to the model's scale and
  time base. The same steps then apply, but the noise level becomes a parameter
  to infer rather than a known constant.

## Related documentation

- [Inference overview](../inference.md): likelihood-based and simulation-based
  inference compared.
- [How-to: check that an amortised posterior can be trusted](posterior-calibration.md).
- [Jansen-Rit model card](../../reference/model-cards/jansen-rit.md): the
  neural mass model this ERP model derives from [@jansenRit1995].
