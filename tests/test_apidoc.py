"""Automated tests for TVB static API documentation, cross-linking, and search indexing."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import griffe

from tools.apidoc.backlinks import scan_tutorial_backlinks
from tools.apidoc.callgraph import build_class_hierarchy, extract_static_uses
from tools.apidoc.config import AnchorRegistry, find_repo_root, find_tvb_search_path
from tools.apidoc.docstring import render_docstring, rst_to_myst
from tools.apidoc.loader import load_tvb_package
from tools.apidoc.render import build_symbol_table
from tools.apidoc.traits import extract_trait


def test_rst_to_myst_conversions() -> None:
    raw = r"""
    Summary with :math:`V` and :class:`~tvb.simulator.models.oscillator.Generic2dOscillator`.

    .. math::
        \dot{V} &= -V \\
        \dot{W} &= V

    .. note::
        Important detail with ``inline``.

    .. [FH_1961] FitzHugh, R. 1961.

    +---------------------------+
    |  Table 1                  |
    +--------------+------------+
    |Parameter     |  Value     |
    +==============+============+
    | a            |     -2.0   |
    +--------------+------------+

    >>> x = 1 + 1
    >>> x
    2
    """

    def resolver(sym: str, _kind: str | None) -> str | None:
        if sym.endswith("Generic2dOscillator"):
            return "tvb.simulator.models.oscillator.md#cls-g2d"
        return None

    out = rst_to_myst(raw, resolver)
    assert "$V$" in out
    assert "[Generic2dOscillator](tvb.simulator.models.oscillator.md#cls-g2d)" in out
    assert "\\begin{aligned}" in out
    assert ":::{note}" in out
    assert "**[FH_1961]** FitzHugh, R. 1961." in out
    assert "**Table 1**" in out
    assert "| Parameter | Value |\n| --- | --- |" in out
    assert "```python\n>>> x = 1 + 1" in out


def test_sphinx_param_and_numpy_docstring_rendering() -> None:
    ds_text = """
    Do something.

    :param alpha: coupling weight with :math:`\\alpha`
    :type alpha: float
    :return: computed array
    """
    ds = griffe.Docstring(ds_text, parser="numpy")
    rendered = render_docstring(ds)
    assert "Parameters" in rendered
    assert "`alpha`" in rendered
    assert "$\\alpha$" in rendered
    assert "Returns" in rendered


def test_anchor_case_collision_safety() -> None:
    reg = AnchorRegistry()
    a1 = reg.anchor_for("class", "tvb.datatypes.surfaces.Surface")
    a2 = reg.anchor_for("class", "tvb.datatypes.surfaces.surface")
    a3 = reg.anchor_for("module", "tvb.datatypes.surfaces")
    assert a1 != a2
    assert a1.lower() != a2.lower()
    assert a1 != a3
    # Deterministic across repeated lookups
    assert reg.anchor_for("class", "tvb.datatypes.surfaces.surface") == a2
    # Long qualnames stay bounded <= 64 chars so mystmd preserves explicit ids
    long_anchor = reg.anchor_for(
        "method",
        "tvb.simulator.integrators.Integrator.reconfigure_boundaries_and_clamping_for_integration_state_variables",
    )
    assert len(long_anchor) <= 64


def test_neotraits_extraction_on_generic2d_oscillator() -> None:
    repo_root = find_repo_root()
    search_path = find_tvb_search_path(repo_root)
    pkg = load_tvb_package(search_path, scope="tvb.simulator.models.oscillator")
    g2d = pkg.modules["tvb.simulator.models.oscillator"].members["Generic2dOscillator"]
    tau_trait = extract_trait(g2d.members["tau"])
    assert tau_trait is not None
    assert tau_trait.trait_kind == "NArray"
    assert "Range(" in tau_trait.domain_expr
    assert "np.array" in tau_trait.default_expr
    assert ":math:`" in tau_trait.label


def test_callgraph_and_star_import_backlinks() -> None:
    repo_root = find_repo_root()
    search_path = find_tvb_search_path(repo_root)
    pkg = load_tvb_package(search_path, scope="tvb.simulator")
    anchors = AnchorRegistry()
    symbols, short_names, anchor_to_sym = build_symbol_table(pkg, anchors)
    known = set(symbols.keys())

    hierarchy = build_class_hierarchy(pkg, known)
    g2d_path = "tvb.simulator.models.oscillator.Generic2dOscillator"
    assert "tvb.simulator.models.base.ModelNumbaDfun" in hierarchy.bases.get(g2d_path, [])

    uses = extract_static_uses(pkg, known, hierarchy)
    sim_run = "tvb.simulator.simulator.Simulator.run"
    assert sim_run in uses and len(uses[sim_run]) > 0

    backlinks = scan_tutorial_backlinks(
        repo_root / "content", pkg, known, short_names, anchor_to_sym
    )
    # Must resolve `from tvb.simulator.lab import *` usage of Generic2dOscillator / Simulator
    assert len(backlinks.get(g2d_path, [])) >= 10
    assert len(backlinks.get("tvb.simulator.simulator.Simulator", [])) >= 10


def test_generated_api_integrity_when_present() -> None:
    repo_root = find_repo_root()
    xref_path = repo_root / "content" / "reference" / "api" / "api-xref-map.json"
    symbols_path = repo_root / "_build" / "apidoc" / "api-symbols.json"
    if not xref_path.is_file() or not symbols_path.is_file():
        return

    xref = json.loads(xref_path.read_text(encoding="utf-8"))
    syms = json.loads(symbols_path.read_text(encoding="utf-8"))
    assert len(syms) > 1000
    anchors = [v["anchor"] for v in xref["symbols"].values()]
    assert len(anchors) == len(set(a.lower() for a in anchors))
    for item in syms[:50]:
        assert {"id", "name", "kind", "module", "signature", "summary", "url", "used_in_count"} <= set(item)
