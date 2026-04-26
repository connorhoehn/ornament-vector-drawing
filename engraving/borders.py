"""Plate borders — compose running ornament along rectangular paths."""
from __future__ import annotations

from typing import Callable

from .geometry import Polyline
from .ornament import array_along_path


def rectangular_border(x0: float, y0: float, w: float, h: float,
                       unit: Callable[[float], list[Polyline]],
                       unit_size: float, unit_width: float | None = None,
                       corner_inset: float = 0.0) -> list[Polyline]:
    """Run a unit motif around a rectangle.

    corner_inset: motif is omitted from this many mm at each corner to leave
    room for a corner treatment.
    """
    inset = corner_inset
    top = [(x0 + inset, y0), (x0 + w - inset, y0)]
    right = [(x0 + w, y0 + inset), (x0 + w, y0 + h - inset)]
    bottom = [(x0 + w - inset, y0 + h), (x0 + inset, y0 + h)]
    left = [(x0, y0 + h - inset), (x0, y0 + inset)]

    out: list[Polyline] = []
    for seg in (top, right, bottom, left):
        out.extend(array_along_path(seg, unit, unit_size, unit_width=unit_width))
    return out


def corner_rosette(cx: float, cy: float, r: float) -> list[Polyline]:
    """Simple eight-petal rosette for inside a corner."""
    import math
    pts: list[Polyline] = []
    outer = []
    for i in range(48):
        t = 2 * math.pi * i / 48
        k = 0.7 + 0.3 * math.cos(8 * t)
        outer.append((cx + r * k * math.cos(t), cy + r * k * math.sin(t)))
    outer.append(outer[0])
    pts.append(outer)
    # inner circle
    inner = []
    for i in range(24):
        t = 2 * math.pi * i / 24
        inner.append((cx + r * 0.25 * math.cos(t), cy + r * 0.25 * math.sin(t)))
    inner.append(inner[0])
    pts.append(inner)
    return pts
