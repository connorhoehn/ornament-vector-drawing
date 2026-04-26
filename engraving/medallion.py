"""Medallions — oval portrait frames with laurel wreath borders.

A medallion is an oval frame band (two concentric ovals) optionally
surrounded by a laurel wreath — a ring of leaf pairs radiating outward.
Below the medallion a draped ribbon tie may hang asymmetrically.

Construction:
    1. Outer oval (the frame edge).
    2. Inner oval (offset inward ~3mm to form the frame band).
    3. (optional) Laurel wreath: pairs of small leaves placed along the
       outer oval's circumference, each rotated so the leaf "grows"
       outward from the frame.
    4. (optional) Ribbon tie: a small bow at the top plus two pendant
       ribbons flowing asymmetrically to one side.
"""
from __future__ import annotations

import math
from typing import Literal

from .acanthus import acanthus_leaf
from .geometry import (Point, Polyline, arc, cubic_bezier)
from .schema import ElementResult


# ---------------------------------------------------------------------------
# Oval helpers
# ---------------------------------------------------------------------------

def _ellipse(cx: float, cy: float, rx: float, ry: float,
             steps: int = 96) -> Polyline:
    pts: Polyline = []
    for i in range(steps):
        t = 2.0 * math.pi * i / steps
        pts.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
    pts.append(pts[0])
    return pts


def _rotate_pts(pts: list[Point], theta: float,
                ox: float = 0.0, oy: float = 0.0) -> list[Point]:
    c, s = math.cos(theta), math.sin(theta)
    return [(ox + c * x - s * y, oy + s * x + c * y) for x, y in pts]


def _small_laurel_leaf(size: float) -> list[Polyline]:
    """Tiny 3-lobe laurel-style leaf, tip up (local frame).

    Uses the acanthus builder at small scale; the resulting silhouette
    reads as a stylised laurel leaf.
    """
    return acanthus_leaf(width=size * 0.7, height=size,
                         lobe_count=3, fingers_per_lobe=3,
                         turnover=0.2, variant="rinceau")


# ---------------------------------------------------------------------------
# Ribbon tie (bow + pendants)
# ---------------------------------------------------------------------------

def _ribbon_tie(cx: float, cy_top: float, width: float,
                height: float) -> list[Polyline]:
    """Asymmetric ribbon draped at the top of the medallion.

    ``cy_top`` is the y of the bow center; the pendants fall below and
    drift to one side to give the ribbon an asymmetric feel.
    """
    polys: list[Polyline] = []
    # Bow: two loops left+right of center
    loop_w = width * 0.18
    loop_h = height * 0.08
    # Left loop
    left_loop: Polyline = []
    for i in range(24):
        t = 2.0 * math.pi * i / 24
        left_loop.append((cx - loop_w * 0.8 + loop_w * math.cos(t),
                          cy_top + loop_h * math.sin(t)))
    left_loop.append(left_loop[0])
    polys.append(left_loop)
    # Right loop
    right_loop: Polyline = []
    for i in range(24):
        t = 2.0 * math.pi * i / 24
        right_loop.append((cx + loop_w * 0.8 + loop_w * math.cos(t),
                           cy_top + loop_h * math.sin(t)))
    right_loop.append(right_loop[0])
    polys.append(right_loop)
    # Central knot
    knot_w = width * 0.08
    knot_h = height * 0.05
    knot: Polyline = []
    for i in range(20):
        t = 2.0 * math.pi * i / 20
        knot.append((cx + knot_w * math.cos(t),
                     cy_top + knot_h * math.sin(t)))
    knot.append(knot[0])
    polys.append(knot)

    # Pendants: two flowing ribbons, one longer on the right (asymmetric).
    pendant_L = cubic_bezier(
        (cx - knot_w * 0.6, cy_top + knot_h * 0.8),
        (cx - width * 0.18, cy_top + height * 0.25),
        (cx - width * 0.08, cy_top + height * 0.35),
        (cx - width * 0.22, cy_top + height * 0.55),
        steps=24,
    )
    polys.append(pendant_L)
    pendant_L_edge = cubic_bezier(
        (cx - knot_w * 0.2, cy_top + knot_h * 0.8),
        (cx - width * 0.10, cy_top + height * 0.25),
        (cx + width * 0.00, cy_top + height * 0.35),
        (cx - width * 0.12, cy_top + height * 0.55),
        steps=24,
    )
    polys.append(pendant_L_edge)

    pendant_R = cubic_bezier(
        (cx + knot_w * 0.6, cy_top + knot_h * 0.8),
        (cx + width * 0.22, cy_top + height * 0.35),
        (cx + width * 0.28, cy_top + height * 0.55),
        (cx + width * 0.40, cy_top + height * 0.70),
        steps=24,
    )
    polys.append(pendant_R)
    pendant_R_edge = cubic_bezier(
        (cx + knot_w * 0.2, cy_top + knot_h * 0.8),
        (cx + width * 0.14, cy_top + height * 0.35),
        (cx + width * 0.20, cy_top + height * 0.55),
        (cx + width * 0.32, cy_top + height * 0.70),
        steps=24,
    )
    polys.append(pendant_R_edge)

    return polys


# ---------------------------------------------------------------------------
# Laurel wreath
# ---------------------------------------------------------------------------

def _laurel_wreath(cx: float, cy: float, rx: float, ry: float,
                   leaf_size: float, gap_top: float = 0.0) -> list[Polyline]:
    """Generate a ring of leaf pairs radiating outward from an oval.

    Parameters
    ----------
    cx, cy, rx, ry
        Oval center and semi-axes (outer oval of the medallion).
    leaf_size
        Length of each small leaf in mm.
    gap_top
        Angular gap at the top (in radians) to leave room for a bow/knot.
        If 0, leaves are uniformly distributed around the full circle.
    """
    polys: list[Polyline] = []
    # Circumference estimate (Ramanujan's approximation)
    h = ((rx - ry) / (rx + ry)) ** 2 if (rx + ry) > 0 else 0
    circ = math.pi * (rx + ry) * (1 + 3 * h / (10 + math.sqrt(4 - 3 * h)))
    # Spacing: leaves overlap slightly so wreath reads solid
    spacing = leaf_size * 0.55
    n_leaves = max(12, int(circ / spacing))

    # Sample the leaf once; we'll rotate per station.
    proto = _small_laurel_leaf(leaf_size)

    # Angular range
    if gap_top > 0:
        # Gap centered at top of oval (angle = -pi/2 in math coords,
        # which in SVG y-down coords is actually... we draw in SVG: the
        # top of the oval is at angle = 3*pi/2 (or -pi/2) in parametric
        # (cos, sin) notation, but since y increases DOWN in our SVG
        # space, the "top" of the oval (smaller y) corresponds to the
        # angle where sin(t) is negative — i.e. t = 3*pi/2 or -pi/2.
        top_angle = -math.pi / 2.0
        start_ang = top_angle + gap_top / 2
        end_ang = top_angle + 2 * math.pi - gap_top / 2
    else:
        start_ang = 0.0
        end_ang = 2 * math.pi

    for k in range(n_leaves):
        frac = k / n_leaves
        ang = start_ang + frac * (end_ang - start_ang)
        # Point on outer oval
        ox = cx + rx * math.cos(ang)
        oy = cy + ry * math.sin(ang)
        # Outward normal at this point of the ellipse (direction of grad):
        # normal = (cos(ang) / rx, sin(ang) / ry), normalized
        nx_raw = math.cos(ang) / rx if rx != 0 else 0
        ny_raw = math.sin(ang) / ry if ry != 0 else 0
        n_len = math.hypot(nx_raw, ny_raw) or 1.0
        nx, ny = nx_raw / n_len, ny_raw / n_len

        # Leaf's local +y axis points toward BASE (toward oval center);
        # local -y points toward TIP (outward, along normal).
        # Rotation: local -y -> (nx, ny); i.e. local +y -> (-nx, -ny).
        # Angle from (0, 1) (local +y) to (-nx, -ny).
        theta = math.atan2(-nx, -ny) - math.atan2(0, 1)

        # Slight tilt: alternate leaves tilt forward / back to simulate
        # the classical staggered laurel pattern.
        tilt = math.radians(14) * (1 if k % 2 == 0 else -1)
        theta += tilt

        # Place: the leaf's base (local (0, +h/2)) should sit ON the
        # oval at (ox, oy). After rotation by theta, that local point
        # maps to rot((0, h/2), theta). So translation is (ox, oy) - rot.
        h_local = leaf_size / 2.0
        rot_base = _rotate_pts([(0.0, h_local)], theta)[0]
        tdx = ox - rot_base[0]
        tdy = oy - rot_base[1]

        for pl in proto:
            rotated = _rotate_pts(list(pl), theta)
            placed = [(x + tdx, y + tdy) for x, y in rotated]
            polys.append(placed)

    return polys


# ---------------------------------------------------------------------------
# Top-level medallion
# ---------------------------------------------------------------------------

def medallion(cx: float, cy: float, width: float, height: float,
              with_wreath: bool = True,
              with_ribbon: bool = False) -> ElementResult:
    """Oval frame with optional laurel wreath and ribbon tie.

    Parameters
    ----------
    cx, cy, width, height
        Center and outer dimensions (frame envelope).  Wreath leaves
        project beyond this envelope.
    with_wreath
        Ring of laurel leaf pairs around the outer oval.
    with_ribbon
        Asymmetric ribbon tie draped over the top of the frame.

    Returns
    -------
    ElementResult with:
        kind = "medallion"
        polylines layers: ``outer``, ``inner``, ``wreath``, ``ribbon``
        anchors: ``center``, ``top``, ``bottom``, ``left``, ``right``
    """
    result = ElementResult(
        kind="medallion",
        polylines={"outer": [], "inner": [], "wreath": [], "ribbon": []},
        metadata={"width": width, "height": height,
                  "with_wreath": with_wreath,
                  "with_ribbon": with_ribbon},
    )

    rx_outer = width / 2.0
    ry_outer = height / 2.0
    # Frame band: 3mm inward, but scale with size for small medallions
    band = max(1.5, min(3.0, 0.05 * min(width, height)))
    rx_inner = max(0.5, rx_outer - band)
    ry_inner = max(0.5, ry_outer - band)

    outer = _ellipse(cx, cy, rx_outer, ry_outer)
    inner = _ellipse(cx, cy, rx_inner, ry_inner)
    result.polylines["outer"] = [outer]
    result.polylines["inner"] = [inner]

    if with_wreath:
        # Leaf size proportional to medallion's minor semi-axis
        leaf_size = min(rx_outer, ry_outer) * 0.25
        leaf_size = max(3.0, leaf_size)
        # When there's a ribbon, leave an angular gap at the top for the bow
        gap_top = math.radians(35) if with_ribbon else 0.0
        wreath = _laurel_wreath(cx, cy, rx_outer, ry_outer,
                                leaf_size=leaf_size, gap_top=gap_top)
        result.polylines["wreath"] = wreath

    if with_ribbon:
        ribbon = _ribbon_tie(cx, cy - ry_outer - band * 0.5,
                             width=width, height=height)
        result.polylines["ribbon"] = ribbon

    result.add_anchor("center", cx, cy, "center")
    result.add_anchor("top", cx, cy - ry_outer, "attach")
    result.add_anchor("bottom", cx, cy + ry_outer, "attach")
    result.add_anchor("left", cx - rx_outer, cy, "attach")
    result.add_anchor("right", cx + rx_outer, cy, "attach")

    result.compute_bbox()
    return result


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import drawsvg as dw
    from engraving.preview import render_svg_to_png

    canvas_w, canvas_h = 480, 260
    d = dw.Drawing(canvas_w, canvas_h, origin=(0, 0))
    d.append(dw.Rectangle(0, 0, canvas_w, canvas_h, fill="white"))

    configs = [
        ("plain", 80, 130, 80, 100, False, False),
        ("wreath", 200, 130, 80, 100, True, False),
        ("wreath+ribbon", 360, 130, 80, 100, True, True),
    ]
    for label, cx, cy, w, h, ww, wr in configs:
        m = medallion(cx=cx, cy=cy, width=w, height=h,
                      with_wreath=ww, with_ribbon=wr)
        for layer, lines in m.polylines.items():
            for pl in lines:
                if not pl:
                    continue
                d.append(dw.Lines(
                    *[c for pt in pl for c in pt],
                    close=False, fill='none',
                    stroke='black', stroke_width=0.3,
                ))
        d.append(dw.Text(label, font_size=7, x=cx - 25, y=250, fill='black'))

    d.save_svg('/tmp/medallion_test.svg')
    render_svg_to_png('/tmp/medallion_test.svg',
                      '/tmp/medallion_test.png', dpi=200)
    print("wrote /tmp/medallion_test.svg and /tmp/medallion_test.png")
