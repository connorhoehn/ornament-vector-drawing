"""Geometric primitives: points, transforms, curves, symmetry helpers.

All coordinates in millimeters. Y increases downward to match SVG convention —
every module follows this so there are no flips at the boundary.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

Point = tuple[float, float]
Polyline = list[Point]


@dataclass(frozen=True)
class Transform:
    """2D affine transform as a 3x3 matrix in homogeneous coords."""
    m: np.ndarray

    @staticmethod
    def identity() -> "Transform":
        return Transform(np.eye(3))

    @staticmethod
    def translate(dx: float, dy: float) -> "Transform":
        m = np.eye(3)
        m[0, 2] = dx
        m[1, 2] = dy
        return Transform(m)

    @staticmethod
    def scale(sx: float, sy: float | None = None) -> "Transform":
        if sy is None:
            sy = sx
        m = np.eye(3)
        m[0, 0] = sx
        m[1, 1] = sy
        return Transform(m)

    @staticmethod
    def rotate(radians: float, cx: float = 0.0, cy: float = 0.0) -> "Transform":
        c, s = math.cos(radians), math.sin(radians)
        m = np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]])
        if cx or cy:
            return Transform.translate(cx, cy) @ Transform(m) @ Transform.translate(-cx, -cy)
        return Transform(m)

    @staticmethod
    def mirror_x(x0: float = 0.0) -> "Transform":
        """Mirror across a vertical line x = x0."""
        m = np.array([[-1.0, 0.0, 2.0 * x0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])
        return Transform(m)

    @staticmethod
    def mirror_y(y0: float = 0.0) -> "Transform":
        """Mirror across a horizontal line y = y0."""
        m = np.array([[1.0, 0.0, 0.0], [0.0, -1.0, 2.0 * y0], [0.0, 0.0, 1.0]])
        return Transform(m)

    def __matmul__(self, other: "Transform") -> "Transform":
        return Transform(self.m @ other.m)

    def apply(self, pts: Iterable[Point]) -> Polyline:
        arr = np.asarray(list(pts), dtype=float)
        if arr.size == 0:
            return []
        hom = np.hstack([arr, np.ones((len(arr), 1))])
        out = (self.m @ hom.T).T
        return [(float(x), float(y)) for x, y, _ in out]


def cubic_bezier(p0: Point, p1: Point, p2: Point, p3: Point, steps: int = 32) -> Polyline:
    """Sample a cubic Bezier as a polyline."""
    t = np.linspace(0.0, 1.0, steps)
    omt = 1.0 - t
    b0 = omt ** 3
    b1 = 3 * omt ** 2 * t
    b2 = 3 * omt * t ** 2
    b3 = t ** 3
    xs = b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0]
    ys = b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1]
    return list(zip(xs.tolist(), ys.tolist()))


def quadratic_bezier(p0: Point, p1: Point, p2: Point, steps: int = 24) -> Polyline:
    t = np.linspace(0.0, 1.0, steps)
    omt = 1.0 - t
    xs = omt ** 2 * p0[0] + 2 * omt * t * p1[0] + t ** 2 * p2[0]
    ys = omt ** 2 * p0[1] + 2 * omt * t * p1[1] + t ** 2 * p2[1]
    return list(zip(xs.tolist(), ys.tolist()))


def arc(cx: float, cy: float, r: float, a0: float, a1: float, steps: int = 48) -> Polyline:
    """Circular arc from a0 to a1 (radians)."""
    ts = np.linspace(a0, a1, steps)
    return [(cx + r * math.cos(t), cy + r * math.sin(t)) for t in ts]


def log_spiral(cx: float, cy: float, a: float, b: float, t0: float, t1: float, steps: int = 200) -> Polyline:
    """Logarithmic spiral r = a * exp(b*t). Used for Baroque cartouche spines."""
    ts = np.linspace(t0, t1, steps)
    return [(cx + a * math.exp(b * t) * math.cos(t),
             cy + a * math.exp(b * t) * math.sin(t)) for t in ts]


def line(p0: Point, p1: Point, steps: int = 2) -> Polyline:
    xs = np.linspace(p0[0], p1[0], steps)
    ys = np.linspace(p0[1], p1[1], steps)
    return list(zip(xs.tolist(), ys.tolist()))


def mirror_path_x(pts: Sequence[Point], x0: float) -> Polyline:
    return [(2 * x0 - x, y) for x, y in pts]


def mirror_path_y(pts: Sequence[Point], y0: float) -> Polyline:
    return [(x, 2 * y0 - y) for x, y in pts]


def translate_path(pts: Sequence[Point], dx: float, dy: float) -> Polyline:
    return [(x + dx, y + dy) for x, y in pts]


def scale_path(pts: Sequence[Point], sx: float, sy: float | None = None,
               ox: float = 0.0, oy: float = 0.0) -> Polyline:
    if sy is None:
        sy = sx
    return [((x - ox) * sx + ox, (y - oy) * sy + oy) for x, y in pts]


def path_length(pts: Sequence[Point]) -> float:
    if len(pts) < 2:
        return 0.0
    total = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        total += math.hypot(x1 - x0, y1 - y0)
    return total


def resample_path(pts: Sequence[Point], spacing: float) -> Polyline:
    """Resample a polyline at uniform arc-length spacing."""
    if len(pts) < 2:
        return list(pts)
    arr = np.asarray(pts, dtype=float)
    seg = np.linalg.norm(np.diff(arr, axis=0), axis=1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    total = cum[-1]
    if total == 0:
        return [pts[0]]
    n = max(2, int(math.ceil(total / spacing)) + 1)
    s = np.linspace(0.0, total, n)
    xs = np.interp(s, cum, arr[:, 0])
    ys = np.interp(s, cum, arr[:, 1])
    return list(zip(xs.tolist(), ys.tolist()))


def rect_corners(x: float, y: float, w: float, h: float) -> Polyline:
    """Closed rectangle polyline."""
    return [(x, y), (x + w, y), (x + w, y + h), (x, y + h), (x, y)]
