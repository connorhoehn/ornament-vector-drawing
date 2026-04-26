"""Classical window treatments for facade elevations.

Period-standard window compositions: architrave surround, sill on corbels,
decorative hood (cornice, triangular pediment, segmental pediment), optional
keystone. Coordinate convention follows the rest of the package: y increases
downward (SVG). "Top" means smaller y; "below" means larger y.

All dimensions in millimeters.
"""
from __future__ import annotations

import math
from typing import Optional

from shapely.geometry import Polygon

from .elements import Shadow
from .geometry import Point, Polyline, arc, rect_corners


def _closed_rect(x: float, y: float, w: float, h: float) -> Polyline:
    return rect_corners(x, y, w, h)


def _architrave(x: float, y_top: float, w: float, h: float,
                arch_w: float) -> tuple[list[Polyline], list[Shadow]]:
    """3-fascia molded frame around the opening.

    Draws outer rectangle, inner rectangle (the opening edge), and two
    intermediate fasciae (progressively inset). Also returns thin shadows
    along the bottom of each fascia step.
    """
    polylines: list[Polyline] = []
    shadows: list[Shadow] = []

    # Outer = opening expanded by arch_w on every side.
    ox0 = x - arch_w
    oy0 = y_top - arch_w
    ow = w + 2 * arch_w
    oh = h + 2 * arch_w
    polylines.append(_closed_rect(ox0, oy0, ow, oh))

    # 2 intermediate fascia rectangles, stepping inward.
    # Each step: offset inward by (arch_w / 3), so fasciae sit at 1/3 and 2/3.
    step = arch_w / 3.0
    for k in (1, 2):
        dx = step * k
        polylines.append(_closed_rect(x - arch_w + dx, y_top - arch_w + dx,
                                      w + 2 * (arch_w - dx),
                                      h + 2 * (arch_w - dx)))

    # Inner rect (opening boundary). The caller also returns an "opening" key
    # but we include the inner architrave rect here too, so the architrave
    # list is self-contained as a drawn frame.
    polylines.append(_closed_rect(x, y_top, w, h))

    # Shadow along the bottom of each horizontal fascia step — a thin band
    # sitting on top of the step just below the architrave edge.
    # Fascia step bottoms are at:
    #   y = y_top + h + arch_w - dx  (outer side, below the opening)
    # Light from upper-left -> cast below each outward step.
    band = arch_w * 0.12
    for k in (0, 1, 2):
        dx = step * k
        y_band_top = y_top + h + arch_w - dx - band
        x_left = x - arch_w + dx
        x_right = x + w + arch_w - dx
        shadows.append(Shadow(Polygon([
            (x_left, y_band_top),
            (x_right, y_band_top),
            (x_right, y_band_top + band),
            (x_left, y_band_top + band),
        ]), angle_deg=15.0, density="light"))

    return polylines, shadows


def _sill(x: float, y_top: float, w: float, h: float,
          sill_h: float, sill_proj: float,
          arch_w: float) -> tuple[list[Polyline], list[Shadow]]:
    """Projecting sill block below the opening, seated on two small corbels."""
    polylines: list[Polyline] = []
    shadows: list[Shadow] = []

    # Sill top is flush with the bottom of the architrave (y_top + h + arch_w).
    sill_top_y = y_top + h + arch_w
    sill_x0 = x - sill_proj
    sill_x1 = x + w + sill_proj
    sill_w = sill_x1 - sill_x0

    # Main sill slab
    polylines.append(_closed_rect(sill_x0, sill_top_y, sill_w, sill_h))

    # Small top nosing rule a quarter way down — reads as a drip edge.
    nosing_y = sill_top_y + sill_h * 0.3
    polylines.append([(sill_x0, nosing_y), (sill_x1, nosing_y)])

    # Cavetto (quarter-round concave) transitions on the outside ends —
    # small arcs that tuck the sill back toward the architrave line.
    cav_r = min(sill_proj, sill_h) * 0.6
    if cav_r > 1e-6:
        # Left cavetto: arc center at (sill_x0, sill_top_y + sill_h + cav_r),
        # sweeping a quarter from (sill_x0, sill_top_y + sill_h) curving
        # outward-downward. We draw the decorative arc below the sill.
        left_cav = arc(sill_x0 + cav_r, sill_top_y + sill_h,
                       cav_r, math.pi, 1.5 * math.pi, steps=16)
        right_cav = arc(sill_x1 - cav_r, sill_top_y + sill_h,
                        cav_r, 1.5 * math.pi, 2.0 * math.pi, steps=16)
        polylines.append(left_cav)
        polylines.append(right_cav)

    # Two small corbel blocks under the sill, aligned with the outer edges
    # of the opening (not the sill's own outer edge).
    corbel_w = arch_w * 0.9
    corbel_h = sill_h * 1.2
    corbel_top_y = sill_top_y + sill_h
    # Left corbel centered on the opening's left edge
    lc_x = x - corbel_w / 2
    rc_x = x + w - corbel_w / 2
    # Taper: bottom slightly narrower than top (draw as trapezoid).
    taper = corbel_w * 0.25
    for cx0 in (lc_x, rc_x):
        polylines.append([
            (cx0, corbel_top_y),
            (cx0 + corbel_w, corbel_top_y),
            (cx0 + corbel_w - taper / 2, corbel_top_y + corbel_h),
            (cx0 + taper / 2, corbel_top_y + corbel_h),
            (cx0, corbel_top_y),
        ])

    # Underside shadow of the sill slab — between the two corbels.
    under = Polygon([
        (sill_x0, sill_top_y + sill_h),
        (sill_x1, sill_top_y + sill_h),
        (sill_x1, sill_top_y + sill_h + sill_h * 0.25),
        (sill_x0, sill_top_y + sill_h + sill_h * 0.25),
    ])
    shadows.append(Shadow(under, angle_deg=15.0, density="dark"))

    return polylines, shadows


def _cornice_hood(x: float, y_top: float, w: float, arch_w: float
                  ) -> tuple[list[Polyline], list[Shadow], float, float, float]:
    """Flat cornice band above the architrave.

    Returns (polylines, shadows, cornice_left_x, cornice_right_x,
    cornice_top_y) — callers (triangular, segmental) may sit on the cornice's
    top edge.
    """
    polylines: list[Polyline] = []
    shadows: list[Shadow] = []

    cornice_h = arch_w
    cornice_bot_y = y_top - arch_w              # sits on top of the architrave
    cornice_top_y = cornice_bot_y - cornice_h
    # Project ~0.4 * arch_w beyond the architrave outer edge on each side.
    proj = arch_w * 0.4
    cx0 = x - arch_w - proj
    cx1 = x + w + arch_w + proj
    cornice_w = cx1 - cx0

    polylines.append(_closed_rect(cx0, cornice_top_y, cornice_w, cornice_h))

    # Small cyma recta rule — a single horizontal line 35% down the band,
    # mimicking the ogee profile edge.
    rule_y = cornice_top_y + cornice_h * 0.35
    polylines.append([(cx0, rule_y), (cx1, rule_y)])

    # A second fainter rule near the bottom, for the fillet above the soffit.
    rule2_y = cornice_top_y + cornice_h * 0.80
    polylines.append([(cx0, rule2_y), (cx1, rule2_y)])

    # Soffit shadow along the underside of the cornice, between architrave and
    # cornice projection.
    soffit = Polygon([
        (cx0, cornice_bot_y),
        (cx1, cornice_bot_y),
        (x + w + arch_w, cornice_bot_y + cornice_h * 0.18),
        (x - arch_w, cornice_bot_y + cornice_h * 0.18),
    ])
    shadows.append(Shadow(soffit, angle_deg=10.0, density="dark"))

    return polylines, shadows, cx0, cx1, cornice_top_y


def _triangular_hood(x: float, y_top: float, w: float, arch_w: float
                     ) -> tuple[list[Polyline], list[Shadow]]:
    """Cornice + small triangular pediment, 14 degree slope."""
    polylines: list[Polyline] = []
    shadows: list[Shadow] = []

    corn_poly, corn_shadows, cx0, cx1, cornice_top_y = _cornice_hood(
        x, y_top, w, arch_w)
    polylines.extend(corn_poly)
    shadows.extend(corn_shadows)

    # Pediment sits on top of the cornice.
    span = cx1 - cx0
    slope = math.tan(math.radians(14.0))
    apex_x = (cx0 + cx1) / 2.0
    apex_y = cornice_top_y - (span / 2.0) * slope
    base_y = cornice_top_y

    # Outer triangle (closed)
    polylines.append([
        (cx0, base_y),
        (apex_x, apex_y),
        (cx1, base_y),
        (cx0, base_y),
    ])
    # Inner (tympanum) — inset along the rake edges.
    inset = arch_w * 0.35
    dx_edge = inset / math.cos(math.radians(14.0))
    polylines.append([
        (cx0 + dx_edge, base_y - inset),
        (apex_x, apex_y + dx_edge),
        (cx1 - dx_edge, base_y - inset),
        (cx0 + dx_edge, base_y - inset),
    ])

    # Shadow on the right-hand interior slope (light from upper left).
    shadows.append(Shadow(Polygon([
        (apex_x, apex_y + dx_edge),
        (cx1 - dx_edge, base_y - inset),
        (apex_x, base_y - inset),
    ]), angle_deg=50.0, density="light"))

    return polylines, shadows


def _segmental_hood(x: float, y_top: float, w: float, arch_w: float
                    ) -> tuple[list[Polyline], list[Shadow]]:
    """Cornice + shallow segmental arch hood (rise ~ span / 10)."""
    polylines: list[Polyline] = []
    shadows: list[Shadow] = []

    corn_poly, corn_shadows, cx0, cx1, cornice_top_y = _cornice_hood(
        x, y_top, w, arch_w)
    polylines.extend(corn_poly)
    shadows.extend(corn_shadows)

    span = cx1 - cx0
    rise = span / 10.0
    base_y = cornice_top_y
    # Segmental arc parameters: chord = span, rise = rise.
    # r = (chord^2 / (8 * rise)) + (rise / 2)
    r = (span * span) / (8.0 * rise) + rise / 2.0
    # Center is directly below the midpoint of the chord by (r - rise).
    # In SVG (y down), "above the base line" = smaller y. The arc opens
    # downward (toward larger y on the base), so the center is below the
    # apex and on the base-side at y = base_y + (r - rise).
    cx_c = (cx0 + cx1) / 2.0
    cy_c = base_y + (r - rise)
    # Half-angle from the center to the springer points.
    half_ang = math.asin((span / 2.0) / r)
    # Angles: measuring from +x axis, the springers are at
    # angle = pi +/- half_ang relative to center (they are above the center).
    # Since y-down: a point above center has y < cy_c, so sin(theta) < 0 when
    # theta is in (-pi, 0). Use theta from (-pi + half_ang) sweeping to
    # (-half_ang)? Simpler: parameterize directly.
    # Outer arc (extrados): offset outward by arch_w * 0.5.
    outer_r = r + arch_w * 0.5
    # We want the arc that passes through (cx0, base_y), (cx_c, base_y-rise),
    # (cx1, base_y). Angle at (cx0, base_y) from center (cx_c, cy_c):
    #   dx = cx0 - cx_c = -span/2;  dy = base_y - cy_c = -(r - rise)
    #   theta = atan2(dy, dx)
    a_left = math.atan2(base_y - cy_c, cx0 - cx_c)
    a_right = math.atan2(base_y - cy_c, cx1 - cx_c)
    # atan2 returns in (-pi, pi]; left is in (-pi, -pi/2), right in (-pi/2, 0).
    # Sweep from a_left to a_right going through the top (negative y side).
    intrados = arc(cx_c, cy_c, r, a_left, a_right, steps=48)
    polylines.append(intrados)

    # Outer arc (extrados) — same center, larger radius, ends land on the
    # cornice top line at extended x.
    a_left_o = math.atan2(base_y - cy_c, cx0 - cx_c)
    a_right_o = math.atan2(base_y - cy_c, cx1 - cx_c)
    extrados = arc(cx_c, cy_c, outer_r, a_left_o, a_right_o, steps=48)
    polylines.append(extrados)

    # Vertical end caps connecting intrados and extrados at the springers.
    polylines.append([intrados[0], extrados[0]])
    polylines.append([intrados[-1], extrados[-1]])

    # Shadow under the arch (between intrados and the cornice top line).
    # Use a thin band approximation hugging the intrados.
    shadow_poly_pts = list(intrados) + [(cx1, base_y), (cx0, base_y)]
    try:
        shadow_poly = Polygon(shadow_poly_pts)
        if shadow_poly.is_valid and shadow_poly.area > 0:
            shadows.append(Shadow(shadow_poly, angle_deg=45.0, density="light"))
    except Exception:
        pass

    return polylines, shadows


def _keystone(x: float, y_top: float, w: float, arch_w: float) -> Polyline:
    """Small trapezoidal keystone centered on the top of the architrave.

    Width = arch_w, height = arch_w * 1.5, bottom slightly narrower than top
    (an inverted wedge so the wider face reads upward — classical keystone).
    """
    ks_w_top = arch_w * 1.2
    ks_w_bot = arch_w * 0.8
    ks_h = arch_w * 1.5
    cx = x + w / 2.0
    # The keystone bottom sits at the opening top; it extends upward into
    # the architrave (y decreasing). Architrave outer top = y_top - arch_w.
    # Place keystone bottom at y_top (flush with opening top) and top at
    # y_top - ks_h, so it pierces through the architrave.
    y_bot = y_top
    y_topk = y_top - ks_h
    return [
        (cx - ks_w_bot / 2, y_bot),
        (cx + ks_w_bot / 2, y_bot),
        (cx + ks_w_top / 2, y_topk),
        (cx - ks_w_top / 2, y_topk),
        (cx - ks_w_bot / 2, y_bot),
    ]


def _brackets(x: float, y_top: float, w: float, arch_w: float
              ) -> tuple[list[Polyline], list[Shadow]]:
    """Ancones (S-scroll consoles) flanking the opening below the hood.

    v1: simple tapered rectangles. They sit at the top of the architrave
    (just below where the hood starts) on the outside edges of the surround.
    """
    polylines: list[Polyline] = []
    shadows: list[Shadow] = []

    br_w = arch_w * 0.9
    br_h = arch_w * 1.6
    taper = br_w * 0.25

    # Brackets are placed just outboard of the architrave on both sides,
    # with their top aligned to the top of the architrave (y_top - arch_w),
    # so the cornice hood rests on them.
    br_top_y = y_top - arch_w
    br_bot_y = br_top_y + br_h

    # Left bracket
    lx_outer = x - arch_w - br_w * 0.1  # slight outboard offset for shadow line
    lx_inner = lx_outer + br_w
    polylines.append([
        (lx_outer, br_top_y),
        (lx_inner, br_top_y),
        (lx_inner - taper, br_bot_y),
        (lx_outer + taper, br_bot_y),
        (lx_outer, br_top_y),
    ])

    # Right bracket (mirror)
    rx_outer = x + w + arch_w + br_w * 0.1
    rx_inner = rx_outer - br_w
    polylines.append([
        (rx_inner, br_top_y),
        (rx_outer, br_top_y),
        (rx_outer - taper, br_bot_y),
        (rx_inner + taper, br_bot_y),
        (rx_inner, br_top_y),
    ])

    # A small shadow on the inboard face of each bracket (light upper-left).
    # Right bracket: inboard face is on the LEFT of the bracket — shaded.
    # Left bracket: outboard face is in shadow only weakly; skip for v1.
    shadows.append(Shadow(Polygon([
        (rx_inner, br_top_y),
        (rx_inner + br_w * 0.2, br_top_y),
        (rx_inner + taper + br_w * 0.2, br_bot_y),
        (rx_inner + taper, br_bot_y),
    ]), angle_deg=70.0, density="medium"))

    return polylines, shadows


def window_opening(x: float, y_top: float, w: float, h: float,
                   architrave_w_frac: float = 1 / 6,
                   sill_height_frac: float = 1 / 10,
                   sill_projection_frac: float = 0.15,
                   hood: str = "none",
                   keystone: bool = False) -> dict:
    """A full window elevation.

    See module docstring. Returns a dict with keys:
      opening, architrave, sill, hood, brackets, keystone, shadows,
      overall_bbox.
    """
    if hood not in ("none", "cornice", "triangular", "segmental"):
        raise ValueError(f"unknown hood variant: {hood!r}")

    arch_w = architrave_w_frac * w
    sill_h = sill_height_frac * w
    sill_proj = sill_projection_frac * w

    # Opening: the plain glazed rectangle.
    opening: Polyline = _closed_rect(x, y_top, w, h)

    # Architrave surround
    architrave_polys, arch_shadows = _architrave(x, y_top, w, h, arch_w)

    # Sill + corbels
    sill_polys, sill_shadows = _sill(x, y_top, w, h, sill_h, sill_proj, arch_w)

    # Hood
    hood_polys: list[Polyline] = []
    hood_shadows: list[Shadow] = []
    if hood == "cornice":
        hp, hs, _cx0, _cx1, _ct = _cornice_hood(x, y_top, w, arch_w)
        hood_polys.extend(hp)
        hood_shadows.extend(hs)
    elif hood == "triangular":
        hp, hs = _triangular_hood(x, y_top, w, arch_w)
        hood_polys.extend(hp)
        hood_shadows.extend(hs)
    elif hood == "segmental":
        hp, hs = _segmental_hood(x, y_top, w, arch_w)
        hood_polys.extend(hp)
        hood_shadows.extend(hs)
    # "none" -> empty

    # Brackets (ancones) when a hood exists
    brackets_polys: list[Polyline] = []
    bracket_shadows: list[Shadow] = []
    if hood != "none":
        brackets_polys, bracket_shadows = _brackets(x, y_top, w, arch_w)

    # Keystone
    keystone_poly: Optional[Polyline] = None
    if keystone:
        keystone_poly = _keystone(x, y_top, w, arch_w)

    # Combined shadows
    shadows: list[Shadow] = []
    shadows.extend(arch_shadows)
    shadows.extend(sill_shadows)
    shadows.extend(hood_shadows)
    shadows.extend(bracket_shadows)

    # Overall bbox — scan every polyline + keystone.
    xs: list[float] = []
    ys: list[float] = []

    def _collect(poly: Polyline) -> None:
        for px, py in poly:
            xs.append(px)
            ys.append(py)

    _collect(opening)
    for p in architrave_polys:
        _collect(p)
    for p in sill_polys:
        _collect(p)
    for p in hood_polys:
        _collect(p)
    for p in brackets_polys:
        _collect(p)
    if keystone_poly is not None:
        _collect(keystone_poly)

    overall_bbox = (min(xs), min(ys), max(xs), max(ys))

    return {
        "opening": opening,
        "architrave": architrave_polys,
        "sill": sill_polys,
        "hood": hood_polys,
        "brackets": brackets_polys,
        "keystone": keystone_poly,
        "shadows": shadows,
        "overall_bbox": overall_bbox,
    }


def _smoke_test() -> None:
    variants = ["none", "cornice", "triangular", "segmental"]
    for v in variants:
        out = window_opening(x=0.0, y_top=0.0, w=40.0, h=70.0,
                             hood=v, keystone=True)
        bbox = out["overall_bbox"]
        counts = {
            "opening": 1 if out["opening"] else 0,
            "architrave": len(out["architrave"]),
            "sill": len(out["sill"]),
            "hood": len(out["hood"]),
            "brackets": len(out["brackets"]),
            "keystone": 1 if out["keystone"] is not None else 0,
            "shadows": len(out["shadows"]),
        }
        print(f"hood={v!r}")
        print(f"  bbox = ({bbox[0]:.2f}, {bbox[1]:.2f}, "
              f"{bbox[2]:.2f}, {bbox[3]:.2f})")
        print(f"  counts = {counts}")


if __name__ == "__main__":
    _smoke_test()
