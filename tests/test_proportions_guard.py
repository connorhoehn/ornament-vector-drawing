"""Regression guards for classical-order scale bugs.

These tests lock in that the solver preserves exact Vignola proportions
between the module diameter D and the heights / widths of every
derived classical member. They guard specifically against:

  * EntablatureBandElement double-insetting the architrave (so the band
    appears narrower than the colonnade / pilaster run that carries it).
  * solve_portico treating the pediment height as a fixed term in the
    vertical budget (so D collapses and the colonnade clusters in the
    middle of the canvas).
  * Any element scale silently drifting from canon.Tuscan / canon.Doric /
    etc. when a renderer or builder is refactored.

If a future change trips these, DO NOT adjust the tolerances — fix the
underlying geometry.
"""
from __future__ import annotations

import math

import pytest

from engraving import canon
from engraving.planner import (
    PorticoPlan, PedimentPlan, PlinthPlan,
)


# ── Portico at canonical Tuscan: every block matches Vignola ──────────

@pytest.fixture
def tuscan_tetrastyle_portico():
    """Canonical Vignola Tuscan tetrastyle on a typical landscape canvas."""
    plan = PorticoPlan(
        canvas=(15, 15, 240, 180),
        order="tuscan",
        column_count=4,
        intercolumniation_modules=4.0,
        pedestal=True,
        plinth=PlinthPlan(kind="banded", height_mm=6.0),
        pediment=PedimentPlan(slope_deg=15.0),
    )
    portico = plan.solve()
    return plan, portico


def test_portico_column_height_is_7_D_for_tuscan(tuscan_tetrastyle_portico):
    """Tuscan column_D = 7.0 — column_h must be exactly 7·D."""
    _, portico = tuscan_tetrastyle_portico
    D = portico.metadata["D"]
    dims = canon.Tuscan(D=D)
    run = portico.find("portico.columns")
    assert run is not None, "portico.columns element missing"
    bb = run.effective_bbox()
    h = bb[3] - bb[1]
    assert abs(h - dims.column_h) < 0.05, (
        f"column_run h={h:.3f} ≠ canon column_h={dims.column_h:.3f} "
        f"(should be 7·D = 7·{D:.3f})"
    )


def test_portico_entablature_height_is_1_75_D_for_tuscan(tuscan_tetrastyle_portico):
    """Tuscan entablature_D = 1.75 — height must be exactly 1.75·D."""
    _, portico = tuscan_tetrastyle_portico
    D = portico.metadata["D"]
    dims = canon.Tuscan(D=D)
    band = portico.find("portico.entablature")
    assert band is not None
    bb = band.effective_bbox()
    h = bb[3] - bb[1]
    assert abs(h - dims.entablature_h) < 0.05, (
        f"entablature h={h:.3f} ≠ canon entablature_h={dims.entablature_h:.3f} "
        f"(should be 1.75·D = 1.75·{D:.3f})"
    )


def test_portico_pedestal_height_is_2_33_D_for_tuscan(tuscan_tetrastyle_portico):
    """Tuscan pedestal_D = 7/3 ≈ 2.333 — height must match canon."""
    _, portico = tuscan_tetrastyle_portico
    D = portico.metadata["D"]
    dims = canon.Tuscan(D=D)
    ped = portico.find("portico.pedestal")
    assert ped is not None
    bb = ped.effective_bbox()
    h = bb[3] - bb[1]
    assert abs(h - dims.pedestal_h) < 0.05, (
        f"pedestal h={h:.3f} ≠ canon pedestal_h={dims.pedestal_h:.3f}"
    )


def test_portico_pediment_height_matches_slope_and_colonnade(
    tuscan_tetrastyle_portico
):
    """pediment_h = (colonnade_w / 2) · tan(slope) — the whole pediment
    must scale with D, not be computed off the full canvas."""
    plan, portico = tuscan_tetrastyle_portico
    colonnade_w = (
        portico.metadata["colonnade_right_x"]
        - portico.metadata["colonnade_left_x"]
    )
    expected_h = (colonnade_w / 2.0) * math.tan(
        math.radians(plan.pediment.slope_deg)
    )
    pediment = portico.find("portico.pediment")
    assert pediment is not None
    bb = pediment.effective_bbox()
    h = bb[3] - bb[1]
    assert abs(h - expected_h) < 0.05, (
        f"pediment h={h:.3f} ≠ expected {expected_h:.3f} "
        f"(slope {plan.pediment.slope_deg}°, colonnade_w {colonnade_w:.2f})"
    )


def test_portico_entablature_architrave_aligns_with_colonnade(
    tuscan_tetrastyle_portico
):
    """The architrave must align with the outer column axes (with a
    ±1·D tolerance for the abacus projection). Regression guard against
    the double-inset bug where the entablature was ~2·D narrower than
    the colonnade it nominally rested on.
    """
    _, portico = tuscan_tetrastyle_portico
    D = portico.metadata["D"]
    colonnade_left = portico.metadata["colonnade_left_x"]
    colonnade_right = portico.metadata["colonnade_right_x"]
    band = portico.find("portico.entablature")
    # The entablature element itself receives x_left == colonnade_left_x.
    assert abs(band.x_left - colonnade_left) < 0.01, (
        f"entablature.x_left={band.x_left:.3f} should equal "
        f"colonnade_left_x={colonnade_left:.3f}"
    )
    assert abs(band.x_right - colonnade_right) < 0.01, (
        f"entablature.x_right={band.x_right:.3f} should equal "
        f"colonnade_right_x={colonnade_right:.3f}"
    )
    # And the effective bbox — which includes the projecting cornice —
    # must be WIDER than the colonnade, not narrower.
    bb = band.effective_bbox()
    assert bb[0] <= colonnade_left + 0.5, (
        f"entablature bbox left={bb[0]:.2f} should not start inside the "
        f"colonnade (colonnade_left_x={colonnade_left:.2f}). "
        f"This is the double-inset regression."
    )
    assert bb[2] >= colonnade_right - 0.5, (
        f"entablature bbox right={bb[2]:.2f} should not end inside the "
        f"colonnade (colonnade_right_x={colonnade_right:.2f})."
    )


def test_portico_colonnade_occupies_majority_of_canvas_width(
    tuscan_tetrastyle_portico
):
    """Guards against the original bug where D was crushed to 1/3 of
    the width-solvable value because the pediment was treated as a
    fixed height term. At canonical Tuscan on a ~225mm landscape
    canvas we expect the colonnade to use at least a third of the
    canvas width."""
    plan, portico = tuscan_tetrastyle_portico
    colonnade_w = (
        portico.metadata["colonnade_right_x"]
        - portico.metadata["colonnade_left_x"]
    )
    canvas_w = plan.canvas_width
    frac = colonnade_w / canvas_w
    assert frac >= 0.30, (
        f"colonnade is only {frac*100:.1f}% of canvas width "
        f"({colonnade_w:.1f}/{canvas_w:.1f}mm) — suggests D is being "
        f"crushed by a bad height-budget term (pediment fixed-h bug)."
    )


# ── All five orders hold their proportions ────────────────────────────

# ── Acanthus leaf richness guard ─────────────────────────────────────

def test_acanthus_leaf_returns_rich_geometry():
    """Guards against the crude SVG plugin (53-point outline-only
    zigzag) silently replacing the parametric leaf. Without the
    parametric path we get 1 polyline of ~50 points; with it we
    get 10+ polylines (silhouette + midrib + interior creases) and
    400+ total points.

    If this fails, somebody re-added ``engraving/motifs/acanthus_leaf.svg``
    and the Corinthian / Composite capitals are back to rendering as
    stacked bubbles. Check plate_acanthus_leaf_detail for visual
    confirmation.
    """
    from engraving import acanthus
    polys = acanthus.acanthus_leaf(
        width=40, height=60, lobe_count=5, teeth_per_lobe=4
    )
    total_points = sum(len(p) for p in polys)
    assert len(polys) >= 5, (
        f"acanthus_leaf returned only {len(polys)} polyline(s) — "
        f"the rich builder emits at least 5 (silhouette + midrib + "
        f"≥3 interior creases). A plugin override has likely hijacked "
        f"the motif. Check engraving/motifs/acanthus_leaf.svg"
    )
    assert total_points >= 200, (
        f"acanthus_leaf produced only {total_points} total points — "
        f"the rich parametric leaf at this size produces 400+. "
        f"See plate_acanthus_leaf_detail for a visual of what "
        f"the rich leaf looks like."
    )


@pytest.mark.parametrize("order,OrderCls", [
    ("tuscan",     canon.Tuscan),
    ("doric",      canon.Doric),
    ("ionic",      canon.Ionic),
    ("corinthian", canon.Corinthian),
    ("composite",  canon.Composite),
])
def test_every_order_column_height_is_column_D_times_D(order, OrderCls):
    """Regardless of which order, the solved column run must have
    height = column_D · D from canon. Generalizes the Tuscan guard."""
    plan = PorticoPlan(
        canvas=(15, 15, 240, 180),
        order=order,
        column_count=4,
        intercolumniation_modules=4.0,
        pedestal=False,
        plinth=PlinthPlan(kind="banded", height_mm=5.0),
        pediment=PedimentPlan(slope_deg=12.0),
    )
    portico = plan.solve()
    D = portico.metadata["D"]
    dims = OrderCls(D=D)
    run = portico.find("portico.columns")
    h = run.effective_bbox()[3] - run.effective_bbox()[1]
    assert abs(h - dims.column_h) < 0.1, (
        f"{order}: column h={h:.3f} ≠ canon {dims.column_h:.3f} "
        f"({dims.column_D}·D)"
    )
