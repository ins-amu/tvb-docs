"""Shared 'single notebook' computational core for the tvb-docs marimo prototype.

This is the canonical analysis (adapted from the tvbl demo): a FitzHugh-Nagumo
network simulation used by the tvbl quickstart tutorial. Parameter inference
lives in tvbl.infer and the pages under content/user-guide/inference.

Model (tvbl.core.DFun), FitzHugh-Nagumo with delayed network coupling Cx:
    dX/dt = tau * (X - X**3/3 + Y)
    dY/dt = (1/tau) * (a - k*Cx - X)
"""
from __future__ import annotations

import numpy as np
import scipy.sparse

import tvbl

def make_network(num_node=30, sparsity=0.3, horizon=256, dt=0.1, seed=42):
    """Random sparse delayed connectome (CSR weights + integer delays)."""
    rng = np.random.RandomState(seed)
    weights, lengths = rng.rand(2, num_node, num_node).astype("f")
    lengths[:] *= 0.8
    lengths *= horizon * dt * 0.8
    zero_mask = weights < (1 - sparsity)
    weights[zero_mask] = 0
    csr_weights = scipy.sparse.csr_matrix(weights)
    idelays = (lengths[~zero_mask] / dt).astype("i") + 2
    return csr_weights, idelays


def run_sim(a=1.28, tau=1.35, log_k=-4.80, log_z=0.16,
            num_node=30, num_time=500, dt=0.1, horizon=256,
            num_item=1, num_skip=1, seed=42):
    """Run one FitzHugh-Nagumo network simulation; return trace."""
    csr_weights, idelays = make_network(num_node=num_node, horizon=horizon, dt=dt, seed=seed)
    sim_params = np.r_[a, tau, np.exp(log_k) / num_node * 80][:, None].astype("f")
    z_scale = np.sqrt(dt) * np.r_[0.01, 0.1].astype("f") * np.exp(log_z)
    dfun = tvbl.DFun(sim_params=sim_params)
    return tvbl.run(
        csr_weights, idelays, dfun, z_scale, horizon,
        num_item=num_item, num_node=num_node, num_time=num_time,
        dt=dt, num_skip=num_skip, show_time=False,
    )
