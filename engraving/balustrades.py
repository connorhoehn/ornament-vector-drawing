"""Classical balustrades — balusters, rails, and dado pedestals in elevation.

Reference: Ware, *American Vignola* pp. 38-40 ("Pedestals — Plate XVI,
Parapets, Balustrades"). Ware describes the baluster as having a cap and
base each one-quarter of the total height, with the shaft profile taking
the outline of a Quirked Cyma Reversa whose widest point (the belly) is
about one-third of the way up from the bottom of the baluster and whose
width at the belly is roughly one-third of the baluster's height.
Neighbouring balusters are set about half the baluster height apart on
centers, and runs of more than about a dozen balusters are interrupted
by a larger dado pedestal (Ware's "Uncut Baluster" or post).

Coordinate convention: elevation view, Y increases downward (SVG style).
"y_bottom" is the ground line of the baluster; heights grow upward by
subtracting from y_bottom. Every polyline is in mm.
"""
from __future__ import annotations

from dataclasses import dataclass

from shapely.geometry import Polygon

from .geometry import (
    Point,
    Polyline,
    cubic_bezier,
    mirror_path_x,
    rect_corners,
)


@dataclass
class Shadow:
    """A shadow region (shapely Polygon) with a preferred hatch angle."""
    polygon: Polygon
    angle_deg: float = 45.0
    density: str = "medium"


# --------------------------------------------------------------------------
# Single baluster
# --------------------------------------------------------------------------

def _tuscan_right_silhouette(cx: float, y_bottom: float,
                             height: float, max_diam: float) -> Polyline:
    """Right-hand silhouette of a Tuscan (single-belly) baluster.

    Starts at the outer-right corner of the plinth (at y_bottom) and
    walks upward (decreasing y) to the outer-right corner of the
    abacus. The plinth and abacus rectangles themselves are emitted
    as separate polylines.
    """
    h = height
    r_max = max_diam / 2.0
    r_plinth = max_diam * 0.55       # half-width of square plinth
    r_abacus = max_diam * 0.55       # half-width of square abacus (top cap)
    r_neck = max_diam * 0.35 / 2.0   # narrowest: ~0.35·max_diam

    # Vertical anchor points (measured from y_bottom, upward = subtract).
    y_plinth_top = y_bottom - h * 0.08            # top of square plinth
    y_lower_torus_top = y_bottom - h * 0.18       # upper edge of base torus
    y_belly = y_bottom - h * 0.33                 # widest point of the vase
    y_neck = y_bottom - h * 0.72                  # narrowest point (waist)
    y_upper_torus_bot = y_bottom - h * 0.82       # lower edge of neck torus
    y_upper_torus_top = y_bottom - h * 0.88       # upper edge of neck torus
    y_abacus_bot = y_bottom - h * 0.92            # bottom of square abacus
    y_top = y_bottom - h                          # top of abacus

    pts: list[Point] = []
    # Outer edge of plinth
    pts.append((cx + r_plinth, y_bottom))
    pts.append((cx + r_plinth, y_plinth_top))
    # Step inward onto the shaft and form the lower torus (half-circle bump)
    pts.append((cx + r_max * 0.95, y_plinth_top))
    # Lower torus: quick outward bulge back to max_diam at the belly.
    torus_bot = cubic_bezier(
        (cx + r_max * 0.95, y_plinth_top),
        (cx + r_max * 1.02, y_plinth_top - h * 0.02),
        (cx + r_max * 1.02, y_lower_torus_top + h * 0.02),
        (cx + r_max, y_lower_torus_top),
        steps=14,
    )
    pts.extend(torus_bot[1:])
    # Short fillet from top of lower torus down to belly (stays near max).
    pts.append((cx + r_max, y_belly))
    # Cyma-reversa shaft: convex upper-belly shoulder flowing into concave
    # flare toward the neck. Two cubic beziers joined at the point of
    # contrary flexure, roughly midway between belly and neck.
    y_flex = (y_belly + y_neck) / 2.0
    r_flex = (r_max + r_neck) / 2.0
    upper_belly = cubic_bezier(
        (cx + r_max, y_belly),
        (cx + r_max, y_belly - (y_belly - y_flex) * 0.55),
        (cx + r_flex + (r_max - r_flex) * 0.35, y_flex + (y_belly - y_flex) * 0.15),
        (cx + r_flex, y_flex),
        steps=22,
    )
    pts.extend(upper_belly[1:])
    waist = cubic_bezier(
        (cx + r_flex, y_flex),
        (cx + r_flex - (r_flex - r_neck) * 0.35, y_flex - (y_flex - y_neck) * 0.55),
        (cx + r_neck, y_neck + (y_flex - y_neck) * 0.25),
        (cx + r_neck, y_neck),
        steps=22,
    )
    pts.extend(waist[1:])
    # Small fillet at the neck, then upper torus ring under the abacus.
    pts.append((cx + r_neck, y_neck - h * 0.02))
    upper_torus = cubic_bezier(
        (cx + r_neck, y_neck - h * 0.02),
        (cx + r_max * 0.85, y_upper_torus_bot + h * 0.01),
        (cx + r_max * 0.85, y_upper_torus_top - h * 0.005),
        (cx + r_max * 0.55, y_upper_torus_top),
        steps=14,
    )
    pts.extend(upper_torus[1:])
    # Fillet under the abacus, then step out to the abacus corner.
    pts.append((cx + r_max * 0.55, y_abacus_bot))
    pts.append((cx + r_abacus, y_abacus_bot))
    pts.append((cx + r_abacus, y_top))
    return pts


def _renaissance_right_silhouette(cx: float, y_bottom: float,
                                  height: float, max_diam: float) -> Polyline:
    """Right-hand silhouette of a Renaissance (double-belly) baluster.

    Has an extra waist and belly in the lower half — base to base two
    small vases, exactly as Ware describes the 'Double Baluster'.
    """
    h = height
    r_max = max_diam / 2.0
    r_plinth = max_diam * 0.55
    r_abacus = max_diam * 0.55
    r_waist_lo = max_diam * 0.32 / 2.0   # mid waist between two bellies
    r_neck = max_diam * 0.30 / 2.0       # upper neck

    y_plinth_top = y_bottom - h * 0.09
    y_lower_belly = y_bottom - h * 0.24   # widest of lower vase
    y_mid_waist = y_bottom - h * 0.48     # narrow between vases
    y_upper_belly = y_bottom - h * 0.62   # widest of upper vase (smaller)
    y_neck = y_bottom - h * 0.80          # upper neck
    y_upper_torus_top = y_bottom - h * 0.88
    y_abacus_bot = y_bottom - h * 0.92
    y_top = y_bottom - h

    pts: list[Point] = []
    pts.append((cx + r_plinth, y_bottom))
    pts.append((cx + r_plinth, y_plinth_top))
    pts.append((cx + r_max * 0.95, y_plinth_top))
    # Lower belly: rise to max_diam at y_lower_belly
    lower = cubic_bezier(
        (cx + r_max * 0.95, y_plinth_top),
        (cx + r_max * 1.02, y_plinth_top - h * 0.04),
        (cx + r_max * 1.02, y_lower_belly + h * 0.04),
        (cx + r_max, y_lower_belly),
        steps=18,
    )
    pts.extend(lower[1:])
    # Cyma from lower belly → mid waist (convex → concave)
    y_flex1 = (y_lower_belly + y_mid_waist) / 2.0
    r_flex1 = (r_max + r_waist_lo) / 2.0
    to_waist = cubic_bezier(
        (cx + r_max, y_lower_belly),
        (cx + r_max, y_lower_belly - (y_lower_belly - y_flex1) * 0.5),
        (cx + r_flex1, y_flex1),
        (cx + r_waist_lo, y_mid_waist),
        steps=22,
    )
    pts.extend(to_waist[1:])
    # Upper belly (smaller): grow back out
    r_upper_belly = max_diam * 0.84 / 2.0
    y_flex2 = (y_mid_waist + y_upper_belly) / 2.0
    r_flex2 = (r_waist_lo + r_upper_belly) / 2.0
    to_upper = cubic_bezier(
        (cx + r_waist_lo, y_mid_waist),
        (cx + r_waist_lo, y_mid_waist - (y_mid_waist - y_flex2) * 0.45),
        (cx + r_flex2, y_flex2),
        (cx + r_upper_belly, y_upper_belly),
        steps=22,
    )
    pts.extend(to_upper[1:])
    # Waist from upper belly to neck
    y_flex3 = (y_upper_belly + y_neck) / 2.0
    r_flex3 = (r_upper_belly + r_neck) / 2.0
    to_neck = cubic_bezier(
        (cx + r_upper_belly, y_upper_belly),
        (cx + r_upper_belly, y_upper_belly - (y_upper_belly - y_flex3) * 0.55),
        (cx + r_flex3, y_flex3),
        (cx + r_neck, y_neck),
        steps=22,
    )
    pts.extend(to_neck[1:])
    # Upper torus ring
    upper_torus = cubic_bezier(
        (cx + r_neck, y_neck),
        (cx + r_max * 0.80, y_neck - h * 0.04),
        (cx + r_max * 0.80, y_upper_torus_top - h * 0.01),
        (cx + r_max * 0.55, y_upper_torus_top),
        steps=14,
    )
    pts.extend(upper_torus[1:])
    pts.append((cx + r_max * 0.55, y_abacus_bot))
    pts.append((cx + r_abacus, y_abacus_bot))
    pts.append((cx + r_abacus, y_top))
    return pts


def baluster_silhouette(cx: float, y_bottom: float,
                        height: float, max_diam: float,
                        variant: str = "tuscan") -> list[Polyline]:
    """Return [right_silhouette, left_silhouette, plinth_rect, cap_rect]
    polylines for one baluster drawn bottom-up.

    variant: "tuscan" (single belly) or "renaissance" (double belly).
    """
    variant = variant.lower()
    if variant == "renaissance":
        right = _renaissance_right_silhouette(cx, y_bottom, height, max_diam)
    else:  # tuscan (default) — also covers unknown variants gracefully
        right = _tuscan_right_silhouette(cx, y_bottom, height, max_diam)

    left = mirror_path_x(right, cx)

    r_plinth = max_diam * 0.55
    plinth_h = height * 0.08
    plinth_rect = rect_corners(cx - r_plinth, y_bottom - plinth_h,
                               2 * r_plinth, plinth_h)

    r_abacus = max_diam * 0.55
    cap_h = height * 0.08
    cap_rect = rect_corners(cx - r_abacus, y_bottom - height,
                            2 * r_abacus, cap_h)

    return [right, left, plinth_rect, cap_rect]


# --------------------------------------------------------------------------
# Pedestal block
# --------------------------------------------------------------------------

def pedestal_block(cx: float, y_bottom: float, height: float,
                   width: float) -> dict:
    """A square dado pedestal interrupting a balustrade run.

    The block has a small projecting plinth, a plain dado, and a small
    projecting cap — proportions ~1:7:1 as Ware notes for the Tuscan
    pedestal (cap ≈ one-ninth, base ≈ one-ninth of the dado height).
    """
    plinth_h = height * 0.11
    cap_h = height * 0.11
    dado_h = height - plinth_h - cap_h

    half_dado = width / 2.0
    half_plinth = half_dado * 1.15
    half_cap = half_dado * 1.15

    y_top = y_bottom - height
    y_plinth_top = y_bottom - plinth_h
    y_dado_top = y_plinth_top - dado_h
    y_cap_top = y_top

    outline = [
        (cx - half_plinth, y_bottom),
        (cx - half_plinth, y_plinth_top),
        (cx - half_dado, y_plinth_top),
        (cx - half_dado, y_dado_top),
        (cx - half_cap, y_dado_top),
        (cx - half_cap, y_cap_top),
        (cx + half_cap, y_cap_top),
        (cx + half_cap, y_dado_top),
        (cx + half_dado, y_dado_top),
        (cx + half_dado, y_plinth_top),
        (cx + half_plinth, y_plinth_top),
        (cx + half_plinth, y_bottom),
        (cx - half_plinth, y_bottom),
    ]

    # Shadow on the right-hand face of the dado (assume light from upper-left).
    dado_shadow = Polygon([
        (cx + half_dado - width * 0.08, y_plinth_top),
        (cx + half_dado, y_plinth_top),
        (cx + half_dado, y_dado_top),
        (cx + half_dado - width * 0.08, y_dado_top),
    ])
    # Soffit shadow under the cap overhang.
    cap_soffit = Polygon([
        (cx - half_cap, y_dado_top),
        (cx + half_cap, y_dado_top),
        (cx + half_dado, y_dado_top + height * 0.015),
        (cx - half_dado, y_dado_top + height * 0.015),
    ])

    return {
        "outline": outline,
        "shadows": [
            Shadow(dado_shadow, angle_deg=60.0, density="medium"),
            Shadow(cap_soffit, angle_deg=10.0, density="dark"),
        ],
        "top_y": y_top,
        "plinth_top_y": y_plinth_top,
        "dado_top_y": y_dado_top,
        "half_plinth": half_plinth,
        "half_cap": half_cap,
    }


# --------------------------------------------------------------------------
# Full balustrade run
# --------------------------------------------------------------------------

def _top_rail(x0: float, x1: float, y_top: float, h: float) -> list[Polyline]:
    """Continuous handrail rectangle topped by a cyma-reversa fillet.

    Returns horizontal rules (top, bottom, and one intermediate ogee line)
    plus the two end caps. The top rail projects slightly past x0/x1 to
    die into the adjacent pedestals.
    """
    y_bot = y_top + h
    rules: list[Polyline] = [
        [(x0, y_top), (x1, y_top)],           # top edge
        [(x0, y_bot), (x1, y_bot)],           # bottom edge
        [(x0, y_top + h * 0.35), (x1, y_top + h * 0.35)],  # cyma line
        [(x0, y_top + h * 0.60), (x1, y_top + h * 0.60)],  # fillet line
        [(x0, y_top), (x0, y_bot)],
        [(x1, y_top), (x1, y_bot)],
    ]
    return rules


def _bottom_rail(x0: float, x1: float, y_top: float, h: float) -> list[Polyline]:
    """Lower rail (stylobate) below the balusters."""
    y_bot = y_top + h
    rules: list[Polyline] = [
        [(x0, y_top), (x1, y_top)],
        [(x0, y_bot), (x1, y_bot)],
        [(x0, y_top + h * 0.35), (x1, y_top + h * 0.35)],  # torus/fillet line
        [(x0, y_top), (x0, y_bot)],
        [(x1, y_top), (x1, y_bot)],
    ]
    return rules


def balustrade_run(x0: float, x1: float, y_top_of_rail: float,
                   height: float,
                   baluster_variant: str = "tuscan",
                   baluster_oc: float | None = None,
                   include_pedestals_at: list[float] | None = None) -> dict:
    """A continuous run of balusters with top rail and bottom rail.

    x0, x1           horizontal extent of the run.
    y_top_of_rail    y at the very top of the top (upper) rail.
    height           total height from bottom of bottom rail to top of
                     top rail. Rails together take ~1/3 of this; the
                     remainder is the baluster shaft length.
    baluster_variant "tuscan" or "renaissance".
    baluster_oc      on-center spacing. Defaults to 1.5 × max_diam so a
                     clear space of roughly one diameter remains between
                     neighbours — close to Ware's rule of "half the
                     baluster height apart on centers".
    include_pedestals_at  list of x-positions at which to insert square
                          dado pedestal blocks. The run is broken into
                          sub-segments between neighbouring pedestals
                          (and the end-points), each filled with its own
                          set of balusters and rail segments.

    Returns a dict with keys: top_rail, bottom_rail, balusters, pedestals,
    shadows.
    """
    # --- Vertical layout ---------------------------------------------------
    top_rail_h = height * 0.16
    bot_rail_h = height * 0.18
    baluster_h = height - top_rail_h - bot_rail_h

    y_top_rail_top = y_top_of_rail
    y_top_rail_bot = y_top_of_rail + top_rail_h
    y_bal_bottom = y_top_rail_bot + baluster_h       # ground line for balusters
    y_bot_rail_top = y_bal_bottom                    # bottom rail starts here
    y_bot_rail_bot = y_bot_rail_top + bot_rail_h

    # Baluster proportions — Ware: height ≈ 3 × max diam.
    max_diam = baluster_h / 3.0
    if baluster_oc is None:
        baluster_oc = max_diam * 1.5

    # --- Split run at pedestals -------------------------------------------
    include_pedestals_at = include_pedestals_at or []
    # Pedestal width: a touch wider than the baluster plinth, so they read
    # as stronger posts.
    ped_width = max_diam * 1.8

    # Cluster pedestal positions that fall inside [x0, x1]. A pedestal at
    # exactly x0 or x1 sits as an end post rather than splitting the run.
    peds_inside = sorted(p for p in include_pedestals_at if x0 < p < x1)
    peds_at_ends = [p for p in include_pedestals_at if p == x0 or p == x1]

    # Build segments (x_lo, x_hi) of clear space between pedestals/ends.
    segments: list[tuple[float, float]] = []
    cursor = x0
    # Account for a pedestal sitting at x0 (end post): it consumes a
    # half-width of space inside the run.
    if x0 in peds_at_ends:
        cursor = x0 + ped_width / 2.0
    for p in peds_inside:
        seg_hi = p - ped_width / 2.0
        if seg_hi > cursor:
            segments.append((cursor, seg_hi))
        cursor = p + ped_width / 2.0
    seg_hi_final = x1 - (ped_width / 2.0 if x1 in peds_at_ends else 0.0)
    if seg_hi_final > cursor:
        segments.append((cursor, seg_hi_final))

    # --- Place balusters within each segment ------------------------------
    balusters: list[list[Polyline]] = []
    top_rail_polys: list[Polyline] = []
    bottom_rail_polys: list[Polyline] = []
    for seg_lo, seg_hi in segments:
        seg_w = seg_hi - seg_lo
        if seg_w <= 0:
            continue
        # Number of balusters that fit at the nominal on-center spacing
        # with a half-stride margin at each end.
        n = max(1, int(round(seg_w / baluster_oc)))
        # Recompute the actual on-center to spread evenly within the seg.
        actual_oc = seg_w / n
        # First baluster is half-stride in from seg_lo.
        for i in range(n):
            cx_i = seg_lo + actual_oc * (i + 0.5)
            balusters.append(
                baluster_silhouette(cx_i, y_bal_bottom,
                                    baluster_h, max_diam,
                                    variant=baluster_variant)
            )
        # Rails over this segment
        top_rail_polys.extend(_top_rail(seg_lo, seg_hi, y_top_rail_top, top_rail_h))
        bottom_rail_polys.extend(_bottom_rail(seg_lo, seg_hi, y_bot_rail_top, bot_rail_h))

    # --- Pedestal blocks ---------------------------------------------------
    pedestal_polys: list[Polyline] = []
    shadows: list[Shadow] = []
    ped_positions = sorted(set(include_pedestals_at))
    for p in ped_positions:
        if not (x0 <= p <= x1):
            continue
        # Pedestal spans full run height (from top of top rail down to
        # bottom of bottom rail) and a bit beyond.
        block = pedestal_block(p, y_bot_rail_bot, height, ped_width)
        pedestal_polys.append(block["outline"])
        shadows.extend(block["shadows"])

    return {
        "top_rail": top_rail_polys,
        "bottom_rail": bottom_rail_polys,
        "balusters": balusters,
        "pedestals": pedestal_polys,
        "shadows": shadows,
        # Extras useful for callers stitching a full elevation:
        "baluster_height": baluster_h,
        "baluster_max_diam": max_diam,
        "baluster_oc": baluster_oc,
        "y_top_of_top_rail": y_top_rail_top,
        "y_bottom_of_bottom_rail": y_bot_rail_bot,
    }


# --------------------------------------------------------------------------
# Smoke test
# --------------------------------------------------------------------------

def _smoke_test() -> None:
    # Single baluster
    polys = baluster_silhouette(cx=50.0, y_bottom=200.0,
                                height=80.0, max_diam=25.0,
                                variant="tuscan")
    assert len(polys) == 4, f"expected 4 polylines, got {len(polys)}"
    right, left, plinth, cap = polys
    assert len(right) > 10 and len(left) > 10, "silhouettes should have many pts"
    assert len(plinth) == 5 and len(cap) == 5, "plinth/cap should be closed rects"
    print(f"single baluster: right={len(right)} pts, left={len(left)} pts, "
          f"plinth={len(plinth)} pts, cap={len(cap)} pts")

    # Balustrade run
    run = balustrade_run(x0=30.0, x1=270.0, y_top_of_rail=120.0, height=80.0,
                         include_pedestals_at=[60.0, 180.0, 270.0])
    print(f"run baluster_height = {run['baluster_height']:.2f}, "
          f"max_diam = {run['baluster_max_diam']:.2f}, "
          f"on-center = {run['baluster_oc']:.2f}")
    print(f"run baluster count: {len(run['balusters'])}")
    print(f"run pedestal count: {len(run['pedestals'])}")
    print(f"top-rail polylines: {len(run['top_rail'])}, "
          f"bottom-rail polylines: {len(run['bottom_rail'])}")
    print(f"shadows: {len(run['shadows'])}")

    # Each baluster must have both right and left silhouettes.
    for i, bpolys in enumerate(run["balusters"]):
        assert len(bpolys) == 4, f"baluster #{i} has {len(bpolys)} parts"
        r, l, _, _ = bpolys
        assert len(r) > 5 and len(l) > 5, f"baluster #{i} silhouette empty"
    print(f"all {len(run['balusters'])} balusters have right+left silhouettes")


if __name__ == "__main__":
    _smoke_test()
