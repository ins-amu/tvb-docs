"""Numerical parity and JS compilation tests for ``tvb_card_widgets``."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from tvb.simulator import models as tvb_models

from tvb_card_widgets import MODEL_CARD_SPECS, build_model_spec, card_widget

TRAJECTURTLE_WIDGET_JS = (
    Path(__file__).resolve().parents[2]
    / "trajecturtle"
    / "src"
    / "tvb_phaseplane"
    / "static"
    / "widget.js"
)


def _interior_test_states(cfg) -> list[list[float]]:
    """Generate 5 deterministic interior states within ``cfg.state_vars`` ranges."""
    ranges = list(cfg.state_vars.values())
    fractions = [0.2, 0.35, 0.5, 0.65, 0.8]
    states = []
    for f in fractions:
        states.append([lo + f * (hi - lo) for lo, hi in ranges])
    return states


@pytest.mark.parametrize(
    "key",
    [k for k, cfg in MODEL_CARD_SPECS.items() if cfg.tvb_class is not None],
)
def test_tvb_dfun_numerical_parity(key: str) -> None:
    """Assert ``ModelSpec.rhs_function(defaults)`` matches ``tvb_model.dfun``."""
    cfg = MODEL_CARD_SPECS[key]
    spec = build_model_spec(key)
    defaults = {p: vals[0] for p, vals in cfg.params.items()}
    rhs = spec.rhs_function(defaults)

    tvb_cls = getattr(tvb_models, cfg.tvb_class)
    tvb_model = tvb_cls()
    tvb_model.configure()

    n_cvar = len(tvb_model.cvar)
    coupling = np.zeros((n_cvar, 1, 1), dtype=float)

    for state in _interior_test_states(cfg):
        spec_deriv = np.asarray(rhs(0.0, state), dtype=float)
        tvb_state = np.asarray(state, dtype=float)[:, None, None]
        tvb_deriv = np.asarray(
            tvb_model.dfun(tvb_state, coupling, local_coupling=0.0),
            dtype=float,
        ).reshape(-1)
        np.testing.assert_allclose(
            spec_deriv,
            tvb_deriv,
            rtol=1e-5,
            atol=1e-6,
            err_msg=f"Parity mismatch for {key} at state={state}",
        )


def test_all_card_specs_build_widgets() -> None:
    """Every registered card key builds a valid ``PhasePlaneWidget``."""
    for key in MODEL_CARD_SPECS:
        w = card_widget(key)
        assert w.model_name == "custom"
        assert w.presentation == "figure"
        assert w.model_spec is not None


def test_js_compilation_and_finite_dynamics() -> None:
    """Verify all card specs compile in Nerdamer and produce finite dynamics."""
    if not TRAJECTURTLE_WIDGET_JS.is_file():
        pytest.skip("trajecturtle static/widget.js not found")

    nvm_node = Path.home() / ".nvm" / "versions" / "node" / "v22.21.1" / "bin" / "node"
    node_bin = str(nvm_node) if nvm_node.is_file() else shutil.which("node")
    if not node_bin:
        pytest.skip("node not available")

    payloads = []
    for key, cfg in MODEL_CARD_SPECS.items():
        w = card_widget(key)
        payloads.append(
            {
                "key": key,
                "model_name": w.model_name,
                "model_spec": w.model_spec,
                "params": w.params,
                "state_names": w.state_names,
                "xlim": w.xlim,
                "ylim": w.ylim,
                "x0": w.x0,
                "y0": w.y0,
                "dt": w.dt,
                "t_max": min(float(w.t_max), 20.0),
                "display": list(w.display),
                "clamped": w.clamped,
                "bounds": {k: list(v) for k, v in cfg.bounds.items()},
            }
        )

    js_script = """
import fs from 'node:fs';
import { pathToFileURL } from 'node:url';
const widgetUrl = process.argv[1];
const payloads = JSON.parse(fs.readFileSync(0, 'utf8'));
// Minimal DOM stub for module import
globalThis.window = globalThis;
globalThis.document = { createElement: () => ({}), documentElement: {} };
const { computeExperiment } = await import(widgetUrl);
for (const state of payloads) {
  const m = { get: (k) => state[k], set: (k, v) => { state[k] = v; } };
  computeExperiment(m);
  const traj = state.trajectory;
  if (!Array.isArray(traj) || traj.length < 2) {
    throw new Error(`${state.key}: empty trajectory`);
  }
  for (const row of traj) {
    if (row.some((v) => !Number.isFinite(v))) {
      throw new Error(`${state.key}: non-finite trajectory point ${row}`);
    }
  }
  for (const [varName, [lo, hi]] of Object.entries(state.bounds)) {
    const idx = state.state_names.indexOf(varName);
    for (const row of traj) {
      const val = row[idx + 1];
      if (lo !== null && val < lo - 1e-12) {
        throw new Error(`${state.key}: ${varName}=${val} < lower bound ${lo}`);
      }
      if (hi !== null && val > hi + 1e-12) {
        throw new Error(`${state.key}: ${varName}=${val} > upper bound ${hi}`);
      }
    }
  }
}
console.log(`Verified ${payloads.length} card specs in JS`);
"""
    proc = subprocess.run(
        [node_bin, "--input-type=module", "-e", js_script, TRAJECTURTLE_WIDGET_JS.as_uri()],
        input=json.dumps(payloads),
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ},
    )
    assert proc.returncode == 0, f"Node smoke test failed:\n{proc.stderr}\n{proc.stdout}"
    assert f"Verified {len(MODEL_CARD_SPECS)} card specs in JS" in proc.stdout
