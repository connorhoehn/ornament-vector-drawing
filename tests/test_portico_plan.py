"""Phase 29 — Tests for the PorticoPlan / PedimentPlan pipeline."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from engraving.containment import validate_tree
from engraving.planner import (
    PorticoPlan, PedimentPlan, PlinthPlan, PlanInfeasible,
)
from engraving.planner.elements import (
    PorticoElement, ColumnRunElement, PedimentElement, PedestalCourseElement,
)


class TestPedimentPlan:
    def test_default_slope_is_valid(self):
        p = PedimentPlan()
        assert 12.0 <= p.slope_deg <= 22.5

    def test_rejects_too_shallow_slope(self):
        """Pediments < 12° break classical proportion."""
        with pytest.raises(ValueError, match=r"slope_deg"):
            PedimentPlan(slope_deg=5.0)

    def test_rejects_too_steep_slope(self):
        """Pediments > 22.5° are not classical."""
        with pytest.raises(ValueError, match=r"slope_deg"):
            PedimentPlan(slope_deg=30.0)

    def test_accepts_boundary_slopes(self):
        # Both endpoints must be accepted (inclusive).
        PedimentPlan(slope_deg=12.0)
        PedimentPlan(slope_deg=22.5)


class TestPorticoPlanBasics:
    def test_default_canvas_and_order(self):
        p = PorticoPlan()
        assert p.order == "tuscan"
        assert p.column_count == 4

    def test_rejects_invalid_order(self):
        with pytest.raises(ValueError, match=r"order"):
            PorticoPlan(order="goofy")

    def test_rejects_zero_columns(self):
        with pytest.raises(ValueError, match=r"column_count"):
            PorticoPlan(column_count=1)

    def test_rejects_inverted_canvas(self):
        with pytest.raises(ValueError, match=r"canvas"):
            PorticoPlan(canvas=(100, 100, 50, 50))


class TestPorticoSolver:
    def _mkplan(self, **overrides) -> PorticoPlan:
        defaults = dict(
            canvas=(0, 0, 600, 400),
            order="tuscan",
            column_count=4,
            intercolumniation_modules=4.0,
            pedestal=True,
            plinth=PlinthPlan(kind="banded", height_mm=7.0),
            pediment=PedimentPlan(slope_deg=15.0),
        )
        defaults.update(overrides)
        return PorticoPlan(**defaults)

    def test_solve_returns_portico_element(self):
        plan = self._mkplan()
        root = plan.solve()
        assert isinstance(root, PorticoElement)

    def test_solve_emits_expected_children(self):
        plan = self._mkplan()
        root = plan.solve()
        kinds = {child.kind for child in root.children}
        # plinth, pedestal, column_run, entablature_band, pediment
        assert "plinth" in kinds
        assert "pedestal" in kinds
        assert "column_run" in kinds
        assert "entablature_band" in kinds
        assert "pediment" in kinds

    def test_column_run_has_expected_column_count(self):
        plan = self._mkplan(column_count=6)
        root = plan.solve()
        run = next(c for c in root.children if isinstance(c, ColumnRunElement))
        # Each column is a child of the ColumnRunElement.
        assert len(run.children) == 6

    def test_pediment_apex_above_base(self):
        plan = self._mkplan()
        root = plan.solve()
        pediment = next(c for c in root.children
                        if isinstance(c, PedimentElement))
        apex_x, apex_y = pediment.apex_xy
        # In SVG y-down, apex_y must be STRICTLY less than base y.
        assert apex_y < pediment.y_base
        # Apex x must be the midpoint of the base.
        assert abs(apex_x - (pediment.x_left + pediment.x_right) / 2) < 1e-6

    def test_infeasible_when_canvas_too_narrow(self):
        """4 columns at 4M intercolumniation need comfortable width; a
        25mm-wide canvas cannot shrink D small enough to keep the
        entablature band tall enough to render."""
        # Very narrow canvas with 10 columns at wide intercolumniation:
        # the derived D shrinks toward zero, and the height budget runs
        # out. We expect a PlanInfeasible.
        plan = PorticoPlan(
            canvas=(0, 0, 10, 600),   # absurdly narrow
            order="corinthian",
            column_count=10,
            intercolumniation_modules=4.0,
            pedestal=True,
            plinth=PlinthPlan(kind="smooth", height_mm=300.0),   # plinth eats
                                                                  # almost all height
            pediment=PedimentPlan(slope_deg=22.5),
        )
        with pytest.raises(PlanInfeasible):
            plan.solve()

    def test_infeasible_when_canvas_too_short(self):
        plan = PorticoPlan(
            canvas=(0, 0, 600, 10),   # 10mm tall — no room even for columns
            order="corinthian",
            column_count=4,
            pedestal=True,
            plinth=PlinthPlan(kind="smooth", height_mm=12.0),   # exceeds canvas
            pediment=PedimentPlan(slope_deg=20.0),
        )
        with pytest.raises(PlanInfeasible):
            plan.solve()

    def test_solved_tree_has_no_layer_a_violations(self):
        plan = self._mkplan()
        root = plan.solve()
        violations = validate_tree(root, tol=1.5)
        # Only truly structural (overshoot > 3mm) would have raised in the
        # solver; we still assert zero Layer A violations here.
        assert violations == [], \
            f"expected no violations; got: " + "; ".join(str(v) for v in violations)

    def test_solver_works_without_pediment_or_plinth(self):
        """Optional components can be dropped."""
        plan = PorticoPlan(
            canvas=(0, 0, 600, 300),
            order="doric",
            column_count=4,
            intercolumniation_modules=2.25,    # Vignola eustyle
            pedestal=False,
            plinth=None,
            pediment=None,
        )
        root = plan.solve()
        kinds = {c.kind for c in root.children}
        assert "plinth" not in kinds
        assert "pedestal" not in kinds
        assert "pediment" not in kinds
        assert "column_run" in kinds
        assert "entablature_band" in kinds


class TestPorticoPlate:
    def test_plate_runs_end_to_end(self, tmp_path, monkeypatch):
        """plate_portico_plan builds, validates, and writes an SVG."""
        # Run the plate. It writes to config.OUT_DIR, not tmp_path — we
        # just check that the returned path exists and is a non-empty SVG.
        from plates.plate_portico_plan import build_validated
        svg_path, report = build_validated()
        assert os.path.exists(svg_path)
        # Non-trivial size means we actually wrote geometry.
        size = os.path.getsize(svg_path)
        assert size > 5000, f"SVG suspiciously small: {size} bytes"
        # The SVG should contain XML.
        text = Path(svg_path).read_text()
        assert text.startswith("<?xml") or text.lstrip().startswith("<svg")
        # The report is iterable and has a len; 0 errors for the default plan.
        assert len(report) == 0, f"unexpected report errors: {list(report)}"

    def test_plate_plan_embedded_in_svg(self):
        """The plate uses save_svg_with_plan, which embeds the plan as YAML
        metadata inside the SVG for round-tripping."""
        from plates.plate_portico_plan import build_validated
        svg_path, _ = build_validated()
        text = Path(svg_path).read_text()
        assert 'id="facade-plan"' in text, (
            "expected embedded plan metadata"
        )
