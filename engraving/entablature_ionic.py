"""Ionic entablature in elevation, after Ware's *American Vignola* (1903), pp. 15–18.

Total height 2¼ D, subdivided:
  - Architrave  ⅝D : three fasciae of equal height, crowned by ovolo + fillet
                     (this small crowning molding replaces the Doric taenia).
  - Frieze      ¾D : plain band (sometimes sculpted — left empty in v1).
  - Cornice     ⅞D : bed mold (cyma reversa) → dentil course → corona (with
                     a small cavetto drip beneath it) → cymatium (cyma recta).

Dentils are cut at height 1/12 D, width 1/18 D, on-center spacing 1/6 D so the
interdentil gap is 1/12 D — larger than the tooth itself.

The cornice projects outward from the architrave/frieze face via a stepped
corbel: each band of the architrave projects slightly more than the one
beneath it, the frieze projects a trifle farther, and the cornice projects
substantially to cast the characteristic deep soffit shadow.

Coordinate convention: elevation drawing, y increases downward (SVG).
"""
from __future__ import annotations

from shapely.geometry import Polygon

from . import canon
from . import profiles as P
from .elements import Shadow
from .geometry import Point, Polyline, line, translate_path


def ionic_entablature(left_x: float, right_x: float, top_of_capital_y: float,
                      dims: canon.Ionic,
                      *, return_result: bool = False):
    """Ionic entablature spanning from left_x to right_x, sitting on top of
    the capital at y = top_of_capital_y. Grows upward (smaller y).

    Returns:
        When ``return_result`` is ``False`` (default), a dict with keys:
          polylines  list[Polyline]  outline + band rules + molding profiles
          shadows    list[Shadow]    corona soffit, dentil interstices, fascia shades
          dentils    list[Polyline]  closed rectangles for the dentil course
          top_y      float           y of the very top of the cymatium
          left_edge  float           outermost x on the left (cornice projection)
          right_edge float           outermost x on the right (cornice projection)
        When ``return_result`` is ``True``, an ``ElementResult`` with anchors,
        metadata (architrave_h, frieze_h, cornice_h, total_h, num_dentils),
        and categorized polylines.
    """
    D = dims.D
    M = dims.M

    arch_h = dims.architrave_h                # ⅝D
    frieze_h = dims.frieze_h                  # ¾D
    corn_h = dims.cornice_h                   # ⅞D

    # --- Vertical divisions (y grows downward) ---------------------------
    y_arch_bot = top_of_capital_y
    y_arch_top = y_arch_bot - arch_h
    y_frieze_top = y_arch_top - frieze_h
    y_cornice_top = y_frieze_top - corn_h

    # Fasciae: three bands + crowning ovolo+fillet occupying roughly ⅛D.
    # Use 3/16 D for each fascia (total 9/16 D) and 1/16 D for ovolo+fillet
    # so the four pieces sum to 10/16 = 5/8 D (the architrave height).
    fascia_h = (3.0 / 16.0) * D
    crown_h = arch_h - 3 * fascia_h           # = 1/16 D
    ovolo_h = crown_h * 0.65
    crown_fillet_h = crown_h - ovolo_h

    # Horizontal projection scheme. Units in M for legibility.
    proj_f1 = 0.00 * M                        # bottom fascia flush
    proj_f2 = 0.08 * M
    proj_f3 = 0.16 * M
    proj_crown = 0.26 * M                     # ovolo + fillet lip
    proj_frieze_bot = 0.30 * M
    proj_frieze_top = 0.36 * M

    # Cornice bands (bottom → top of the cornice)
    bedmold_h = (1.0 / 8.0) * D               # ⅛D  cyma-reversa bed mold
    dentil_band_h = (1.0 / 6.0) * D           # ⅙D  dentil course + framing fillets
    cymatium_h = (1.0 / 4.0) * D              # ¼D  cyma recta at top
    # Corona fills what's left, with a small cavetto drip below it.
    corona_total_h = corn_h - bedmold_h - dentil_band_h - cymatium_h
    drip_h = (1.0 / 24.0) * D                 # small cavetto below corona
    corona_h = corona_total_h - drip_h

    # y boundaries within the cornice
    y_bedmold_bot = y_frieze_top
    y_bedmold_top = y_bedmold_bot - bedmold_h
    y_dentil_bot = y_bedmold_top
    y_dentil_top = y_dentil_bot - dentil_band_h
    y_drip_bot = y_dentil_top
    y_drip_top = y_drip_bot - drip_h
    y_corona_bot = y_drip_top
    y_corona_top = y_corona_bot - corona_h
    y_cym_bot = y_corona_top
    y_cym_top = y_cym_bot - cymatium_h
    assert abs(y_cym_top - y_cornice_top) < 1e-6

    # Cornice projection increments (each step projects further than prior)
    proj_bedmold_bot = proj_frieze_top
    proj_bedmold_top = proj_bedmold_bot + 0.35 * M
    proj_dentil_front = proj_bedmold_top + 0.10 * M
    proj_corona_front = proj_dentil_front + 0.55 * M
    proj_cym_top = proj_corona_front + 0.30 * M

    polylines: list[Polyline] = []
    shadows: list[Shadow] = []

    # ========================================================================
    #   ARCHITRAVE — three fasciae, corbeled outward, crowned by ovolo+fillet
    # ========================================================================
    # Fascia 1 (bottom), Fascia 2 (middle), Fascia 3 (top) — each ~3/16 D tall.
    y_f1_bot = y_arch_bot
    y_f1_top = y_arch_bot - fascia_h
    y_f2_bot = y_f1_top
    y_f2_top = y_f2_bot - fascia_h
    y_f3_bot = y_f2_top
    y_f3_top = y_f3_bot - fascia_h
    y_crown_bot = y_f3_top
    y_crown_top = y_arch_top

    # Horizontal rules at fascia boundaries (bottom, between 1-2, between 2-3,
    # top of fascia 3, bottom of frieze)
    polylines.append(line((left_x - proj_f1, y_f1_bot),
                          (right_x + proj_f1, y_f1_bot)))
    polylines.append(line((left_x - proj_f2, y_f1_top),
                          (right_x + proj_f2, y_f1_top)))
    polylines.append(line((left_x - proj_f3, y_f2_top),
                          (right_x + proj_f3, y_f2_top)))
    polylines.append(line((left_x - proj_f3, y_f3_top),
                          (right_x + proj_f3, y_f3_top)))

    # Vertical edges of each fascia (left + right) forming the stepped corbel
    # Left side:
    polylines.append(line((left_x - proj_f1, y_f1_bot),
                          (left_x - proj_f1, y_f1_top)))
    polylines.append(line((left_x - proj_f2, y_f1_top),
                          (left_x - proj_f2, y_f2_top)))
    polylines.append(line((left_x - proj_f3, y_f2_top),
                          (left_x - proj_f3, y_f3_top)))
    # Right side:
    polylines.append(line((right_x + proj_f1, y_f1_bot),
                          (right_x + proj_f1, y_f1_top)))
    polylines.append(line((right_x + proj_f2, y_f1_top),
                          (right_x + proj_f2, y_f2_top)))
    polylines.append(line((right_x + proj_f3, y_f2_top),
                          (right_x + proj_f3, y_f3_top)))

    # Crowning ovolo + fillet on top of fascia 3. Ovolo profile drawn on both
    # sides; a horizontal rule carries across the full length.
    ovolo_proj = proj_crown - proj_f3
    # Right side ovolo: grows from (right_x + proj_f3, y_crown_bot) up to
    # (right_x + proj_crown, y_crown_bot - ovolo_h).
    ovolo_right = P.ovolo(ovolo_h, ovolo_proj,
                          x0=right_x + proj_f3, y0=y_crown_bot - ovolo_h)
    # profiles grow downward by convention; flip vertically about the top
    # attach point so it reads as an upward-curving crown here.
    ovolo_right = [(x, 2 * (y_crown_bot - ovolo_h) + ovolo_h - y) for x, y in ovolo_right]
    polylines.append(ovolo_right)
    # Mirror the right-side profile about the span centerline
    # (x_mirror = left_x + right_x − x), NOT about left_x alone.
    ovolo_left = [(left_x + right_x - x, y) for x, y in ovolo_right]
    polylines.append(ovolo_left)

    # Fillet above the ovolo — a thin horizontal band at width = proj_crown.
    polylines.append(line((left_x - proj_crown, y_crown_bot - ovolo_h),
                          (right_x + proj_crown, y_crown_bot - ovolo_h)))
    polylines.append(line((left_x - proj_crown, y_crown_top),
                          (right_x + proj_crown, y_crown_top)))
    polylines.append(line((left_x - proj_crown, y_crown_bot - ovolo_h),
                          (left_x - proj_crown, y_crown_top)))
    polylines.append(line((right_x + proj_crown, y_crown_bot - ovolo_h),
                          (right_x + proj_crown, y_crown_top)))

    # Light shadows underneath each fascia (where it overhangs the one below).
    for (y_over, proj_over, proj_under) in [
            (y_f1_top, proj_f2, proj_f1),
            (y_f2_top, proj_f3, proj_f2),
            (y_f3_top, proj_crown, proj_f3)]:
        if proj_over - proj_under <= 0:
            continue
        band_h = fascia_h * 0.18
        poly = Polygon([
            (left_x - proj_over, y_over),
            (right_x + proj_over, y_over),
            (right_x + proj_over, y_over + band_h),
            (left_x - proj_over, y_over + band_h),
        ])
        shadows.append(Shadow(poly, angle_deg=10.0, density="light"))

    # ========================================================================
    #   FRIEZE — plain rectangular band with tiny top + bottom projections
    # ========================================================================
    # Canonical shared-y rule: each horizontal rule shared between two adjacent
    # bands is emitted by exactly one of them — the LOWER band's top edge.
    # The architrave's crown-fillet top already supplies y_arch_top, so the
    # frieze does NOT re-emit its bottom rule. Slanted side edges still run
    # from the architrave's crown projection up to the frieze top projection.
    polylines.append(line((left_x - proj_frieze_top, y_frieze_top),
                          (right_x + proj_frieze_top, y_frieze_top)))
    polylines.append(line((left_x - proj_frieze_bot, y_arch_top),
                          (left_x - proj_frieze_top, y_frieze_top)))
    polylines.append(line((right_x + proj_frieze_bot, y_arch_top),
                          (right_x + proj_frieze_top, y_frieze_top)))

    # ========================================================================
    #   CORNICE — bed mold, dentils, corona (with drip), cymatium
    # ========================================================================
    # --- Bed mold (cyma reversa) ---
    bedmold_proj = proj_bedmold_top - proj_bedmold_bot
    cr_right = P.cyma_reversa(bedmold_h, bedmold_proj,
                              x0=right_x + proj_bedmold_bot, y0=y_bedmold_bot - bedmold_h)
    # flip vertically so it opens upward-outward
    cr_right = [(x, 2 * (y_bedmold_bot - bedmold_h / 2) - y) for x, y in cr_right]
    polylines.append(cr_right)
    cr_left = [(left_x + right_x - x, y) for x, y in cr_right]
    polylines.append(cr_left)
    # Bed mold top rule
    polylines.append(line((left_x - proj_bedmold_top, y_bedmold_top),
                          (right_x + proj_bedmold_top, y_bedmold_top)))

    # --- Dentil course ---
    # Fillet above bedmold / below dentils: small sliver at top of bedmold.
    # Dentil framing: a thin fillet above + below the teeth (each ≈ 1/24 D).
    dentil_frame_h = (1.0 / 24.0) * D
    y_dentil_tooth_bot = y_dentil_bot - dentil_frame_h
    y_dentil_tooth_top = y_dentil_tooth_bot - (D / 12.0)
    # Tooth row must fit between the two framing fillets
    actual_tooth_h = y_dentil_tooth_bot - y_dentil_tooth_top
    # Top and framing rails of dentil band. We do NOT emit a rule at
    # y_dentil_bot — that horizontal is already supplied by the bed mold's
    # top rule above (canonical lower-band-owns-the-shared-edge rule).
    polylines.append(line((left_x - proj_dentil_front, y_dentil_tooth_bot),
                          (right_x + proj_dentil_front, y_dentil_tooth_bot)))
    polylines.append(line((left_x - proj_dentil_front, y_dentil_tooth_top),
                          (right_x + proj_dentil_front, y_dentil_tooth_top)))
    polylines.append(line((left_x - proj_dentil_front, y_dentil_top),
                          (right_x + proj_dentil_front, y_dentil_top)))

    # Vertical edges of the dentil band
    polylines.append(line((left_x - proj_dentil_front, y_dentil_bot),
                          (left_x - proj_dentil_front, y_dentil_top)))
    polylines.append(line((right_x + proj_dentil_front, y_dentil_bot),
                          (right_x + proj_dentil_front, y_dentil_top)))

    # Teeth — Ware's canonical proportions:
    #   width  = 1/18 D
    #   oc     = 1/6 D  (canon: dentil_oc_D)
    #   gap    = oc − width = 1/6 − 1/18 = 3/18 − 1/18 = 2/18 = 1/9 D
    # For D=20 mm over a ~260 mm span this gives ~66 dentils (Ware p.18 tab.).
    tooth_w = D / 18.0
    oc_target = dims.dentil_oc_D * D          # 1/6 D per canon
    gap = oc_target - tooth_w                 # = D/9
    dentil_length = (right_x + proj_dentil_front) - (left_x - proj_dentil_front)
    dentils = P.dentil_strip(dentil_length, tooth_w, actual_tooth_h, gap,
                             x0=left_x - proj_dentil_front,
                             y0=y_dentil_tooth_top)

    # Dentil interstice shadows — each gap between teeth casts a narrow dark rect.
    if dentils:
        for a, b in zip(dentils, dentils[1:]):
            # a is left tooth, b is right tooth
            xa_right = a[1][0]                # right edge of left tooth
            xb_left = b[0][0]                 # left edge of right tooth
            if xb_left <= xa_right:
                continue
            gap_poly = Polygon([
                (xa_right, y_dentil_tooth_top),
                (xb_left, y_dentil_tooth_top),
                (xb_left, y_dentil_tooth_bot),
                (xa_right, y_dentil_tooth_bot),
            ])
            shadows.append(Shadow(gap_poly, angle_deg=90.0, density="dark"))

    # --- Drip (small cavetto under corona) ---
    drip_proj = proj_corona_front - proj_dentil_front
    cav_right = P.cavetto(drip_h, drip_proj,
                          x0=right_x + proj_dentil_front, y0=y_drip_bot - drip_h)
    # flip to read as a drip receding outward-upward
    cav_right = [(x, 2 * (y_drip_bot - drip_h / 2) - y) for x, y in cav_right]
    polylines.append(cav_right)
    cav_left = [(left_x + right_x - x, y) for x, y in cav_right]
    polylines.append(cav_left)

    # --- Corona (large plain band) ---
    polylines.append(line((left_x - proj_corona_front, y_drip_top),
                          (right_x + proj_corona_front, y_drip_top)))
    polylines.append(line((left_x - proj_corona_front, y_corona_top),
                          (right_x + proj_corona_front, y_corona_top)))
    polylines.append(line((left_x - proj_corona_front, y_drip_top),
                          (left_x - proj_corona_front, y_corona_top)))
    polylines.append(line((right_x + proj_corona_front, y_drip_top),
                          (right_x + proj_corona_front, y_corona_top)))

    # Corona soffit shadow — the deep, dark band under the corona's projection.
    # Soffit sits between the dentil face and the corona front face, along
    # y = y_corona_bot (top of drip) = y_drip_top.
    soffit = Polygon([
        (left_x - proj_corona_front, y_dentil_top),
        (right_x + proj_corona_front, y_dentil_top),
        (right_x + proj_dentil_front, y_drip_top),
        (left_x - proj_dentil_front, y_drip_top),
    ])
    shadows.append(Shadow(soffit, angle_deg=15.0, density="dark"))

    # --- Cymatium (cyma recta at top) ---
    cym_proj = proj_cym_top - proj_corona_front
    cym_right = P.cyma_recta(cymatium_h, cym_proj,
                             x0=right_x + proj_corona_front, y0=y_cym_bot - cymatium_h)
    cym_right = [(x, 2 * (y_cym_bot - cymatium_h / 2) - y) for x, y in cym_right]
    polylines.append(cym_right)
    cym_left = [(left_x + right_x - x, y) for x, y in cym_right]
    polylines.append(cym_left)

    # Top rule of cymatium
    polylines.append(line((left_x - proj_cym_top, y_cym_top),
                          (right_x + proj_cym_top, y_cym_top)))

    left_edge = left_x - proj_cym_top
    right_edge = right_x + proj_cym_top

    legacy = {
        "polylines": polylines,
        "shadows": shadows,
        "dentils": dentils,
        "top_y": y_cornice_top,
        "left_edge": left_edge,
        "right_edge": right_edge,
    }
    if not return_result:
        return legacy

    from .schema import ElementResult
    result = ElementResult(kind="ionic_entablature", dims_ref=dims)
    result.add_polylines("fasciae", polylines)
    result.add_polylines("dentils", dentils)
    result.shadows = list(shadows)

    # Attach anchors at the capital-top (bottom_*) and cymatium-top (top_*).
    result.add_anchor("bottom_left", left_x, top_of_capital_y, "attach")
    result.add_anchor("bottom_right", right_x, top_of_capital_y, "attach")
    result.add_anchor("top_left", left_edge, y_cornice_top, "attach")
    result.add_anchor("top_right", right_edge, y_cornice_top, "attach")

    # Horizontal-level anchors on the left side (centerline info).
    result.add_anchor("architrave_top", left_x, y_arch_top)
    result.add_anchor("frieze_top", left_x, y_frieze_top)
    result.add_anchor("dentil_band_bottom", left_x - proj_dentil_front, y_dentil_bot)
    result.add_anchor("dentil_band_top", left_x - proj_dentil_front, y_dentil_top)
    result.add_anchor("corona_top", left_x - proj_corona_front, y_corona_top)

    result.metadata["num_dentils"] = len(dentils)
    result.metadata["architrave_h"] = y_arch_bot - y_arch_top
    result.metadata["frieze_h"] = y_arch_top - y_frieze_top
    result.metadata["cornice_h"] = y_frieze_top - y_cornice_top
    result.metadata["total_h"] = top_of_capital_y - y_cornice_top
    result.compute_bbox()
    return result


# --- Smoke test ----------------------------------------------------------

if __name__ == "__main__":
    dims = canon.Ionic(D=20)
    result = ionic_entablature(left_x=40, right_x=260,
                               top_of_capital_y=200, dims=dims)
    dentil_oc_mm = dims.dentil_oc_D * dims.D
    expected_dentils = (260 - 40) / dentil_oc_mm
    print(f"Ionic entablature (D={dims.D} mm):")
    print(f"  entablature height  = {dims.entablature_h:.2f} mm "
          f"(= {dims.entablature_D} D)")
    print(f"  architrave          = {dims.architrave_h:.2f} mm")
    print(f"  frieze              = {dims.frieze_h:.2f} mm")
    print(f"  cornice             = {dims.cornice_h:.2f} mm")
    print(f"  polylines           = {len(result['polylines'])}")
    print(f"  shadows             = {len(result['shadows'])}")
    print(f"  dentils             = {len(result['dentils'])} "
          f"(expected ~{expected_dentils:.1f})")
    print(f"  top_y               = {result['top_y']:.2f}")
    print(f"  left_edge           = {result['left_edge']:.2f}")
    print(f"  right_edge          = {result['right_edge']:.2f}")
