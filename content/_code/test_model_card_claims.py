"""Regression checks for documented claims about JansenRit and SupHopf.

The Jansen-Rit and SupHopf model cards (``content/reference/model-cards/``),
the worked examples in ``content/explanation/bifurcation-analysis.md`` and the
how-to guides ``content/howtos/jansen-rit-alpha-network.md`` and
``hopf-whole-brain-model.md`` quote defaults, coupling conventions and
bifurcation points of the TVB models. These tests recompute them from the
installed ``tvb.simulator``, so that a change upstream (a new default, a
different ``cvar``, a fixed sign) shows up as a failing test rather than as a
silently wrong page.

Most checks are equilibrium / linear-stability algebra on TVB's own
``_numpy_dfun``; one runs a short seeded network simulation.
"""
from __future__ import annotations

import numpy as np
import pytest
from scipy.optimize import brentq
from tvb.simulator import coupling as tvb_coupling
from tvb.simulator import models as tvb_models

# ---------------------------------------------------------------------------
# Jansen-Rit
# ---------------------------------------------------------------------------


def _jr(**kw) -> tvb_models.JansenRit:
    m = tvb_models.JansenRit(**{k: np.array([v]) for k, v in kw.items()})
    m.configure()
    return m


def _jr_sigm(m, v):
    return 2.0 * m.nu_max[0] / (1.0 + np.exp(m.r[0] * (m.v0[0] - v)))


def _jr_equilibrium(m, y0):
    """Equilibrium state parametrised by y0 (y3 = y4 = y5 = 0)."""
    A, a, B, b, J = m.A[0], m.a[0], m.B[0], m.b[0], m.J[0]
    y1 = A / a * (m.mu[0] + m.a_2[0] * J * _jr_sigm(m, m.a_1[0] * J * y0))
    y2 = B / b * m.a_4[0] * J * _jr_sigm(m, m.a_3[0] * J * y0)
    return np.array([y0, y1, y2, 0.0, 0.0, 0.0])


def _jr_fixed_points(m):
    def g(y0):
        s = _jr_equilibrium(m, y0)
        return y0 - m.A[0] / m.a[0] * _jr_sigm(m, s[1] - s[2])

    hi = m.A[0] / m.a[0] * 2.0 * m.nu_max[0] + 0.5
    grid = np.linspace(-0.5, hi, 20001)
    vals = np.array([g(x) for x in grid])
    idx = np.nonzero(np.sign(vals[:-1]) != np.sign(vals[1:]))[0]
    return [_jr_equilibrium(m, brentq(g, grid[i], grid[i + 1], xtol=1e-14)) for i in idx]


def _jacobian(m, s, h=1e-7):
    n = s.size

    def f(z):
        return m._numpy_dfun(z.reshape(n, 1, 1), np.zeros((m.cvar.size, 1, 1)))[:, 0, 0]

    jac = np.zeros((n, n))
    for k in range(n):
        e = np.zeros(n)
        e[k] = h * max(1.0, abs(s[k]))
        jac[:, k] = (f(s + e) - f(s - e)) / (2.0 * e[k])
    return jac


def _upper_branch_leading_real(mu, v0):
    m = _jr(mu=mu, v0=v0)
    s = _jr_fixed_points(m)[-1]
    return np.linalg.eigvals(_jacobian(m, s)).real.max()


def _bisect(pred, lo, hi, it=30):
    plo = pred(lo)
    assert pred(hi) != plo, "no sign change in bracket"
    for _ in range(it):
        mid = 0.5 * (lo + hi)
        if pred(mid) == plo:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def test_jansen_rit_declared_structure():
    m = _jr()
    assert tuple(m.state_variables) == ("y0", "y1", "y2", "y3", "y4", "y5")
    assert list(m.cvar) == [1, 2]
    # stimulus is routed to cvar unless stvar is set explicitly
    assert list(m.stvar) == [1, 2]
    assert tuple(m.variables_of_interest) == ("y0", "y1", "y2", "y3")
    defaults = dict(A=3.25, B=22.0, a=0.1, b=0.05, v0=5.52, nu_max=0.0025, r=0.56,
                    J=135.0, a_1=1.0, a_2=0.8, a_3=0.25, a_4=0.25, mu=0.22,
                    p_min=0.12, p_max=0.32)
    for name, value in defaults.items():
        assert getattr(m, name)[0] == pytest.approx(value), name


def test_jansen_rit_numba_matches_numpy():
    m = _jr()
    rng = np.random.default_rng(0)
    scale = np.array([0.05, 5.0, 5.0, 1.0, 5.0, 5.0])[:, None, None]
    y = rng.uniform(-1, 1, (6, 4, 1)) * scale
    c = rng.uniform(0, 0.01, (2, 4, 1))
    np.testing.assert_allclose(m.dfun(y, c), m._numpy_dfun(y, c), rtol=1e-12, atol=1e-14)


def test_sigmoidal_jansen_rit_coupling_defaults():
    c = tvb_coupling.SigmoidalJansenRit()
    assert c.midpoint[0] == pytest.approx(6.0)  # != JansenRit.v0 default (5.52)
    assert c.cmax[0] == pytest.approx(2 * 0.0025)
    assert c.r[0] == pytest.approx(0.56)


def test_jansen_rit_reproduces_grimbert_faugeras_2006():
    """With v0 = 6 mV TVB's JansenRit has the bifurcations reported by
    Grimbert & Faugeras (2006), Neural Comput 18:3052, in pulses/s:
    Hopf at p = -12.15, 89.83, 315.70 and a saddle-node at p = 113.58."""
    v0 = 6.0
    unstable = lambda mu: _upper_branch_leading_real(mu, v0) > 0  # noqa: E731
    assert _bisect(unstable, -0.03, 0.0) * 1e3 == pytest.approx(-12.15, abs=0.02)
    assert _bisect(unstable, 0.05, 0.10) * 1e3 == pytest.approx(89.83, abs=0.02)
    assert _bisect(unstable, 0.20, 0.33) * 1e3 == pytest.approx(315.70, abs=0.02)
    three = lambda mu: len(_jr_fixed_points(_jr(mu=mu, v0=v0))) > 1  # noqa: E731
    assert _bisect(three, 0.08, 0.13) * 1e3 == pytest.approx(113.58, abs=0.02)


def test_jansen_rit_default_v0_has_no_stable_upper_focus_in_mu_domain():
    """With the shipped v0 = 5.52 the upper equilibrium stays unstable over
    the whole trait domain of mu (0 - 0.22 ms^-1); its upper Hopf moves to
    mu ~ 0.516 ms^-1."""
    for mu in (0.12, 0.16, 0.22):
        assert _upper_branch_leading_real(mu, 5.52) > 0
    hopf = _bisect(lambda mu: _upper_branch_leading_real(mu, 5.52) > 0, 0.3, 2.0)
    assert hopf == pytest.approx(0.516, abs=0.002)


# ---------------------------------------------------------------------------
# SupHopf (Stuart-Landau)
# ---------------------------------------------------------------------------


def _hopf(a=-0.5, omega=1.0):
    m = tvb_models.SupHopf(a=np.array([a]), omega=np.array([omega]))
    m.configure()
    return m


def test_suphopf_declared_structure():
    m = _hopf()
    assert m.a[0] == pytest.approx(-0.5)
    assert m.omega[0] == pytest.approx(1.0)
    assert list(m.cvar) == [0, 1]
    assert tuple(m.variables_of_interest) == ("x",)


def test_suphopf_numba_matches_numpy_with_local_coupling():
    m = _hopf()
    rng = np.random.default_rng(1)
    y = rng.normal(size=(2, 4, 1))
    c = rng.normal(size=(2, 4, 1))
    np.testing.assert_allclose(m.dfun(y, c, 0.3), m._numpy_dfun(y, c, 0.3), rtol=1e-12)
    # local coupling only enters the x equation
    d0 = m._numpy_dfun(y, c, 0.0)
    d1 = m._numpy_dfun(y, c, 0.3)
    np.testing.assert_allclose(d1[0] - d0[0], 0.3 * y[0])
    np.testing.assert_allclose(d1[1], d0[1])


@pytest.mark.parametrize("a, omega", [(-0.5, 1.0), (-0.05, 2 * np.pi * 0.05), (0.3, 3.0)])
def test_suphopf_linearisation_at_origin(a, omega):
    ev = np.sort_complex(np.linalg.eigvals(_jacobian(_hopf(a, omega), np.zeros(2))))
    np.testing.assert_allclose(ev, np.sort_complex(np.array([a - 1j * omega, a + 1j * omega])),
                               atol=1e-6)


@pytest.mark.parametrize("a, omega", [(0.25, 1.0), (4.0, 0.3)])
def test_suphopf_limit_cycle_is_a_circle_of_radius_sqrt_a(a, omega):
    m = _hopf(a, omega)
    theta = np.linspace(0, 2 * np.pi, 7)
    s = np.sqrt(a) * np.vstack([np.cos(theta), np.sin(theta)])[:, :, None]
    d = m._numpy_dfun(s, np.zeros((2, theta.size, 1)))[:, :, 0]
    # on the circle the flow is purely tangential with angular speed omega
    np.testing.assert_allclose(d[0], -omega * s[1, :, 0], atol=1e-12)
    np.testing.assert_allclose(d[1], omega * s[0, :, 0], atol=1e-12)


def test_suphopf_network_rest_stability_depends_on_coupling_function():
    """Linearised at the all-zero state, a network of identical SupHopf nodes
    with weights W and global scale G has Jacobian blocks
      Difference: (a +- i omega) I - G L,  L = diag(W 1) - W  (Laplacian)
      Linear:     (a +- i omega) I + G W
    so Difference coupling can never destabilise rest when a < 0, while
    Linear coupling does once a + G lambda_max(W) > 0."""
    rng = np.random.default_rng(2)
    n = 12
    W = rng.uniform(0, 1, (n, n))
    W = 0.5 * (W + W.T)
    np.fill_diagonal(W, 0)
    a, G = -0.5, 1.0
    L = np.diag(W.sum(1)) - W
    assert (a - G * np.linalg.eigvalsh(L)).max() < 0
    assert a + G * np.linalg.eigvalsh(W).max() > 0
    # TVB's Difference coupling is a * sum_j W_ij (x_j - x_i)
    x = rng.normal(size=n)
    pre = tvb_coupling.Difference(a=np.array([G]))
    assert pre.pre(x[:, None], x[None, :]).shape == (n, n)
    np.testing.assert_allclose(G * (W * (x[None, :] - x[:, None])).sum(1), -G * L @ x)


def test_jansen_rit_network_in_input_range_gives_alpha():
    """The network configuration recommended on the card (max in-strength 1,
    mu = p_min, coupling a = (p_max - p_min)/cmax, noise on y4) keeps every
    region's input in Jansen & Rit's 120-320 pulses/s window and gives alpha
    in most regions at a physiological offset."""
    # not tvb.simulator.lab: its logger setup breaks under pytest's capture
    from tvb.datatypes import connectivity
    from tvb.simulator import integrators, monitors, noise, simulator

    jrm = tvb_models.JansenRit(v0=np.array([6.0]))
    jrm.mu = jrm.p_min.copy()
    conn = connectivity.Connectivity.from_file()
    conn.weights = conn.weights / conn.weights.sum(axis=1).max()
    cpl = tvb_coupling.SigmoidalJansenRit()
    cpl.a = (jrm.p_max - jrm.p_min) / cpl.cmax
    assert (cpl.a * cpl.cmax * conn.weights.sum(axis=1)).max() == pytest.approx(0.2)
    nsig = np.zeros(6)
    nsig[4] = ((jrm.a * jrm.A * (jrm.p_max - jrm.p_min) * 0.5) ** 2 / 2.0).item()
    sim = simulator.Simulator(
        model=jrm, connectivity=conn, coupling=cpl,
        integrator=integrators.HeunStochastic(
            dt=2 ** -4, noise=noise.Additive(nsig=nsig, random_stream=np.random.RandomState(42))),
        monitors=(monitors.TemporalAverage(period=2 ** -2),),
        simulation_length=3000.0,
    ).configure()
    (t, d), = sim.run()
    keep = t >= 1000.0
    v = d[keep, 1, :, 0] - d[keep, 2, :, 0]
    f = np.fft.rfftfreq(v.shape[0], 0.25e-3)
    power = np.abs(np.fft.rfft(v - v.mean(0), axis=0)) ** 2
    peak = f[f > 1][np.argmax(power[f > 1], axis=0)]
    assert ((peak >= 8) & (peak <= 13)).mean() > 0.8
    assert 5.0 < np.median(v.mean(0)) < 10.0
