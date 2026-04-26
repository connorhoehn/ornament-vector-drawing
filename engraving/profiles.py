"""Classical moldings as parametric 2D profiles (side section).

Each profile is a function that returns a polyline traced from the top-inward
corner outward. Profiles start at (0, 0) at the upper attach point and advance
downward (positive y) and outward (positive x). Compose by translating and
concatenating.

All dimensions in mm.
"""
from __future__ import annotations

import math
from typing import Sequence

from .geometry import Point, Polyline, arc, cubic_bezier, translate_path


def fillet(h: float, x_offset: float = 0.0, y0: float = 0.0) -> Polyline:
    """Plain vertical band of height h. Acts as a spacer between moldings."""
    return [(x_offset, y0), (x_offset, y0 + h)]


def listel(w: float, h: float, x0: float = 0.0, y0: float = 0.0) -> Polyline:
    """Listel (fillet/plinth) — a square projection of width w, height h."""
    return [
        (x0, y0),
        (x0 + w, y0),
        (x0 + w, y0 + h),
        (x0, y0 + h),
    ]


def ovolo(h: float, projection: float, x0: float = 0.0, y0: float = 0.0,
          steps: int = 24) -> Polyline:
    """Ovolo (quarter round, convex). Height h, projecting by `projection`."""
    # quarter arc from (x0, y0) down-right to (x0+projection, y0+h)
    cx = x0
    cy = y0 + h
    return arc(cx, cy, max(h, projection), -math.pi / 2, 0.0, steps=steps) \
        if abs(h - projection) < 1e-9 else _squashed_quarter(x0, y0, projection, h, steps)


def cavetto(h: float, projection: float, x0: float = 0.0, y0: float = 0.0,
            steps: int = 24) -> Polyline:
    """Cavetto (concave quarter). Recedes into the wall as it descends."""
    # concave quarter: centre at the outer-top corner
    cx = x0 + projection
    cy = y0
    return arc(cx, cy, max(h, projection), math.pi, math.pi / 2, steps=steps) \
        if abs(h - projection) < 1e-9 else _squashed_concave(x0, y0, projection, h, steps)


def _squashed_quarter(x0: float, y0: float, proj: float, h: float, steps: int) -> Polyline:
    """Ovolo as an ellipse quarter when projection ≠ height."""
    pts: list[Point] = []
    for i in range(steps):
        t = -math.pi / 2 + (math.pi / 2) * (i / (steps - 1))
        pts.append((x0 + proj * (1 + math.cos(math.pi + t)),
                    y0 + h + h * math.sin(t)))
    return pts


def _squashed_concave(x0: float, y0: float, proj: float, h: float, steps: int) -> Polyline:
    """Cavetto as an ellipse quarter when projection ≠ height."""
    pts: list[Point] = []
    for i in range(steps):
        t = math.pi + (math.pi / 2) * (i / (steps - 1))
        pts.append((x0 + proj + proj * math.cos(t),
                    y0 + h * (1 + math.sin(t))))
    return pts


def torus(r: float, x0: float = 0.0, y0: float = 0.0, steps: int = 36) -> Polyline:
    """Torus (half-circle cushion). Height 2r, projects by 2r."""
    return arc(x0, y0 + r, r, -math.pi / 2, math.pi / 2, steps=steps)


def astragal(r: float, x0: float = 0.0, y0: float = 0.0, steps: int = 24) -> Polyline:
    """Astragal (small torus, a.k.a. bead in profile)."""
    return torus(r, x0, y0, steps)


def scotia(h: float, projection: float, x0: float = 0.0, y0: float = 0.0,
           steps: int = 48) -> Polyline:
    """Scotia — compound concave, deeper than cavetto. Two arcs of unequal radii."""
    # Upper shallow arc (larger radius), lower deep arc (smaller) — classical split
    h1 = h * 0.4
    h2 = h - h1
    r1 = projection * 0.55
    r2 = projection * 0.95
    # first arc: from (x0, y0) inward to the deepest point
    c1 = (x0 + r1, y0)
    arc1 = arc(c1[0], c1[1], r1, math.pi, math.pi / 2, steps=steps // 2)
    deepest = arc1[-1]
    # second arc: from deepest point to (x0, y0+h) with smaller projection
    c2 = (x0 + r2, y0 + h)
    arc2 = arc(c2[0], c2[1], r2, -math.pi / 2, -math.pi, steps=steps // 2)
    # resample / splice: we need arc1 ending at deepest, arc2 starting near deepest
    return arc1 + arc2


def cyma_recta(h: float, projection: float, x0: float = 0.0, y0: float = 0.0) -> Polyline:
    """Cyma recta — concave above, convex below. S-curve outward at top."""
    p1 = (x0, y0)
    p2 = (x0, y0 + h * 0.25)
    p3 = (x0 + projection * 0.5, y0 + h * 0.5)
    p4 = (x0 + projection, y0 + h * 0.75)
    p5 = (x0 + projection, y0 + h)
    # Compose two cubic beziers for the S.
    upper = cubic_bezier(p1,
                         (x0, y0 + h * 0.35),
                         (x0 + projection * 0.15, y0 + h * 0.5),
                         p3, steps=20)
    lower = cubic_bezier(p3,
                         (x0 + projection * 0.85, y0 + h * 0.5),
                         (x0 + projection, y0 + h * 0.65),
                         p5, steps=20)
    return upper + lower[1:]


def cyma_reversa(h: float, projection: float, x0: float = 0.0, y0: float = 0.0) -> Polyline:
    """Cyma reversa — convex above, concave below. Opposite of cyma recta."""
    p1 = (x0, y0)
    p3 = (x0 + projection * 0.5, y0 + h * 0.5)
    p5 = (x0 + projection, y0 + h)
    upper = cubic_bezier(p1,
                         (x0 + projection * 0.15, y0),
                         (x0 + projection * 0.5, y0 + h * 0.15),
                         p3, steps=20)
    lower = cubic_bezier(p3,
                         (x0 + projection * 0.5, y0 + h * 0.85),
                         (x0 + projection, y0 + h),
                         p5, steps=20)
    return upper + lower[1:]


def dentil_strip(length: float, tooth_w: float, tooth_h: float, gap: float,
                 x0: float = 0.0, y0: float = 0.0) -> list[Polyline]:
    """Dentil course — a run of little rectangles along x.

    Returns a list of closed polylines, one per tooth, for easy fill/stroke.
    """
    polys: list[Polyline] = []
    stride = tooth_w + gap
    n = int((length + gap) // stride)
    total_w = n * stride - gap
    x_start = x0 + (length - total_w) / 2
    for i in range(n):
        xi = x_start + i * stride
        polys.append([
            (xi, y0),
            (xi + tooth_w, y0),
            (xi + tooth_w, y0 + tooth_h),
            (xi, y0 + tooth_h),
            (xi, y0),
        ])
    return polys


def bead_strip(length: float, bead_r: float, x0: float = 0.0, y0: float = 0.0) -> list[tuple[Point, float]]:
    """Bead-and-reel running strip (simplified: all beads). Returns (center, r) pairs."""
    out: list[tuple[Point, float]] = []
    stride = bead_r * 2.1
    n = int(length // stride)
    xs = x0 + (length - (n - 1) * stride) / 2
    for i in range(n):
        out.append(((xs + i * stride, y0), bead_r))
    return out


# --- composition utilities -----------------------------------------------

def stack_vertical(profiles: Sequence[Polyline], x0: float = 0.0, y0: float = 0.0) -> Polyline:
    """Stack profile polylines tail-to-head. Each profile's local origin is its
    attach point; we translate each so its first point sits where the previous
    ended. Returns the concatenated path."""
    out: list[Point] = []
    cursor = (x0, y0)
    for prof in profiles:
        if not prof:
            continue
        first = prof[0]
        dx = cursor[0] - first[0]
        dy = cursor[1] - first[1]
        translated = translate_path(prof, dx, dy)
        if out:
            out.extend(translated[1:])
        else:
            out.extend(translated)
        cursor = out[-1]
    return out


def extrude_profile(profile: Polyline, length: float, axis: str = "x") -> tuple[Polyline, Polyline]:
    """Given a 2D profile traced in side view, return the two horizontal lines that
    bound its extrusion along `axis` — useful for representing a horizontal
    cornice in elevation: profile becomes the side silhouette, and we also need
    the top/bottom edges running across the full length.

    Returns (top_edge, bottom_edge) polylines in 2D.
    """
    if not profile:
        return [], []
    if axis == "x":
        y_top = profile[0][1]
        y_bot = profile[-1][1]
        return ([(0.0, y_top), (length, y_top)],
                [(0.0, y_bot), (length, y_bot)])
    y_top = profile[0][0]
    y_bot = profile[-1][0]
    return ([(y_top, 0.0), (y_top, length)],
            [(y_bot, 0.0), (y_bot, length)])
