import numpy as np
import pytest

from tvbl.cde import MAFEstimator
from tvbl.infer import (
    BoxUniform, Gamma, LogPosterior, NPE, Standardizer, central_coverage,
    ess_bulk, ess_tail, hpd_coverage, laplace_approximation, rhat, sbc_histogram,
    sbc_ranks, shrinkage_zscore, student_t_proposal,
)


@pytest.mark.parametrize("prior, theta", [
    (BoxUniform([0.0, -2.0], [1.0, 5.0]), np.array([[0.3, 1.0], [0.9, -1.5]])),
    (Gamma([2.0, 5.0], [1.0, 3.0]), np.array([[0.7, 1.2], [3.0, 0.4]])),
])
def test_bijection_round_trip_and_jacobian(prior, theta):
    u = prior.to_unbounded(theta)
    np.testing.assert_allclose(prior.from_unbounded(u), theta, rtol=1e-6)
    h = 1e-6
    for row in range(theta.shape[0]):
        jac = np.empty((theta.shape[1],) * 2)
        for k in range(theta.shape[1]):
            step = np.zeros(theta.shape[1])
            step[k] = h
            jac[:, k] = (prior.to_unbounded(theta[row] + step) - prior.to_unbounded(theta[row] - step))[0] / (2 * h)
        expected = np.log(abs(np.linalg.det(jac)))
        np.testing.assert_allclose(prior.log_abs_det_jacobian(theta[row:row + 1])[0], expected, rtol=1e-4)


def test_box_uniform_log_prob_and_bounds():
    prior = BoxUniform([0.0], [2.0])
    assert prior.log_prob(np.array([[1.0]]))[0] == pytest.approx(-np.log(2.0))
    assert prior.log_prob(np.array([[2.5]]))[0] == -np.inf
    with pytest.raises(ValueError):
        BoxUniform([1.0], [1.0])


def test_standardizer_handles_constant_columns():
    data = np.column_stack([np.arange(10.0), np.full(10, 3.0)])
    scaler = Standardizer(data)
    out = scaler(data)
    assert np.all(np.isfinite(out))
    np.testing.assert_allclose(scaler.inverse(out), data)


def _gaussian_problem(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    prior = BoxUniform([-3.0], [3.0])
    theta = prior.sample(n, rng)
    x = theta + 0.5 * rng.standard_normal(theta.shape)
    return prior, theta, x


def test_npe_recovers_gaussian_posterior_and_normalises():
    prior, theta, x = _gaussian_problem()
    post = NPE(prior, n_flows=3, hidden_units=32).train(theta, x, n_iter=1500, learning_rate=1e-2, batch_size=256, patience=None)
    s = post.sample(np.array([0.5]), 4000, np.random.RandomState(0))
    assert abs(s.mean() - 0.5) < 0.1
    assert abs(s.std() - 0.5) < 0.08
    grid = np.linspace(-3, 3, 2001)[:, None]
    density = np.exp(post.log_prob(grid, np.array([0.5])))
    assert np.trapezoid(density, grid[:, 0]) == pytest.approx(1.0, abs=0.03)
    assert np.all((s >= -3) & (s <= 3))


def test_sbc_ranks_uniform_for_trained_estimator():
    prior, theta, x = _gaussian_problem(n=4000)
    post = NPE(prior, n_flows=3, hidden_units=32).train(theta[:3500], x[:3500], n_iter=1500, learning_rate=1e-2, batch_size=256, patience=None)
    ranks = sbc_ranks(post, theta[3500:], x[3500:], 200, np.random.RandomState(1))
    cover = central_coverage(ranks, 200, [0.5, 0.9])
    np.testing.assert_allclose(cover[:, 0], [0.5, 0.9], atol=0.08)


def test_early_stopping_restores_best_weights_and_is_optional():
    prior, theta, x = _gaussian_problem(n=600)
    u = prior.to_unbounded(theta)
    est = MAFEstimator(param_dim=1, feature_dim=1, n_flows=2, hidden_units=16)
    est.train(u.astype("f"), x.astype("f"), n_iter=50, use_tqdm=False)
    assert len(est.loss_history) == 50 and est.val_loss_history == []
    est2 = MAFEstimator(param_dim=1, feature_dim=1, n_flows=2, hidden_units=16)
    est2.train(u.astype("f"), x.astype("f"), n_iter=2000, batch_size=64, validation_fraction=0.2, patience=3, use_tqdm=False)
    assert len(est2.loss_history) < 2000
    assert min(est2.val_loss_history) <= est2.val_loss_history[-1]


def test_laplace_exact_for_gaussian():
    cov_true = np.array([[2.0, 0.6], [0.6, 1.0]])
    prec = np.linalg.inv(cov_true)
    mean = np.array([1.0, -2.0])

    def log_density(u):
        d = u - mean
        return -0.5 * np.einsum("ni,ij,nj->n", d, prec, d)

    cov, log_z = laplace_approximation(log_density, mean, step=1e-2)
    np.testing.assert_allclose(cov, cov_true, rtol=1e-5)
    assert log_z == pytest.approx(0.5 * 2 * np.log(2 * np.pi) + 0.5 * np.log(np.linalg.det(cov_true)), rel=1e-6)


def test_log_posterior_includes_jacobian():
    prior = Gamma([3.0], [2.0])
    lp = LogPosterior(prior, lambda th: np.zeros(th.shape[0]))
    u = np.linspace(-8, 5, 8001)[:, None]
    density = np.exp(lp(u))
    assert np.trapezoid(density, u[:, 0]) == pytest.approx(1.0, abs=1e-3)


def test_rhat_and_ess_match_arviz_reference():
    # Reference values from arviz 0.23.4: az.rhat(method="rank"),
    # az.ess(method="bulk") and az.ess(method="tail") on the same draws.
    rng = np.random.default_rng(123)
    x = np.zeros((4, 601))
    e = rng.standard_normal((4, 601))
    for t in range(1, 601):
        x[:, t] = 0.7 * x[:, t - 1] + e[:, t]
    x[3] *= 1.5
    chains = x[..., None]
    assert rhat(chains)[0] == pytest.approx(1.019997752022035, rel=1e-9)
    assert ess_bulk(chains)[0] == pytest.approx(409.0424971980018, rel=1e-9)
    assert ess_tail(chains)[0] == pytest.approx(570.433713828216, rel=1e-9)


def test_rhat_and_ess_on_known_chains():
    rng = np.random.default_rng(0)
    iid = rng.standard_normal((4, 1000, 2))
    assert np.all(rhat(iid) < 1.01)
    assert np.all(ess_bulk(iid) > 3000)

    shifted = iid.copy()
    shifted[0] += 3.0
    assert np.all(rhat(shifted) > 1.3)

    scaled = iid.copy()
    scaled[0] *= 4.0
    assert np.all(rhat(scaled) > 1.1)

    ar = np.zeros((4, 4000, 1))
    noise = rng.standard_normal((4, 4000, 1))
    for t in range(1, 4000):
        ar[:, t] = 0.9 * ar[:, t - 1] + noise[:, t]
    expected = 4 * 4000 * (1 - 0.9) / (1 + 0.9)
    assert ess_bulk(ar)[0] == pytest.approx(expected, rel=0.25)


class ExactGaussianPosterior:
    """Analytic posterior of theta ~ N(0, 1), x | theta ~ N(theta, s^2)."""

    def __init__(self, noise_sd, scale=1.0):
        self.var = 1.0 / (1.0 + 1.0 / noise_sd ** 2)
        self.gain = self.var / noise_sd ** 2
        self.scale = scale

    def sample(self, x, n, rng):
        x = np.atleast_2d(x)
        z = rng.standard_normal((x.shape[0], n, 1))
        return self.gain * x[:, None, :] + self.scale * np.sqrt(self.var) * z

    def log_prob(self, theta, x):
        sd = self.scale * np.sqrt(self.var)
        return -0.5 * ((theta[:, 0] - self.gain * np.ravel(x)[0]) / sd) ** 2 - np.log(sd)


@pytest.mark.parametrize("scale, calibrated", [(1.0, True), (0.5, False)])
def test_calibration_checks_on_exact_and_overconfident_posteriors(scale, calibrated):
    rng = np.random.default_rng(4)
    theta = rng.standard_normal((2000, 1))
    x = theta + 0.5 * rng.standard_normal(theta.shape)
    post = ExactGaussianPosterior(0.5, scale)
    ranks = sbc_ranks(post, theta, x, 199, rng)
    counts, (low, high) = sbc_histogram(ranks, 199, n_bins=10)
    levels = np.array([0.5, 0.9])
    central = central_coverage(ranks, 199, levels)[:, 0]
    hpd = hpd_coverage(post, theta[:400], x[:400], 199, rng, levels)
    if calibrated:
        assert np.all((counts >= low - 15) & (counts <= high + 15))
        np.testing.assert_allclose(central, levels, atol=0.04)
        np.testing.assert_allclose(hpd, levels, atol=0.07)
    else:
        assert counts[0, 0] > high and counts[-1, 0] > high
        assert np.all(central < levels - 0.15)
        assert np.all(hpd < levels - 0.15)


def test_sbc_histogram_rejects_uneven_bins():
    with pytest.raises(ValueError):
        sbc_histogram(np.zeros((5, 1), dtype=int), 200, n_bins=10)


def _maf_in_float64(param_dim, feature_dim, context_units, seed=0):
    est = MAFEstimator(param_dim=param_dim, feature_dim=feature_dim, n_flows=3, hidden_units=8, context_units=context_units)
    weights = est._initialize_weights(np.random.RandomState(seed))
    rng = np.random.default_rng(seed + 1)
    return est, {k: rng.normal(0.0, 0.3, size=v.shape) for k, v in weights.items()}


@pytest.mark.parametrize("param_dim", [1, 3])
@pytest.mark.parametrize("context_units", [False, True])
def test_maf_gradient_matches_finite_differences(param_dim, context_units):
    est, weights = _maf_in_float64(param_dim, 2, context_units)
    rng = np.random.default_rng(7)
    params = rng.standard_normal((20, param_dim))
    features = rng.standard_normal((20, 2))
    _, grads = est._loss_and_grad(weights, features, params)
    h = 1e-6
    for key, value in weights.items():
        numeric = np.zeros_like(value)
        for idx in np.ndindex(value.shape):
            old = value[idx]
            value[idx] = old + h
            up = est._loss_function(weights, features, params)
            value[idx] = old - h
            down = est._loss_function(weights, features, params)
            value[idx] = old
            numeric[idx] = (up - down) / (2 * h)
        np.testing.assert_allclose(grads[key], numeric, rtol=1e-5, atol=1e-8, err_msg=key)


@pytest.mark.parametrize("context_units", [False, True])
def test_maf_density_normalises_in_two_dimensions(context_units):
    est, weights = _maf_in_float64(2, 1, context_units)
    est.weights = weights
    g = np.linspace(-9, 9, 451)
    grid = np.stack(np.meshgrid(g, g, indexing="ij"), axis=-1).reshape(-1, 2)
    density = np.exp(est.log_prob(np.full((grid.shape[0], 1), 0.7), grid)).reshape(g.size, g.size)
    total = np.trapezoid(np.trapezoid(density, g, axis=1), g)
    assert total == pytest.approx(1.0, abs=1e-3)


def test_maf_sampling_inverts_density():
    est, weights = _maf_in_float64(3, 2, True)
    est.weights = {k: v.astype("f") for k, v in weights.items()}
    features = np.array([[0.3, -1.2]], dtype="f")
    samples = est.sample(features, 20000, np.random.RandomState(0))[0]
    lp = est.log_prob(np.repeat(features, len(samples), axis=0), samples.astype("f"))
    _, caches = est._get_log_prob_np(est.weights, np.repeat(features, len(samples), axis=0), samples.astype("f"))
    base = caches[-1]["u_out"]
    np.testing.assert_allclose(base.mean(axis=0), 0.0, atol=0.03)
    np.testing.assert_allclose(base.std(axis=0), 1.0, atol=0.03)
    assert np.all(np.isfinite(lp))


def test_student_t_independence_sampler_targets_the_posterior():
    emcee = pytest.importorskip("emcee")
    target_cov = np.array([[1.0, 0.9], [0.9, 1.5]])
    target_mean = np.array([0.5, -1.0])
    prec = np.linalg.inv(target_cov)

    def log_target(u):
        z = u - target_mean
        return -0.5 * np.einsum("ni,ij,nj->n", z, prec, z)

    # A deliberately misplaced and too-narrow proposal: correctness must come
    # from the Hastings ratio, not from the proposal matching the target.
    move = emcee.moves.MHMove(student_t_proposal(np.array([0.8, -0.6]), 0.6 * target_cov))
    sampler = emcee.EnsembleSampler(16, 2, log_target, vectorize=True, moves=move)
    np.random.seed(0)
    sampler.random_state = np.random.RandomState(1).get_state()
    sampler.run_mcmc(np.random.default_rng(2).normal(size=(16, 2)), 6000, progress=False)
    draws = sampler.get_chain(discard=1000)
    assert np.all(rhat(draws.transpose(1, 0, 2)) < 1.01)
    flat = draws.reshape(-1, 2)
    np.testing.assert_allclose(flat.mean(axis=0), target_mean, atol=0.05)
    np.testing.assert_allclose(np.cov(flat.T), target_cov, atol=0.08)


def test_shrinkage_and_zscore():
    samples = np.random.default_rng(0).normal(2.0, 0.5, size=(5000, 1))
    shrinkage, z = shrinkage_zscore(samples, np.array([2.0]), np.array([2.0]))
    assert shrinkage[0] == pytest.approx(1 - 0.25 / 4, abs=0.02)
    assert abs(z[0]) < 0.05
