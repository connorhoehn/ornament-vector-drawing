"""Validation library — geometric predicates over Anchors, Polylines, and ElementResults.

Build-time assertions that replace the render-then-eyeball loop for structural
correctness. Aesthetic judgment (stroke balance, tonal density) remains visual;
everything else is a predicate.

Two usage modes:
- STRICT — raise `ValidationError` on first failure (used in tests)
- COLLECT — return a list of errors (used during iterative plate development
  so the user can see ALL issues at once)

Every predicate takes a `label` kwarg so error messages identify which rule
fired. Tolerances default to 0.1 mm (finer than engraving hairline).
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence

from shapely.geometry import LineString, Polygon, box as shp_box, Point as ShpPoint
from shapely.ops import unary_union

from ..schema import Anchor, BBox, Polyline, ElementResult

DEFAULT_TOL = 0.1  # mm


class ValidationError(AssertionError):
    """Raised by strict predicates; also collected into reports."""


# ──────────────────────────────────────────────────────────────────────────
# Scalar predicates
# ──────────────────────────────────────────────────────────────────────────

def approx_equal(a: float, b: float, tol: float = DEFAULT_TOL,
                 label: str = "") -> None:
    if abs(a - b) > tol:
        raise ValidationError(
            f"{label or 'values'} differ: {a:.4f} vs {b:.4f} (tol={tol})"
        )


def approx_zero(a: float, tol: float = DEFAULT_TOL, label: str = "") -> None:
    if abs(a) > tol:
        raise ValidationError(f"{label or 'value'} should be 0: {a:.4f} (tol={tol})")


def in_range(a: float, lo: float, hi: float, label: str = "") -> None:
    if not (lo <= a <= hi):
        raise ValidationError(
            f"{label or 'value'} {a:.4f} out of [{lo}, {hi}]"
        )


def aspect_ratio_in_range(measured: float, denominator: float,
                          min_ratio: float, max_ratio: float,
                          label: str = "") -> None:
    """Check ``measured / denominator`` sits within [min_ratio, max_ratio].

    Used for relational sizing rules like Vignola's arcade convention
    (pier_width ≈ ⅓..½ of clear span). Guards against divide-by-zero
    on the denominator.
    """
    if denominator == 0:
        raise ValidationError(
            f"{label or 'aspect ratio'} denominator is zero"
        )
    ratio = measured / denominator
    if not (min_ratio <= ratio <= max_ratio):
        raise ValidationError(
            f"{label or 'aspect ratio'} {ratio:.3f} "
            f"(= {measured:.3f} / {denominator:.3f}) "
            f"out of [{min_ratio}, {max_ratio}]"
        )


def relative_height(taller_h: float, shorter_h: float,
                    expected_ratio: float, tol: float = 0.05,
                    label: str = "") -> None:
    """Cross-order (or cross-element) height comparison.

    ``expected_ratio`` = shorter_h / taller_h. E.g. Greek Doric (5.5D)
    vs Roman Doric (8D) at matched D → expected_ratio ≈ 5.5/8 ≈ 0.69.
    Tolerance is an absolute fraction of the expected ratio.
    """
    if taller_h == 0:
        raise ValidationError(
            f"{label or 'relative height'} taller value is zero"
        )
    actual = shorter_h / taller_h
    if abs(actual - expected_ratio) > tol:
        raise ValidationError(
            f"{label or 'relative height'} ratio {actual:.3f} "
            f"differs from expected {expected_ratio:.3f} (tol={tol})"
        )


def min_feature_visible_at_scale(feature_size_mm: float,
                                 plate_diagonal_mm: float,
                                 min_mm: float = 0.4,
                                 min_fraction: float = 0.002,
                                 label: str = "") -> None:
    """Catch detail-visibility-at-scale failures.

    ``min_mm`` is an absolute ink-readable floor (0.4 mm ≈ two hairlines);
    ``min_fraction`` is a proportion-of-plate floor (0.2% of the plate
    diagonal). A feature must satisfy BOTH bounds.
    """
    if feature_size_mm < min_mm:
        raise ValidationError(
            f"{label or 'feature'} {feature_size_mm:.2f} mm below "
            f"absolute min {min_mm} mm — will not print"
        )
    if plate_diagonal_mm > 0 and feature_size_mm / plate_diagonal_mm < min_fraction:
        raise ValidationError(
            f"{label or 'feature'} {feature_size_mm:.2f} mm is only "
            f"{100 * feature_size_mm / plate_diagonal_mm:.3f}% of plate "
            f"diagonal ({plate_diagonal_mm:.0f} mm); min is "
            f"{100 * min_fraction:.2f}%"
        )


# ──────────────────────────────────────────────────────────────────────────
# Anchor predicates
# ──────────────────────────────────────────────────────────────────────────

def aligned_vertical(a: Anchor, b: Anchor, tol: float = DEFAULT_TOL) -> None:
    """Two anchors share an x-coordinate (vertically aligned)."""
    if abs(a.x - b.x) > tol:
        raise ValidationError(
            f"anchors '{a.name}' and '{b.name}' not vertically aligned: "
            f"x={a.x:.3f} vs {b.x:.3f}"
        )


def aligned_horizontal(a: Anchor, b: Anchor, tol: float = DEFAULT_TOL) -> None:
    """Two anchors share a y-coordinate."""
    if abs(a.y - b.y) > tol:
        raise ValidationError(
            f"anchors '{a.name}' and '{b.name}' not horizontally aligned: "
            f"y={a.y:.3f} vs {b.y:.3f}"
        )


def meets(upper: Anchor, lower: Anchor, tol: float = DEFAULT_TOL) -> None:
    """Two anchors must coincide (edges that must touch).

    In SVG coords (y down), ``upper`` is the anchor of the element whose
    bottom edge sits on ``lower``'s top edge. Both x and y must match.
    """
    if abs(upper.x - lower.x) > tol or abs(upper.y - lower.y) > tol:
        raise ValidationError(
            f"anchors '{upper.name}' and '{lower.name}' do not meet: "
            f"({upper.x:.3f}, {upper.y:.3f}) vs ({lower.x:.3f}, {lower.y:.3f})"
        )


def distance_equals(a: Anchor, b: Anchor, d: float, tol: float = DEFAULT_TOL,
                    label: str = "") -> None:
    actual = math.hypot(a.x - b.x, a.y - b.y)
    if abs(actual - d) > tol:
        raise ValidationError(
            f"{label or f'distance {a.name}↔{b.name}'}: "
            f"{actual:.3f} ≠ {d:.3f} (tol={tol})"
        )


def above(upper: Anchor, lower: Anchor, min_gap: float = 0.0) -> None:
    """In SVG coords (y down), ``upper`` must have smaller y than ``lower``."""
    if upper.y > lower.y - min_gap:
        raise ValidationError(
            f"'{upper.name}' (y={upper.y:.3f}) not above '{lower.name}' "
            f"(y={lower.y:.3f}) by at least {min_gap}"
        )


def below(lower: Anchor, upper: Anchor, min_gap: float = 0.0) -> None:
    above(upper, lower, min_gap)


# ──────────────────────────────────────────────────────────────────────────
# Bounding box / containment
# ──────────────────────────────────────────────────────────────────────────

def contained(child: BBox, parent: BBox, margin: float = 0.0,
              label: str = "") -> None:
    if not (child[0] >= parent[0] - margin and
            child[1] >= parent[1] - margin and
            child[2] <= parent[2] + margin and
            child[3] <= parent[3] + margin):
        raise ValidationError(
            f"{label or 'child bbox'} {child} not contained in {parent} "
            f"(margin={margin})"
        )


def disjoint(a: BBox, b: BBox, min_sep: float = 0.0, label: str = "") -> None:
    if not (a[2] + min_sep < b[0] or b[2] + min_sep < a[0] or
            a[3] + min_sep < b[1] or b[3] + min_sep < a[1]):
        raise ValidationError(
            f"{label or 'bboxes'} {a} and {b} overlap (min_sep={min_sep})"
        )


# ──────────────────────────────────────────────────────────────────────────
# Polyline predicates
# ──────────────────────────────────────────────────────────────────────────

def is_closed(polyline: Sequence, tol: float = 0.05, label: str = "") -> None:
    if len(polyline) < 3:
        raise ValidationError(f"{label or 'polyline'} too short to be closed")
    p0, p1 = polyline[0], polyline[-1]
    if math.hypot(p0[0] - p1[0], p0[1] - p1[1]) > tol:
        raise ValidationError(
            f"{label or 'polyline'} not closed: first={p0}, last={p1}"
        )


def no_self_intersection(polyline: Sequence, label: str = "") -> None:
    """Shapely LinearRing reports invalid when edges cross."""
    from shapely.geometry import LinearRing
    from shapely.validation import explain_validity
    try:
        ring = LinearRing(list(polyline))
    except Exception as e:
        raise ValidationError(f"{label or 'polyline'} invalid: {e}")
    if not ring.is_valid:
        raise ValidationError(
            f"{label or 'polyline'} self-intersects: {explain_validity(ring)}"
        )


def no_duplicate_lines(polylines: Sequence[Sequence], tol: float = 0.05,
                       label: str = "") -> None:
    """Catch the entablature-overlap bug: two 2-point polylines representing
    the same segment (forward or reversed)."""
    seen: set[tuple] = set()
    dupes: list[tuple[int, int]] = []
    for i, pl in enumerate(polylines):
        if len(pl) != 2:
            continue
        a, b = pl[0], pl[1]
        # Round to tol grid to make hash-able
        key_fwd = (round(a[0] / tol), round(a[1] / tol),
                   round(b[0] / tol), round(b[1] / tol))
        key_rev = (round(b[0] / tol), round(b[1] / tol),
                   round(a[0] / tol), round(a[1] / tol))
        if key_fwd in seen or key_rev in seen:
            dupes.append((i, len(seen)))
        seen.add(key_fwd)
    if dupes:
        raise ValidationError(
            f"{label or 'polylines'} contain {len(dupes)} duplicate lines"
        )


def monotonic_in_radius(polyline: Sequence, center: tuple[float, float],
                        direction: str = "decreasing",
                        tol: float = 0.5, label: str = "") -> None:
    """For spirals. All distances from center must move monotonically.

    Allow small tolerance per step to absorb sampling noise.
    """
    radii = [math.hypot(x - center[0], y - center[1]) for x, y in polyline]
    for i in range(1, len(radii)):
        if direction == "decreasing" and radii[i] > radii[i - 1] + tol:
            raise ValidationError(
                f"{label or 'spiral'} not decreasing at step {i}: "
                f"{radii[i-1]:.3f} → {radii[i]:.3f}"
            )
        if direction == "increasing" and radii[i] < radii[i - 1] - tol:
            raise ValidationError(
                f"{label or 'spiral'} not increasing at step {i}"
            )


def total_angle_sweep(polyline: Sequence, center: tuple[float, float]) -> float:
    """Return total signed angle swept by polyline around center, in radians.
    Useful for checking volute has 3 full turns = 6π."""
    if len(polyline) < 2:
        return 0.0
    total = 0.0
    px, py = polyline[0]
    a_prev = math.atan2(py - center[1], px - center[0])
    for x, y in polyline[1:]:
        a = math.atan2(y - center[1], x - center[0])
        da = a - a_prev
        # Unwrap
        while da > math.pi:
            da -= 2 * math.pi
        while da < -math.pi:
            da += 2 * math.pi
        total += da
        a_prev = a
    return total


def mirror_symmetric(polyline: Sequence, axis_x: float,
                     tol: float = 0.5, label: str = "") -> None:
    """For bilaterally symmetric shapes: every point has a near-mirror on the
    other side of ``axis_x``. Tolerance is loose because parametric curves
    won't mirror perfectly pixel-for-pixel."""
    pts = list(polyline)
    if len(pts) < 4:
        return
    # For each point, find nearest mirrored counterpart
    from shapely.geometry import MultiPoint
    mirrored = [(2 * axis_x - x, y) for x, y in pts]
    mp = MultiPoint([(x, y) for x, y in pts])
    worst = 0.0
    for mx, my in mirrored:
        nearest_dist = min(math.hypot(mx - p[0], my - p[1]) for p in pts)
        worst = max(worst, nearest_dist)
    if worst > tol:
        raise ValidationError(
            f"{label or 'polyline'} not mirror-symmetric about x={axis_x}: "
            f"worst mismatch {worst:.3f} > tol {tol}"
        )


def point_inside(p: tuple[float, float], polygon_polyline: Sequence,
                 label: str = "") -> None:
    poly = Polygon(list(polygon_polyline))
    if not poly.covers(ShpPoint(p)):
        raise ValidationError(
            f"{label or 'point'} {p} not inside polygon"
        )


# ──────────────────────────────────────────────────────────────────────────
# Counting predicates
# ──────────────────────────────────────────────────────────────────────────

def count_equals(actual: int, expected: int, label: str = "") -> None:
    if actual != expected:
        raise ValidationError(
            f"{label or 'count'}: {actual} ≠ {expected}"
        )


def count_in_range(actual: int, lo: int, hi: int, label: str = "") -> None:
    if not (lo <= actual <= hi):
        raise ValidationError(
            f"{label or 'count'}: {actual} not in [{lo}, {hi}]"
        )


# ──────────────────────────────────────────────────────────────────────────
# Architectural-specific predicates
# ──────────────────────────────────────────────────────────────────────────

def opening_cleared_from_wall(opening_bbox: BBox,
                              wall_block_polylines: Sequence[Sequence],
                              label: str = "") -> None:
    """No wall block's closed polyline intersects the opening interior.

    The facade wall-clip step is supposed to subtract openings from blocks.
    If any block polyline's shapely-polygon has non-empty intersection with
    the opening rectangle, the clip failed.
    """
    opening = shp_box(*opening_bbox)
    offenders = []
    for i, bp in enumerate(wall_block_polylines):
        if len(bp) < 4:
            continue
        try:
            poly = Polygon(list(bp))
        except Exception:
            continue
        if not poly.is_valid:
            continue
        inter = poly.intersection(opening)
        # Allow tiny numerical slivers
        if inter.area > 0.5:  # mm²
            offenders.append(i)
    if offenders:
        raise ValidationError(
            f"{label or 'wall'} contains {len(offenders)} block(s) overlapping "
            f"opening {opening_bbox} — openings_cleared_from_wall failed"
        )


def voussoirs_above_springing(voussoir_polylines: Sequence[Sequence],
                              y_spring: float, tol: float = 0.2,
                              label: str = "") -> None:
    """Every voussoir corner must have y ≤ y_spring + tol (SVG: y grows down,
    so above-springing means smaller y)."""
    violators = []
    for i, vp in enumerate(voussoir_polylines):
        for x, y in vp:
            if y > y_spring + tol:
                violators.append((i, x, y))
    if violators:
        raise ValidationError(
            f"{label or 'voussoirs'}: {len(violators)} corner(s) below "
            f"springing y={y_spring}; first: {violators[0]}"
        )


def triglyph_over_every_column(triglyph_centers_x: Sequence[float],
                               column_axes_x: Sequence[float],
                               tol: float = 0.5, label: str = "") -> None:
    """For each column axis, at least one triglyph centre within tol."""
    missing = []
    for cx in column_axes_x:
        if not any(abs(tx - cx) < tol for tx in triglyph_centers_x):
            missing.append(cx)
    if missing:
        raise ValidationError(
            f"{label or 'Doric frieze'}: no triglyph over column axes "
            f"{missing}"
        )


def pediment_slope_in_canonical_range(slope_deg: float,
                                      lo: float = 10.0,
                                      hi: float = 25.0,
                                      label: str = "pediment slope") -> None:
    """Canonical pediment slopes: 12°–15° (Roman/Renaissance), up to ~22.5°
    for steep Doric pediments. Values outside [10°, 25°] are flagged."""
    if not (lo <= slope_deg <= hi):
        raise ValidationError(
            f"{label} {slope_deg}° outside canonical [{lo}°, {hi}°]"
        )


def dentils_per_bay(dentil_polylines: Sequence[Sequence],
                    bay_xs: Sequence[float],
                    expected_per_bay: int = 4,
                    tol: int = 1,
                    label: str = "dentils per bay") -> None:
    """Group dentils by which bay they fall in (between adjacent axes in
    ``bay_xs``). Each bay should contain ``expected_per_bay ± tol`` dentils.

    ``bay_xs`` is a sorted list of x-values that partition the cornice into
    bays (e.g. adjacent modillion axes or column axes). For N axes we get
    N-1 bays. Dentils whose centre-x falls strictly between two adjacent
    axes are assigned to that bay.
    """
    xs = sorted(bay_xs)
    if len(xs) < 2:
        return  # not enough axes to define a bay
    # Dentil centre x-values.
    centres = []
    for dp in dentil_polylines:
        if len(dp) < 3:
            continue
        dxs = [p[0] for p in dp]
        centres.append(sum(dxs) / len(dxs))
    # Bucket each centre into the bay (xs[i], xs[i+1]).
    bay_counts = [0] * (len(xs) - 1)
    for c in centres:
        for i in range(len(xs) - 1):
            if xs[i] < c < xs[i + 1]:
                bay_counts[i] += 1
                break
    bad = []
    for i, cnt in enumerate(bay_counts):
        if abs(cnt - expected_per_bay) > tol:
            bad.append((i, cnt))
    if bad:
        raise ValidationError(
            f"{label}: expected {expected_per_bay} ± {tol} per bay, but "
            f"{len(bad)} bay(s) off; first: bay #{bad[0][0]} has "
            f"{bad[0][1]} dentils (all bay counts: {bay_counts})"
        )


def modillion_over_column_axes(modillion_polylines: Sequence[Sequence],
                               column_axes_x: Sequence[float],
                               tol: float = 0.5,
                               label: str = "modillions over columns") -> None:
    """For each column axis, at least one modillion's centre x is within
    ``tol`` of that axis. Ware: a modillion is centred over each column axis
    in Corinthian / Composite entablatures."""
    if not column_axes_x:
        return
    # Compute each modillion's centre (mean of its outline's x-values).
    mod_centres: list[float] = []
    for mp in modillion_polylines:
        if len(mp) < 3:
            continue
        mxs = [p[0] for p in mp]
        mod_centres.append(sum(mxs) / len(mxs))
    missing = []
    for cx in column_axes_x:
        if not any(abs(mc - cx) <= tol for mc in mod_centres):
            missing.append(cx)
    if missing:
        raise ValidationError(
            f"{label}: no modillion within {tol} of column axes {missing}"
        )


def dentil_spacing_matches(dentil_polylines: Sequence[Sequence],
                           expected_oc: float, tol: float = 0.15,
                           label: str = "") -> None:
    """Consecutive dentil centres should be ``expected_oc`` apart."""
    centres = []
    for dp in dentil_polylines:
        if len(dp) < 4:
            continue
        xs = [p[0] for p in dp]
        centres.append(sum(xs) / len(xs))
    centres.sort()
    if len(centres) < 2:
        return
    bad = []
    for i in range(1, len(centres)):
        d = centres[i] - centres[i - 1]
        if abs(d - expected_oc) > tol:
            bad.append((i, d))
    if bad:
        raise ValidationError(
            f"{label or 'dentils'}: spacing drifted at {len(bad)} positions; "
            f"expected {expected_oc:.3f} ± {tol}; first bad: {bad[0]}"
        )


# ──────────────────────────────────────────────────────────────────────────
# Report collection (non-strict mode)
# ──────────────────────────────────────────────────────────────────────────

class ValidationReport:
    """Collect errors from multiple predicates without aborting on first."""

    def __init__(self):
        self.errors: list[str] = []

    def check(self, fn, *args, **kwargs) -> bool:
        try:
            fn(*args, **kwargs)
            return True
        except ValidationError as e:
            self.errors.append(str(e))
            return False

    def raise_if_any(self) -> None:
        if self.errors:
            msg = "\n  ".join(self.errors)
            raise ValidationError(f"{len(self.errors)} validation error(s):\n  {msg}")

    def __bool__(self) -> bool:
        return not self.errors

    def __len__(self) -> int:
        return len(self.errors)

    def __iter__(self):
        return iter(self.errors)
