"""Jittered stippling inside a shapely region, optionally with a density map.

Used for soft tonal areas (sky, background washes) where parallel hatching
would read as too mechanical.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
from shapely.geometry import Point as ShpPoint, Polygon, MultiPolygon

from .geometry import Point


def stipple(region, density: float = 2.0, jitter: float = 0.3,
            seed: int = 0) -> list[Point]:
    """Uniformly stipple `region` at roughly `density` dots per mm^2."""
    if not isinstance(region, (Polygon, MultiPolygon)):
        region = Polygon(region)
    minx, miny, maxx, maxy = region.bounds
    grid = 1.0 / np.sqrt(density)
    rng = np.random.default_rng(seed)
    pts: list[Point] = []
    y = miny
    while y <= maxy:
        x = minx
        while x <= maxx:
            jx = rng.uniform(-jitter, jitter) * grid
            jy = rng.uniform(-jitter, jitter) * grid
            p = (x + jx, y + jy)
            if region.contains(ShpPoint(p)):
                pts.append(p)
            x += grid
        y += grid
    return pts


def stipple_weighted(region, density_fn: Callable[[float, float], float],
                     max_density: float = 4.0, jitter: float = 0.3,
                     seed: int = 0) -> list[Point]:
    """Density varies per-point. density_fn(x, y) returns [0, 1]."""
    if not isinstance(region, (Polygon, MultiPolygon)):
        region = Polygon(region)
    minx, miny, maxx, maxy = region.bounds
    grid = 1.0 / np.sqrt(max_density)
    rng = np.random.default_rng(seed)
    pts: list[Point] = []
    y = miny
    while y <= maxy:
        x = minx
        while x <= maxx:
            jx = rng.uniform(-jitter, jitter) * grid
            jy = rng.uniform(-jitter, jitter) * grid
            p = (x + jx, y + jy)
            if region.contains(ShpPoint(p)) and rng.random() < density_fn(p[0], p[1]):
                pts.append(p)
            x += grid
        y += grid
    return pts
