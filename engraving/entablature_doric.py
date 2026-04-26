"""Doric Mutulary entablature in elevation, after Ware's *American Vignola*
(1903), pp. 11-14.

The Doric entablature is 2D tall:
  - Architrave ½D (subdivided: lower band ⅓, upper band ⅓, taenia+regula+guttae ⅓)
  - Frieze ¾D (triglyphs ½D wide × ¾D tall alternating with metopes ¾D × ¾D)
  - Cornice ¾D (Mutulary variant — four equal bands: cap-of-triglyph fillet,
    bed mold, corona, cymatium)

Triglyphs are centered over every column axis AND at the midpoint between
adjacent columns. Each triglyph carries a regula (with 6 guttae pendant) just
below the taenia, and a mutule on the cornice soffit directly above. Metopes
fill the spaces between triglyphs; at each end of the run a corner-metope
fragment (1/6 D wide) completes the rhythm.

Coordinate convention: mm, y DOWN. The entablature grows UPWARD (decreasing y)
from `top_of_capital_y`.
"""
from __future__ import annotations

from shapely.geometry import Polygon

from . import canon
from .elements import Shadow
from .geometry import Point, Polyline, line, rect_corners


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _hline(x0: float, x1: float, y: float) -> Polyline:
    return [(x0, y), (x1, y)]


def _vline(x: float, y0: float, y1: float) -> Polyline:
    return [(x, y0), (x, y1)]


def _rect(x: float, y_top: float, w: float, h: float) -> Polyline:
    """Closed rect. x = left, y_top = smaller y (higher on page), h grows DOWN."""
    return [
        (x, y_top),
        (x + w, y_top),
        (x + w, y_top + h),
        (x, y_top + h),
        (x, y_top),
    ]


# ---------------------------------------------------------------------------
# main builder
# ---------------------------------------------------------------------------

def doric_entablature(left_x: float, right_x: float, top_of_capital_y: float,
                      dims: canon.Doric,
                      column_axes_x: list[float],
                      *, return_result: bool = False):
    """Doric Mutulary entablature. See module docstring for rationale.

    When ``return_result`` is ``False`` (default) returns the legacy dict
    (backward compatible for plates). When ``True`` returns an
    ``ElementResult`` with categorized polylines, anchors, metadata, and a
    computed bbox — consumed by the validation library.
    """
    D = dims.D
    M = dims.M

    # --- canonical sub-heights ----------------------------------------------
    arch_h = dims.architrave_h          # ½D
    fr_h = dims.frieze_h                # ¾D
    corn_h = dims.cornice_h             # ¾D

    # y levels (remember: smaller y = higher on page)
    y_arch_bot = top_of_capital_y
    y_arch_top = y_arch_bot - arch_h
    y_frieze_bot = y_arch_top
    y_frieze_top = y_frieze_bot - fr_h
    y_corn_bot = y_frieze_top
    y_corn_top = y_corn_bot - corn_h

    # --- projections (forward of column face) -------------------------------
    # Doric rhythm: architrave face is flush; frieze face sits back a hair so
    # triglyphs stand proud; cornice oversails by ~½D over the triglyph face.
    project_arch = 0.0
    project_fr = -M * 0.05        # slight recess
    project_corn = 0.5 * D        # ½D — classic mutulary oversail

    ax0 = left_x - project_arch
    ax1 = right_x + project_arch
    fx0 = left_x - project_fr     # NB: project_fr is negative → fx0 > left_x
    fx1 = right_x + project_fr
    cx0 = left_x - project_corn
    cx1 = right_x + project_corn

    polylines: list[Polyline] = []
    shadows: list[Shadow] = []
    triglyphs: list[Polyline] = []
    metopes: list[Polyline] = []
    guttae: list[Polyline] = []
    mutules: list[Polyline] = []

    # =========================================================================
    # 1. ARCHITRAVE  (½D)
    # =========================================================================
    # Outer box
    polylines.append(_hline(ax0, ax1, y_arch_bot))
    polylines.append(_hline(ax0, ax1, y_arch_top))
    polylines.append(_vline(ax0, y_arch_top, y_arch_bot))
    polylines.append(_vline(ax1, y_arch_top, y_arch_bot))

    # Divide architrave vertically: lower band 1/3, upper band 1/3, taenia
    # region 1/3. Ware: the taenia/regula/guttae occupy the TOP third.
    third = arch_h / 3.0
    y_band_mid = y_arch_bot - third            # top of lower band
    y_band_upper_top = y_arch_bot - 2 * third  # top of middle (upper-band) = bottom of taenia region
    polylines.append(_hline(ax0, ax1, y_band_mid))
    polylines.append(_hline(ax0, ax1, y_band_upper_top))

    # Light shadow on the bottom of the architrave (under-bevel hint)
    arch_under = Polygon([
        (ax0, y_arch_bot - arch_h * 0.08),
        (ax1, y_arch_bot - arch_h * 0.08),
        (ax1, y_arch_bot),
        (ax0, y_arch_bot),
    ])
    shadows.append(Shadow(arch_under, angle_deg=10.0, density="light"))

    # --- Taenia: thin fillet along the very top of the architrave ----------
    taenia_h = D / 22.0          # ≈ 1/22 D
    taenia_proj = taenia_h       # projects forward by its own height
    # Taenia occupies the top of the taenia-region (top third's upper slice)
    y_taenia_top = y_arch_top                # coincides with top of architrave
    y_taenia_bot = y_arch_top + taenia_h     # (grows DOWN into the taenia region)
    # Horizontal rule marking bottom edge of the taenia
    polylines.append(_hline(ax0 - taenia_proj, ax1 + taenia_proj, y_taenia_bot))
    # Vertical tips of the taenia's projection at each end
    polylines.append(_vline(ax0 - taenia_proj, y_taenia_top, y_taenia_bot))
    polylines.append(_vline(ax1 + taenia_proj, y_taenia_top, y_taenia_bot))

    # =========================================================================
    # 2. FRIEZE  (¾D) — triglyphs + metopes
    # =========================================================================
    polylines.append(_hline(fx0, fx1, y_frieze_bot))
    polylines.append(_hline(fx0, fx1, y_frieze_top))
    polylines.append(_vline(fx0, y_frieze_top, y_frieze_bot))
    polylines.append(_vline(fx1, y_frieze_top, y_frieze_bot))

    trig_w = dims.triglyph_width_D * D        # ½D
    corner_metope_w = dims.corner_metope_D * D  # 1/6 D

    # --- triglyph centers: one on each column axis, one at each midpoint ---
    axes = sorted(column_axes_x)
    trig_centers: list[float] = list(axes)
    for a, b in zip(axes, axes[1:]):
        trig_centers.append((a + b) / 2.0)
    trig_centers.sort()

    # --- draw triglyphs ----------------------------------------------------
    # A triglyph is ½D wide, ¾D tall. It has two full vertical V-channels and
    # two half-channels flanking. The face splits into 5 equal vertical slivers:
    #   | shank | chan | shank | chan | shank |   where the outer shanks are
    # half-width so the channels read as full. A flat "cap" fillet crowns it.
    cap_h = fr_h / 12.0   # small fillet across triglyph top (breaks at angles)
    shank_w = trig_w / 5.0   # 5 equal slivers across the face

    for cx in trig_centers:
        tx0 = cx - trig_w / 2
        # closed outline
        trig_rect = _rect(tx0, y_frieze_top, trig_w, fr_h)
        triglyphs.append(trig_rect)
        # outline strokes explicitly (so a plate that skips the triglyphs list
        # still picks them up in polylines)
        polylines.append(_hline(tx0, tx0 + trig_w, y_frieze_top))
        polylines.append(_vline(tx0, y_frieze_top, y_frieze_bot))
        polylines.append(_vline(tx0 + trig_w, y_frieze_top, y_frieze_bot))

        # Cap of triglyph — thin horizontal rule a cap_h below the top.
        polylines.append(_hline(tx0, tx0 + trig_w, y_frieze_top + cap_h))

        # Two full V-channels: centers at 2/5 and 3/5 of the triglyph width
        # (i.e. second and fourth sliver centerlines).
        # Each V-channel drawn as a *pair* of vertical lines marking the
        # channel edges, plus a centerline (the deepest part of the V).
        for i in (1, 2, 3):  # three interior shank/channel boundaries
            x_edge = tx0 + i * shank_w
            polylines.append(_vline(x_edge, y_frieze_top + cap_h, y_frieze_bot))
        # Centerlines of the two full channels (V-groove bottom)
        for ch_i in (1, 2):  # channels are at slivers 2 and 4 (1-indexed: 2, 4)
            # sliver 2 center = tx0 + 1.5 * shank_w; sliver 4 center = tx0 + 3.5*shank_w
            x_cl = tx0 + (ch_i * 2 - 0.5) * shank_w
            polylines.append(_vline(x_cl, y_frieze_top + cap_h, y_frieze_bot))

        # Half-channels flanking: centerlines at the very edges of the triglyph
        # — these are the left and right half-grooves. (Two single centerlines.)
        # Already implicit in tx0 and tx0+trig_w as vertical edges; nothing to
        # add unless we want a recessed sliver line.

        # Small shadow in each full V-channel
        for ch_i in (1, 2):
            x_cl = tx0 + (ch_i * 2 - 0.5) * shank_w
            ch_shadow = Polygon([
                (x_cl - shank_w * 0.25, y_frieze_top + cap_h),
                (x_cl + shank_w * 0.25, y_frieze_top + cap_h),
                (x_cl + shank_w * 0.25, y_frieze_bot),
                (x_cl - shank_w * 0.25, y_frieze_bot),
            ])
            shadows.append(Shadow(ch_shadow, angle_deg=85.0, density="dark"))

    # --- draw metopes (fills between adjacent triglyphs + corner fragments) ---
    # Interior metopes: between every pair of adjacent triglyphs.
    trig_centers_sorted = sorted(trig_centers)
    for cL, cR in zip(trig_centers_sorted, trig_centers_sorted[1:]):
        mx0 = cL + trig_w / 2
        mx1 = cR - trig_w / 2
        if mx1 - mx0 > 1e-6:
            metopes.append(_rect(mx0, y_frieze_top, mx1 - mx0, fr_h))
            # Its edges are already provided by the triglyphs' vertical lines
            # plus the frieze top/bottom; no new strokes required.

    # Corner metopes: from frieze edge to first/last triglyph outer face.
    # These are small fragments (~1/6 D).
    first_trig_left = trig_centers_sorted[0] - trig_w / 2
    last_trig_right = trig_centers_sorted[-1] + trig_w / 2
    # left corner metope
    if first_trig_left - fx0 > 1e-6:
        w = first_trig_left - fx0
        metopes.append(_rect(fx0, y_frieze_top, w, fr_h))
    # right corner metope
    if fx1 - last_trig_right > 1e-6:
        w = fx1 - last_trig_right
        metopes.append(_rect(last_trig_right, y_frieze_top, w, fr_h))

    # =========================================================================
    # 3. REGULAE + GUTTAE (in the taenia region of the architrave,
    #    one set under each triglyph)
    # =========================================================================
    # Regula: thin listel directly under the taenia, aligned with its triglyph,
    # width = trig_w, height roughly = taenia_h.
    regula_h = taenia_h
    y_regula_top = y_taenia_bot                   # sits just under the taenia
    y_regula_bot = y_regula_top + regula_h        # downward

    # Gutta: 6 small rectangles hanging below each regula, equal spacing.
    gutta_count = dims.gutta_count                # 6
    gutta_h = (third - taenia_h - regula_h) * 0.75  # fits in taenia region
    # width per gutta: a tight fraction of the slot
    slot_w = trig_w / gutta_count
    gutta_w = slot_w * 0.55
    y_gutta_top = y_regula_bot
    y_gutta_bot = y_gutta_top + gutta_h

    for cx in trig_centers:
        tx0 = cx - trig_w / 2
        # Regula rectangle (closed polyline)
        reg = _rect(tx0, y_regula_top, trig_w, regula_h)
        polylines.append(reg)
        # Rules on the regula's edges (already in the closed polyline; but
        # stroking the horizontal rules separately helps plate renderers).
        polylines.append(_hline(tx0, tx0 + trig_w, y_regula_bot))

        # 6 guttae spaced across the regula's width
        for i in range(gutta_count):
            gx0 = tx0 + (i + 0.5) * slot_w - gutta_w / 2
            guttae.append(_rect(gx0, y_gutta_top, gutta_w, gutta_h))

    # =========================================================================
    # 4. CORNICE  (¾D) — Mutulary variant: 4 equal horizontal bands.
    # =========================================================================
    # Bands, top to bottom: cymatium, corona, bed mold, cap-of-triglyph fillet.
    # (Ware numbers them from the frieze upward: cap fillet first, then bed
    # mold, then corona, then cymatium.) Each band = ¼ × corn_h.
    band_h = corn_h / 4.0
    # y from cornice bottom upward (y decreases):
    y_c_cap_top = y_corn_bot - band_h           # top of cap-of-triglyph
    y_c_bed_top = y_c_cap_top - band_h          # top of bed mold
    y_c_corona_top = y_c_bed_top - band_h       # top of corona
    # y_corn_top = y_c_corona_top - band_h (cymatium band sits on top)

    # Outer cornice rectangle
    polylines.append(_hline(cx0, cx1, y_corn_bot))
    polylines.append(_hline(cx0, cx1, y_corn_top))
    polylines.append(_vline(cx0, y_corn_top, y_corn_bot))
    polylines.append(_vline(cx1, y_corn_top, y_corn_bot))

    # Three interior band rules
    polylines.append(_hline(cx0, cx1, y_c_cap_top))
    polylines.append(_hline(cx0, cx1, y_c_bed_top))
    polylines.append(_hline(cx0, cx1, y_c_corona_top))

    # Soffit shadow (dense hatch under the corona, between frieze face and
    # cornice's front edge).
    soffit_poly = Polygon([
        (cx0, y_corn_bot),
        (cx1, y_corn_bot),
        (fx1, y_corn_bot + band_h * 0.35),
        (fx0, y_corn_bot + band_h * 0.35),
    ])
    shadows.append(Shadow(soffit_poly, angle_deg=10.0, density="dark"))

    # =========================================================================
    # 5. MUTULES  (one per triglyph, on the cornice soffit)
    # =========================================================================
    # Mutule: thin rectangular plaque under the corona's soffit, centered on
    # each triglyph. Width slightly less than triglyph, projection ≈ ½D — but
    # in elevation it reads as a rectangle whose height = the cap-of-triglyph
    # band. Carries a stipple of guttae (~18) across its face.
    mutule_h = band_h * 0.9                   # most of the cap-of-triglyph band
    mutule_w = trig_w * 0.95                  # slightly narrower than triglyph
    y_mutule_top = y_corn_bot - mutule_h      # sits just above the frieze line
    # Mutule gutta stipple
    mu_gutta_rows = 3
    mu_gutta_cols = 6                         # 3 × 6 = 18 small drops per mutule
    mu_gw = mutule_w / (mu_gutta_cols * 1.6)
    mu_gh = mutule_h / (mu_gutta_rows * 1.8)
    for cx in trig_centers:
        mx0 = cx - mutule_w / 2
        mutules.append(_rect(mx0, y_mutule_top, mutule_w, mutule_h))
        # Stipple the guttae on the mutule face
        for r in range(mu_gutta_rows):
            for c in range(mu_gutta_cols):
                gx = mx0 + (c + 0.5) * (mutule_w / mu_gutta_cols) - mu_gw / 2
                gy = y_mutule_top + (r + 0.5) * (mutule_h / mu_gutta_rows) - mu_gh / 2
                guttae.append(_rect(gx, gy, mu_gw, mu_gh))

    legacy = {
        "polylines": polylines,
        "shadows": shadows,
        "triglyphs": triglyphs,
        "metopes": metopes,
        "guttae": guttae,
        "mutules": mutules,
        "top_y": y_corn_top,
        "left_edge": cx0,
        "right_edge": cx1,
    }
    if not return_result:
        return legacy

    from .schema import ElementResult
    result = ElementResult(kind="doric_entablature", dims_ref=dims)
    result.add_polylines("fasciae", polylines)
    result.add_polylines("triglyphs", triglyphs)
    result.add_polylines("metopes", metopes)
    result.add_polylines("guttae", guttae)
    result.add_polylines("mutules", mutules)
    result.shadows = list(shadows)

    # Attach / edge anchors (bottom = on-capital, top = cornice top).
    result.add_anchor("bottom_left", cx0, top_of_capital_y, "attach")
    result.add_anchor("bottom_right", cx1, top_of_capital_y, "attach")
    result.add_anchor("top_left", cx0, y_corn_top, "attach")
    result.add_anchor("top_right", cx1, y_corn_top, "attach")

    # Architrave / frieze / cornice level anchors
    result.add_anchor("architrave_bottom_left", ax0, y_arch_bot)
    result.add_anchor("architrave_bottom_right", ax1, y_arch_bot)
    result.add_anchor("architrave_top_left", ax0, y_arch_top)
    result.add_anchor("architrave_top_right", ax1, y_arch_top)
    result.add_anchor("frieze_bottom_left", fx0, y_frieze_bot)
    result.add_anchor("frieze_bottom_right", fx1, y_frieze_bot)
    result.add_anchor("frieze_top_left", fx0, y_frieze_top)
    result.add_anchor("frieze_top_right", fx1, y_frieze_top)
    result.add_anchor("cornice_bottom_left", cx0, y_corn_bot)
    result.add_anchor("cornice_bottom_right", cx1, y_corn_bot)

    # Triglyph centers as "triglyph_i" anchors. Closed-polyline rects repeat
    # their first vertex, which skews a naive mean; use bbox centre instead.
    for i, trig in enumerate(triglyphs):
        xs = [p[0] for p in trig]
        ys = [p[1] for p in trig]
        result.add_anchor(f"triglyph_{i}",
                          (min(xs) + max(xs)) / 2.0,
                          (min(ys) + max(ys)) / 2.0, "center")

    result.metadata["num_triglyphs"] = len(triglyphs)
    result.metadata["num_metopes"] = len(metopes)
    result.metadata["num_guttae"] = len(guttae)
    result.metadata["num_mutules"] = len(mutules)
    result.metadata["architrave_h"] = y_arch_bot - y_arch_top
    result.metadata["frieze_h"] = y_arch_top - y_frieze_top
    result.metadata["cornice_h"] = y_frieze_top - y_corn_top
    result.metadata["total_h"] = top_of_capital_y - y_corn_top
    result.compute_bbox()
    return result


# ---------------------------------------------------------------------------
# smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    dims = canon.Doric(D=20)
    result = doric_entablature(
        left_x=40,
        right_x=260,
        top_of_capital_y=200,
        dims=dims,
        column_axes_x=[60, 120, 180, 240],
    )
    print(f"triglyphs: {len(result['triglyphs'])}")
    print(f"metopes:   {len(result['metopes'])}")
    print(f"mutules:   {len(result['mutules'])}")
    # Separate regula-guttae (6 per triglyph) from mutule-guttae (18 per mutule)
    regula_guttae_count = len(result['triglyphs']) * dims.gutta_count
    mutule_guttae_count = len(result['guttae']) - regula_guttae_count
    print(f"guttae (regula): {regula_guttae_count}")
    print(f"guttae (mutule): {mutule_guttae_count}")
    print(f"guttae (total):  {len(result['guttae'])}")
    print(f"polylines: {len(result['polylines'])}")
    print(f"shadows:   {len(result['shadows'])}")
    print(f"top_y: {result['top_y']}")
    print(f"left_edge: {result['left_edge']}  right_edge: {result['right_edge']}")
