"""Column flutes that follow the shaft's entasis.

Elevation-view arrises (flute edges) for classical column shafts. The shaft is
modeled with a simple 2-segment entasis: cylindrical for the lower fraction,
then a linear taper from r_lower to r_upper at the top.
"""
from __future__ import annotations

import math

from engraving.geometry import Polyline


def _radius_at(y: float, y_bot: float, y_top: float,
               r_lower: float, r_upper: float,
               entasis_break: float) -> float:
    # y-axis points DOWN; y_top < y_bot. The cylindrical zone is adjacent to
    # y_bot, taper begins at y_shaft_break and ends at y_top.
    y_shaft_break = y_bot + (y_top - y_bot) * entasis_break
    if y >= y_shaft_break:
        return r_lower
    span = y_top - y_shaft_break
    if span == 0:
        return r_upper
    t = (y - y_shaft_break) / span
    return r_lower + (r_upper - r_lower) * t


def flutes(cx: float, y_bot: float, y_top: float,
           r_lower: float, r_upper: float,
           flute_count: int, with_fillet: bool,
           entasis_break: float = 1 / 3) -> list[Polyline]:
    """Return polylines for the visible arrises (flute-edges) across the shaft
    in elevation. Each polyline is a vertical line following the shaft taper.

    - cx: shaft centerline x
    - y_bot: bottom of fluted region (NOT the base — the top of the apophyge)
    - y_top: top of fluted region (NOT the cap — the astragal bottom)
    - flute_count: total flutes around the circumference (Doric 20, Ionic/Corinth 24)
    - with_fillet: Doric has no fillet (arrises are sharp), Ionic/Corinth have fillets
    - entasis_break: fraction of shaft height from bottom where taper begins
    """
    del with_fillet  # consumed by fillet_strips; present here for API parity

    visible = flute_count // 2
    n_arrises = visible + 1
    n_steps = 12

    polylines: list[Polyline] = []
    for i in range(n_arrises):
        theta = -math.pi / 2 + math.pi * (i / visible)
        cos_theta = math.cos(theta)
        poly: Polyline = []
        for step in range(n_steps):
            t = step / (n_steps - 1)
            y = y_bot + (y_top - y_bot) * t
            r_at_y = _radius_at(y, y_bot, y_top, r_lower, r_upper, entasis_break)
            x = cx + r_at_y * cos_theta
            poly.append((x, y))
        polylines.append(poly)
    return polylines


def fillet_strips(cx: float, y_bot: float, y_top: float,
                  r_lower: float, r_upper: float,
                  flute_count: int,
                  entasis_break: float = 1 / 3) -> list[Polyline]:
    """For Ionic/Corinthian: return pairs of lines flanking each arris
    representing the fillet between flutes. Fillet width ≈ 1/3 of flute width."""
    visible = flute_count // 2
    n_steps = 12

    # Fillet width as a fraction of flute pitch; flute pitch is 2π r / flute_count,
    # so fillet half-width in angle is (fillet_frac * pitch) / (2 r) applied as
    # a small angular offset around each arris's theta. Using 1/3 fillet width.
    fillet_frac = 1.0 / 3.0
    half_angle = (fillet_frac * (2 * math.pi / flute_count)) / 2.0

    strips: list[Polyline] = []
    for i in range(visible + 1):
        theta = -math.pi / 2 + math.pi * (i / visible)
        # Skip silhouette arrises: a fillet outside the shaft silhouette would
        # cross the outline and has no visible width in elevation.
        if i == 0 or i == visible:
            continue
        for side in (-1, 1):
            theta_s = theta + side * half_angle
            cos_theta = math.cos(theta_s)
            poly: Polyline = []
            for step in range(n_steps):
                t = step / (n_steps - 1)
                y = y_bot + (y_top - y_bot) * t
                r_at_y = _radius_at(y, y_bot, y_top, r_lower, r_upper, entasis_break)
                x = cx + r_at_y * cos_theta
                poly.append((x, y))
            strips.append(poly)
    return strips


if __name__ == "__main__":
    from engraving import canon

    order = canon.Ionic(D=20.0)
    cx = 0.0
    y_bot = 0.0
    y_top = -order.shaft_h  # y points down, so top of shaft is negative
    r_lower = order.lower_diam / 2
    r_upper = order.upper_diam / 2

    polys = flutes(cx, y_bot, y_top, r_lower, r_upper,
                   flute_count=order.flute_count, with_fillet=True)

    xs = [x for p in polys for x, _ in p]
    ys = [y for p in polys for _, y in p]
    bbox = (min(xs), min(ys), max(xs), max(ys))
    print(f"polylines: {len(polys)}")
    print(f"bbox (x_min, y_min, x_max, y_max): {bbox}")

    strips = fillet_strips(cx, y_bot, y_top, r_lower, r_upper,
                           flute_count=order.flute_count)
    print(f"fillet strips: {len(strips)}")
