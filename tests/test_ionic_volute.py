"""Tests for the Holm 12-centre Ionic volute construction (Phase 38).

The canonical Ionic volute is a 12-arc chain whose centres cascade inside
the eye in a tight inward staircase. These tests pin the geometric
invariants that distinguish the Holm construction from a simple log spiral
and from the pre-Phase 38 approximation.
"""
from __future__ import annotations

import math

import pytest

from engraving import canon
from engraving.order_ionic import ionic_column_silhouette
from engraving.order_composite import composite_column_silhouette
from engraving.volute import ionic_volute, ionic_volute_holm


# ---------------------------------------------------------------------------
# Holm primitive — invariants
# ---------------------------------------------------------------------------

def test_holm_returns_dense_outer_spiral():
    """The outer spiral is >100 points (vs ~20 of a simple spiral).

    The 12-arc construction at 32 samples/arc yields ~370 points, several
    times denser than a log-spiral approximation at the same scale.
    """
    parts = ionic_volute_holm(cx=0.0, cy=0.0,
                              r_outer=10.0, r_eye=1.5,
                              fillet_frac=1.0 / 3.0, hand="right")
    outer = parts["outer"][0]
    assert len(outer) > 100, (
        f"Holm outer spiral should have >100 points, got {len(outer)}")


def test_holm_outer_spiral_monotonic_radius():
    """Distance from the eye centre decreases (modulo per-step sampling
    noise) as we walk the spiral from start to end.

    Small radial increases between adjacent samples are allowed because
    each arc is drawn around a centre that drifts inside the eye (the
    characteristic Holm inflection). The tolerance is half the eye
    radius — validated by engraving.validate.
    """
    r_eye = 1.5
    parts = ionic_volute_holm(cx=0.0, cy=0.0,
                              r_outer=10.0, r_eye=r_eye,
                              fillet_frac=1.0 / 3.0, hand="right")
    outer = parts["outer"][0]
    tol = max(0.5, 0.5 * r_eye)
    rs = [math.hypot(x, y) for x, y in outer]
    for i in range(1, len(rs)):
        assert rs[i] <= rs[i - 1] + tol, (
            f"radial monotonicity broken at step {i}: "
            f"{rs[i-1]:.3f} -> {rs[i]:.3f} (tol={tol:.3f})")


def test_holm_spiral_starts_at_top_of_volute():
    """The first sample of the outer spiral sits directly above the eye
    centre at (cx, cy - r_outer) — the canonical Vignola starting point.

    In SVG y-down coordinates 'above' means smaller y.
    """
    r_outer = 10.0
    parts = ionic_volute_holm(cx=50.0, cy=80.0,
                              r_outer=r_outer, r_eye=1.5,
                              fillet_frac=1.0 / 3.0, hand="right")
    start = parts["outer"][0][0]
    assert abs(start[0] - 50.0) < 1e-6
    assert abs(start[1] - (80.0 - r_outer)) < 1e-6


def test_holm_spiral_ends_inside_eye():
    """After 12 quarter-turns the outline has entered the eye: the final
    sample is within the eye circle (dist < r_eye)."""
    cx, cy = 0.0, 0.0
    r_eye = 1.67
    parts = ionic_volute_holm(cx=cx, cy=cy,
                              r_outer=11.11, r_eye=r_eye,
                              fillet_frac=1.0 / 3.0, hand="right")
    end = parts["outer"][0][-1]
    d_end = math.hypot(end[0] - cx, end[1] - cy)
    assert d_end < r_eye, (
        f"endpoint should be inside eye (r={r_eye:.2f}), got dist={d_end:.3f}")


def test_holm_hand_left_mirrors_right():
    """hand='left' is the exact x-mirror of hand='right' about the eye
    centre's x. Every sample on the left spiral equals the x-flipped
    sample on the right spiral."""
    cx = 5.0
    parts_r = ionic_volute_holm(cx=cx, cy=0.0,
                                r_outer=10.0, r_eye=1.5,
                                fillet_frac=1.0 / 3.0, hand="right")
    parts_l = ionic_volute_holm(cx=cx, cy=0.0,
                                r_outer=10.0, r_eye=1.5,
                                fillet_frac=1.0 / 3.0, hand="left")
    outer_r = parts_r["outer"][0]
    outer_l = parts_l["outer"][0]
    assert len(outer_r) == len(outer_l)
    for (xr, yr), (xl, yl) in zip(outer_r, outer_l):
        assert abs((2 * cx - xr) - xl) < 1e-9, \
            f"left spiral is not the x-mirror of right at ({xr}, {yr})"
        assert abs(yr - yl) < 1e-9


# ---------------------------------------------------------------------------
# Integration — Ionic / Composite columns
# ---------------------------------------------------------------------------

def test_ionic_column_volutes_layer_is_dense():
    """A rendered Ionic column's 'volutes' ElementResult layer contains
    enough points that the scroll reads as a real spiral, not a handful
    of straight segments."""
    dims = canon.Ionic(D=60.0)
    result = ionic_column_silhouette(dims, cx=100.0, base_y=600.0,
                                     return_result=True)
    volute_polys = result.polylines.get("volutes", [])
    total_pts = sum(len(pl) for pl in volute_polys)
    assert total_pts > 100, (
        f"Ionic 'volutes' layer must have >100 points across its polylines, "
        f"got {total_pts}")


def test_composite_column_volutes_layer_is_dense():
    """Composite order re-uses the Holm volute for its upper Scamozzi
    scrolls; the 'volutes' layer must carry the same density."""
    dims = canon.Composite(D=60.0)
    result = composite_column_silhouette(dims, cx=100.0, base_y=600.0,
                                         return_result=True)
    volute_polys = result.polylines.get("volutes", [])
    total_pts = sum(len(pl) for pl in volute_polys)
    assert total_pts > 100, (
        f"Composite 'volutes' layer must have >100 points, got {total_pts}")


# ---------------------------------------------------------------------------
# Legacy wrapper preserves the ionic_volute dict interface
# ---------------------------------------------------------------------------

def test_ionic_volute_wrapper_preserves_keys():
    """The historical ionic_volute(D, ...) wrapper routes through the
    Holm primitive but preserves the 'outer' / 'channel' / 'fillet' /
    'eye' dict contract expected by the five-orders builders."""
    parts = ionic_volute(eye_cx=0.0, eye_cy=0.0, D=60.0,
                         direction="right", include_channel=True)
    for key in ("outer", "fillet", "eye", "channel"):
        assert key in parts, f"missing key '{key}' in ionic_volute result"
    assert len(parts["outer"]) == 1
    assert len(parts["channel"]) == 1
    assert len(parts["eye"]) == 1
    # fillet is two horizontal segments (top + bottom edges of the band)
    assert len(parts["fillet"]) == 2
