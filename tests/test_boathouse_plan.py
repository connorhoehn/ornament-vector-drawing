"""Phase 30 — Tests for the BoathousePlan / RoofPlan pipeline."""
from __future__ import annotations

import math
import os
from pathlib import Path

import pytest

from engraving.containment import validate_tree
from engraving.planner import (
    BoathousePlan, RoofPlan, PlinthPlan, PlanInfeasible,
)
from engraving.planner.elements import (
    BoathouseElement, RoofElement,
)


class TestRoofPlan:
    def test_default_slope_is_valid(self):
        r = RoofPlan()
        assert 5.0 <= r.slope_deg <= 45.0

    def test_rejects_too_shallow_slope(self):
        """Roof slope < 5° is effectively flat — not a gable."""
        with pytest.raises(ValueError, match=r"slope_deg"):
            RoofPlan(slope_deg=2.0)

    def test_rejects_too_steep_slope(self):
        """Roof slope > 45° is steeper than any boathouse precedent."""
        with pytest.raises(ValueError, match=r"slope_deg"):
            RoofPlan(slope_deg=60.0)

    def test_accepts_boundary_slopes(self):
        RoofPlan(slope_deg=5.0)
        RoofPlan(slope_deg=45.0)

    def test_rejects_negative_overhang(self):
        with pytest.raises(ValueError, match=r"overhang_mm"):
            RoofPlan(overhang_mm=-1.0)


class TestBoathousePlanBasics:
    def test_default_canvas_and_bay_count(self):
        p = BoathousePlan()
        assert p.bay_count == 3
        assert p.bay_kind == "arched"
        assert p.has_upper_story is True

    def test_rejects_invalid_bay_kind(self):
        with pytest.raises(ValueError, match=r"bay_kind"):
            BoathousePlan(bay_kind="pointed")  # type: ignore[arg-type]

    def test_rejects_zero_bays(self):
        with pytest.raises(ValueError, match=r"bay_count"):
            BoathousePlan(bay_count=0)

    def test_rejects_inverted_canvas(self):
        with pytest.raises(ValueError, match=r"canvas"):
            BoathousePlan(canvas=(100, 100, 50, 50))


class TestBoathouseSolver:
    def _mkplan(self, **overrides) -> BoathousePlan:
        defaults = dict(
            canvas=(0, 0, 240, 160),
            bay_count=3,
            bay_kind="arched",
            has_upper_story=True,
            upper_story_window_count=5,
            roof=RoofPlan(slope_deg=22.0, overhang_mm=6.0,
                           has_shingle_hatch=True),
            plinth=PlinthPlan(kind="banded", height_mm=6.0),
        )
        defaults.update(overrides)
        return BoathousePlan(**defaults)

    def test_solve_returns_boathouse_element(self):
        plan = self._mkplan()
        root = plan.solve()
        assert isinstance(root, BoathouseElement)

    def test_solve_emits_expected_children(self):
        plan = self._mkplan()
        root = plan.solve()
        kinds = {child.kind for child in root.children}
        # plinth + boat story + upper story + roof
        assert "plinth" in kinds
        assert "story" in kinds
        assert "roof" in kinds

    def test_infeasible_when_canvas_too_short(self):
        """A 10mm tall canvas cannot fit plinth + gable + stories."""
        plan = BoathousePlan(
            canvas=(0, 0, 240, 10),
            bay_count=3,
            bay_kind="arched",
            has_upper_story=True,
            upper_story_window_count=5,
            roof=RoofPlan(slope_deg=22.0, overhang_mm=6.0),
            plinth=PlinthPlan(kind="smooth", height_mm=6.0),
        )
        with pytest.raises(PlanInfeasible):
            plan.solve()

    def test_infeasible_when_canvas_too_narrow(self):
        """20mm wide with 5 bays — bay_pitch drops below readable floor."""
        plan = BoathousePlan(
            canvas=(0, 0, 20, 200),
            bay_count=5,
            bay_kind="arched",
            has_upper_story=False,
            upper_story_window_count=0,
            roof=RoofPlan(slope_deg=22.0, overhang_mm=2.0),
            plinth=None,
        )
        with pytest.raises(PlanInfeasible):
            plan.solve()

    def test_solved_tree_has_no_layer_a_violations(self):
        """Solved tree must pass validate_tree with zero Layer A violations."""
        plan = self._mkplan()
        root = plan.solve()
        violations = validate_tree(root, tol=1.5)
        assert violations == [], (
            f"expected no violations; got: "
            + "; ".join(str(v) for v in violations)
        )

    def test_vertical_stack_sums_to_canvas_height(self):
        """plinth_h + boat_bay_h + upper_story_h + gable_h == canvas_h
        within 0.5mm."""
        plan = self._mkplan()
        root = plan.solve()
        md = root.metadata
        total = (md["plinth_h"] + md["boat_bay_h"]
                 + md["upper_story_h"] + md["gable_h"])
        assert abs(total - plan.canvas_height) < 0.5, (
            f"vertical stack {total:.3f}mm does not match canvas_h "
            f"{plan.canvas_height:.3f}mm"
        )

    def test_gable_height_matches_slope_geometry(self):
        """gable_h = (canvas_w / 2) * tan(slope), no cap."""
        plan = self._mkplan()
        root = plan.solve()
        expected = (plan.canvas_width / 2.0) * math.tan(
            math.radians(plan.roof.slope_deg))
        assert abs(root.metadata["gable_h"] - expected) < 0.1

    def test_bay_count_honored(self):
        plan = self._mkplan(bay_count=4)
        root = plan.solve()
        boat_band = next(c for c in root.children
                         if c.id == "boathouse.boat_band")
        # Children = 1 wall + 4 bays
        bay_children = [c for c in boat_band.children if c.kind == "bay"]
        assert len(bay_children) == 4

    def test_trabeated_kind_works(self):
        plan = self._mkplan(bay_kind="trabeated")
        root = plan.solve()
        # The boat band should still have bays + a wall.
        boat_band = next(c for c in root.children
                         if c.id == "boathouse.boat_band")
        assert any(c.kind == "bay" for c in boat_band.children)

    def test_solver_works_without_upper_story(self):
        plan = self._mkplan(has_upper_story=False,
                             upper_story_window_count=0)
        root = plan.solve()
        # Only one StoryElement (the boat band), no upper band.
        story_ids = {c.id for c in root.children if c.kind == "story"}
        assert "boathouse.boat_band" in story_ids
        assert "boathouse.upper_band" not in story_ids


class TestRoofElement:
    def test_rake_geometry_consistent_with_slope(self):
        """The rendered rake from wall edge to apex has slope == slope_deg."""
        plan = BoathousePlan(
            canvas=(0, 0, 240, 160),
            bay_count=3,
            bay_kind="arched",
            has_upper_story=True,
            upper_story_window_count=5,
            roof=RoofPlan(slope_deg=22.0, overhang_mm=6.0),
            plinth=PlinthPlan(kind="banded", height_mm=6.0),
        )
        root = plan.solve()
        roof = next(c for c in root.children if isinstance(c, RoofElement))
        # Rake from (x_left_eave, y_eave) to (apex_x, y_apex) has slope
        # = gable_height / (apex_x - x_left_eave) = slope_deg
        dx = roof.apex_x - roof.x_left_eave
        dy = roof.gable_height
        computed_slope = math.degrees(math.atan2(dy, dx))
        assert abs(computed_slope - roof.slope_deg) < 1.0


class TestBoathousePlate:
    def test_plate_runs_end_to_end(self):
        """plate_boathouse_plan builds, validates, and writes an SVG."""
        from plates.plate_boathouse_plan import build_validated
        svg_path, report = build_validated()
        assert os.path.exists(svg_path)
        size = os.path.getsize(svg_path)
        assert size > 5000, f"SVG suspiciously small: {size} bytes"
        text = Path(svg_path).read_text()
        assert text.startswith("<?xml") or text.lstrip().startswith("<svg")
        assert len(report) == 0, (
            f"unexpected report errors: {list(report)}"
        )

    def test_plate_plan_embedded_in_svg(self):
        """The plate uses save_svg_with_plan, embedding the plan as YAML."""
        from plates.plate_boathouse_plan import build_validated
        svg_path, _ = build_validated()
        text = Path(svg_path).read_text()
        assert 'id="facade-plan"' in text, (
            "expected embedded plan metadata"
        )
