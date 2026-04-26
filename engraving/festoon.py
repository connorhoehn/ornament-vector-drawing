"""Festoons, swags, garlands — drooping botanical ornaments.

A festoon hangs between two attachment points ("rosettes" at the top).
The spine is a parabolic or catenary curve drooping between them.
Along the spine, leaves / flowers / fruit are arrayed; the ends tie to
each attachment with small ribbon knots.

Construction:
    1. Spine curve: a cubic bezier from attach_left through a control
       midpoint pulled downward by ``droop`` to attach_right.  This gives
       a soft parabolic droop that reads as a hanging garland.
    2. Unit motif: depending on ``style``, a small acanthus leaf, a
       pomegranate/grape cluster, or a ribbon pleat.  Each motif is
       oriented along the spine tangent and placed at arc-length
       intervals.
    3. Terminals: a small ribbon knot at each attachment end ties the
       garland to its hanging point.

``swag`` is the simpler variant: just the spine (or a ribbon band with
oscillating amplitude) between the two points.
"""
from __future__ import annotations

import math
from typing import Literal

from .acanthus import acanthus_leaf
from .geometry import (Point, Polyline, arc, cubic_bezier,
                       mirror_path_x, path_length, resample_path,
                       translate_path)
from .schema import ElementResult


# ---------------------------------------------------------------------------
# Spine
# ---------------------------------------------------------------------------

def _spine_curve(attach_left: Point, attach_right: Point,
                 droop: float, steps: int = 96) -> Polyline:
    """Cubic-bezier drooping spine between two attachment points.

    Control points are pulled straight down by ~1.33 * droop so that the
    midpoint of the curve dips by approximately ``droop`` below the
    attachment line (cubic bezier midpoint sits at 3/4 of control offset).
    """
    lx, ly = attach_left
    rx, ry = attach_right
    # In SVG coords y grows downward, so "droop" adds to y.
    # Bezier midpoint for symmetric controls at height d is at 0.75 * d.
    ctrl_offset = droop / 0.75 if droop else 0.0
    # Control points sit at 1/3 and 2/3 along x, pulled down by ctrl_offset
    # from the CHORD line (so the curve droops uniformly regardless of
    # any slope between the two attachments).
    c1 = (lx + (rx - lx) / 3.0, ly + (ry - ly) / 3.0 + ctrl_offset)
    c2 = (lx + 2 * (rx - lx) / 3.0, ly + 2 * (ry - ly) / 3.0 + ctrl_offset)
    return cubic_bezier(attach_left, c1, c2, attach_right, steps=steps)


def _tangent_at(spine: list[Point], idx: int) -> tuple[float, float]:
    """Unit tangent at spine[idx] using central differences."""
    n = len(spine)
    if n < 2:
        return (1.0, 0.0)
    if idx <= 0:
        a, b = spine[0], spine[1]
    elif idx >= n - 1:
        a, b = spine[-2], spine[-1]
    else:
        a, b = spine[idx - 1], spine[idx + 1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1.0
    return (dx / L, dy / L)


def _rotate_pts(pts: list[Point], theta: float) -> list[Point]:
    c, s = math.cos(theta), math.sin(theta)
    return [(c * x - s * y, s * x + c * y) for x, y in pts]


# ---------------------------------------------------------------------------
# Motif units
# ---------------------------------------------------------------------------

def _leaf_unit(size: float) -> list[Polyline]:
    """Small acanthus leaflet for a leaf garland."""
    # A 3-lobe small acanthus; the rinceau variant gives a slimmer leaf.
    return acanthus_leaf(width=size * 0.9, height=size,
                         lobe_count=3, fingers_per_lobe=3,
                         turnover=0.3, variant="rinceau")


def _fruit_unit(size: float) -> list[Polyline]:
    """Stylized fruit/flower cluster — a central disc flanked by two berries.

    Pomegranate-like silhouette: a circle with a small "crown" at the
    bottom and two teardrop leaves flanking the top.
    """
    pts: list[Polyline] = []
    # Main fruit: circle
    main_r = size * 0.40
    main = arc(0.0, 0.0, main_r, 0.0, 2 * math.pi, steps=28)
    main.append(main[0])
    pts.append(main)
    # Crown: small star-burst at the bottom (local +y since y grows down)
    crown_y = main_r * 0.95
    crown: Polyline = []
    for k in range(5):
        t = -math.pi / 2 + (k / 4) * math.pi * 0.35
        r = main_r * 0.15
        crown.append((r * math.cos(t), crown_y + r * math.sin(t)))
    pts.append(crown)
    # Two side berries
    side_r = size * 0.18
    for sign in (-1, +1):
        cx = sign * main_r * 1.1
        cy = -main_r * 0.2
        b = arc(cx, cy, side_r, 0.0, 2 * math.pi, steps=18)
        b.append(b[0])
        pts.append(b)
    # A small leaf pair on top (pointing up in local frame = -y)
    leaf_h = size * 0.4
    leaf_w = size * 0.2
    left_leaf = [
        (-main_r * 0.3, -main_r * 0.9),
        (-main_r * 0.3 - leaf_w, -main_r * 0.9 - leaf_h * 0.5),
        (-main_r * 0.3, -main_r * 0.9 - leaf_h),
        (-main_r * 0.3 + leaf_w * 0.3, -main_r * 0.9 - leaf_h * 0.5),
        (-main_r * 0.3, -main_r * 0.9),
    ]
    right_leaf = [(-x, y) for x, y in left_leaf]
    pts.append(left_leaf)
    pts.append(right_leaf)
    return pts


def _ribbon_unit(size: float) -> list[Polyline]:
    """A single ribbon pleat — a shallow diagonal stripe."""
    # A diamond-ish pleat centered at origin; width = size, height = size*0.5.
    half_w = size * 0.5
    half_h = size * 0.25
    outline = [
        (-half_w, 0),
        (-half_w * 0.3, -half_h),
        (half_w * 0.3, -half_h),
        (half_w, 0),
        (half_w * 0.3, half_h),
        (-half_w * 0.3, half_h),
        (-half_w, 0),
    ]
    # A small inner fold line
    fold = [(-half_w * 0.3, -half_h * 0.6), (half_w * 0.3, half_h * 0.6)]
    return [outline, fold]


# ---------------------------------------------------------------------------
# Ribbon knot
# ---------------------------------------------------------------------------

def ribbon_knot(center: Point, size: float,
                loop_count: int = 2) -> list[Polyline]:
    """A tied-ribbon knot for attaching festoon ends.

    The knot is drawn as a small central oval (the "tie") with
    ``loop_count`` loops fanning out above and a pair of pendant tails
    falling below.
    """
    cx, cy = center
    polys: list[Polyline] = []

    # Central tie: small closed ellipse
    tie_w = size * 0.35
    tie_h = size * 0.22
    tie: Polyline = []
    for i in range(24):
        t = 2.0 * math.pi * i / 24
        tie.append((cx + tie_w / 2 * math.cos(t),
                    cy + tie_h / 2 * math.sin(t)))
    tie.append(tie[0])
    polys.append(tie)

    # Loops fanning out above (negative y in SVG = up).
    # Arranged symmetrically around the vertical axis.
    for k in range(loop_count):
        # Spacing angles symmetric about the vertical axis
        if loop_count == 1:
            angles = [-math.pi / 2]
        else:
            offset = (k - (loop_count - 1) / 2) * math.radians(50)
            angles = [-math.pi / 2 + offset]
        for ang in angles:
            # Loop center: offset from tie center along ang direction
            r_out = size * 0.55
            lcx = cx + r_out * 0.55 * math.cos(ang)
            lcy = cy + r_out * 0.55 * math.sin(ang)
            # Loop ellipse, rotated so major axis points along ang
            loop_pts_local: Polyline = []
            lw = size * 0.28
            lh = size * 0.14
            for i in range(24):
                t = 2.0 * math.pi * i / 24
                loop_pts_local.append((lw * math.cos(t), lh * math.sin(t)))
            loop_pts_local.append(loop_pts_local[0])
            # Rotate so the loop's major axis points along ang.
            rot_angle = ang + math.pi / 2  # local +x -> ang direction
            c, s = math.cos(rot_angle), math.sin(rot_angle)
            loop_pts = [(lcx + c * x - s * y, lcy + s * x + c * y)
                        for x, y in loop_pts_local]
            polys.append(loop_pts)

    # Pendant tails below the tie (positive y direction in SVG).
    tail_len = size * 0.7
    for sign in (-1, +1):
        tx_top = cx + sign * tie_w * 0.3
        ty_top = cy + tie_h * 0.4
        # S-curve tail
        tail = cubic_bezier(
            (tx_top, ty_top),
            (tx_top + sign * size * 0.15, ty_top + tail_len * 0.4),
            (tx_top - sign * size * 0.05, ty_top + tail_len * 0.75),
            (tx_top + sign * size * 0.25, ty_top + tail_len),
            steps=16,
        )
        polys.append(tail)

    return polys


# ---------------------------------------------------------------------------
# Festoon
# ---------------------------------------------------------------------------

def festoon(attach_left: Point, attach_right: Point, droop: float,
            style: Literal["leaf", "fruit", "ribbon"] = "leaf",
            element_count: int = 7) -> ElementResult:
    """Festoon hanging between two points.

    Parameters
    ----------
    attach_left, attach_right
        Attachment point coordinates ``(x, y)``.  The garland hangs
        between these; in SVG coords (y-down) they are typically at the
        same y but any orientation works.
    droop
        How far (in mm) the midpoint of the festoon falls below the
        straight line between the attachments.  Must be > 0 for a proper
        droop.
    style
        * ``"leaf"`` — acanthus garland (the Vitruvian default)
        * ``"fruit"`` — pomegranate/grape clusters with flanking berries
        * ``"ribbon"`` — repeating ribbon pleats (plain bunting)
    element_count
        Number of ornamental units to place along the festoon.  Odd
        counts give a unit exactly at the lowest point.

    Returns
    -------
    ElementResult with:
        kind = "festoon"
        polylines layers: ``spine``, ``elements``, ``knots``
        anchors: ``attach_left``, ``attach_right``, ``low_point``
        metadata: ``style``, ``element_count``, ``droop``
    """
    result = ElementResult(
        kind="festoon",
        polylines={"spine": [], "elements": [], "knots": []},
        metadata={"style": style, "element_count": element_count,
                  "droop": droop},
    )

    # --- Spine -----------------------------------------------------------
    spine = _spine_curve(attach_left, attach_right, droop, steps=128)
    result.polylines["spine"] = [spine]

    # Lowest point (maximum y in SVG coords) — used as an anchor.
    low_idx = max(range(len(spine)), key=lambda i: spine[i][1])
    low_pt = spine[low_idx]

    # --- Unit motif selection --------------------------------------------
    # Size of each unit is set so elements are spaced ~one-unit-width
    # apart along the spine.  Keep elements inside the spine so we trim
    # the outermost pair (those sit under the knots).
    total = path_length(spine)
    interior_count = max(1, element_count)
    # Leave margin for knots at each end.
    margin_frac = 0.12
    interior_start = total * margin_frac
    interior_end = total * (1.0 - margin_frac)
    interior_len = max(0.0, interior_end - interior_start)

    unit_size = interior_len / max(1, interior_count + 1)
    unit_size = max(unit_size, 1.0)

    # Resample the spine densely so we can locate arc-length stations.
    if total > 0:
        dense = resample_path(spine, max(total / 400.0, 0.25))
    else:
        dense = list(spine)

    def pt_at_s(s: float) -> tuple[Point, int]:
        """Return (point, index) at arc-length s (clamped to dense path)."""
        if not dense:
            return (attach_left, 0)
        cum = 0.0
        for i in range(1, len(dense)):
            seg = math.hypot(dense[i][0] - dense[i - 1][0],
                             dense[i][1] - dense[i - 1][1])
            if cum + seg >= s:
                # interpolate
                if seg == 0:
                    return (dense[i], i)
                frac = (s - cum) / seg
                x = dense[i - 1][0] + frac * (dense[i][0] - dense[i - 1][0])
                y = dense[i - 1][1] + frac * (dense[i][1] - dense[i - 1][1])
                return ((x, y), i)
            cum += seg
        return (dense[-1], len(dense) - 1)

    if style == "leaf":
        proto = _leaf_unit(unit_size)
    elif style == "fruit":
        proto = _fruit_unit(unit_size)
    elif style == "ribbon":
        proto = _ribbon_unit(unit_size)
    else:
        proto = _leaf_unit(unit_size)

    # --- Place units along the spine -------------------------------------
    elements_layer: list[Polyline] = []
    for k in range(interior_count):
        # Fractional position along interior range
        if interior_count == 1:
            s_frac = 0.5
        else:
            s_frac = (k + 0.5) / interior_count
        s = interior_start + s_frac * interior_len
        (px, py), idx = pt_at_s(s)
        tx, ty = _tangent_at(dense, idx)

        # Rotate: the unit's local "up" (-y) should point AWAY from the
        # spine's downward normal — i.e., leaves/fruit hang BELOW the
        # spine.  In SVG coords, tangent (tx, ty); downward normal is
        # (-ty, +tx) if tangent points right.  But we want the motif's
        # base (local +y) to point toward the spine's downward direction
        # so the motif hangs off the underside.
        # For a simple approach: rotate so local +x aligns with tangent,
        # then shift motif slightly below spine.
        theta = math.atan2(ty, tx)

        # Place the motif: rotate, then translate to station.  For
        # leaves/fruit, push the motif slightly below the spine so it
        # "hangs" rather than overlapping the line.
        push = unit_size * 0.45 if style in ("leaf", "fruit") else 0.0
        # Downward-of-spine direction in SVG coords: perpendicular to
        # tangent, pointing to the +y side.  Candidate normals:
        # n1 = (-ty, tx), n2 = (ty, -tx).  We want the one whose y > 0.
        if tx >= 0:
            nx, ny = -ty, tx
        else:
            nx, ny = ty, -tx
        if ny < 0:
            nx, ny = -nx, -ny
        ox = px + nx * push
        oy = py + ny * push

        for pl in proto:
            rot = _rotate_pts(list(pl), theta)
            placed = [(x + ox, y + oy) for x, y in rot]
            elements_layer.append(placed)

    result.polylines["elements"] = elements_layer

    # --- Knots at each end ----------------------------------------------
    knot_size = max(3.0, unit_size * 1.1)
    result.polylines["knots"] = (
        ribbon_knot(attach_left, knot_size, loop_count=2)
        + ribbon_knot(attach_right, knot_size, loop_count=2)
    )

    # --- Anchors --------------------------------------------------------
    result.add_anchor("attach_left", attach_left[0], attach_left[1], "attach")
    result.add_anchor("attach_right", attach_right[0], attach_right[1], "attach")
    result.add_anchor("low_point", low_pt[0], low_pt[1], "center")

    result.compute_bbox()
    return result


# ---------------------------------------------------------------------------
# Swag (plain drooping curve or ribbon)
# ---------------------------------------------------------------------------

def swag(attach_left: Point, attach_right: Point, droop: float,
         amplitude: float = 0.0) -> ElementResult:
    """Plain swag — a drooping curve (or ribbon band) between two points.

    Parameters
    ----------
    attach_left, attach_right
        Attachment points.
    droop
        Midpoint offset below the chord.
    amplitude
        If > 0, the swag is rendered as a ribbon band of this width with
        oscillating folds.  If 0 (default), the swag is a single spine
        curve plus a parallel lower band at a small fixed offset.

    Returns
    -------
    ElementResult with kind = "swag", polylines layers: ``spine``,
    ``band``, ``knots``, anchors: ``attach_left``, ``attach_right``,
    ``low_point``.
    """
    result = ElementResult(
        kind="swag",
        polylines={"spine": [], "band": [], "knots": []},
        metadata={"droop": droop, "amplitude": amplitude},
    )

    spine = _spine_curve(attach_left, attach_right, droop, steps=96)
    result.polylines["spine"] = [spine]

    # Lower band: either a fixed-offset ribbon or an oscillating band.
    if amplitude > 0:
        # Ribbon band: the spine is the top; the lower edge oscillates
        # with `amplitude` at about 1.5 * element_count folds across.
        total = path_length(spine)
        dense = resample_path(spine, max(total / 400.0, 0.25))
        freq = max(3.0, total / max(8.0, droop * 1.5))
        lower: Polyline = []
        cum = 0.0
        for i in range(len(dense)):
            if i > 0:
                cum += math.hypot(dense[i][0] - dense[i - 1][0],
                                  dense[i][1] - dense[i - 1][1])
            t = cum / total if total else 0.0
            tx, ty = _tangent_at(dense, i)
            # Downward normal in SVG
            if tx >= 0:
                nx, ny = -ty, tx
            else:
                nx, ny = ty, -tx
            if ny < 0:
                nx, ny = -nx, -ny
            off = amplitude * (0.6 + 0.4 * math.sin(t * math.pi * freq))
            lower.append((dense[i][0] + nx * off, dense[i][1] + ny * off))
        result.polylines["band"] = [lower]
    else:
        # Simple parallel band a small distance below
        offset = max(1.0, droop * 0.08)
        total = path_length(spine)
        dense = resample_path(spine, max(total / 300.0, 0.25))
        lower: Polyline = []
        for i, (px, py) in enumerate(dense):
            tx, ty = _tangent_at(dense, i)
            if tx >= 0:
                nx, ny = -ty, tx
            else:
                nx, ny = ty, -tx
            if ny < 0:
                nx, ny = -nx, -ny
            lower.append((px + nx * offset, py + ny * offset))
        result.polylines["band"] = [lower]

    # Knots at each end
    knot_size = max(3.0, droop * 0.18)
    result.polylines["knots"] = (
        ribbon_knot(attach_left, knot_size, loop_count=2)
        + ribbon_knot(attach_right, knot_size, loop_count=2)
    )

    low_idx = max(range(len(spine)), key=lambda i: spine[i][1])
    low_pt = spine[low_idx]

    result.add_anchor("attach_left", attach_left[0], attach_left[1], "attach")
    result.add_anchor("attach_right", attach_right[0], attach_right[1], "attach")
    result.add_anchor("low_point", low_pt[0], low_pt[1], "center")

    result.compute_bbox()
    return result


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import drawsvg as dw
    from engraving.preview import render_svg_to_png

    canvas_w, canvas_h = 360, 280
    d = dw.Drawing(canvas_w, canvas_h, origin=(0, 0))
    d.append(dw.Rectangle(0, 0, canvas_w, canvas_h, fill="white"))

    def _draw(polys_by_layer, stroke="black", stroke_width=0.3):
        for layer, lines in polys_by_layer.items():
            for pl in lines:
                if not pl:
                    continue
                d.append(dw.Lines(
                    *[c for pt in pl for c in pt],
                    close=False, fill='none',
                    stroke=stroke, stroke_width=stroke_width,
                ))

    # Row 1: three festoon styles
    for i, style in enumerate(["leaf", "fruit", "ribbon"]):
        ax, ay = 20 + i * 110, 50
        bx, by = ax + 100, ay
        f = festoon((ax, ay), (bx, by), droop=40, style=style,
                    element_count=7)
        _draw(f.polylines)

    # Row 2: swag variants (plain + ribbon)
    f_plain = swag((20, 170), (120, 170), droop=40, amplitude=0.0)
    _draw(f_plain.polylines)
    f_rib = swag((140, 170), (240, 170), droop=40, amplitude=6.0)
    _draw(f_rib.polylines)

    # Row 2 right: a short standalone ribbon knot
    for kn in ribbon_knot((290, 200), size=20, loop_count=2):
        d.append(dw.Lines(*[c for pt in kn for c in pt],
                          close=False, fill='none',
                          stroke='black', stroke_width=0.3))

    d.save_svg('/tmp/festoon_test.svg')
    render_svg_to_png('/tmp/festoon_test.svg',
                      '/tmp/festoon_test.png', dpi=200)
    print("wrote /tmp/festoon_test.svg and /tmp/festoon_test.png")
