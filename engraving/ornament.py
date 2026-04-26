"""Ornamental motifs that array along a path.

Each motif is a function unit(size) -> list[Polyline] returning the motif's
polylines in a local frame centered at (0,0) with +x = direction of travel.

`array_along_path` takes a path (polyline) and a unit function, resamples the
path at unit spacing, and places oriented copies of the unit along it.
"""
from __future__ import annotations

import math
from typing import Callable, Sequence

from .geometry import (Point, Polyline, arc, cubic_bezier, line, path_length,
                       quadratic_bezier, resample_path)


# --- unit motifs -------------------------------------------------------------

def egg_and_dart(size: float) -> list[Polyline]:
    """One bay of egg-and-dart. Width == 2*size."""
    w = 2 * size
    pts: list[Polyline] = []
    # Egg: pointed-oval outline
    egg_w = size * 0.90
    egg_h = size * 1.15
    egg = (
        quadratic_bezier((-egg_w / 2, 0), (-egg_w / 2, -egg_h * 0.55), (0, -egg_h * 0.5), steps=16)
        + quadratic_bezier((0, -egg_h * 0.5), (egg_w / 2, -egg_h * 0.55), (egg_w / 2, 0), steps=16)[1:]
        + quadratic_bezier((egg_w / 2, 0), (egg_w / 2 * 0.75, egg_h * 0.50), (0, egg_h * 0.60), steps=16)[1:]
        + quadratic_bezier((0, egg_h * 0.60), (-egg_w / 2 * 0.75, egg_h * 0.50), (-egg_w / 2, 0), steps=16)[1:]
    )
    pts.append(egg)
    # Containing husk/shell outside the egg
    husk_w = size * 1.05
    husk_h = size * 1.30
    husk_left = quadratic_bezier((-husk_w / 2, egg_h * 0.3),
                                 (-husk_w / 2, -husk_h * 0.45),
                                 (0, -husk_h * 0.55), steps=20)
    husk_right = quadratic_bezier((0, -husk_h * 0.55),
                                  (husk_w / 2, -husk_h * 0.45),
                                  (husk_w / 2, egg_h * 0.3), steps=20)
    pts.append(husk_left + husk_right[1:])
    # Dart in the gap to the right (half-dart; full dart forms with next bay's half)
    dart_x = size
    dart_top = -size * 0.5
    dart_bot = size * 0.55
    dart = [(dart_x, dart_top), (dart_x + size * 0.08, (dart_top + dart_bot) / 2),
            (dart_x, dart_bot)]
    pts.append(dart)
    return pts


def bead_and_reel(size: float) -> list[Polyline]:
    """One bead + one reel. Width ≈ 2.2 * size."""
    r = size * 0.45
    pts: list[Polyline] = []
    # Bead (circle) at x=0
    bead = arc(0.0, 0.0, r, 0.0, 2 * math.pi, steps=24)
    pts.append(bead)
    # Reel (two tangent discs) at x = 1.1 * size
    reel_cx = 1.1 * size
    reel_r = size * 0.3
    reel_a = arc(reel_cx - reel_r * 0.9, 0.0, reel_r, 0.0, 2 * math.pi, steps=20)
    reel_b = arc(reel_cx + reel_r * 0.9, 0.0, reel_r, 0.0, 2 * math.pi, steps=20)
    pts.append(reel_a)
    pts.append(reel_b)
    return pts


def guilloche(size: float) -> list[Polyline]:
    """One lobe of a two-strand guilloche. Width = 2*size, lobe radius = size/2."""
    r = size / 2
    cx1, cx2 = 0.0, size
    # Two interlocking arcs
    a = arc(cx1, 0.0, r, -math.pi / 2, math.pi / 2, steps=24)
    b = arc(cx2, 0.0, r, math.pi / 2, 3 * math.pi / 2, steps=24)
    return [a, b]


def leaf_tip(size: float) -> list[Polyline]:
    """Simple stylized leaf (pointed-oval) for running border use."""
    w = size * 0.8
    h = size * 1.3
    return [cubic_bezier((-w / 2, 0), (-w / 2, -h * 0.6), (w / 2, -h * 0.6), (w / 2, 0), steps=20)
            + cubic_bezier((w / 2, 0), (w / 2 * 0.8, h * 0.5), (-w / 2 * 0.8, h * 0.5),
                           (-w / 2, 0), steps=20)[1:]]


def wheat_ear(size: float) -> list[Polyline]:
    """Vertical stylized wheat ear, spindle-shaped with internal chevrons."""
    spindle = [cubic_bezier((0, -size), (size * 0.4, -size * 0.5), (size * 0.4, size * 0.5), (0, size), steps=18)
               + cubic_bezier((0, size), (-size * 0.4, size * 0.5), (-size * 0.4, -size * 0.5), (0, -size), steps=18)[1:]]
    # chevrons
    chev: list[Polyline] = []
    for t in (-0.6, -0.2, 0.2, 0.6):
        y = t * size
        chev.append([(-size * 0.25, y), (0, y + size * 0.05), (size * 0.25, y)])
    return spindle + chev


# --- array along path --------------------------------------------------------

def array_along_path(path: Sequence[Point], unit: Callable[[float], list[Polyline]],
                     unit_size: float, unit_width: float | None = None,
                     orient: bool = True) -> list[Polyline]:
    """Place a copy of unit(unit_size) along path at spacing `unit_width`.

    unit_width defaults to unit_size * 2.  Orientation: local +x aligned with
    path tangent when orient=True.
    """
    if unit_width is None:
        unit_width = unit_size * 2.0
    total = path_length(path)
    if total < unit_width:
        return []
    n = int(total // unit_width)
    # resample to 2*n+1 points to get stable tangents
    rs = resample_path(path, unit_width)
    out: list[Polyline] = []
    for i in range(min(n, len(rs) - 1)):
        p0 = rs[i]
        p1 = rs[i + 1]
        cx = (p0[0] + p1[0]) / 2
        cy = (p0[1] + p1[1]) / 2
        if orient:
            ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
        else:
            ang = 0.0
        cos_a, sin_a = math.cos(ang), math.sin(ang)
        for poly in unit(unit_size):
            rotated: Polyline = []
            for x, y in poly:
                rx = x * cos_a - y * sin_a + cx
                ry = x * sin_a + y * cos_a + cy
                rotated.append((rx, ry))
            out.append(rotated)
    return out
