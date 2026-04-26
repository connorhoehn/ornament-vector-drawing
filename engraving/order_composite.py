"""Composite column silhouette + capital in elevation, after Ware's
*American Vignola* (1903), pp. 22-24.

The Composite order is Ware's hybrid: "the Composite Capital, Fig. 82: the
two lower rows of leaves and the Caulicoli are the same as in the
Corinthian. But the Caulicoli carry only a stunted leaf-bud, and the upper
row of leaves and the sixteen Volutes are replaced by the large Scrolls,
Echinus, and Astragal of a complete Ionic Capital, with four faces like
Scamozzi's."

So the capital reads, bottom-to-top, as:
  - astragal at shaft top (bead)
  - acanthus row 1 (lower) — 3 visible leaves in elevation
  - acanthus row 2 (upper) — 3 visible leaves, offset 45 deg
  - caulicoli + stunted leaf-buds (short zone of stubby stems)
  - intermediate astragal (bead) separating Corinthian lower / Ionic upper
  - echinus (ovolo) from shaft radius out to abacus edge
  - large Ionic scrolls — Scamozzi four-faced, big (½D tall, ½D apart,
    1½D wide per canon)
  - abacus — square block with concave sides (2D diagonal, 1½D flat sides)

Proportions (canon.Composite):
  column_D    = 10D  (same as Corinthian)
  base_D      = ½D   (Attic base, plinth + lower torus + scotia + upper
                       torus + fillet)
  capital_D   = ⁷⁄₆ D

This module mirrors the structure of `order_doric`/`order_ionic` — it
returns the same 7-polyline silhouette tuple first, then appends the
capital ornament polylines.

Fluting and entablature belong to separate modules.
"""
from __future__ import annotations

import math

from . import canon
from .acanthus import acanthus_leaf
from .geometry import (Point, Polyline, arc, cubic_bezier, line,
                       mirror_path_x, translate_path)
from .schema import ElementResult
from .volute import ionic_volute


def _arc(cx: float, cy: float, rx: float, ry: float,
         t0: float, t1: float, n: int) -> Polyline:
    pts: list[Point] = []
    for i in range(n):
        t = t0 + (t1 - t0) * (i / (n - 1))
        pts.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
    return pts


def composite_column_silhouette(dims: canon.Composite,
                                cx: float, base_y: float,
                                *, return_result: bool = False):
    """Return polylines for a Composite column in elevation.

    base_y = bottom of column (top of pedestal). Column grows up
             (y decreases, SVG y-down).
    cx    = column centerline x.

    If ``return_result=True``, returns an :class:`ElementResult` with named
    anchors and categorized polyline layers. Otherwise (default) returns the
    legacy flat list of polylines for backward compatibility.

    Return order (matches the Tuscan/Doric convention):
      [0] right silhouette
      [1] left silhouette
      [2] cap_top_rule
      [3] col_bot_rule
      [4] plinth_top_rule
      [5] shaft_top_rule
      [6] abacus_bot_rule
      + acanthus row 1 leaves (polylines)
      + acanthus row 2 leaves (polylines)
      + caulicoli leaf-bud bumps
      + echinus center curve
      + left volute polylines (outer, channel, eye)
      + right volute polylines (outer, channel, eye)
      + abacus outline polylines (top edge, concave sides, fleuron)
    """
    D = dims.D
    M = dims.M
    r_lo = D / 2            # = M
    r_up = dims.upper_diam / 2

    # ── Base (Attic base, ½D) ──────────────────────────────────────────
    # Same pattern as Ionic/Corinthian: plinth → lower torus → scotia →
    # upper torus → fillet.
    base_h = dims.base_h
    plinth_h = 0.30 * base_h
    lower_torus_h = 0.18 * base_h
    scotia_h = 0.18 * base_h
    upper_torus_h = 0.22 * base_h
    fillet_base_h = base_h - plinth_h - lower_torus_h - scotia_h - upper_torus_h

    plinth_half = (7.0 / 6.0) * D / 2                 # 7/12 D
    torus_r_lower = 0.5 * lower_torus_h
    torus_r_upper = 0.5 * upper_torus_h
    lower_torus_bulge = min(torus_r_lower, plinth_half - r_lo - 0.005 * D)
    upper_torus_bulge = min(torus_r_upper, plinth_half - r_lo - 0.015 * D)
    scotia_depth = 0.035 * D

    y_col_bot = base_y
    y_plinth_top = y_col_bot - plinth_h
    y_lower_torus_top = y_plinth_top - lower_torus_h
    y_scotia_top = y_lower_torus_top - scotia_h
    y_upper_torus_top = y_scotia_top - upper_torus_h
    y_base_top = y_upper_torus_top - fillet_base_h

    # ── Shaft ──────────────────────────────────────────────────────────
    # Linear entasis, r_up = 5/6 × D / 2. Cylindrical bottom third then
    # tapered to r_up.
    shaft_break_y = y_base_top - dims.shaft_h / 3.0
    y_shaft_top = y_base_top - dims.shaft_h

    # Small astragal (bead) terminating the shaft, just below the capital.
    astragal_r = D / 44.0
    astragal_h = 2 * astragal_r
    y_astragal_top = y_shaft_top - astragal_h

    # ── Capital (⁷⁄₆ D total) ──────────────────────────────────────────
    # Subdivide bottom-to-top:
    #   acanthus row 1 : 7/18 D
    #   acanthus row 2 : 7/18 D
    #   caulicoli zone :  1/12 D  (stunted leaf-buds)
    #   intermediate astragal : small bead
    #   echinus        :  1/9  D
    #   ionic scrolls  : remaining span (centered on eye = 1/3 D below
    #                    abacus bottom; scroll ½D tall per canon)
    #   abacus         :  1/6  D  (Corinthian-style)
    cap_h = dims.capital_h
    leaf_row_h = (1.0 / 3.0) * cap_h                # 7/18 D per row
    caulicoli_h = D / 12.0
    inter_astragal_r = D / 60.0
    inter_astragal_h = 2 * inter_astragal_r
    echinus_h = D / 9.0
    abacus_h = cap_h / 7.0                          # Corinthian-style thin abacus

    # Abacus width: classical Corinthian/Composite has 2D diagonal
    # measurement; the front-face flat span (between concave arcs) is ~1½D.
    abacus_half_diag = D                             # half of 2D diagonal
    abacus_half = (9.0 / 12.0) * D                   # 1½D / 2 = ¾D half-width

    # Place vertical anchors bottom-to-top inside the capital.
    y_cap_bot = y_astragal_top                       # top of the shaft astragal
    y_cap_top = y_cap_bot - cap_h

    y_row1_bot = y_cap_bot
    y_row1_top = y_row1_bot - leaf_row_h             # top of lower leaf row
    y_row2_bot = y_row1_top
    y_row2_top = y_row2_bot - leaf_row_h
    y_caul_bot = y_row2_top
    y_caul_top = y_caul_bot - caulicoli_h
    y_inter_astragal_bot = y_caul_top
    y_inter_astragal_top = y_inter_astragal_bot - inter_astragal_h
    y_echinus_bot = y_inter_astragal_top
    y_echinus_top = y_echinus_bot - echinus_h
    # Abacus sits at the very top.
    y_abacus_bot = y_cap_top + abacus_h
    # The Ionic scroll zone occupies [y_abacus_bot, y_echinus_top]. Eye
    # position: 1/3 D below the abacus bottom per spec.
    y_eye = y_abacus_bot + D / 3.0

    # ── Build right silhouette bottom-to-top (base → shaft → cap outer) ─
    R: list[Point] = []
    # Plinth
    R.append((cx + plinth_half, y_col_bot))
    R.append((cx + plinth_half, y_plinth_top))
    # Step inward to the lower torus
    R.append((cx + r_lo, y_plinth_top))
    # Lower torus
    l_tor_cy = y_plinth_top - torus_r_lower
    R += _arc(cx + r_lo, l_tor_cy,
              lower_torus_bulge, torus_r_lower,
              math.pi / 2, -math.pi / 2, 22)
    # Scotia — concave bite
    sc_cy = (y_lower_torus_top + y_scotia_top) / 2
    sc_half_h = (y_lower_torus_top - y_scotia_top) / 2
    R += _arc(cx + r_lo, sc_cy,
              scotia_depth, sc_half_h,
              -math.pi / 2, -3 * math.pi / 2, 22)
    # Upper torus
    u_tor_cy = y_scotia_top - torus_r_upper
    R += _arc(cx + r_lo, u_tor_cy,
              upper_torus_bulge, torus_r_upper,
              math.pi / 2, -math.pi / 2, 22)
    # Fillet above upper torus
    R.append((cx + r_lo, y_base_top))

    # Shaft: cylindrical third then linear taper
    R.append((cx + r_lo, shaft_break_y))
    R.append((cx + r_up, y_shaft_top))

    # Shaft-top astragal bead
    ast_cy = (y_shaft_top + y_astragal_top) / 2
    R += _arc(cx + r_up, ast_cy, astragal_r, astragal_r,
              math.pi / 2, -math.pi / 2, 13)

    # Capital outer silhouette: the bell is implicit — the leaves overlap
    # the outer outline. For the engraved silhouette we trace the bell as
    # a subtle flare that just barely opens up from r_up at the base to
    # the echinus outer radius at its top, so the acanthus rows overlay
    # cleanly. The silhouette keeps a clean bell profile from shaft astragal
    # up through the caulicoli zone, then flares into the echinus, then
    # into the abacus.
    bell_r_bot = r_up                                # at y_cap_bot
    bell_r_top = r_up + D / 12.0                     # slight flare at caulicoli top

    # Bell side: gentle outward curve (cubic) from (cx+r_up, y_cap_bot)
    # up to (cx+bell_r_top, y_inter_astragal_bot).
    bell_pts = cubic_bezier(
        (cx + bell_r_bot, y_cap_bot),
        (cx + bell_r_bot, y_cap_bot - cap_h * 0.35),
        (cx + bell_r_top, y_row2_top - cap_h * 0.05),
        (cx + bell_r_top, y_inter_astragal_bot),
        steps=24,
    )
    R.extend(bell_pts)

    # Intermediate astragal (small bead bulging right)
    inter_ast_cy = (y_inter_astragal_bot + y_inter_astragal_top) / 2
    R += _arc(cx + bell_r_top, inter_ast_cy,
              inter_astragal_r, inter_astragal_r,
              math.pi / 2, -math.pi / 2, 11)

    # Echinus — shallow convex ovolo from bell_r_top up & out to abacus
    # edge. Quarter-ellipse.
    echinus_project = abacus_half - bell_r_top
    R += _arc(cx + bell_r_top, y_echinus_top,
              echinus_project, echinus_h,
              math.pi / 2, 0.0, 20)

    # Abacus outline on the right: straight up from echinus top to cap top.
    R.append((cx + abacus_half, y_abacus_bot))
    R.append((cx + abacus_half, y_cap_top))

    L = mirror_path_x(R, cx)

    cap_top = [(cx - abacus_half, y_cap_top), (cx + abacus_half, y_cap_top)]
    col_bot = [(cx - plinth_half, y_col_bot), (cx + plinth_half, y_col_bot)]
    plinth_top = [(cx - plinth_half, y_plinth_top),
                  (cx + plinth_half, y_plinth_top)]
    shaft_top_rule = [(cx - r_up, y_shaft_top), (cx + r_up, y_shaft_top)]
    abacus_bot = [(cx - abacus_half, y_abacus_bot),
                  (cx + abacus_half, y_abacus_bot)]

    out: list[Polyline] = [R, L, cap_top, col_bot, plinth_top,
                           shaft_top_rule, abacus_bot]

    # Track ornament layers so that when ``return_result=True`` we can
    # categorize them in the ElementResult. They are still appended to
    # ``out`` in the historical order for backward compatibility.
    acanthus_row1_polys: list[Polyline] = []
    acanthus_row2_polys: list[Polyline] = []
    caulicoli_polys: list[Polyline] = []
    echinus_polys: list[Polyline] = []
    volute_polys: list[Polyline] = []
    abacus_polys: list[Polyline] = []
    fleuron_polys: list[Polyline] = []

    # ── Capital ornament ───────────────────────────────────────────────

    # Acanthus row 1 (lower) — 3 leaves in elevation. The row fills a band
    # from (cx - bell_r_bot) .. (cx + bell_r_bot) (with a slight widening
    # toward the top of the row). Center one on the axis, flank by two.
    leaf_h1 = leaf_row_h * 0.95
    leaf_w1 = (2 * bell_r_bot) / 3.0 * 1.05          # gentle horizontal overlap
    # Leaf center y (acanthus_leaf's local origin is at mid-height with
    # tip UP at -height/2 and base at +height/2).
    row1_cy = (y_row1_bot + y_row1_top) / 2
    row1_spacing = (2 * bell_r_bot) / 3.0
    row1_centers_x = [cx - row1_spacing, cx, cx + row1_spacing]
    for lx in row1_centers_x:
        leaf_polys = acanthus_leaf(width=leaf_w1, height=leaf_h1,
                                   lobe_count=5, teeth_per_lobe=5,
                                   turnover=0.3, variant="corinthian")
        for pl in leaf_polys:
            tp = translate_path(pl, lx, row1_cy)
            out.append(tp)
            acanthus_row1_polys.append(tp)

    # Acanthus row 2 (upper) — 3 leaves offset so they sit between the
    # row-1 leaves in plan (simulated here by offsetting by half the row-1
    # spacing). The center-back leaf peeks between the two front leaves —
    # smaller and slightly taller relative to the flanks so it reads as
    # partially obscured behind them. Each leaf is slightly larger (the
    # capital flares upward).
    leaf_h2 = leaf_row_h * 0.95
    row2_bell_r = bell_r_bot + D / 20.0              # bell slightly wider up here
    row2_spacing = (2 * row2_bell_r) / 3.0
    leaf_w2 = row2_spacing * 1.10
    row2_cy = (y_row2_bot + y_row2_top) / 2
    # Offset by half-spacing so row-2 leaves interleave with row-1 leaves.
    # Flanking leaves (front) + a slightly smaller center-back leaf that
    # reads as peeking between them in elevation.
    row2_flank_centers_x = [cx - 0.5 * row2_spacing,
                            cx + 0.5 * row2_spacing]
    for lx in row2_flank_centers_x:
        leaf_polys = acanthus_leaf(width=leaf_w2, height=leaf_h2,
                                   lobe_count=5, teeth_per_lobe=5,
                                   turnover=0.35, variant="corinthian")
        for pl in leaf_polys:
            tp = translate_path(pl, lx, row2_cy)
            out.append(tp)
            acanthus_row2_polys.append(tp)

    # Center-back leaf — on the centerline, slightly smaller and shifted
    # upward so its tip shows between the two flanking leaves' bases
    # (partially obscured, as in a three-quarter elevation view).
    center_back_w = leaf_w2 * 0.72
    center_back_h = leaf_h2 * 0.85
    center_back_cy = row2_cy - leaf_row_h * 0.10     # peek up slightly
    center_back = acanthus_leaf(width=center_back_w, height=center_back_h,
                                lobe_count=5, teeth_per_lobe=5,
                                turnover=0.35, variant="corinthian")
    for pl in center_back:
        tp = translate_path(pl, cx, center_back_cy)
        out.append(tp)
        acanthus_row2_polys.append(tp)

    # Caulicoli + stunted leaf-buds: short zone above row 2 with stubby
    # stems. Draw as small bumps (semicircular domes) at a few axial
    # positions, representing the tops of the caulicoli stems pressed
    # against the underside of the scrolls/echinus.
    caul_r = caulicoli_h * 0.45
    caul_cy = y_caul_bot - caul_r
    # Four bud positions across the capital — two per side.
    bud_xs = [cx - row2_bell_r * 0.70, cx - row2_bell_r * 0.25,
              cx + row2_bell_r * 0.25, cx + row2_bell_r * 0.70]
    for bx in bud_xs:
        bump = _arc(bx, caul_cy, caul_r, caul_r,
                    math.pi, 0.0, 17)               # top half-dome
        out.append(bump)
        caulicoli_polys.append(bump)
        # Short vertical stem below the bud
        stem = [(bx, y_caul_bot), (bx, y_caul_top + caul_r * 0.5)]
        out.append(stem)
        caulicoli_polys.append(stem)

    # Echinus center curve — a gentle hump visible between the two
    # scrolls, sitting just above the intermediate astragal.
    echinus_center_half = bell_r_top + echinus_project * 0.4
    echinus_center_ry = echinus_h * 0.9
    echinus_center = _arc(cx, y_echinus_bot,
                          echinus_center_half, echinus_center_ry,
                          math.pi, 2 * math.pi, 36)
    out.append(echinus_center)
    echinus_polys.append(echinus_center)

    # ── Ionic scrolls (Scamozzi — large, four-faced) ───────────────────
    # Canon Composite: scroll_height_D = ½D, scroll_spacing_D = ½D (eye
    # to eye), scroll_width_D = 1½D. The pair spans 2D outer-to-outer,
    # which matches the 2D abacus diagonal.
    #
    # Eye positions: spacing ½D so eyes sit at cx ± ¼D. But the spec also
    # says the scrolls should be big and cover half the abacus; the spec
    # says "eye at 1/3 D below the abacus bottom". Canonical Scamozzi
    # places each eye under the corner of the abacus — so place eyes at
    # the edge of the echinus projection (like Ionic), with the big
    # scroll covering the zone from the eye outward to the abacus corner
    # and inward to the echinus center. We use eye_x at the edge of the
    # full abacus interior, which matches the ½D scroll_spacing_D (eyes
    # are ½D apart) when scaled up.
    #
    # Use D/3 (1/3 D) as a good Scamozzi compromise — it places eyes at
    # roughly the echinus edge, giving the required "bigger than plain
    # Ionic" coverage.
    eye_x_right = cx + D / 3.0
    eye_x_left = cx - D / 3.0
    eye_y = y_eye

    # The stock ionic_volute already sizes to 4/9 D tall. For Composite
    # we want ½D tall — scale the volute polylines about the eye by
    # (½ / (4/9)) = 9/8 = 1.125.
    scroll_scale = (0.5) / (4.0 / 9.0)              # 1.125

    def _scale_about(pts: list[Point], sx: float, sy: float,
                     ox: float, oy: float) -> list[Point]:
        return [((x - ox) * sx + ox, (y - oy) * sy + oy) for x, y in pts]

    vl = ionic_volute(eye_x_left, eye_y, D,
                      direction="left", include_channel=True)
    vr = ionic_volute(eye_x_right, eye_y, D,
                      direction="right", include_channel=True)

    for key in ("outer", "channel", "eye"):
        for pl in vl.get(key, []):
            scaled = _scale_about(pl, scroll_scale, scroll_scale,
                                  eye_x_left, eye_y)
            out.append(scaled)
            volute_polys.append(scaled)
    for key in ("outer", "channel", "eye"):
        for pl in vr.get(key, []):
            scaled = _scale_about(pl, scroll_scale, scroll_scale,
                                  eye_x_right, eye_y)
            out.append(scaled)
            volute_polys.append(scaled)

    # ── Abacus concave-sided top with central fleuron ──────────────────
    # Each face of the abacus curves inward at its middle. Ware shows a
    # quarter-circle concavity whose chord equals the flat face span and
    # whose sagitta (depth) is a small fraction of D. The central fleuron
    # is a tiny rosette on each face.
    #
    # Front face runs from (cx - abacus_half, y_cap_top)
    # to (cx + abacus_half, y_cap_top). The concavity dips UP into the
    # abacus (y decreases) by sagitta ≈ D/24.
    sagitta = D / 24.0
    # Quadratic bezier for the top of the abacus face (a gentle upward dip).
    abacus_top_curve = cubic_bezier(
        (cx - abacus_half, y_cap_top),
        (cx - abacus_half * 0.40, y_cap_top - sagitta),
        (cx + abacus_half * 0.40, y_cap_top - sagitta),
        (cx + abacus_half, y_cap_top),
        steps=36,
    )
    out.append(abacus_top_curve)
    abacus_polys.append(abacus_top_curve)

    # Central fleuron — small rosette at the midpoint of the concave top.
    fleuron_cy = y_cap_top - sagitta
    fleuron_r = D / 40.0
    fleuron = arc(cx, fleuron_cy, fleuron_r, 0.0, 2.0 * math.pi, steps=32)
    if fleuron and fleuron[0] != fleuron[-1]:
        fleuron.append(fleuron[0])
    out.append(fleuron)
    fleuron_polys.append(fleuron)
    # 4 small petal notches around the fleuron
    for i in range(4):
        theta = i * math.pi / 2.0 + math.pi / 4.0
        petal_end = (cx + 1.6 * fleuron_r * math.cos(theta),
                     fleuron_cy + 1.6 * fleuron_r * math.sin(theta))
        petal = line((cx + fleuron_r * math.cos(theta),
                      fleuron_cy + fleuron_r * math.sin(theta)),
                     petal_end, steps=2)
        out.append(petal)
        fleuron_polys.append(petal)

    if not return_result:
        return out

    result = ElementResult(kind="composite_column", dims_ref=dims)
    result.add_polylines("silhouette", [R, L])
    result.add_polylines("rules", [cap_top, col_bot, plinth_top,
                                   shaft_top_rule, abacus_bot])
    result.add_polylines("acanthus", acanthus_row1_polys + acanthus_row2_polys)
    result.add_polylines("caulicoli", caulicoli_polys)
    result.add_polylines("echinus", echinus_polys)
    result.add_polylines("volutes", volute_polys)
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
    result.add_anchor("bell_bottom", cx, y_cap_bot)
    result.add_anchor("bell_top", cx, y_abacus_bot)
    result.add_anchor("abacus_bottom_right", cx + abacus_half, y_abacus_bot)
    result.add_anchor("abacus_bottom_left", cx - abacus_half, y_abacus_bot)
    result.add_anchor("abacus_top_right", cx + abacus_half, y_cap_top)
    result.add_anchor("abacus_top_left", cx - abacus_half, y_cap_top)
    result.add_anchor("top_center", cx, y_cap_top, "attach")
    result.add_anchor("axis", cx, (y_col_bot + y_cap_top) / 2, "axis")
    result.add_anchor("volute_eye_right", eye_x_right, eye_y, "center")
    result.add_anchor("volute_eye_left", eye_x_left, eye_y, "center")
    result.add_anchor("helix_right", eye_x_right, eye_y, "center")
    result.add_anchor("helix_left", eye_x_left, eye_y, "center")
    result.add_anchor("fleuron_center", cx, fleuron_cy, "center")
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
    result.metadata["num_acanthus_row1"] = 3
    result.metadata["num_acanthus_row2"] = 3
    result.metadata["num_caulicoli"] = 4
    result.metadata["num_volutes"] = 2
    result.metadata["has_fleuron"] = True
    # ── Subdivisional metadata (for finer-grained validation) ───────────
    # Attic base: plinth → lower torus → scotia → upper torus → fillet
    # (Ware p.24).
    result.metadata["base_plinth_h"] = y_col_bot - y_plinth_top
    result.metadata["base_lower_torus_h"] = y_plinth_top - y_lower_torus_top
    result.metadata["base_scotia_h"] = y_lower_torus_top - y_scotia_top
    result.metadata["base_upper_torus_h"] = y_scotia_top - y_upper_torus_top
    result.metadata["base_torus_h"] = (
        result.metadata["base_lower_torus_h"]
        + result.metadata["base_upper_torus_h"])
    result.metadata["base_fillet_h"] = y_upper_torus_top - y_base_top
    # Capital: acanthus row 1 + acanthus row 2 + caulicoli + echinus +
    # volute (scroll) zone + abacus (Ware p.24).
    result.metadata["cap_acanthus_row1_h"] = leaf_row_h
    result.metadata["cap_acanthus_row2_h"] = leaf_row_h
    result.metadata["cap_caulicoli_h"] = caulicoli_h
    result.metadata["cap_echinus_h"] = echinus_h
    # Volute height measured from the actual volute polylines (the scrolls
    # in Composite span a y-range that overlaps the echinus, not a separate
    # vertical zone in the capital).
    if volute_polys:
        _vys = [p[1] for pl in volute_polys for p in pl]
        result.metadata["cap_volute_h"] = max(_vys) - min(_vys)
    else:
        result.metadata["cap_volute_h"] = 0.0
    result.metadata["cap_abacus_h"] = y_abacus_bot - y_cap_top
    # Bell = acanthus row 1 + row 2 + caulicoli (everything below scrolls).
    result.metadata["cap_bell_h"] = (leaf_row_h * 2 + caulicoli_h
                                     + inter_astragal_h)
    result.compute_bbox()
    return result


# ── Smoke test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import drawsvg as dw

    dims = canon.Composite(D=24)
    polys = composite_column_silhouette(dims, cx=100, base_y=220)

    # Column spans y = [-20..220] and x = [82..118] at these params; pad and
    # size the viewBox to avoid clipping either end of the silhouette.
    W, H = 200.0, 280.0
    vb_x, vb_y = 0.0, -40.0
    d = dw.Drawing(width=f"{W}mm", height=f"{H}mm",
                   viewBox=f"{vb_x} {vb_y} {W} {H}")
    d.append(dw.Rectangle(vb_x, vb_y, W, H, fill="white"))

    for poly in polys:
        if len(poly) < 2:
            continue
        flat: list[float] = []
        for x, y in poly:
            flat.extend([x, y])
        d.append(dw.Lines(*flat, close=False, fill="none",
                          stroke="black", stroke_width=0.25,
                          stroke_linecap="round", stroke_linejoin="round"))

    d.save_svg("/tmp/composite_test.svg")
    print(f"Wrote /tmp/composite_test.svg — {len(polys)} polylines; "
          f"column height {dims.column_h:.1f} mm at D={dims.D} mm.")

    # Validation smoke test
    dims_v = canon.Composite(D=20.0)
    result = composite_column_silhouette(dims_v, 100.0, 200.0, return_result=True)
    assert result.kind == "composite_column"
    assert "bottom_center" in result.anchors
    assert "top_center" in result.anchors
    assert result.bbox != (0.0, 0.0, 0.0, 0.0)
    print(f"composite_column: {len(result.anchors)} anchors, "
          f"bbox={result.bbox}, "
          f"{sum(len(v) for v in result.polylines.values())} polylines")

    # Render to PNG via Playwright for visual inspection.
    try:
        from engraving.preview import render_svg_to_png
        out_png = render_svg_to_png('/tmp/composite_test.svg',
                                    '/tmp/composite_test.png', dpi=150)
        print(f"Wrote {out_png}")
    except Exception as exc:
        print(f"PNG preview skipped: {exc!r}")
