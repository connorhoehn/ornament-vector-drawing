"""Tests for the parametric-variation catalog (Phase 36 / Phase 27).

Covers sweep parsing, override application, and end-to-end render of a
small 2×2 catalog to a tmp_path.
"""
from __future__ import annotations

import pytest

from engraving.planner import (
    FacadePlan, StoryPlan, BayPlan, OpeningPlan, ParapetPlan, PilasterPlan,
    PlinthPlan,
)
from engraving.planner.catalog import (
    SUPPORTED_SWEEP_KEYS, UnknownSweepKey,
    apply_overrides, catalog_name, parse_sweep_spec, render_catalog,
    sweep_combinations, validate_sweep_keys,
)


# ── Fixtures ──────────────────────────────────────────────────────────

def _make_base_plan() -> FacadePlan:
    """A small, feasible base plan for catalog tests."""
    plan = FacadePlan(
        canvas=(20, 30, 230, 180),
        stories=[
            StoryPlan(height_ratio=1.2, wall="arcuated",
                      has_order="doric", label="ground"),
            StoryPlan(height_ratio=1.3, wall="smooth",
                      has_order="ionic", label="piano_nobile"),
            StoryPlan(height_ratio=0.8, wall="smooth", label="attic"),
        ],
        parapet=ParapetPlan(kind="balustrade", height_ratio=0.25),
        plinth=PlinthPlan(kind="banded", height_mm=6.0),
        with_quoins=True,
    )
    for i in range(3):
        is_centre = (i == 1)
        plan.bays.append(BayPlan(
            openings=[
                OpeningPlan(
                    kind="arch_door" if is_centre else "arch_window",
                    width_frac=0.5, height_frac=0.30,
                    has_keystone=True,
                ),
                OpeningPlan(kind="window", width_frac=0.38,
                             height_frac=0.46, hood="triangular",
                             has_keystone=True),
                OpeningPlan(kind="window", width_frac=0.30,
                             height_frac=0.40, hood="cornice"),
            ],
            pilasters=PilasterPlan(order="ionic", width_frac=0.08),
            width_weight=1.15 if is_centre else 1.0,
            label="entry" if is_centre else f"bay_{i}",
        ))
    return plan


# ── Sweep parsing ────────────────────────────────────────────────────

class TestParseSweep:
    def test_single_axis(self):
        spec = parse_sweep_spec(["bays:3,5,7"])
        assert spec == {"bays": [3, 5, 7]}

    def test_multi_axis(self):
        spec = parse_sweep_spec([
            "bays:3,5",
            "piano_nobile_order:doric,ionic,corinthian",
        ])
        assert spec == {
            "bays": [3, 5],
            "piano_nobile_order": ["doric", "ionic", "corinthian"],
        }

    def test_mixed_types(self):
        spec = parse_sweep_spec(["quoins:yes,no"])
        # Values are kept as strings when neither int nor float parses.
        assert spec == {"quoins": ["yes", "no"]}

    def test_missing_colon_rejects(self):
        with pytest.raises(ValueError, match="must be"):
            parse_sweep_spec(["bays=3"])

    def test_unknown_key_rejects(self):
        with pytest.raises(UnknownSweepKey):
            parse_sweep_spec(["wobble:3,5"])


class TestSweepCombinations:
    def test_single_axis_is_identity(self):
        out = list(sweep_combinations({"bays": [3, 5, 7]}))
        assert out == [{"bays": 3}, {"bays": 5}, {"bays": 7}]

    def test_two_axis_is_cartesian(self):
        out = list(sweep_combinations({
            "bays": [3, 5],
            "quoins": ["yes", "no"],
        }))
        assert len(out) == 4   # 2 × 2
        # All four combinations present, regardless of order.
        assert {
            (d["bays"], d["quoins"]) for d in out
        } == {(3, "yes"), (3, "no"), (5, "yes"), (5, "no")}


# ── Override application ──────────────────────────────────────────────

class TestApplyOverrides:
    def test_bays_scale_up(self):
        base = _make_base_plan()
        plan = apply_overrides(base, {"bays": 5})
        assert len(plan.bays) == 5

    def test_bays_scale_down(self):
        base = _make_base_plan()
        plan = apply_overrides(base, {"bays": 1})
        assert len(plan.bays) == 1

    def test_piano_nobile_order_propagates_to_pilasters(self):
        base = _make_base_plan()
        plan = apply_overrides(base, {"piano_nobile_order": "corinthian"})
        ordered = [s for s in plan.stories if s.has_order is not None][0]
        assert ordered.has_order == "corinthian"
        # Pilasters should agree with the new order.
        for b in plan.bays:
            if b.pilasters is not None:
                assert b.pilasters.order == "corinthian"

    def test_ground_wall_changes_lowest_story(self):
        base = _make_base_plan()
        plan = apply_overrides(base, {"ground_wall": "rock_faced"})
        assert plan.stories[0].wall == "rock_faced"

    def test_parapet_kind_none_drops_parapet(self):
        base = _make_base_plan()
        plan = apply_overrides(base, {"parapet_kind": "none"})
        assert plan.parapet is None

    def test_plinth_kind_none_drops_plinth(self):
        base = _make_base_plan()
        plan = apply_overrides(base, {"plinth_kind": "none"})
        assert plan.plinth is None

    def test_quoins_yes_and_no(self):
        base = _make_base_plan()
        on = apply_overrides(base, {"quoins": "yes"})
        off = apply_overrides(base, {"quoins": "no"})
        assert on.with_quoins is True
        assert off.with_quoins is False

    def test_base_plan_is_not_mutated(self):
        base = _make_base_plan()
        n_before = len(base.bays)
        apply_overrides(base, {"bays": 9})
        # Deep-copy guarantees the base stays pristine for the next combo.
        assert len(base.bays) == n_before


# ── End-to-end render ─────────────────────────────────────────────────

class TestRenderCatalog:
    def test_two_axis_produces_svgs(self, tmp_path):
        base = _make_base_plan()
        sweep = {
            "parapet_kind": ["balustrade", "none"],
            "plinth_kind":  ["banded", "none"],
        }
        summary = render_catalog(base, sweep, tmp_path, prefix="test")
        assert summary["total"] == 4
        # Every combination either rendered or was infeasible; total match.
        assert (len(summary["ok"]) + len(summary["infeasible"])
                == summary["total"])

    def test_writes_index_and_base(self, tmp_path):
        base = _make_base_plan()
        render_catalog(base, {"quoins": ["yes", "no"]}, tmp_path,
                        prefix="test")
        assert (tmp_path / "index.md").exists()
        assert (tmp_path / "base.yaml").exists()
        index = (tmp_path / "index.md").read_text()
        assert "quoins=yes" in index
        assert "quoins=no" in index

    def test_deterministic_names(self, tmp_path):
        base = _make_base_plan()
        summary_a = render_catalog(base, {"quoins": ["yes"]},
                                     tmp_path / "a", prefix="xx")
        summary_b = render_catalog(base, {"quoins": ["yes"]},
                                     tmp_path / "b", prefix="xx")
        names_a = {r["name"] for r in summary_a["ok"]}
        names_b = {r["name"] for r in summary_b["ok"]}
        assert names_a == names_b


def test_catalog_name_sorted_keys():
    a = catalog_name({"bays": 5, "quoins": "yes"}, prefix="p")
    b = catalog_name({"quoins": "yes", "bays": 5}, prefix="p")
    assert a == b   # key order must not affect filename


def test_supported_keys_are_documented():
    # Regression guard: if someone adds a new override branch, they must
    # register the key here. Keeps the CLI --help accurate.
    assert "bays" in SUPPORTED_SWEEP_KEYS
    assert "piano_nobile_order" in SUPPORTED_SWEEP_KEYS
    assert "quoins" in SUPPORTED_SWEEP_KEYS
    validate_sweep_keys(SUPPORTED_SWEEP_KEYS)   # must not raise
