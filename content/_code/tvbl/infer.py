"""
Inference utilities built on plain NumPy and SciPy.

Simulation-based inference
    Priors that know how to map their support onto the real line, feature and
    parameter standardisation, and :class:`NPE`, which wraps a conditional
    density estimator from :mod:`tvbl.cde` into an amortised posterior.

Calibration
    Simulation-based calibration ranks and their histogram, expected
    coverage of central intervals and highest-density regions, and the
    shrinkage / z-score summary of posterior quality.

Likelihood-based inference
    A vectorised log-posterior in unconstrained coordinates (suitable for
    ``emcee`` with ``vectorize=True``), a Student-t independence proposal for
    Metropolis-Hastings, a finite-difference Laplace approximation,
    information criteria, and the rank-normalised R-hat and bulk and tail
    effective sample sizes of Vehtari et al. (2021).
"""

import numpy as np
from scipy import special, stats

from .cde import MAFEstimator


# =============================================================================
# == Priors
# =============================================================================

class BoxUniform:
    """Independent uniform prior on a box ``[low, high]``.

    The unconstrained coordinate is ``logit((theta - low) / (high - low))``,
    so a density estimator working on that coordinate can never place mass
    outside the box.
    """

    def __init__(self, low, high):
        self.low = np.asarray(low, dtype=float).reshape(-1)
        self.high = np.asarray(high, dtype=float).reshape(-1)
        if self.low.shape != self.high.shape or np.any(self.high <= self.low):
            raise ValueError("low and high must have the same shape with high > low.")
        self.dim = self.low.size

    @property
    def mean(self):
        return 0.5 * (self.low + self.high)

    @property
    def std(self):
        return (self.high - self.low) / np.sqrt(12.0)

    def sample(self, n, rng):
        return rng.uniform(self.low, self.high, size=(n, self.dim))

    def log_prob(self, theta):
        theta = np.atleast_2d(theta)
        inside = np.all((theta >= self.low) & (theta <= self.high), axis=-1)
        return np.where(inside, -np.sum(np.log(self.high - self.low)), -np.inf)

    def _unit(self, theta):
        s = (np.atleast_2d(theta) - self.low) / (self.high - self.low)
        return np.clip(s, 1e-9, 1.0 - 1e-9)

    def to_unbounded(self, theta):
        return special.logit(self._unit(theta))

    def from_unbounded(self, u):
        return self.low + (self.high - self.low) * special.expit(u)

    def log_abs_det_jacobian(self, theta):
        """``log |du/dtheta|`` summed over dimensions."""
        s = self._unit(theta)
        return -np.sum(np.log(s * (1.0 - s)) + np.log(self.high - self.low), axis=-1)


class Gamma:
    """Independent Gamma prior with per-dimension ``shape`` and ``rate``.

    The unconstrained coordinate is ``log(theta)``.
    """

    def __init__(self, shape, rate):
        self.shape = np.asarray(shape, dtype=float).reshape(-1)
        self.rate = np.asarray(rate, dtype=float).reshape(-1)
        if self.shape.shape != self.rate.shape:
            raise ValueError("shape and rate must have the same length.")
        self.dim = self.shape.size

    @property
    def mean(self):
        return self.shape / self.rate

    @property
    def std(self):
        return np.sqrt(self.shape) / self.rate

    def sample(self, n, rng):
        return rng.gamma(self.shape, 1.0 / self.rate, size=(n, self.dim))

    def log_prob(self, theta):
        theta = np.atleast_2d(theta)
        with np.errstate(divide="ignore", invalid="ignore"):
            lp = stats.gamma.logpdf(theta, a=self.shape, scale=1.0 / self.rate)
        return np.where(np.all(theta > 0, axis=-1), np.sum(lp, axis=-1), -np.inf)

    def ppf(self, q):
        return stats.gamma.ppf(q, a=self.shape, scale=1.0 / self.rate)

    def to_unbounded(self, theta):
        return np.log(np.atleast_2d(theta))

    def from_unbounded(self, u):
        return np.exp(u)

    def log_abs_det_jacobian(self, theta):
        return -np.sum(np.log(np.atleast_2d(theta)), axis=-1)


# =============================================================================
# == Neural posterior estimation
# =============================================================================

class Standardizer:
    """Z-scores columns using statistics of the data it was built from.

    Columns with (near) zero spread are only centred, so constant features
    do not produce infinities.
    """

    def __init__(self, data, min_std=1e-8):
        data = np.asarray(data, dtype=float)
        self.mean = data.mean(axis=0)
        std = data.std(axis=0)
        self.std = np.where(std > min_std, std, 1.0)

    def __call__(self, data):
        return (np.asarray(data) - self.mean) / self.std

    def inverse(self, data):
        return np.asarray(data) * self.std + self.mean

    @property
    def log_scale(self):
        return np.sum(np.log(self.std))


class NPE:
    """Amortised neural posterior estimation.

    The estimator learns ``q(theta | x)`` from simulated pairs.  Internally the
    parameters are mapped to the prior's unconstrained coordinate and both
    parameters and features are standardised, which is what makes a small
    density estimator train reliably.  All of this is undone when sampling or
    evaluating densities, which are therefore in the original units.

    Parameters
    ----------
    prior : BoxUniform or Gamma
        The prior the training parameters were drawn from.
    estimator : class, optional
        A :class:`tvbl.cde.ConditionalDensityEstimator` subclass.
    **estimator_kwargs
        Passed to the estimator (e.g. ``n_flows``, ``hidden_units``).
    """

    def __init__(self, prior, estimator=MAFEstimator, **estimator_kwargs):
        self.prior = prior
        self.estimator_class = estimator
        if estimator is MAFEstimator:
            estimator_kwargs.setdefault("context_units", True)
        self.estimator_kwargs = estimator_kwargs
        self.estimator = None

    def train(self, theta, x, n_iter=3000, learning_rate=1e-3, batch_size=256,
              validation_fraction=0.1, patience=20, clip_norm=5.0, seed=0,
              use_tqdm=False, **train_kwargs):
        """Fit the estimator to simulated pairs ``theta`` ``(n, dim)`` and
        ``x`` ``(n, n_features)``.

        Rows with non-finite values or parameters outside the prior support
        are dropped.  The defaults follow common practice for neural posterior
        estimation (as in the ``sbi`` package): Adam on minibatches, ten per
        cent of the data held out, training stopped after ``patience`` epochs
        without improvement of the validation loss (the best weights are
        kept), and the gradient norm clipped at ``clip_norm``.  ``n_iter`` is
        an upper bound on the number of gradient steps.  Returns ``self``.
        """
        theta = np.asarray(theta, dtype=float)
        x = np.asarray(x, dtype=float)
        ok = np.all(np.isfinite(theta), axis=1) & np.all(np.isfinite(x), axis=1)
        ok &= np.isfinite(self.prior.log_prob(theta))
        theta, x = theta[ok], x[ok]
        self.n_train = theta.shape[0]

        u = self.prior.to_unbounded(theta)
        self.theta_scaler = Standardizer(u)
        self.x_scaler = Standardizer(x)
        self.estimator = self.estimator_class(
            param_dim=theta.shape[1], feature_dim=x.shape[1], **self.estimator_kwargs)
        self.estimator.train(
            self.theta_scaler(u).astype("f"), self.x_scaler(x).astype("f"),
            n_iter=n_iter, learning_rate=learning_rate, seed=seed,
            use_tqdm=use_tqdm, batch_size=batch_size,
            validation_fraction=validation_fraction, patience=patience,
            clip_norm=clip_norm, **train_kwargs)
        return self

    @property
    def loss_history(self):
        return self.estimator.loss_history

    @property
    def val_loss_history(self):
        return getattr(self.estimator, "val_loss_history", [])

    def sample(self, x_obs, n_samples, rng):
        """Posterior samples for one observation ``(n_feat,)`` -> ``(n, dim)``
        or for several ``(m, n_feat)`` -> ``(m, n, dim)``."""
        if self.estimator is None:
            raise RuntimeError("Call train() first.")
        x_obs = np.asarray(x_obs, dtype=float)
        single = x_obs.ndim == 1
        xs = self.x_scaler(np.atleast_2d(x_obs)).astype("f")
        w = self.estimator.sample(xs, n_samples, rng)
        theta = self.prior.from_unbounded(self.theta_scaler.inverse(w))
        return theta[0] if single else theta

    def log_prob(self, theta, x_obs):
        """``log q(theta | x)``; ``x_obs`` may be one observation or one per row."""
        if self.estimator is None:
            raise RuntimeError("Call train() first.")
        theta = np.atleast_2d(np.asarray(theta, dtype=float))
        xs = self.x_scaler(np.atleast_2d(np.asarray(x_obs, dtype=float)))
        xs = np.broadcast_to(xs, (theta.shape[0], xs.shape[1]))
        w = self.theta_scaler(self.prior.to_unbounded(theta))
        lp = self.estimator.log_prob(xs.astype("f"), w.astype("f")).astype(float)
        lp = lp - self.theta_scaler.log_scale + self.prior.log_abs_det_jacobian(theta)
        return np.where(np.isfinite(self.prior.log_prob(theta)), lp, -np.inf)


# =============================================================================
# == Calibration
# =============================================================================

def sbc_ranks(posterior, theta, x, n_samples, rng):
    """Simulation-based calibration ranks.

    For each test pair ``(theta[i], x[i])`` (with ``theta[i]`` drawn from the
    prior) count how many of ``n_samples`` posterior draws fall below the
    true value.  For a calibrated posterior every rank in ``0..n_samples`` is
    equally likely.  Returns an integer array of shape ``(n_test, dim)``.
    """
    samples = posterior.sample(np.asarray(x), n_samples, rng)
    return np.sum(samples < np.asarray(theta)[:, None, :], axis=1)


def sbc_histogram(ranks, n_samples, n_bins=10, band=0.99):
    """Counts of SBC ranks per bin and the band expected under uniformity.

    Ranks take the ``n_samples + 1`` values ``0..n_samples``.  Unless that
    number is divisible by ``n_bins`` some bins collect more ranks than
    others and the histogram cannot be flat even for a perfect posterior,
    so this case is rejected.  Returns ``(counts, (low, high))`` where
    ``counts`` has shape ``(n_bins, dim)`` and the band holds the central
    ``band`` probability of a binomial count for each bin.
    """
    if (n_samples + 1) % n_bins:
        raise ValueError("n_samples + 1 must be divisible by n_bins.")
    ranks = np.asarray(ranks)
    width = (n_samples + 1) // n_bins
    counts = np.stack([np.bincount(ranks[:, k] // width, minlength=n_bins) for k in range(ranks.shape[1])], axis=1)
    tail = (1.0 - band) / 2.0
    low, high = stats.binom(ranks.shape[0], 1.0 / n_bins).ppf([tail, 1.0 - tail])
    return counts, (low, high)


def central_coverage(ranks, n_samples, levels):
    """Empirical coverage of central credible intervals, per parameter.

    The truth lies inside the central interval of credibility ``a`` exactly
    when its rank quantile is within ``a / 2`` of the median, so coverage
    follows from the SBC ranks.  Returns ``(len(levels), dim)``.
    """
    q = (np.asarray(ranks) + 0.5) / (n_samples + 1)
    levels = np.asarray(levels, dtype=float)
    return np.mean(np.abs(q[None] - 0.5) <= levels[:, None, None] / 2, axis=1)


def hpd_coverage(posterior, theta, x, n_samples, rng, levels):
    """Joint expected coverage of highest-density regions.

    The truth lies in the highest-density region of credibility ``a`` when the
    fraction of posterior draws with a higher density than the truth is below
    ``a``.  Returns an array with one coverage value per level.
    """
    theta, x = np.asarray(theta), np.asarray(x)
    samples = posterior.sample(x, n_samples, rng)
    fractions = np.empty(theta.shape[0])
    for i in range(theta.shape[0]):
        lp_samples = posterior.log_prob(samples[i], x[i])
        lp_true = posterior.log_prob(theta[i:i + 1], x[i])[0]
        fractions[i] = np.mean(lp_samples > lp_true)
    levels = np.asarray(levels, dtype=float)
    return np.mean(fractions[None, :] < levels[:, None], axis=1)


def pairplot(samples, labels, truth=None, limits=None, max_points=2000, color="C0", fig=None,
             truth_color="C3"):
    """Marginal histograms on the diagonal and pairwise scatter below it.

    ``samples`` has shape ``(n, dim)``; ``truth`` (optional) is marked in
    ``truth_color`` and ``limits`` is a list of ``(low, high)`` per
    dimension.  Passing the returned figure back as ``fig`` overlays a second
    set of samples.
    """
    import matplotlib.pyplot as plt

    samples = np.asarray(samples)
    d = samples.shape[1]
    thin = samples[:: max(1, samples.shape[0] // max_points)]
    if fig is None:
        fig, _ = plt.subplots(d, d, figsize=(1.9 * d + 0.6, 1.9 * d + 0.6))
    axes = np.asarray(fig.axes).reshape(d, d)
    for i in range(d):
        for j in range(d):
            ax = axes[i, j]
            if j > i:
                ax.set_visible(False)
                continue
            if i == j:
                ax.hist(samples[:, i], bins=40, density=True, histtype="step", color=color)
                ax.set_yticks([])
                if truth is not None:
                    ax.axvline(truth[i], color=truth_color, lw=1.2)
            else:
                ax.plot(thin[:, j], thin[:, i], ".", ms=1.5, alpha=0.3, color=color)
                if truth is not None:
                    ax.plot(truth[j], truth[i], "+", color=truth_color, ms=10, mew=2)
                if limits is not None:
                    ax.set_ylim(limits[i])
            if limits is not None:
                ax.set_xlim(limits[j])
            if i == d - 1:
                ax.set_xlabel(labels[j])
            else:
                ax.set_xticklabels([])
            if j == 0 and i > 0:
                ax.set_ylabel(labels[i])
            elif j > 0:
                ax.set_yticklabels([])
    fig.tight_layout()
    return fig


def shrinkage_zscore(samples, theta_true, prior_std):
    """Posterior shrinkage and z-score.

    ``shrinkage = 1 - var_post / var_prior`` is near 1 when the data are
    informative; ``z = (mean_post - theta_true) / std_post`` measures how
    many posterior standard deviations the estimate is away from the truth.
    ``samples`` has shape ``(..., n_samples, dim)``.
    """
    samples = np.asarray(samples)
    post_mean = samples.mean(axis=-2)
    post_std = samples.std(axis=-2)
    shrinkage = 1.0 - post_std ** 2 / np.asarray(prior_std) ** 2
    zscore = (post_mean - np.asarray(theta_true)) / post_std
    return shrinkage, zscore


# =============================================================================
# == Likelihood-based inference
# =============================================================================

class LogPosterior:
    """Vectorised log-posterior in the prior's unconstrained coordinates.

    ``log_likelihood`` maps an ``(n, dim)`` array of parameters to ``(n,)``
    log-likelihoods.  Calling the object with unconstrained points ``u`` of
    shape ``(n, dim)`` returns ``log p(theta) + log p(data | theta)`` plus the
    log-Jacobian of ``u -> theta``, which is the density an MCMC sampler
    working on ``u`` must target.  Use it with ``emcee`` via
    ``vectorize=True``.
    """

    def __init__(self, prior, log_likelihood):
        self.prior = prior
        self.log_likelihood = log_likelihood

    def to_params(self, u):
        return self.prior.from_unbounded(np.asarray(u))

    def to_unbounded(self, theta):
        return self.prior.to_unbounded(np.asarray(theta))

    def __call__(self, u):
        u = np.atleast_2d(u)
        theta = self.to_params(u)
        lp = self.prior.log_prob(theta) - self.prior.log_abs_det_jacobian(theta)
        good = np.isfinite(lp)
        out = np.full(u.shape[0], -np.inf)
        if np.any(good):
            ll = np.asarray(self.log_likelihood(theta[good]), dtype=float)
            out[good] = np.where(np.isfinite(ll), lp[good] + ll, -np.inf)
        return out


def student_t_proposal(mean, cov, df=5.0):
    """Independence proposal for Metropolis-Hastings.

    Draws every candidate from a multivariate Student-t with the given
    location and scale, regardless of the current state.  When ``mean`` and
    ``cov`` approximate the target (for example from a warm-up run or a
    Laplace approximation), successive draws are nearly independent; the
    heavy tails keep the importance ratio bounded where the target has more
    mass than a Gaussian would.  The returned function has the signature
    ``(x0, random) -> (x1, log_ratio)`` expected by ``emcee.moves.MHMove``,
    where ``log_ratio = log q(x0) - log q(x1)`` is the Hastings correction.
    """
    mean = np.asarray(mean, dtype=float)
    chol = np.linalg.cholesky(cov)
    precision = np.linalg.inv(cov)
    dim = mean.size

    def log_q(x):
        z = x - mean
        return -0.5 * (df + dim) * np.log1p(np.einsum("ni,ij,nj->n", z, precision, z) / df)

    def propose(x0, random):
        z = random.standard_normal(x0.shape) @ chol.T
        w = random.chisquare(df, size=x0.shape[0]) / df
        x1 = mean + z / np.sqrt(w)[:, None]
        return x1, log_q(x0) - log_q(x1)

    return propose


def laplace_approximation(log_density, u_map, step=1e-3):
    """Gaussian approximation around a mode of ``log_density``.

    The Hessian is built from central finite differences, with every
    perturbed point evaluated in a single vectorised call.  Returns the
    covariance in the coordinates of ``u_map`` and the Laplace estimate of
    the log-normalising constant (the log model evidence when
    ``log_density`` is an unnormalised log-posterior).
    """
    u_map = np.asarray(u_map, dtype=float)
    d = u_map.size
    eye = np.eye(d) * step
    points = [u_map]
    pairs = [(i, j) for i in range(d) for j in range(i, d)]
    for i, j in pairs:
        for si, sj in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
            points.append(u_map + si * eye[i] + sj * eye[j])
    values = log_density(np.array(points))
    f0, rest = values[0], values[1:].reshape(-1, 4)
    hess = np.empty((d, d))
    for k, (i, j) in enumerate(pairs):
        fpp, fpm, fmp, fmm = rest[k]
        hess[i, j] = hess[j, i] = (fpp - fpm - fmp + fmm) / (4 * step * step)
    precision = -hess
    sign, logdet = np.linalg.slogdet(precision)
    if sign <= 0:
        raise np.linalg.LinAlgError("The Hessian is not negative definite at u_map.")
    cov = np.linalg.inv(precision)
    log_evidence = f0 + 0.5 * d * np.log(2 * np.pi) - 0.5 * logdet
    return cov, log_evidence


def aic(max_log_likelihood, n_params):
    return 2 * n_params - 2 * max_log_likelihood


def bic(max_log_likelihood, n_params, n_data):
    return n_params * np.log(n_data) - 2 * max_log_likelihood


def _split_chains(x):
    """Halve each chain, dropping the middle draw when the length is odd."""
    half = x.shape[1] // 2
    return np.concatenate([x[:, :half], x[:, x.shape[1] - half:]], axis=0)


def _z_scale(x):
    """Rank-normalise all draws jointly to standard normal scores."""
    ranks = stats.rankdata(x, method="average").reshape(x.shape)
    return stats.norm.ppf((ranks - 0.375) / (x.size + 0.25))


def _rhat_basic(x):
    """Potential scale reduction for draws ``x`` of shape (chains, draws)."""
    n = x.shape[1]
    within = np.mean(np.var(x, axis=1, ddof=1))
    between = n * np.var(np.mean(x, axis=1), ddof=1)
    if not np.isfinite(within) or within <= 0:
        return np.nan
    return np.sqrt((between / within + n - 1) / n)


def _ess_basic(x):
    """Effective sample size for draws of shape (chains, draws).

    Autocorrelations are combined across chains and truncated with Geyer's
    initial positive and initial monotone sequences, as in Stan and ArviZ.
    """
    x = np.asarray(x, dtype=float)
    m, n = x.shape
    if n < 4 or not np.all(np.isfinite(x)):
        return np.nan
    centred = x - x.mean(axis=1, keepdims=True)
    size = 1 << int(np.ceil(np.log2(2 * n)))
    spec = np.fft.rfft(centred, n=size, axis=1)
    acov = np.fft.irfft(spec * np.conj(spec), n=size, axis=1)[:, :n] / n
    mean_var = np.mean(acov[:, 0]) * n / (n - 1.0)
    var_plus = mean_var * (n - 1.0) / n
    if m > 1:
        var_plus += np.var(x.mean(axis=1), ddof=1)
    if var_plus <= 0:
        return np.nan
    rho = np.zeros(n)
    rho_even = 1.0
    rho[0] = rho_even
    rho_odd = 1.0 - (mean_var - np.mean(acov[:, 1])) / var_plus
    rho[1] = rho_odd
    t = 1
    while t < n - 3 and rho_even + rho_odd > 0.0:
        rho_even = 1.0 - (mean_var - np.mean(acov[:, t + 1])) / var_plus
        rho_odd = 1.0 - (mean_var - np.mean(acov[:, t + 2])) / var_plus
        if rho_even + rho_odd >= 0:
            rho[t + 1] = rho_even
            rho[t + 2] = rho_odd
        t += 2
    max_t = t - 2
    if rho_even > 0:
        rho[max_t + 1] = rho_even
    t = 1
    while t <= max_t - 2:
        if rho[t + 1] + rho[t + 2] > rho[t - 1] + rho[t]:
            rho[t + 1] = rho[t + 2] = (rho[t - 1] + rho[t]) / 2.0
        t += 2
    tau = -1.0 + 2.0 * np.sum(rho[:max_t + 1]) + np.sum(rho[max_t + 1:max_t + 2])
    tau = max(tau, 1.0 / np.log10(m * n))
    return m * n / tau


def _per_parameter(chains, fn):
    chains = np.asarray(chains, dtype=float)
    if chains.ndim == 2:
        chains = chains[..., None]
    return np.array([fn(chains[:, :, k]) for k in range(chains.shape[2])])


def rhat(chains):
    """Rank-normalised split R-hat [Vehtari et al. 2021].

    ``chains`` has shape ``(n_chains, n_draws, dim)``.  The statistic is the
    larger of R-hat computed on rank-normalised split chains (sensitive to
    differences in location) and on their folded version (sensitive to
    differences in scale and tails).  Values below 1.01 indicate that the
    chains agree.
    """
    def one(x):
        bulk = _rhat_basic(_z_scale(_split_chains(x)))
        folded = np.abs(x - np.median(x))
        tail = _rhat_basic(_z_scale(_split_chains(folded)))
        return max(bulk, tail)
    return _per_parameter(chains, one)


def ess_bulk(chains):
    """Bulk effective sample size, from rank-normalised split chains.

    Measures how well the centre of the distribution (means, medians) is
    estimated.  ``chains`` has shape ``(n_chains, n_draws, dim)``.
    """
    return _per_parameter(chains, lambda x: _ess_basic(_z_scale(_split_chains(x))))


def ess_tail(chains):
    """Tail effective sample size, the smaller of the effective sample sizes
    for the indicators of the 5% and 95% quantiles.

    Measures how well tail quantities such as a 90% interval are estimated.
    """
    def one(x):
        values = []
        for q in (0.05, 0.95):
            indicator = (x <= np.quantile(x, q)).astype(float)
            values.append(_ess_basic(_split_chains(indicator)))
        return min(values)
    return _per_parameter(chains, one)
