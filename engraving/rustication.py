"""Expanded rustication variants for masonry walls.

Rustication is the treatment of ashlar blocks so the joints and/or faces read
strongly. The existing `elements.rusticated_block_wall` produces banded
rustication (horizontal V-grooves only, flush vertical joints). This module
provides a richer peer set covering six historical variants:

- banded          horizontal channels only (Italian ground floor, Renaissance)
- chamfered       V-grooves on every joint (both horizontal + vertical)
- smooth          no face carving, broad V-joints (late-Renaissance palazzo)
- rock_faced      block face stippled to suggest unhewn stone (Quattro cento)
- vermiculated    worm-track grooves carved across each face (French 18c)
- arcuated        rustication integrated with arched openings; voussoirs
                  radiate from a springing line, blocks below the springing
                  lay normally, blocks that would intersect the opening are
                  skipped.

Coordinate convention matches the rest of the package: y increases downward.
Each wall sits with its top-left corner at (x0, y0) and extends +width to the
right and +height downward.
"""
from __future__ import annotations

import math
import random
from typing import Literal

from shapely.geometry import Polygon

from .elements import Shadow
from .geometry import Point, Polyline, arc
from . import stippling


Variant = Literal["banded", "chamfered", "smooth", "rock_faced",
                  "vermiculated", "arcuated"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _block_grid(x0: float, y0: float, width: float, height: float,
                course_h: float, block_w: float,
                bond: str) -> tuple[list[tuple[float, float, float, float, int]],
                                    list[float], float]:
    """Generate block rectangles and the list of horizontal course y-lines.

    Returns:
        blocks: list of (xx, y, xxe, y+ch, row_index) tuples clipped to wall
        course_ys: y values of every horizontal course line (including top
                   and bottom of wall)
        actual_course_h: actual course height used (height / n_courses)
    """
    n_courses = max(1, int(round(height / course_h)))
    actual_course_h = height / n_courses

    blocks: list[tuple[float, float, float, float, int]] = []
    course_ys: list[float] = [y0 + i * actual_course_h for i in range(n_courses + 1)]

    for row in range(n_courses):
        y_top = y0 + row * actual_course_h
        y_bot = y_top + actual_course_h
        offset = (block_w / 2) if (bond == "running" and row % 2 == 1) else 0.0
        x = x0 - offset
        while x < x0 + width:
            xx = max(x, x0)
            xxe = min(x + block_w, x0 + width)
            if xx < xxe:
                blocks.append((xx, y_top, xxe, y_bot, row))
            x += block_w
    return blocks, course_ys, actual_course_h


def _horizontal_joint_shadow(x0: float, width: float, y: float, v: float) -> Polygon:
    """V-groove shadow band centred on y, thickness v."""
    half = v / 2
    return Polygon([
        (x0, y - half), (x0 + width, y - half),
        (x0 + width, y + half), (x0, y + half),
    ])


def _vertical_joint_shadow(x: float, y_top: float, y_bot: float, v: float) -> Polygon:
    """V-groove shadow band centred on x, thickness v."""
    half = v / 2
    return Polygon([
        (x - half, y_top), (x + half, y_top),
        (x + half, y_bot), (x - half, y_bot),
    ])


def _rectangle(x0: float, y0: float, x1: float, y1: float) -> Polyline:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]


# ---------------------------------------------------------------------------
# Face-carving helpers
# ---------------------------------------------------------------------------

def _vermiculated_face(xx: float, y_top: float, xxe: float, y_bot: float,
                       rng: random.Random,
                       n_worms_min: int = 5, n_worms_max: int = 10
                       ) -> list[Polyline]:
    """Draw 5-10 worm-like sine polylines across the block face."""
    worms: list[Polyline] = []
    inset_x = (xxe - xx) * 0.08
    inset_y = (y_bot - y_top) * 0.12
    left = xx + inset_x
    right = xxe - inset_x
    top = y_top + inset_y
    bot = y_bot - inset_y
    if right <= left or bot <= top:
        return worms
    n_worms = rng.randint(n_worms_min, n_worms_max)
    height = bot - top
    span = right - left

    for i in range(n_worms):
        # Base y-line for this worm, evenly spaced within the inset area.
        t = (i + 0.5) / n_worms
        base_y = top + t * height
        # Amplitude: small fraction of a single band's vertical slot
        amp = 0.35 * (height / n_worms) * rng.uniform(0.55, 1.0)
        phase = rng.uniform(0.0, 2.0 * math.pi)
        freq_cycles = rng.uniform(1.5, 3.0)  # full cycles across the block
        omega = 2.0 * math.pi * freq_cycles / span
        steps = 36
        pts: Polyline = []
        for s in range(steps + 1):
            x = left + span * s / steps
            y = base_y + amp * math.sin(omega * (x - left) + phase)
            # keep inside the block face
            y = max(top, min(bot, y))
            pts.append((x, y))
        worms.append(pts)
    return worms


def _rock_faced_stipples(xx: float, y_top: float, xxe: float, y_bot: float,
                         seed: int) -> list[Point]:
    """Stipple the block interior, inset 10% from each edge."""
    bw = xxe - xx
    bh = y_bot - y_top
    inset_x = bw * 0.10
    inset_y = bh * 0.10
    region = Polygon([
        (xx + inset_x, y_top + inset_y),
        (xxe - inset_x, y_top + inset_y),
        (xxe - inset_x, y_bot - inset_y),
        (xx + inset_x, y_bot - inset_y),
    ])
    if region.is_empty or region.area <= 0:
        return []
    # Target 100-200 dots/block. Area is (bw*0.8)*(bh*0.8). Solve density.
    inner_area = region.area
    target = 150  # midpoint
    density = target / max(inner_area, 1e-6)
    return stippling.stipple(region, density=density, jitter=0.45, seed=seed)


# ---------------------------------------------------------------------------
# Arch helpers (arcuated)
# ---------------------------------------------------------------------------

def _semicircular_voussoirs(cx: float, y_spring: float, span: float,
                            ring_thickness: float,
                            n_voussoirs: int = 11) -> list[Polyline]:
    """Return polylines for each radiating voussoir wedge (closed quads).

    The voussoir ring is constrained to the UPPER semicircle only: angles
    run from pi (west-springing) through 3*pi/2 (apex) to 2*pi (east-
    springing). In SVG's y-down convention, sin(theta) is in [-1, 0] across
    this range, so every corner has y = y_spring + r*sin(theta) <= y_spring,
    which guarantees no voussoir corner drops below the springing line.

    Each wedge corner is also clamped defensively to y_spring so tiny
    floating-point excursions (sin(pi) returning ~1e-16 instead of 0) can
    never leak a corner below the chord.
    """
    if n_voussoirs < 3:
        n_voussoirs = 3
    if n_voussoirs % 2 == 0:
        n_voussoirs += 1  # ensure a keystone at the apex
    r_in = span / 2
    r_out = r_in + ring_thickness
    # angles go from pi (left springing) to 2*pi (right springing) in SVG
    # y-down convention. Apex is at angle 3*pi/2 (y smaller). The upper
    # semicircle has sin(theta) in [-1, 0] so corners stay at or above
    # y_spring.
    a0 = math.pi
    a1 = 2.0 * math.pi

    def _corner(r: float, theta: float) -> tuple[float, float]:
        # Clamp y to y_spring so numeric fuzz at the chord endpoints
        # (sin(pi), sin(2*pi)) can't produce a point fractionally below
        # the springing line.
        y = y_spring + r * math.sin(theta)
        if y > y_spring:
            y = y_spring
        return (cx + r * math.cos(theta), y)

    wedges: list[Polyline] = []
    for k in range(n_voussoirs):
        ak = a0 + (a1 - a0) * k / n_voussoirs
        ak1 = a0 + (a1 - a0) * (k + 1) / n_voussoirs
        p0 = _corner(r_in, ak)
        p1 = _corner(r_out, ak)
        p2 = _corner(r_out, ak1)
        p3 = _corner(r_in, ak1)
        # Every corner of every voussoir must lie on or above the springing
        # line (SVG: y <= y_spring). If any point violates, skip the wedge
        # rather than emit geometry that would produce a "fan" below the
        # intrados.
        corners = [p0, p1, p2, p3]
        if any(pt[1] > y_spring + 1e-6 for pt in corners):
            continue
        wedges.append([p0, p1, p2, p3, p0])
    return wedges


def _arch_opening_polygon(cx: float, y_spring: float, span: float) -> Polygon:
    """The negative-space polygon of a semicircular arch opening.

    Semicircle of radius span/2 above y_spring (y-down SVG convention).
    The arc already starts at left-springing (pi) and ends at right-springing
    (2*pi); shapely closes the ring automatically along the chord.
    """
    r = span / 2
    pts = arc(cx, y_spring, r, math.pi, 2.0 * math.pi, steps=48)
    return Polygon(pts)


def _arch_ring_polygon(cx: float, y_spring: float, span: float,
                       ring_thickness: float) -> Polygon:
    """The polygon of the voussoir ring itself.

    The ring is a half-annulus capped at the springing line. We walk the outer
    arc from left-springing up over to right-springing, then the inner arc
    back from right-springing to left-springing, yielding a single simple
    closed polygon (no interior hole needed).
    """
    r_in = span / 2
    r_out = r_in + ring_thickness
    # y-down: left springing angle = pi, apex at 3*pi/2, right at 2*pi.
    outer = arc(cx, y_spring, r_out, math.pi, 2.0 * math.pi, steps=64)
    inner_back = arc(cx, y_spring, r_in, 2.0 * math.pi, math.pi, steps=64)
    return Polygon(list(outer) + list(inner_back))


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def wall(x0: float, y0: float, width: float, height: float,
         course_h: float, block_w: float,
         variant: Variant = "banded",
         v_joint_w: float = 0.8,
         bond: str = "running",
         arch_springings_y: list[float] | None = None,
         arch_spans: list[tuple[float, float]] | None = None,
         emit_blocks: bool = True,
         seed: int = 0) -> dict:
    """A rusticated wall elevation.

    Returns dict with keys:
        outline:         Polyline
        joints:          list[Polyline]       centerlines of grooves
        joint_shadows:   list[Shadow]
        block_rects:     list[Polyline]
        face_carving:    list[Polyline]       per-face worm grooves
        face_stipples:   list[Point]          dots for rock-faced
        arch_voussoirs:  list[Polyline]       only for arcuated variant

    When ``emit_blocks`` is False, the wall suppresses both block_rects and
    vertical joints, producing only horizontal string-coursing. Intended for
    lightly-banded upper stories that want faint horizontals without a full
    ashlar grid.
    """
    rng = random.Random(seed)

    # --- 'smooth' widens the V-joint substantially ---
    if variant == "smooth":
        v = max(v_joint_w, 2.0)
    else:
        v = v_joint_w

    blocks, course_ys, actual_course_h = _block_grid(
        x0, y0, width, height, course_h, block_w, bond)

    # Determine arch-opening polygons (for skipping blocks that intersect them)
    arch_openings: list[Polygon] = []
    arch_ring_polys: list[Polygon] = []
    arch_springings_y = arch_springings_y or []
    arch_spans = arch_spans or []
    if variant == "arcuated":
        # Use the first springing line for all arches unless there are more
        for i, (cx_arch, sp) in enumerate(arch_spans):
            y_spr = (arch_springings_y[i] if i < len(arch_springings_y)
                     else (arch_springings_y[0] if arch_springings_y
                           else y0 + height * 0.5))
            arch_openings.append(_arch_opening_polygon(cx_arch, y_spr, sp))
            # Voussoir ring thickness is a small fraction of the arch radius
            # (Vignolan practice: ~1/8 to 1/10 of the radius). Previously this
            # was bound to course_h, which for facades with tall ground-floor
            # courses produced fans extending into the piano nobile.
            ring_th = (sp / 2.0) * 0.30
            arch_ring_polys.append(_arch_ring_polygon(
                cx_arch, y_spr, sp, ring_thickness=ring_th))

    arch_union = None
    if arch_openings:
        from shapely.ops import unary_union
        arch_union = unary_union(arch_openings + arch_ring_polys)

    # --- Filter blocks that intersect an arch opening or ring (arcuated only)
    kept_blocks: list[tuple[float, float, float, float, int]] = []
    for (xx, yt, xxe, yb, row) in blocks:
        if arch_union is not None:
            rect = Polygon(_rectangle(xx, yt, xxe, yb))
            if rect.intersects(arch_union):
                # discard blocks that overlap the arch opening/ring
                inter = rect.intersection(arch_union)
                if inter.area > 0.15 * rect.area:
                    continue
        kept_blocks.append((xx, yt, xxe, yb, row))

    # --- Build block_rects
    if emit_blocks:
        block_rects: list[Polyline] = [
            _rectangle(xx, yt, xxe, yb) for (xx, yt, xxe, yb, _) in kept_blocks
        ]
    else:
        block_rects = []

    # --- Horizontal joints (every variant except banded-only behaves the same)
    joints: list[Polyline] = []
    joint_shadows: list[Shadow] = []

    for cy in course_ys[1:-1]:  # skip top and bottom outline edges
        # Clip horizontal joint to exclude ranges swallowed by arch openings
        segments: list[tuple[float, float]] = [(x0, x0 + width)]
        if arch_union is not None:
            new_segments: list[tuple[float, float]] = []
            for sx, ex in segments:
                # subtract x-intervals where horizontal line intersects arch_union
                # sample: find intervals within [sx, ex] that are outside arch_union
                sample_n = max(2, int((ex - sx) / 0.5))
                step = (ex - sx) / sample_n
                intervals: list[tuple[float, float]] = []
                cur_start: float | None = None
                for k in range(sample_n + 1):
                    xk = sx + k * step
                    p = (xk, cy)
                    from shapely.geometry import Point as ShpPoint
                    inside = arch_union.contains(ShpPoint(p))
                    if not inside and cur_start is None:
                        cur_start = xk
                    elif inside and cur_start is not None:
                        intervals.append((cur_start, xk - step))
                        cur_start = None
                if cur_start is not None:
                    intervals.append((cur_start, ex))
                new_segments.extend(intervals)
            segments = new_segments
        for sx, ex in segments:
            if ex - sx <= 1e-6:
                continue
            joints.append([(sx, cy), (ex, cy)])
            joint_shadows.append(Shadow(
                _horizontal_joint_shadow(sx, ex - sx, cy, v),
                angle_deg=10.0,
                density="medium"))

    # --- Vertical joints depending on variant
    include_v_grooves = variant in ("chamfered", "smooth", "rock_faced",
                                    "vermiculated", "arcuated")
    # 'banded' leaves vertical joints flush (no shadow, but still draw a faint
    # centerline so the block edges are visible).
    # When emit_blocks=False (horizontal-only banded), skip vertical joints
    # entirely — only string-coursing remains.
    vertical_joint_iter = kept_blocks if emit_blocks else []
    for (xx, yt, xxe, yb, row) in vertical_joint_iter:
        # right-edge vertical joint, unless it coincides with wall edge
        jx = xxe
        if jx < x0 + width - 1e-6 and jx > x0 + 1e-6:
            joints.append([(jx, yt), (jx, yb)])
            if include_v_grooves:
                joint_shadows.append(Shadow(
                    _vertical_joint_shadow(jx, yt, yb, v),
                    angle_deg=80.0,
                    density="medium"))
                # 'chamfered' gets shadow bands on BOTH sides of the joint
                # (a V-groove has two inward-inclined faces). Duplicate
                # slightly offset to the left so the resulting pair hatches
                # as two faces of the V.
                if variant == "chamfered":
                    joint_shadows.append(Shadow(
                        _vertical_joint_shadow(jx - v * 0.5, yt, yb, v * 0.5),
                        angle_deg=100.0,
                        density="light"))

    # --- Face carving (variant-specific)
    face_carving: list[Polyline] = []
    face_stipples: list[Point] = []

    if variant == "vermiculated":
        for i, (xx, yt, xxe, yb, _) in enumerate(kept_blocks):
            worms = _vermiculated_face(xx, yt, xxe, yb,
                                       rng=random.Random(seed + i))
            face_carving.extend(worms)
    elif variant == "rock_faced":
        for i, (xx, yt, xxe, yb, _) in enumerate(kept_blocks):
            pts = _rock_faced_stipples(xx, yt, xxe, yb, seed=seed + i)
            face_stipples.extend(pts)

    # --- Arcuated: build voussoirs
    arch_voussoirs: list[Polyline] = []
    if variant == "arcuated":
        for i, (cx_arch, sp) in enumerate(arch_spans):
            y_spr = (arch_springings_y[i] if i < len(arch_springings_y)
                     else (arch_springings_y[0] if arch_springings_y
                           else y0 + height * 0.5))
            # Voussoir depth is a small fraction of the arch radius
            # (Vignolan practice: ~1/8 to 1/10 of the radius). This keeps
            # the ring tight around the arch instead of fanning up into
            # the story above.
            ring_th = (sp / 2.0) * 0.30
            arch_voussoirs.extend(_semicircular_voussoirs(
                cx_arch, y_spr, sp,
                ring_thickness=ring_th,
                n_voussoirs=11))

    outline = _rectangle(x0, y0, x0 + width, y0 + height)

    return {
        "outline": outline,
        "joints": joints,
        "joint_shadows": joint_shadows,
        "block_rects": block_rects,
        "face_carving": face_carving,
        "face_stipples": face_stipples,
        "arch_voussoirs": arch_voussoirs,
    }


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

def _smoke() -> None:
    variants: list[Variant] = ["banded", "chamfered", "smooth", "rock_faced",
                               "vermiculated", "arcuated"]
    print(f"{'variant':<14}  blocks  joints  shadows  carving  stipples  voussoirs")
    print("-" * 70)
    for v in variants:
        kwargs: dict = {}
        if v == "arcuated":
            kwargs["arch_springings_y"] = [60.0]
            kwargs["arch_spans"] = [(100.0, 60.0)]
        r = wall(0, 0, 200, 120, course_h=20, block_w=30, variant=v, **kwargs)
        print(f"{v:<14}  {len(r['block_rects']):>6}  "
              f"{len(r['joints']):>6}  "
              f"{len(r['joint_shadows']):>7}  "
              f"{len(r['face_carving']):>7}  "
              f"{len(r['face_stipples']):>8}  "
              f"{len(r['arch_voussoirs']):>9}")


if __name__ == "__main__":
    _smoke()
