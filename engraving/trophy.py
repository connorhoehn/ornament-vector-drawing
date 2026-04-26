"""Trophies — symmetric piles of emblematic objects.

Variants:
  "martial" — shields, swords, helmets, standards
  "musical" — lyres, trumpets, scrolls
  "scientific" — compass, globes, books, papers
  "naval" — anchors, ropes, trident

Each trophy is bilaterally symmetric about a central vertical axis at
``cx``.  Stylized silhouettes are the correct idiom for classical
engraving — pile-of-objects compositions read by SHAPE, not surface
detail.  Objects are laid out on a notional "pile": central upright
object at the bottom, crossed pair behind it (extending outward and
upward), and crowning object at the top.
"""
from __future__ import annotations

import math
from typing import Literal

from .geometry import (Point, Polyline, arc, cubic_bezier, line,
                       mirror_path_x, rect_corners)
from .schema import ElementResult


# ---------------------------------------------------------------------------
# Primitive shape helpers
# ---------------------------------------------------------------------------

def _circle(cx: float, cy: float, r: float, steps: int = 32) -> Polyline:
    pts = arc(cx, cy, r, 0.0, 2.0 * math.pi, steps=steps)
    pts.append(pts[0])
    return pts


def _ellipse(cx: float, cy: float, rx: float, ry: float,
             steps: int = 40) -> Polyline:
    pts: Polyline = []
    for i in range(steps):
        t = 2.0 * math.pi * i / steps
        pts.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
    pts.append(pts[0])
    return pts


def _rotated_rect(cx: float, cy: float, w: float, h: float,
                  theta: float) -> Polyline:
    """Rectangle centered at (cx, cy), rotated by theta (rad)."""
    c, s = math.cos(theta), math.sin(theta)
    hw, hh = w / 2.0, h / 2.0
    corners = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh), (-hw, -hh)]
    return [(cx + c * x - s * y, cy + s * x + c * y) for x, y in corners]


def _sword(hilt: Point, tip: Point, blade_w: float) -> list[Polyline]:
    """Stylized sword: blade + crossguard + pommel."""
    hx, hy = hilt
    tx, ty = tip
    dx, dy = tx - hx, ty - hy
    L = math.hypot(dx, dy) or 1.0
    ux, uy = dx / L, dy / L
    # Perpendicular unit (right-hand side)
    px, py = -uy, ux

    polys: list[Polyline] = []

    # Blade: quadrilateral from hilt to tip, slightly tapered.
    blade_base_half = blade_w / 2.0
    blade_tip_half = blade_w * 0.2
    blade = [
        (hx + px * blade_base_half, hy + py * blade_base_half),
        (tx + px * blade_tip_half, ty + py * blade_tip_half),
        (tx, ty),
        (tx - px * blade_tip_half, ty - py * blade_tip_half),
        (hx - px * blade_base_half, hy - py * blade_base_half),
        (hx + px * blade_base_half, hy + py * blade_base_half),
    ]
    polys.append(blade)

    # Crossguard: short bar perpendicular to blade at the hilt.
    cross_half = blade_w * 2.0
    cross_thick = blade_w * 0.6
    cg_center = (hx - ux * cross_thick * 0.5, hy - uy * cross_thick * 0.5)
    cg: Polyline = []
    for sign_p in (1, -1):
        for sign_u in (-1, 1):
            cg.append((cg_center[0] + px * sign_p * cross_half
                       + ux * sign_u * cross_thick,
                       cg_center[1] + py * sign_p * cross_half
                       + uy * sign_u * cross_thick))
    # reorder into polygon: +p-u, +p+u, -p+u, -p-u, close.
    cg_order = [
        (cg_center[0] + px * cross_half - ux * cross_thick,
         cg_center[1] + py * cross_half - uy * cross_thick),
        (cg_center[0] + px * cross_half + ux * cross_thick,
         cg_center[1] + py * cross_half + uy * cross_thick),
        (cg_center[0] - px * cross_half + ux * cross_thick,
         cg_center[1] - py * cross_half + uy * cross_thick),
        (cg_center[0] - px * cross_half - ux * cross_thick,
         cg_center[1] - py * cross_half - uy * cross_thick),
    ]
    cg_order.append(cg_order[0])
    polys.append(cg_order)

    # Grip: short rectangle from crossguard to pommel (opposite of blade)
    grip_len = blade_w * 2.5
    grip_half = blade_w * 0.35
    g_base = (hx - ux * cross_thick, hy - uy * cross_thick)
    g_end = (g_base[0] - ux * grip_len, g_base[1] - uy * grip_len)
    grip = [
        (g_base[0] + px * grip_half, g_base[1] + py * grip_half),
        (g_end[0] + px * grip_half, g_end[1] + py * grip_half),
        (g_end[0] - px * grip_half, g_end[1] - py * grip_half),
        (g_base[0] - px * grip_half, g_base[1] - py * grip_half),
        (g_base[0] + px * grip_half, g_base[1] + py * grip_half),
    ]
    polys.append(grip)

    # Pommel: small circle at the end of the grip.
    polys.append(_circle(g_end[0], g_end[1], blade_w * 0.65, steps=18))

    return polys


def _shield(cx: float, cy: float, w: float, h: float) -> list[Polyline]:
    """Stylized heater-shield outline with an inner band."""
    # Heater-shape approximated by arcs: top is flat, sides curve in, base
    # comes to a point.
    top_y = cy - h / 2.0
    bot_y = cy + h / 2.0
    half_w = w / 2.0
    top_left = (cx - half_w, top_y)
    top_right = (cx + half_w, top_y)
    bottom = (cx, bot_y)
    # Left curve: from top_left down and inward to the bottom point
    left_curve = cubic_bezier(
        top_left,
        (cx - half_w, top_y + h * 0.55),
        (cx - half_w * 0.55, bot_y - h * 0.12),
        bottom, steps=24,
    )
    right_curve = cubic_bezier(
        top_right,
        (cx + half_w, top_y + h * 0.55),
        (cx + half_w * 0.55, bot_y - h * 0.12),
        bottom, steps=24,
    )
    # Build closed outline: top edge + right curve + (left curve reversed)
    outline: Polyline = [top_left, top_right]
    outline += right_curve[1:]
    outline += list(reversed(left_curve))[1:]
    # Close
    if outline[0] != outline[-1]:
        outline.append(outline[0])
    # Inner band: contract by 1.5mm using uniform per-point shrink toward
    # (cx, cy).
    inset = min(w, h) * 0.08
    inner: Polyline = []
    for x, y in outline:
        dx = x - cx
        dy = y - cy
        L = math.hypot(dx, dy) or 1.0
        inner.append((cx + dx * max(0.0, (L - inset)) / L,
                      cy + dy * max(0.0, (L - inset)) / L))
    return [outline, inner]


def _helmet(cx: float, cy: float, w: float, h: float) -> list[Polyline]:
    """Stylized classical helmet: domed cap + neck band + plume base."""
    polys: list[Polyline] = []
    # Cap: half-ellipse from (cx-w/2, cy+h*0.1) up to (cx+w/2, cy+h*0.1)
    cap_top_y = cy - h * 0.35
    cap_bot_y = cy + h * 0.10
    cap_rx = w / 2.0
    cap_ry = cap_bot_y - cap_top_y
    cap_center_y = cap_bot_y
    # Upper half of ellipse
    cap: Polyline = []
    for i in range(24):
        t = math.pi + math.pi * i / 23  # from pi (left) through -pi/2 (top) to 0 (right)
        cap.append((cx + cap_rx * math.cos(t),
                    cap_center_y + cap_ry * math.sin(t)))
    polys.append(cap)

    # Neck band: short rectangle below the cap
    band_h = h * 0.12
    band_y = cy + h * 0.10
    band = rect_corners(cx - w * 0.35, band_y, w * 0.7, band_h)
    polys.append(band)

    # Plume: a fluttering shape above the cap
    plume_w = w * 0.3
    plume_h = h * 0.5
    plume_base = (cx, cap_top_y)
    plume = cubic_bezier(
        plume_base,
        (cx + plume_w * 0.8, cap_top_y - plume_h * 0.5),
        (cx - plume_w * 0.8, cap_top_y - plume_h * 0.9),
        (cx + plume_w * 0.2, cap_top_y - plume_h),
        steps=24,
    )
    polys.append(plume)
    # Plume back stroke
    plume_back = cubic_bezier(
        plume_base,
        (cx - plume_w * 0.5, cap_top_y - plume_h * 0.4),
        (cx + plume_w * 0.3, cap_top_y - plume_h * 0.85),
        (cx - plume_w * 0.1, cap_top_y - plume_h * 0.95),
        steps=20,
    )
    polys.append(plume_back)
    return polys


def _lyre(cx: float, cy: float, w: float, h: float) -> list[Polyline]:
    """Stylized lyre: U-shaped frame + crossbar + strings."""
    polys: list[Polyline] = []
    # Two curved arms sweeping upward and outward
    base_y = cy + h / 2.0
    top_y = cy - h * 0.35
    arm_span = w * 0.9
    # Left arm: from (cx - w*0.1, base_y) up to (cx - arm_span/2, top_y)
    left_arm = cubic_bezier(
        (cx - w * 0.1, base_y),
        (cx - w * 0.4, base_y - h * 0.1),
        (cx - arm_span / 2.0 - w * 0.05, cy),
        (cx - arm_span / 2.0, top_y),
        steps=24,
    )
    right_arm = [(2 * cx - x, y) for x, y in left_arm]
    polys.append(left_arm)
    polys.append(right_arm)

    # Base: a body — small oval
    body = _ellipse(cx, base_y - h * 0.08, w * 0.25, h * 0.12)
    polys.append(body)

    # Crossbar at the top connecting the two arms
    crossbar = rect_corners(cx - arm_span / 2.0 - w * 0.05, top_y - h * 0.04,
                            arm_span + w * 0.1, h * 0.07)
    polys.append(crossbar)

    # Strings: vertical lines from crossbar down to body
    n_strings = 5
    for k in range(n_strings):
        frac = (k + 0.5) / n_strings
        x = cx - arm_span * 0.25 + arm_span * 0.5 * frac
        polys.append([(x, top_y + h * 0.02), (x, base_y - h * 0.12)])

    return polys


def _trumpet(pivot: Point, length: float, direction_angle: float,
             bell_r: float) -> list[Polyline]:
    """Stylized trumpet: narrow tube with a bell at one end."""
    px, py = pivot
    c, s = math.cos(direction_angle), math.sin(direction_angle)
    # Tube from pivot outward
    tube_w = bell_r * 0.35
    # Points in local coords: tube runs along +x for `length`, bell at +x end
    pts_local = [
        (0.0, -tube_w / 2),
        (length, -tube_w / 2),
        (length, -bell_r),
        (length + bell_r * 0.5, -bell_r),
        (length + bell_r * 0.5, bell_r),
        (length, bell_r),
        (length, tube_w / 2),
        (0.0, tube_w / 2),
        (0.0, -tube_w / 2),
    ]
    return [[(px + c * x - s * y, py + s * x + c * y) for x, y in pts_local]]


def _scroll_rolled(cx: float, cy: float, w: float, h: float) -> list[Polyline]:
    """Stylized rolled scroll: oblique rectangle with a spiral end."""
    polys: list[Polyline] = []
    # Main rectangle (tilted a little)
    theta = math.radians(-12)
    polys.append(_rotated_rect(cx, cy, w, h, theta))
    # Small spiral curl at each end (2 half-turns)
    for sign in (-1, +1):
        # End center in rotated frame: (sign * w/2, 0)
        c, s = math.cos(theta), math.sin(theta)
        ecx = cx + c * (sign * w / 2) - s * 0
        ecy = cy + s * (sign * w / 2) + c * 0
        r0 = h * 0.4
        curl: Polyline = []
        steps = 24
        for k in range(steps):
            t = (k / (steps - 1)) * math.pi * 1.5
            r = r0 * (1 - k / steps * 0.6)
            local_x = r * math.cos(t * sign) * sign
            local_y = r * math.sin(t * sign) - r0
            curl.append((ecx + c * local_x - s * local_y,
                         ecy + s * local_x + c * local_y))
        polys.append(curl)
    return polys


def _book(cx: float, cy: float, w: float, h: float) -> list[Polyline]:
    """Closed book seen from the side: rectangle with horizontal pages lines."""
    polys: list[Polyline] = []
    polys.append(rect_corners(cx - w / 2, cy - h / 2, w, h))
    # Page lines (top, middle, bottom hint)
    for frac in (0.25, 0.5, 0.75):
        y = cy - h / 2 + h * frac
        polys.append([(cx - w / 2 + w * 0.05, y),
                      (cx + w / 2 - w * 0.05, y)])
    return polys


def _compass(cx: float, cy: float, size: float) -> list[Polyline]:
    """Draftsman's compass: two legs joined at a pivot at the top."""
    polys: list[Polyline] = []
    hinge_y = cy - size * 0.45
    foot_y = cy + size * 0.45
    # Left + right leg as quadrilaterals (trapezoids)
    leg_thick_top = size * 0.06
    leg_thick_bot = size * 0.03
    leg_spread = size * 0.35
    for sign in (-1, +1):
        top_x = cx
        bot_x = cx + sign * leg_spread
        # Direction vector from top to bot
        dx = bot_x - top_x
        dy = foot_y - hinge_y
        L = math.hypot(dx, dy) or 1.0
        # Perpendicular
        px = -dy / L
        py = dx / L
        leg = [
            (top_x + px * leg_thick_top, hinge_y + py * leg_thick_top),
            (bot_x + px * leg_thick_bot, foot_y + py * leg_thick_bot),
            (bot_x - px * leg_thick_bot, foot_y - py * leg_thick_bot),
            (top_x - px * leg_thick_top, hinge_y - py * leg_thick_top),
        ]
        leg.append(leg[0])
        polys.append(leg)
    # Pivot disc at hinge
    polys.append(_circle(cx, hinge_y, size * 0.06, steps=18))
    return polys


def _globe(cx: float, cy: float, r: float) -> list[Polyline]:
    """Celestial globe: circle + equator + meridian + stand."""
    polys: list[Polyline] = []
    polys.append(_circle(cx, cy, r, steps=40))
    # Equator (horizontal ellipse — seen at slight tilt)
    polys.append(_ellipse(cx, cy, r * 0.95, r * 0.22))
    # Meridian (vertical ellipse)
    polys.append(_ellipse(cx, cy, r * 0.28, r * 0.95))
    # Stand: a U-arc cradling the globe + base
    arc_pts = arc(cx, cy, r * 1.15, math.pi * 0.1, math.pi * 0.9, steps=24)
    polys.append(arc_pts)
    # Base rectangle
    polys.append(rect_corners(cx - r * 0.4, cy + r * 1.15,
                              r * 0.8, r * 0.12))
    return polys


def _anchor(cx: float, cy: float, size: float) -> list[Polyline]:
    """Classical fouled anchor: shank, stock, crown with flukes."""
    polys: list[Polyline] = []
    # Shank: vertical rect
    shank_w = size * 0.08
    shank_h = size * 0.75
    top_y = cy - size * 0.45
    bot_y = top_y + shank_h
    polys.append(rect_corners(cx - shank_w / 2, top_y, shank_w, shank_h))
    # Ring at top
    polys.append(_circle(cx, top_y - size * 0.08, size * 0.08))
    # Stock: horizontal bar near top
    stock_w = size * 0.5
    stock_h = size * 0.06
    stock_y = top_y + size * 0.12
    polys.append(rect_corners(cx - stock_w / 2, stock_y, stock_w, stock_h))
    # Arms + flukes at bottom: two curved arms sweeping outward-upward
    for sign in (-1, +1):
        arm = cubic_bezier(
            (cx, bot_y - shank_h * 0.05),
            (cx + sign * size * 0.15, bot_y + size * 0.03),
            (cx + sign * size * 0.35, bot_y - size * 0.05),
            (cx + sign * size * 0.42, bot_y - size * 0.18),
            steps=16,
        )
        polys.append(arm)
        # Fluke: little triangle at arm tip
        tip = arm[-1]
        fluke = [
            (tip[0], tip[1]),
            (tip[0] + sign * size * 0.08, tip[1] + size * 0.08),
            (tip[0] - sign * size * 0.02, tip[1] + size * 0.12),
            (tip[0] - sign * size * 0.04, tip[1] + size * 0.02),
            (tip[0], tip[1]),
        ]
        polys.append(fluke)
    return polys


def _oar(hilt: Point, tip: Point, blade_w: float) -> list[Polyline]:
    """Stylized oar: handle + blade at tip."""
    hx, hy = hilt
    tx, ty = tip
    dx, dy = tx - hx, ty - hy
    L = math.hypot(dx, dy) or 1.0
    ux, uy = dx / L, dy / L
    px, py = -uy, ux
    polys: list[Polyline] = []
    # Shaft: thin rectangle
    shaft_half = blade_w * 0.15
    shaft = [
        (hx + px * shaft_half, hy + py * shaft_half),
        (tx + px * shaft_half, ty + py * shaft_half),
        (tx - px * shaft_half, ty - py * shaft_half),
        (hx - px * shaft_half, hy - py * shaft_half),
    ]
    shaft.append(shaft[0])
    polys.append(shaft)
    # Blade: oval at tip extending past the shaft end
    blade_center = (tx + ux * blade_w * 0.8, ty + uy * blade_w * 0.8)
    # Build ellipse aligned with (ux, uy)
    blade_poly: Polyline = []
    for i in range(24):
        t = 2.0 * math.pi * i / 24
        local_x = blade_w * 0.9 * math.cos(t)
        local_y = blade_w * 0.5 * math.sin(t)
        # Local axes: (ux, uy) is along blade long axis
        blade_poly.append((blade_center[0] + ux * local_x + px * local_y,
                           blade_center[1] + uy * local_x + py * local_y))
    blade_poly.append(blade_poly[0])
    polys.append(blade_poly)
    return polys


def _coiled_rope(cx: float, cy: float, r: float) -> list[Polyline]:
    """Coiled rope: concentric arcs."""
    polys: list[Polyline] = []
    # A spiral of 3 turns
    steps = 120
    spiral: Polyline = []
    for i in range(steps):
        t = (i / (steps - 1)) * math.pi * 6.0
        rad = r * (1 - 0.6 * (i / steps))
        spiral.append((cx + rad * math.cos(t), cy + rad * math.sin(t)))
    polys.append(spiral)
    # Outer loop closure
    polys.append(_circle(cx, cy, r, steps=32))
    return polys


# ---------------------------------------------------------------------------
# Compositions
# ---------------------------------------------------------------------------

def _martial(cx: float, cy: float, width: float,
             height: float) -> dict[str, list[Polyline]]:
    """Shield (center) + two crossed swords (behind) + helmet (top)."""
    layers: dict[str, list[Polyline]] = {
        "shield": [], "swords": [], "helmet": [],
    }
    # Helmet at top
    helm_w = width * 0.45
    helm_h = height * 0.30
    helm_cy = cy - height * 0.30
    layers["helmet"].extend(_helmet(cx, helm_cy, helm_w, helm_h))

    # Crossed swords behind shield: each sword goes from a pommel below
    # the helmet's neck out to a tip outside the shield's corner.
    hilt_y = cy - height * 0.10
    tip_y = cy + height * 0.42
    tip_x_offset = width * 0.5
    hilt_x_offset = width * 0.05
    # Right sword: hilt inside-left, tip outside-right below
    layers["swords"].extend(
        _sword(hilt=(cx - hilt_x_offset, hilt_y),
               tip=(cx + tip_x_offset, tip_y),
               blade_w=width * 0.04))
    layers["swords"].extend(
        _sword(hilt=(cx + hilt_x_offset, hilt_y),
               tip=(cx - tip_x_offset, tip_y),
               blade_w=width * 0.04))

    # Shield at center, overlapping the sword intersection
    shield_w = width * 0.55
    shield_h = height * 0.55
    layers["shield"].extend(_shield(cx, cy + height * 0.05, shield_w, shield_h))

    return layers


def _musical(cx: float, cy: float, width: float,
             height: float) -> dict[str, list[Polyline]]:
    """Lyre (center) + two trumpets (crossed behind) + scrolls (flanking)."""
    layers: dict[str, list[Polyline]] = {
        "lyre": [], "trumpets": [], "scrolls": [],
    }

    # Trumpets: crossed behind the lyre
    for sign in (-1, +1):
        pivot = (cx - sign * width * 0.05, cy + height * 0.20)
        ang = math.radians(-35) if sign == 1 else math.radians(180 + 35)
        layers["trumpets"].extend(
            _trumpet(pivot, length=width * 0.4,
                     direction_angle=ang, bell_r=height * 0.07))

    # Lyre (center, slightly elevated)
    lyre_w = width * 0.4
    lyre_h = height * 0.7
    layers["lyre"].extend(_lyre(cx, cy - height * 0.05, lyre_w, lyre_h))

    # Flanking scrolls: generate the RIGHT scroll and mirror for the LEFT
    # so the pair is bilaterally symmetric about cx regardless of the
    # asymmetric curl inside each individual scroll.
    s_cy = cy + height * 0.32
    right_scrolls = _scroll_rolled(cx + width * 0.35, s_cy,
                                    width * 0.22, height * 0.1)
    layers["scrolls"].extend(right_scrolls)
    # Mirror each polyline of the right scroll about cx
    for pl in right_scrolls:
        layers["scrolls"].append([(2 * cx - x, y) for x, y in pl])

    return layers


def _scientific(cx: float, cy: float, width: float,
                height: float) -> dict[str, list[Polyline]]:
    """Globe (top) + compass + stacked books (bottom)."""
    layers: dict[str, list[Polyline]] = {
        "globe": [], "compass": [], "books": [],
    }

    # Books stacked at bottom
    book_h = height * 0.10
    book_w_big = width * 0.55
    book_w_mid = width * 0.48
    book_w_top = width * 0.40
    base_y = cy + height * 0.45
    layers["books"].extend(_book(cx, base_y - book_h * 0.5,
                                 book_w_big, book_h))
    layers["books"].extend(_book(cx, base_y - book_h * 1.55,
                                 book_w_mid, book_h))
    layers["books"].extend(_book(cx, base_y - book_h * 2.55,
                                 book_w_top, book_h))
    top_of_books = base_y - book_h * 3.1

    # Compass behind the globe (legs cross)
    compass_size = height * 0.55
    layers["compass"].extend(
        _compass(cx, cy + height * 0.0, compass_size))

    # Globe at top
    globe_r = min(width, height) * 0.20
    globe_cy = top_of_books - globe_r * 2.1
    layers["globe"].extend(_globe(cx, globe_cy, globe_r))

    return layers


def _naval(cx: float, cy: float, width: float,
           height: float) -> dict[str, list[Polyline]]:
    """Anchor (center) + crossed oars (behind) + coiled rope (base)."""
    layers: dict[str, list[Polyline]] = {
        "anchor": [], "oars": [], "rope": [],
    }

    # Oars crossed behind the anchor
    for sign in (-1, +1):
        hilt = (cx - sign * width * 0.05, cy + height * 0.35)
        tip = (cx + sign * width * 0.48, cy - height * 0.35)
        layers["oars"].extend(_oar(hilt, tip, blade_w=width * 0.06))

    # Anchor in the foreground
    layers["anchor"].extend(_anchor(cx, cy, min(width, height) * 0.9))

    # Coiled rope at base
    rope_r = min(width, height) * 0.15
    layers["rope"].extend(_coiled_rope(cx, cy + height * 0.42, rope_r))

    return layers


# ---------------------------------------------------------------------------
# Top-level trophy
# ---------------------------------------------------------------------------

def trophy(cx: float, cy: float, width: float, height: float,
           style: Literal["martial", "musical",
                          "scientific", "naval"] = "martial"
           ) -> ElementResult:
    """Bilaterally symmetric trophy composition centered at (cx, cy)."""
    result = ElementResult(
        kind="trophy",
        polylines={},
        metadata={"style": style, "width": width, "height": height,
                  "cx": cx, "cy": cy},
    )

    if style == "martial":
        layers = _martial(cx, cy, width, height)
    elif style == "musical":
        layers = _musical(cx, cy, width, height)
    elif style == "scientific":
        layers = _scientific(cx, cy, width, height)
    elif style == "naval":
        layers = _naval(cx, cy, width, height)
    else:
        layers = _martial(cx, cy, width, height)

    for layer, lines in layers.items():
        result.add_polylines(layer, lines)

    # Anchors
    result.add_anchor("center", cx, cy, "center")
    result.add_anchor("axis_top", cx, cy - height / 2.0, "axis")
    result.add_anchor("axis_bottom", cx, cy + height / 2.0, "axis")
    result.add_anchor("left", cx - width / 2.0, cy, "corner")
    result.add_anchor("right", cx + width / 2.0, cy, "corner")

    result.compute_bbox()
    return result


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import drawsvg as dw
    from engraving.preview import render_svg_to_png

    canvas_w, canvas_h = 520, 280
    d = dw.Drawing(canvas_w, canvas_h, origin=(0, 0))
    d.append(dw.Rectangle(0, 0, canvas_w, canvas_h, fill="white"))

    styles = ["martial", "musical", "scientific", "naval"]
    for i, style in enumerate(styles):
        cx = 70 + i * 120
        cy = 140
        t = trophy(cx=cx, cy=cy, width=90, height=200, style=style)
        for layer, lines in t.polylines.items():
            for pl in lines:
                if not pl:
                    continue
                d.append(dw.Lines(
                    *[c for pt in pl for c in pt],
                    close=False, fill='none',
                    stroke='black', stroke_width=0.3,
                ))
        # Label
        d.append(dw.Text(style, font_size=6, x=cx - 15,
                         y=cy + 120, fill='black'))

    d.save_svg('/tmp/trophy_test.svg')
    render_svg_to_png('/tmp/trophy_test.svg',
                      '/tmp/trophy_test.png', dpi=200)
    print("wrote /tmp/trophy_test.svg and /tmp/trophy_test.png")
