"""Parallel / cross / contour-following hatching clipped to shapely polygons.

All inputs are shapely Polygon or MultiPolygon in the same mm coordinate system
as the rest of the pipeline. Output is a list of polylines ready for Page.polyline().
"""
from __future__ import annotations

import math
from typing import Sequence

from shapely.geometry import LineString, MultiLineString, Polygon, MultiPolygon
from shapely.affinity import rotate as shp_rotate
from shapely.ops import unary_union

from .geometry import Point, Polyline


def _to_polygon(region) -> MultiPolygon | Polygon:
    if isinstance(region, (Polygon, MultiPolygon)):
        return region
    # assume polyline (closed)
    return Polygon(region)


def parallel_hatch(region, angle_deg: float = 45.0, spacing: float = 0.45,
                   margin: float = 0.0) -> list[Polyline]:
    """Fill region with parallel lines at angle_deg, `spacing` mm apart.

    angle_deg is measured from horizontal, CCW.
    """
    poly = _to_polygon(region)
    if poly.is_empty:
        return []

    # Rotate region so hatch lines are horizontal, generate horizontals, rotate back.
    cx, cy = poly.centroid.x, poly.centroid.y
    rotated = shp_rotate(poly, -angle_deg, origin=(cx, cy))
    minx, miny, maxx, maxy = rotated.bounds
    minx -= margin; maxx += margin
    miny -= margin; maxy += margin

    lines: list[LineString] = []
    y = miny
    while y <= maxy:
        lines.append(LineString([(minx, y), (maxx, y)]))
        y += spacing

    clipped: list[Polyline] = []
    for ln in lines:
        inter = ln.intersection(rotated)
        if inter.is_empty:
            continue
        if isinstance(inter, LineString):
            segs = [inter]
        elif isinstance(inter, MultiLineString):
            segs = list(inter.geoms)
        else:
            continue
        for s in segs:
            # rotate each segment back
            back = shp_rotate(s, angle_deg, origin=(cx, cy))
            clipped.append([(x, y) for x, y in back.coords])
    return clipped


def cross_hatch(region, angle_deg: float = 45.0, spacing: float = 0.5) -> list[Polyline]:
    return (parallel_hatch(region, angle_deg, spacing)
            + parallel_hatch(region, angle_deg + 90.0, spacing))


def contour_hatch(region, spacing: float = 0.45, steps: int = 20) -> list[Polyline]:
    """Hatch by successive inward buffers — lines follow the boundary."""
    poly = _to_polygon(region)
    out: list[Polyline] = []
    current = poly
    for i in range(steps):
        current = current.buffer(-spacing * (1 if i else 0.5), join_style=2)
        if current.is_empty:
            break
        if isinstance(current, MultiPolygon):
            geoms = list(current.geoms)
        else:
            geoms = [current]
        for g in geoms:
            if g.is_empty:
                continue
            out.append([(x, y) for x, y in g.exterior.coords])
            for hole in g.interiors:
                out.append([(x, y) for x, y in hole.coords])
    return out


def shade_wedge(region, angle_deg: float = 45.0, spacing_near: float = 0.35,
                spacing_far: float = 1.2, gradient_axis_deg: float | None = None) -> list[Polyline]:
    """Variable-spacing parallel hatch. Lines are denser on one side of the
    region to simulate a tonal gradient (shadow falloff).

    gradient_axis_deg: the direction along which density increases. Defaults to
    angle_deg + 90 (perpendicular to hatch direction).
    """
    poly = _to_polygon(region)
    if poly.is_empty:
        return []
    if gradient_axis_deg is None:
        gradient_axis_deg = angle_deg + 90.0

    cx, cy = poly.centroid.x, poly.centroid.y
    rotated = shp_rotate(poly, -angle_deg, origin=(cx, cy))
    minx, miny, maxx, maxy = rotated.bounds
    span = maxy - miny

    # Figure out which end is "near" by comparing gradient_axis direction to
    # hatch direction — after rotation, hatches are horizontal, so the gradient
    # axis relative to horizontal is (gradient_axis_deg - angle_deg).
    gd = math.radians(gradient_axis_deg - angle_deg)
    # If gradient points mostly along +y (rotated), near=top; else near=bottom
    direction_sign = math.sin(gd)

    lines: list[LineString] = []
    y = miny
    # progressively interpolated spacing
    # Use a cumulative approach: step size depends on current normalized position
    while y <= maxy:
        t = (y - miny) / span if span > 0 else 0.5
        if direction_sign < 0:
            t = 1.0 - t
        step = spacing_near + (spacing_far - spacing_near) * t
        lines.append(LineString([(minx, y), (maxx, y)]))
        y += step

    clipped: list[Polyline] = []
    for ln in lines:
        inter = ln.intersection(rotated)
        if inter.is_empty:
            continue
        if isinstance(inter, LineString):
            segs = [inter]
        elif isinstance(inter, MultiLineString):
            segs = list(inter.geoms)
        else:
            continue
        for s in segs:
            back = shp_rotate(s, angle_deg, origin=(cx, cy))
            clipped.append([(x, y) for x, y in back.coords])
    return clipped
