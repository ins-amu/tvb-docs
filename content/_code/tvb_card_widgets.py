"""Centralized TVB model-spec registry for interactive model-card phase planes.

Every spec in ``MODEL_CARD_SPECS`` is built with ``ModelSpec.from_strings`` so
its state variables, equations, parameter names, ranges, defaults, and bounds
match ``tvb.simulator.models.<Class>.dfun`` (or the card's documented
``tvbl.core.DFun`` formulation) rather than Trajecturtle's built-in presets.
"""
from __future__ import annotations

import json
import math
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tvb_phaseplane import ModelSpec, PhasePlaneWidget


@dataclass(frozen=True)
class CardModelConfig:
    """Declarative specification for one model card's phase-plane widget."""

    name: str
    tvb_class: str | None
    equations: dict[str, str]
    state_vars: dict[str, tuple[float, float]]
    params: dict[str, tuple[float, float, float]]
    visible_parameters: list[str]
    dt: float = 0.01
    t_max: float = 100.0
    x0: float | None = None
    y0: float | None = None
    bounds: dict[str, tuple[float | None, float | None]] = field(default_factory=dict)
    display: list[str] | None = None


MODEL_CARD_SPECS: dict[str, CardModelConfig] = {
    "suphopf": CardModelConfig(
        name="SupHopf",
        tvb_class="SupHopf",
        equations={
            "x": "(a - x**2 - y**2) * x - omega * y",
            "y": "(a - x**2 - y**2) * y + omega * x",
        },
        state_vars={"x": (-2.0, 2.0), "y": (-2.0, 2.0)},
        params={
            "a": (-0.5, -10.0, 10.0),
            "omega": (1.0, 0.05, 20.0),
        },
        visible_parameters=["a", "omega"],
        dt=0.02,
        t_max=40.0,
        x0=1.2,
        y0=0.4,
    ),
    "generic_2d_oscillator": CardModelConfig(
        name="Generic2dOscillator",
        tvb_class="Generic2dOscillator",
        equations={
            "V": "d * tau * (-f * V**3 + e * V**2 + g * V + alpha * W + gamma * I)",
            "W": "(d / tau) * (c * V**2 + b * V - beta * W + a)",
        },
        state_vars={"V": (-4.0, 4.0), "W": (-4.0, 4.0)},
        params={
            "tau": (1.0, 1.0, 5.0),
            "I": (0.0, -5.0, 5.0),
            "a": (-2.0, -5.0, 5.0),
            "b": (-10.0, -20.0, 15.0),
            "c": (0.0, -10.0, 10.0),
            "d": (0.02, 0.0001, 1.0),
            "e": (3.0, -5.0, 5.0),
            "f": (1.0, -5.0, 5.0),
            "g": (0.0, -5.0, 5.0),
            "alpha": (1.0, -5.0, 5.0),
            "beta": (1.0, -5.0, 5.0),
            "gamma": (1.0, -1.0, 1.0),
        },
        visible_parameters=["a", "b", "I"],
        dt=0.1,
        t_max=500.0,
        x0=0.5,
        y0=0.0,
    ),
    "fitzhugh_nagumo": CardModelConfig(
        name="FitzHugh–Nagumo (tvbl)",
        tvb_class=None,
        equations={
            "X": "tau * (X - X**3 / 3.0 + Y)",
            "Y": "(1.0 / tau) * (a - X)",
        },
        state_vars={"X": (-3.0, 3.0), "Y": (-3.0, 3.0)},
        params={
            "a": (1.28, 1.0, 1.4),
            "tau": (1.35, 1.0, 2.0),
        },
        visible_parameters=["a", "tau"],
        dt=0.02,
        t_max=80.0,
        x0=-1.0,
        y0=0.5,
    ),
    "montbrio_pazo_roxin": CardModelConfig(
        name="MontbrioPazoRoxin",
        tvb_class="MontbrioPazoRoxin",
        equations={
            "r": "(1.0 / tau) * (Delta / (pi * tau) + 2.0 * V * r)",
            "V": "(1.0 / tau) * (V**2 - (pi * tau * r)**2 + eta + J * tau * r + I)",
        },
        state_vars={"r": (0.0, 2.0), "V": (-2.0, 1.5)},
        params={
            "tau": (1.0, 0.001, 15.0),
            "I": (0.0, -10.0, 10.0),
            "Delta": (1.0, 0.0, 10.0),
            "J": (15.0, -25.0, 25.0),
            "eta": (-5.0, -10.0, 10.0),
            "cr": (1.0, 0.0, 1.0),
            "cv": (0.0, 0.0, 1.0),
        },
        visible_parameters=["eta", "J", "I"],
        dt=0.01,
        t_max=40.0,
        x0=0.2,
        y0=-0.5,
        bounds={"r": (0.0, None)},
    ),
    "coombes_byrne_2d": CardModelConfig(
        name="CoombesByrne2D",
        tvb_class="CoombesByrne2D",
        equations={
            "r": "Delta / pi + 2.0 * V * r - k * pi * r**2",
            "V": "V**2 - pi**2 * r**2 + eta + (v_syn - V) * k * pi * r",
        },
        state_vars={"r": (0.0, 2.0), "V": (-2.0, 1.5)},
        params={
            "Delta": (1.0, 0.0, 10.0),
            "k": (1.0, 0.0, 5.0),
            "v_syn": (-4.0, -20.0, 0.0),
            "eta": (2.0, -10.0, 10.0),
        },
        visible_parameters=["eta", "k", "v_syn"],
        dt=0.01,
        t_max=40.0,
        x0=0.4,
        y0=-0.2,
        bounds={"r": (0.0, None)},
    ),
    "wilson_cowan": CardModelConfig(
        name="WilsonCowan",
        tvb_class="WilsonCowan",
        equations={
            "E": (
                "(-E + (k_e - r_e * E) * c_e * ("
                "1.0 / (1.0 + safe_exp(-a_e * (alpha_e * (c_ee * E - c_ei * I + P - theta_e) - b_e)))"
                " - 1.0 / (1.0 + safe_exp(a_e * b_e))"
                ")) / tau_e"
            ),
            "I": (
                "(-I + (k_i - r_i * I) * c_i * ("
                "1.0 / (1.0 + safe_exp(-a_i * (alpha_i * (c_ie * E - c_ii * I + Q - theta_i) - b_i)))"
                " - 1.0 / (1.0 + safe_exp(a_i * b_i))"
                ")) / tau_i"
            ),
        },
        state_vars={"E": (-0.1, 1.0), "I": (-0.1, 1.0)},
        params={
            "c_ee": (12.0, 11.0, 16.0),
            "c_ei": (4.0, 2.0, 15.0),
            "c_ie": (13.0, 2.0, 22.0),
            "c_ii": (11.0, 2.0, 15.0),
            "tau_e": (10.0, 1.0, 150.0),
            "tau_i": (10.0, 1.0, 150.0),
            "a_e": (1.2, 0.0, 1.4),
            "b_e": (2.8, 1.4, 6.0),
            "c_e": (1.0, 1.0, 20.0),
            "theta_e": (0.0, 0.0, 60.0),
            "a_i": (1.0, 0.0, 2.0),
            "b_i": (4.0, 2.0, 6.0),
            "c_i": (1.0, 1.0, 20.0),
            "theta_i": (0.0, 0.0, 60.0),
            "r_e": (1.0, 0.5, 2.0),
            "r_i": (1.0, 0.5, 2.0),
            "k_e": (1.0, 0.5, 2.0),
            "k_i": (1.0, 0.0, 2.0),
            "P": (0.0, 0.0, 20.0),
            "Q": (0.0, 0.0, 20.0),
            "alpha_e": (1.0, 0.0, 20.0),
            "alpha_i": (1.0, 0.0, 20.0),
        },
        visible_parameters=["P", "c_ee", "c_ei"],
        dt=0.1,
        t_max=200.0,
        x0=0.2,
        y0=0.1,
    ),
}


def build_model_spec(key: str) -> ModelSpec:
    """Construct a validated ``ModelSpec`` for ``key``."""
    cfg = MODEL_CARD_SPECS[key]
    return ModelSpec.from_strings(
        equations=cfg.equations,
        state_vars=cfg.state_vars,
        params=cfg.params,
        display=cfg.display,
        bounds=cfg.bounds or None,
        name=cfg.name,
    )


def card_widget(
    key: str,
    *,
    presentation: str = "figure",
    **overrides: Any,
) -> PhasePlaneWidget:
    """Create a configured ``PhasePlaneWidget`` for model card ``key``."""
    cfg = MODEL_CARD_SPECS[key]
    spec = build_model_spec(key)
    kwargs: dict[str, Any] = {
        "model_spec": spec.to_widget_state(),
        "presentation": presentation,
        "visible_parameters": list(cfg.visible_parameters),
        "dt": cfg.dt,
        "t_max": cfg.t_max,
    }
    if cfg.x0 is not None:
        kwargs["x0"] = cfg.x0
    if cfg.y0 is not None:
        kwargs["y0"] = cfg.y0
    kwargs.update(overrides)
    return PhasePlaneWidget(**kwargs)


def widget_state_payload(key: str, *, presentation: str = "figure") -> dict[str, Any]:
    """Return the JSON-serializable initial state dict for static hydration."""
    w = card_widget(key, presentation=presentation)
    return {
        "model_name": w.model_name,
        "model_spec": w.model_spec,
        "params": w.params,
        "param_info": w.param_info,
        "state_names": w.state_names,
        "xlim": w.xlim,
        "ylim": w.ylim,
        "x0": w.x0,
        "y0": w.y0,
        "dt": w.dt,
        "t_max": w.t_max,
        "display": list(w.display),
        "clamped": w.clamped,
        "integrator": w.integrator,
        "noise_enable": w.noise_enable,
        "noise_sigma": w.noise_sigma,
        "noise_seed": w.noise_seed,
        "show_nullclines": w.show_nullclines,
        "show_vector_field": w.show_vector_field,
        "show_trajectory": w.show_trajectory,
        "show_fixed_points": w.show_fixed_points,
        "presentation": w.presentation,
        "visible_parameters": w.visible_parameters,
        "panels": w.panels,
        "panel_layout": w.panel_layout,
        "view_switcher": w.view_switcher,
        "experiment_id": "",
    }


def export_static_assets(out_dir: str | Path) -> Path:
    """Copy shared ``widget.js``/``widget.css`` and write per-card JSON specs."""
    import tvb_phaseplane

    dest = Path(out_dir)
    specs_dir = dest / "specs"
    specs_dir.mkdir(parents=True, exist_ok=True)
    static_src = Path(tvb_phaseplane.__file__).resolve().parent / "static"
    shutil.copy2(static_src / "widget.js", dest / "widget.js")
    shutil.copy2(static_src / "widget.css", dest / "widget.css")
    for key in MODEL_CARD_SPECS:
        (specs_dir / f"{key}.json").write_text(
            json.dumps(widget_state_payload(key), separators=(",", ":")),
            encoding="utf-8",
        )
    return dest
