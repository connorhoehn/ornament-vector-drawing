"""Corinthian column silhouette in elevation, after Ware's *American Vignola*
(1903), pp. 19-21.

The Corinthian column is the tallest of the five orders (10D) and the capital
is by far the most elaborate: a bell (campana) wrapped in two rows of acanthus
leaves, topped by a ring of helices (small volutes at the corners) and a
concave-sided abacus carrying a central fleuron on each face.

Canonical proportions (from `canon.Corinthian`):
    * Column height = 10 D
    * Base = ½ D (Attic — plinth, lower torus, scotia, upper torus, fillet)
    * Capital = 7/6 D (bell 1 D + abacus 1/6 D)
    * Each leaf row = ⅓ D tall
    * 8 leaves per row, offset 45° between rows
    * 24 flutes with fillets (handled in `fluting.py`)
    * Abacus diagonal = 4/3 D; plain side = 7/6 D; concave dip = 1/12 D

This builder follows the 7-polyline silhouette contract used by `orders.py`
`tuscan_column_silhouette` and `order_doric.py`, then appends acanthus,
helix, bell-curve, and abacus ornament polylines.
"""
from __future__ import annotations

import math

from . import acanthus, canon
from .geometry import (Point, Polyline, arc, cubic_bezier, line,
                       mirror_path_x, translate_path)
from .schema import ElementResult


# ─── local helpers ──────────────────────────────────────────────────────

def _ellipse_arc(cx: float, cy: float, rx: float, ry: float,
                 t0: float, t1: float, n: int) -> Polyline:
    pts: list[Point] = []
    for i in range(n):
        t = t0 + (t1 - t0) * (i / (n - 1))
        pts.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
    return pts


def _spiral(cx: float, cy: float, r0: float, r1: float,
            theta0: float, theta1: float, steps: int = 48) -> Polyline:
    """Archimedean-ish spiral arc from radius r0 at theta0 to r1 at theta1."""
    pts: list[Point] = []
    for i in range(steps):
        t = i / (steps - 1)
        r = r0 + (r1 - r0) * t
        theta = theta0 + (theta1 - theta0) * t
        pts.append((cx + r * math.cos(theta), cy + r * math.sin(theta)))
    return pts


# ─── main builder ───────────────────────────────────────────────────────

def corinthian_column_silhouette(dims: canon.Corinthian,
                                 cx: float, base_y: float,
                                 *, return_result: bool = False):
    """Return polylines for a Corinthian column in elevation.

    base_y = bottom of column (top of pedestal). Column grows up (y decreases).
    cx    = column centerline x.

    Return order:
      1. right_silhouette
      2. left_silhouette
      3. cap_top_rule
      4. col_bot_rule
      5. plinth_top_rule
      6. shaft_top_rule
      7. abacus_bot_rule
      8+. acanthus leaf polylines (row 1), leaf polylines (row 2),
          helix spirals, bell-curve guides, abacus outline.

    If ``return_result=True``, returns an :class:`ElementResult` with named
    anchors and categorized polyline layers. Otherwise (default) returns the
    legacy flat list of polylines for backward compatibility.
    """
    D = dims.D
    M = dims.M
    r_lo = D / 2
    r_up = dims.upper_diam / 2                # 5/6 × D/2

    # ── Base (Attic: plinth + lower torus + scotia + upper torus + fillet) ──
    base_h = dims.base_h                      # ½ D
    plinth_half = (7.0 / 6.0) * D / 2         # 7/12 D

    # Subdivide the ½D base.
    plinth_h = 0.40 * base_h                  # plinth block
    low_torus_h = 0.18 * base_h               # lower torus (larger)
    scotia_h = 0.15 * base_h                  # concave scotia
    up_torus_h = 0.14 * base_h                # upper torus (smaller)
    fillet_base_h = base_h - plinth_h - low_torus_h - scotia_h - up_torus_h

    low_torus_r = low_torus_h / 2
    up_torus_r = up_torus_h / 2
    scotia_proj = M * 0.18                    # how far scotia recedes

    y_col_bot = base_y
    y_plinth_top = y_col_bot - plinth_h
    y_lt_top = y_plinth_top - low_torus_h
    y_sc_top = y_lt_top - scotia_h
    y_ut_top = y_sc_top - up_torus_h
    y_base_top = y_ut_top - fillet_base_h

    # ── Shaft ──────────────────────────────────────────────────────────
    shaft_break_y = y_base_top - dims.shaft_h / 3.0
    y_shaft_top = y_base_top - dims.shaft_h

    # Astragal at the top of the shaft, just below the bell.
    astragal_r = D / 44.0
    astragal_h = 2 * astragal_r
    y_astragal_top = y_shaft_top - astragal_h

    # ── Capital (7/6 D) ────────────────────────────────────────────────
    cap_h = dims.capital_h                    # 7/6 × D
    bell_h = dims.bell_height_D * D           # 1 × D
    abacus_h = cap_h - bell_h                 # 1/6 × D

    y_bell_bot = y_astragal_top               # bell starts where astragal ends
    y_bell_top = y_bell_bot - bell_h
    y_cap_top = y_bell_top - abacus_h
    y_abacus_bot = y_bell_top

    # Abacus half-width (plain side = 7/6 D; concave dip = 1/12 D).
    abacus_half = (7.0 / 6.0) * D / 2
    abacus_concave_dip = D / 12.0

    # Bell profile: curves outward from r_up at the bottom to abacus_half at top.
    bell_top_half = abacus_half - D * 0.04    # bell meets abacus slightly inside
    bell_bot_half = r_up

    # ── Build right silhouette bottom-to-top ──────────────────────────
    R: list[Point] = []

    # Plinth
    R.append((cx + plinth_half, y_col_bot))
    R.append((cx + plinth_half, y_plinth_top))
    R.append((cx + r_lo + (plinth_half - r_lo) * 0.15, y_plinth_top))

    # Lower torus — large half-circle
    lt_cy = y_plinth_top - low_torus_r
    R += _ellipse_arc(cx + r_lo, lt_cy, low_torus_r, low_torus_r,
                      math.pi / 2, -math.pi / 2, 21)

    # Scotia — concave curve that recedes inward then back out
    # Draw as an ellipse-quarter that goes inward at top and outward at bottom.
    sc_cx = cx + r_lo - scotia_proj
    sc_cy = (y_lt_top + y_sc_top) / 2
    # Start at (cx + r_lo, y_lt_top) going inward, then back to (cx + r_lo, y_sc_top)
    R += _ellipse_arc(sc_cx, sc_cy, scotia_proj, scotia_h / 2,
                      0.0, -math.pi, 21)[::-1]

    # Upper torus
    ut_cy = y_sc_top - up_torus_r
    R += _ellipse_arc(cx + r_lo, ut_cy, up_torus_r, up_torus_r,
                      math.pi / 2, -math.pi / 2, 17)

    # Fillet at top of base
    R.append((cx + r_lo, y_base_top))

    # Shaft: cylindrical ⅓, then tapered to r_up
    R.append((cx + r_lo, shaft_break_y))
    R.append((cx + r_up, y_shaft_top))

    # Astragal — small bead bulging right at the top of the shaft
    ast_cy = (y_shaft_top + y_astragal_top) / 2
    R += _ellipse_arc(cx + r_up, ast_cy, astragal_r, astragal_r,
                      math.pi / 2, -math.pi / 2, 13)

    # Bell — cubic bezier from (r_up, y_bell_bot) outward to
    # (bell_top_half, y_bell_top). Control points make the wall flare out
    # more near the top (bell shape).
    bell_p0 = (cx + bell_bot_half, y_bell_bot)
    bell_p1 = (cx + bell_bot_half + (bell_top_half - bell_bot_half) * 0.10,
               y_bell_bot - bell_h * 0.40)
    bell_p2 = (cx + bell_bot_half + (bell_top_half - bell_bot_half) * 0.35,
               y_bell_bot - bell_h * 0.75)
    bell_p3 = (cx + bell_top_half, y_bell_top)
    R += cubic_bezier(bell_p0, bell_p1, bell_p2, bell_p3, steps=32)

    # Abacus — concave top. Right side of abacus: straight side rising,
    # then the top edge is a gentle concave arc dipping down at the center.
    R.append((cx + abacus_half, y_abacus_bot))
    R.append((cx + abacus_half, y_cap_top))

    L = mirror_path_x(R, cx)

    cap_top = [(cx - abacus_half, y_cap_top), (cx + abacus_half, y_cap_top)]
    col_bot = [(cx - plinth_half, y_col_bot), (cx + plinth_half, y_col_bot)]
    plinth_top = [(cx - plinth_half, y_plinth_top), (cx + plinth_half, y_plinth_top)]
    shaft_top_rule = [(cx - r_up, y_shaft_top), (cx + r_up, y_shaft_top)]
    abacus_bot_rule = [(cx - abacus_half, y_abacus_bot),
                       (cx + abacus_half, y_abacus_bot)]

    polylines: list[Polyline] = [R, L, cap_top, col_bot, plinth_top,
                                 shaft_top_rule, abacus_bot_rule]

    # Collect ornament polylines into separate layer-lists so that when
    # ``return_result=True`` we can categorize them. They are still appended
    # to ``polylines`` in the historical order for backward compatibility.
    acanthus_row1_polys: list[Polyline] = []
    acanthus_row2_polys: list[Polyline] = []
    helix_polys: list[Polyline] = []
    caulicoli_polys: list[Polyline] = []
    bell_guide_polys: list[Polyline] = []
    abacus_polys: list[Polyline] = []
    fleuron_polys: list[Polyline] = []

    # ── Ornament on the bell ──────────────────────────────────────────
    leaf_h = dims.leaf_height_D * D            # ⅓ D per leaf row

    # For a bell whose half-width grows from r_up to bell_top_half, an
    # "average" half-width at a given height is useful for leaf placement.
    def bell_half_at(y: float) -> float:
        """Approximate bell half-width at elevation y (linear interp)."""
        if y >= y_bell_bot:
            return bell_bot_half
        if y <= y_bell_top:
            return bell_top_half
        t = (y_bell_bot - y) / (y_bell_bot - y_bell_top)
        # Ease toward the top (flare is steeper near the top).
        t = t * t * (3 - 2 * t) * 0.6 + t * 0.4
        return bell_bot_half + (bell_top_half - bell_bot_half) * t

    # ---- Lower acanthus row (row 1) ----
    # Canonical Corinthian has 8 leaves per row arranged radially around
    # the bell. Projected onto the front elevation, 5 read clearly:
    # one centre leaf, two at the mid-angles (showing both halves), two
    # at the corner angles (showing only their outward halves). We
    # also sketch the inner edges of the two that tuck behind the
    # corner leaves — these are short accent curves rendered by the
    # leaf's own partial silhouette where it enters the bell.
    row1_base_y = y_bell_bot - leaf_h * 0.05
    row1_center_y = row1_base_y - leaf_h / 2
    avg_half_row1 = bell_half_at(row1_center_y)

    def _add_leaf(polys_list: list[Polyline], leaf_polys: list[Polyline],
                  tx: float, ty: float) -> None:
        for poly in leaf_polys:
            tp = translate_path(poly, tx, ty)
            polylines.append(tp)
            polys_list.append(tp)

    # Widths per position (multiples of 2*avg_half).
    central_w = 2 * avg_half_row1 * 0.42
    mid_w = 2 * avg_half_row1 * 0.36
    corner_w = 2 * avg_half_row1 * 0.30
    # Horizontal offsets (dx) from the bell axis in elevation.
    row1_mid_dx = avg_half_row1 * 0.45
    row1_corner_dx = avg_half_row1 * 0.88

    # Centre leaf.
    _add_leaf(acanthus_row1_polys,
              acanthus.acanthus_leaf(width=central_w, height=leaf_h,
                                      lobe_count=3, teeth_per_lobe=3,
                                      turnover=0.28, variant="corinthian"),
              cx, row1_center_y)
    # Mid leaves (± row1_mid_dx).
    for sign in (+1, -1):
        _add_leaf(acanthus_row1_polys,
                  acanthus.acanthus_leaf(width=mid_w,
                                          height=leaf_h * 0.94,
                                          lobe_count=3, teeth_per_lobe=3,
                                          turnover=0.30, variant="corinthian"),
                  cx + sign * row1_mid_dx, row1_center_y)
    # Corner leaves (± row1_corner_dx) — show narrower, angled slightly.
    for sign in (+1, -1):
        _add_leaf(acanthus_row1_polys,
                  acanthus.acanthus_leaf(width=corner_w,
                                          height=leaf_h * 0.90,
                                          lobe_count=3, teeth_per_lobe=3,
                                          turnover=0.34, variant="corinthian"),
                  cx + sign * row1_corner_dx, row1_center_y)

    # ---- Upper acanthus row (row 2) ----
    # Row 2 is staggered 22.5° relative to row 1, so its leaves sit
    # between the row-1 positions in elevation. In a 2D rendering the
    # four cleanly visible ones are ±mid2_dx and ±inner2_dx.
    row2_base_y = row1_base_y - leaf_h * 0.85      # overlap with row 1
    row2_center_y = row2_base_y - leaf_h / 2
    avg_half_row2 = bell_half_at(row2_center_y)

    inner2_dx = avg_half_row2 * 0.22
    mid2_dx = avg_half_row2 * 0.66
    inner2_w = 2 * avg_half_row2 * 0.34
    mid2_w = 2 * avg_half_row2 * 0.32

    # Inner pair (visible between row-1 centre and mid leaves).
    for sign in (+1, -1):
        _add_leaf(acanthus_row2_polys,
                  acanthus.acanthus_leaf(width=inner2_w, height=leaf_h,
                                          lobe_count=3, teeth_per_lobe=3,
                                          turnover=0.30, variant="corinthian"),
                  cx + sign * inner2_dx, row2_center_y)
    # Mid pair (visible between row-1 mid and corner leaves).
    for sign in (+1, -1):
        _add_leaf(acanthus_row2_polys,
                  acanthus.acanthus_leaf(width=mid2_w,
                                          height=leaf_h * 0.90,
                                          lobe_count=3, teeth_per_lobe=3,
                                          turnover=0.32, variant="corinthian"),
                  cx + sign * mid2_dx, row2_center_y)

    # ---- Helices / caulicoli (top third of bell) ----
    # Canonical: 8 caulicoli stems rise from between the upper leaves
    # and split into pairs of helices under the abacus. Each pair has
    # an OUTER helix curling to the corner (becoming the corner volute
    # carrying the abacus) and an INNER helix curling to the centre
    # (meeting under the fleuron). In strict elevation: 2 corner
    # volutes + 2 inner helices + 4 visible caulicoli stems.
    helix_r = D * 0.14   # was 0.10 — corner volutes needed more presence
    helix_y = y_bell_top - helix_r * 0.15

    # Corner volutes: large scrolls at the outer edges of the capital.
    right_eye_cx = cx + bell_top_half - helix_r * 1.05
    left_eye_cx = cx - bell_top_half + helix_r * 1.05
    right_helix = _spiral(cx=right_eye_cx, cy=helix_y,
                          r0=helix_r * 1.10, r1=helix_r * 0.12,
                          theta0=math.radians(40),
                          theta1=math.radians(40 + 360),
                          steps=72)
    polylines.append(right_helix)
    helix_polys.append(right_helix)
    left_helix = _spiral(cx=left_eye_cx, cy=helix_y,
                         r0=helix_r * 1.10, r1=helix_r * 0.12,
                         theta0=math.radians(180 - 40),
                         theta1=math.radians(180 - 40 - 360),
                         steps=72)
    polylines.append(left_helix)
    helix_polys.append(left_helix)

    # Inner helix pair: smaller scrolls flanking the fleuron. They
    # read as the pair that in 3D meets under the central axis of the
    # abacus; in elevation they sit symmetrically near the centreline.
    inner_helix_r = D * 0.065
    inner_helix_y = y_bell_top - inner_helix_r * 0.3
    inner_right_cx = cx + D * 0.14
    inner_left_cx = cx - D * 0.14
    inner_right_helix = _spiral(cx=inner_right_cx, cy=inner_helix_y,
                                 r0=inner_helix_r * 1.10,
                                 r1=inner_helix_r * 0.14,
                                 theta0=math.radians(140),
                                 theta1=math.radians(140 + 300),
                                 steps=54)
    polylines.append(inner_right_helix)
    helix_polys.append(inner_right_helix)
    inner_left_helix = _spiral(cx=inner_left_cx, cy=inner_helix_y,
                                r0=inner_helix_r * 1.10,
                                r1=inner_helix_r * 0.14,
                                theta0=math.radians(180 - 140),
                                theta1=math.radians(180 - 140 - 300),
                                steps=54)
    polylines.append(inner_left_helix)
    helix_polys.append(inner_left_helix)

    # Caulicoli stems: 4 visible in elevation. The OUTER pair sprouts
    # from between the row-2 mid leaves and arcs out to the corner
    # volute; the INNER pair sprouts from between row-2 inner leaves
    # and arcs up to the inner helices near the fleuron.
    def _stem(start: tuple[float, float], end: tuple[float, float],
              sign: int) -> Polyline:
        return cubic_bezier(
            start,
            (start[0] + sign * D * 0.03, start[1] - D * 0.12),
            (end[0] - sign * D * 0.05, end[1] + D * 0.04),
            end, steps=22,
        )

    # Outer caulicoli (to corner volutes).
    out_stem_start_r = (cx + mid2_dx * 0.80,
                        row2_center_y - leaf_h * 0.28)
    out_stem_end_r = (right_eye_cx - helix_r * 0.35,
                      helix_y + helix_r * 0.95)
    polylines.append(_stem(out_stem_start_r, out_stem_end_r, +1))
    caulicoli_polys.append(polylines[-1])

    out_stem_start_l = (cx - mid2_dx * 0.80,
                        row2_center_y - leaf_h * 0.28)
    out_stem_end_l = (left_eye_cx + helix_r * 0.35,
                      helix_y + helix_r * 0.95)
    polylines.append(_stem(out_stem_start_l, out_stem_end_l, -1))
    caulicoli_polys.append(polylines[-1])

    # Inner caulicoli (to inner helices).
    in_stem_start_r = (cx + inner2_dx * 0.85,
                       row2_center_y - leaf_h * 0.30)
    in_stem_end_r = (inner_right_cx - inner_helix_r * 0.5,
                     inner_helix_y + inner_helix_r * 0.95)
    polylines.append(_stem(in_stem_start_r, in_stem_end_r, +1))
    caulicoli_polys.append(polylines[-1])

    in_stem_start_l = (cx - inner2_dx * 0.85,
                       row2_center_y - leaf_h * 0.30)
    in_stem_end_l = (inner_left_cx + inner_helix_r * 0.5,
                     inner_helix_y + inner_helix_r * 0.95)
    polylines.append(_stem(in_stem_start_l, in_stem_end_l, -1))
    caulicoli_polys.append(polylines[-1])

    # ---- Bell-curve guide polylines (subtle reinforcement) ----
    # The shaft-silhouette already traces the bell's outer curve; add two
    # interior guide lines that indicate the bell's inner wall peeking
    # through the gaps between leaves. These read as the "visible bell
    # between the acanthus" in engraved plates.
    inner_top_half = bell_top_half - D * 0.09
    inner_bot_half = bell_bot_half - D * 0.02
    inner_right = cubic_bezier(
        (cx + inner_bot_half, y_bell_bot - leaf_h * 0.2),
        (cx + inner_bot_half + (inner_top_half - inner_bot_half) * 0.10,
         y_bell_bot - bell_h * 0.45),
        (cx + inner_bot_half + (inner_top_half - inner_bot_half) * 0.55,
         y_bell_bot - bell_h * 0.85),
        (cx + inner_top_half, y_bell_top + D * 0.01),
        steps=24,
    )
    polylines.append(inner_right)
    bell_guide_polys.append(inner_right)
    inner_left = mirror_path_x(inner_right, cx)
    polylines.append(inner_left)
    bell_guide_polys.append(inner_left)

    # ---- Abacus outline with concave top edge and central fleuron ----
    # Front face outline (closed polyline): left vertical side, concave top,
    # right vertical side, straight bottom back to start.
    abacus_top_left = (cx - abacus_half, y_cap_top)
    abacus_top_right = (cx + abacus_half, y_cap_top)
    abacus_bot_left = (cx - abacus_half, y_abacus_bot)
    abacus_bot_right = (cx + abacus_half, y_abacus_bot)
    # Concave top arc dips down at center by abacus_concave_dip.
    concave_top = cubic_bezier(
        abacus_top_left,
        (cx - abacus_half * 0.55, y_cap_top + abacus_concave_dip * 0.6),
        (cx + abacus_half * 0.55, y_cap_top + abacus_concave_dip * 0.6),
        abacus_top_right,
        steps=22,
    )
    # Outline: bottom-left -> top-left -> concave-top -> top-right
    # -> bottom-right -> back to bottom-left.
    abacus_outline: Polyline = [abacus_bot_left, abacus_top_left]
    abacus_outline += concave_top[1:]
    abacus_outline.append(abacus_bot_right)
    abacus_outline.append(abacus_bot_left)
    polylines.append(abacus_outline)
    abacus_polys.append(abacus_outline)

    # Fleuron: 5-petal rosette centred on the abacus's concave low
    # point. Canonical Vignola: a prominent central petal rising above
    # the abacus top, flanked by two outer petals curling downward and
    # two side-petals below the central axis line. All radiate from a
    # small calyx cup near the abacus centre.
    fleuron_cx = cx
    fleuron_cy = y_cap_top + abacus_concave_dip * 0.6
    fleuron_r = D * 0.085
    # Central (upper) petal — tall teardrop rising above the axis.
    center_petal = cubic_bezier(
        (fleuron_cx - fleuron_r * 0.35, fleuron_cy),
        (fleuron_cx - fleuron_r * 0.35, fleuron_cy - fleuron_r * 1.35),
        (fleuron_cx + fleuron_r * 0.35, fleuron_cy - fleuron_r * 1.35),
        (fleuron_cx + fleuron_r * 0.35, fleuron_cy),
        steps=22,
    )
    polylines.append(center_petal)
    fleuron_polys.append(center_petal)
    # Upper side-petals: flanking the centre, arcing slightly upward.
    up_r = fleuron_r * 0.85
    for sign in (+1, -1):
        upper_petal = cubic_bezier(
            (fleuron_cx + sign * fleuron_r * 0.20, fleuron_cy - up_r * 0.05),
            (fleuron_cx + sign * up_r * 0.75, fleuron_cy - up_r * 0.85),
            (fleuron_cx + sign * up_r * 1.20, fleuron_cy - up_r * 0.35),
            (fleuron_cx + sign * up_r * 1.05, fleuron_cy + up_r * 0.10),
            steps=18,
        )
        polylines.append(upper_petal)
        fleuron_polys.append(upper_petal)
    # Lower side-petals: splay outward-and-down along the abacus face.
    down_r = fleuron_r * 0.75
    for sign in (+1, -1):
        lower_petal = cubic_bezier(
            (fleuron_cx + sign * fleuron_r * 0.10, fleuron_cy + down_r * 0.15),
            (fleuron_cx + sign * down_r * 0.65, fleuron_cy + down_r * 0.45),
            (fleuron_cx + sign * down_r * 1.10, fleuron_cy + down_r * 0.35),
            (fleuron_cx + sign * down_r * 0.95, fleuron_cy + down_r * 0.10),
            steps=18,
        )
        polylines.append(lower_petal)
        fleuron_polys.append(lower_petal)

    if not return_result:
        return polylines

    result = ElementResult(kind="corinthian_column", dims_ref=dims)
    result.add_polylines("silhouette", [R, L])
    result.add_polylines("rules", [cap_top, col_bot, plinth_top,
                                   shaft_top_rule, abacus_bot_rule])
    result.add_polylines("acanthus", acanthus_row1_polys + acanthus_row2_polys)
    result.add_polylines("helices", helix_polys)
    result.add_polylines("caulicoli", caulicoli_polys)
    result.add_polylines("bell_guides", bell_guide_polys)
    result.add_polylines("abacus", abacus_polys)
    result.add_polylines("fleuron", fleuron_polys)
    result.add_anchor("bottom_center", cx, y_col_bot, "attach")
    result.add_anchor("plinth_top_right", cx + plinth_half, y_plinth_top)
    result.add_anchor("plinth_top_left", cx - plinth_half, y_plinth_top)
    result.add_anchor("base_top_right", cx + r_lo, y_base_top)
    result.add_anchor("base_top_left", cx - r_lo, y_base_top)
    result.add_anchor("shaft_top_right", cx + r_up, y_shaft_top)
    result.add_anchor("shaft_top_left", cx - r_up, y_shaft_top)
    result.add_anchor("astragal_top", cx, y_astragal_top)
    result.add_anchor("bell_bottom", cx, y_bell_bot)
    result.add_anchor("bell_top", cx, y_bell_top)
    result.add_anchor("abacus_bottom_right", cx + abacus_half, y_abacus_bot)
    result.add_anchor("abacus_bottom_left", cx - abacus_half, y_abacus_bot)
    result.add_anchor("abacus_top_right", cx + abacus_half, y_cap_top)
    result.add_anchor("abacus_top_left", cx - abacus_half, y_cap_top)
    result.add_anchor("top_center", cx, y_cap_top, "attach")
    result.add_anchor("axis", cx, (y_col_bot + y_cap_top) / 2, "axis")
    result.add_anchor("helix_right", right_eye_cx, helix_y, "center")
    result.add_anchor("helix_left", left_eye_cx, helix_y, "center")
    result.add_anchor("fleuron_center", fleuron_cx, fleuron_cy, "center")
    # Canonical heights per Ware: the astragal is the TOP of the shaft's
    # decoration (NOT part of the capital block). ``y_cap_top`` sits
    # ``astragal_h`` above the canonical capital top because the drawn bead
    # extends above ``y_shaft_top``; that extra bead height belongs to the
    # shaft's decoration, not to capital_h or column_h.
    result.metadata["base_h"] = y_col_bot - y_base_top
    result.metadata["shaft_h"] = y_base_top - y_shaft_top
    result.metadata["capital_h"] = y_astragal_top - y_cap_top
    result.metadata["column_h"] = (result.metadata["base_h"]
                                   + result.metadata["shaft_h"]
                                   + result.metadata["capital_h"])
    result.metadata["num_acanthus_row1"] = 5
    result.metadata["num_acanthus_row2"] = 4
    result.metadata["num_helices"] = 4     # 2 corner volutes + 2 inner helices
    result.metadata["num_caulicoli"] = 4
    result.metadata["has_fleuron"] = True
    # ── Subdivisional metadata (for finer-grained validation) ───────────
    # Attic base: plinth → lower torus → scotia → upper torus → fillet
    # (Ware p.21).
    result.metadata["base_plinth_h"] = y_col_bot - y_plinth_top
    result.metadata["base_lower_torus_h"] = y_plinth_top - y_lt_top
    result.metadata["base_scotia_h"] = y_lt_top - y_sc_top
    result.metadata["base_upper_torus_h"] = y_sc_top - y_ut_top
    result.metadata["base_torus_h"] = (
        result.metadata["base_lower_torus_h"]
        + result.metadata["base_upper_torus_h"])
    result.metadata["base_fillet_h"] = y_ut_top - y_base_top
    # Capital: bell (1 D) + abacus (1/6 D). Bell is subdivided into two
    # acanthus rows (each ⅓ D) + a helix/caulicoli zone in the top third.
    # row1 spans [row1_base_y → row1_base_y - leaf_h], row2 overlaps it.
    result.metadata["cap_bell_h"] = y_bell_bot - y_bell_top
    result.metadata["cap_acanthus_row1_h"] = leaf_h
    result.metadata["cap_acanthus_row2_h"] = leaf_h
    # Helix zone = top third of the bell above the row-2 leaves.
    result.metadata["cap_helix_h"] = (y_bell_bot - y_bell_top) / 3.0
    result.metadata["cap_abacus_h"] = y_bell_top - y_cap_top
    result.compute_bbox()
    return result


# ── Smoke test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import drawsvg as dw

    from . import preview

    dims = canon.Corinthian(D=24)
    # Spec: cx=100, base_y=220, D=24 on a 220 × 280 mm canvas.
    # (Column height = 10 × 24 = 240 mm; the capital extends above the
    # midline at y=220 toward the top-left corner.)
    polys = corinthian_column_silhouette(dims, cx=100, base_y=220)

    W, H = 220.0, 280.0
    d = dw.Drawing(width=f"{W}mm", height=f"{H}mm", viewBox=f"0 0 {W} {H}")
    d.append(dw.Rectangle(0, 0, W, H, fill="white"))

    for poly in polys:
        if len(poly) < 2:
            continue
        flat: list[float] = []
        for x, y in poly:
            flat.extend([x, y])
        d.append(dw.Lines(*flat, close=False, fill="none",
                          stroke="black", stroke_width=0.25,
                          stroke_linecap="round", stroke_linejoin="round"))

    svg_path = "/tmp/corinthian_test.svg"
    png_path = "/tmp/corinthian_test.png"
    d.save_svg(svg_path)
    print(f"Wrote {svg_path} — {len(polys)} polylines; "
          f"column height {dims.column_h:.1f} mm at D={dims.D} mm.")
    try:
        preview.render_svg_to_png(svg_path, png_path, dpi=150)
        print(f"Wrote {png_path}")
    except Exception as exc:
        print(f"PNG render failed: {exc}")

    # Validation smoke test
    dims_v = canon.Corinthian(D=20.0)
    result = corinthian_column_silhouette(dims_v, 100.0, 200.0, return_result=True)
    assert result.kind == "corinthian_column"
    assert "bottom_center" in result.anchors
    assert "top_center" in result.anchors
    assert result.bbox != (0.0, 0.0, 0.0, 0.0)
    print(f"corinthian_column: {len(result.anchors)} anchors, "
          f"bbox={result.bbox}, "
          f"{sum(len(v) for v in result.polylines.values())} polylines")
