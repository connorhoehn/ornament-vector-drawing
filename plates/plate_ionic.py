"""Plate — The Ionic Order. Single-column Ionic demonstration.

Elevation drawing showing: pedestal + Ionic column (with volutes, per Vignola's
12-center construction) + full Ionic entablature (three-fascia architrave,
plain frieze, cornice with dentils and corona soffit), with cast shadow
hatching and a scale bar.
"""
from __future__ import annotations

from shapely.geometry import Polygon

import config
from engraving import canon, elements, hatching
from engraving.order_ionic import ionic_column_silhouette
from engraving.entablature_ionic import ionic_entablature
from engraving.render import Page, frame
from engraving.typography import title
from engraving.validate.plates import validate_plate_result


def _dedup_polylines(polylines):
    """Drop polylines that are duplicates of an earlier segment (same pair of
    endpoints, within 1e-6). Cheap O(n) with a hashable key; handles 2-point
    horizontals/verticals that are the main overlap source in entablatures.
    """
    seen = set()
    out = []
    for pl in polylines:
        if len(pl) == 2:
            p0, p1 = pl[0], pl[1]
            key_fwd = (round(p0[0], 4), round(p0[1], 4),
                       round(p1[0], 4), round(p1[1], 4))
            key_rev = (round(p1[0], 4), round(p1[1], 4),
                       round(p0[0], 4), round(p0[1], 4))
            if key_fwd in seen or key_rev in seen:
                continue
            seen.add(key_fwd)
        out.append(pl)
    return out


def build_validated() -> tuple[str, "object"]:
    """Render + validate. Returns (svg_path, ValidationReport)."""
    page = Page()
    frame(page)

    title_y = config.FRAME_INSET + 8
    title(page, "THE  IONIC  ORDER",
          x=config.PLATE_W / 2, y=title_y,
          font_size_mm=5.0, anchor="middle",
          stroke_width=config.STROKE_FINE)
    # Unicode right-single-quote so the apostrophe typesets cleanly.
    title(page, "\u2014 after Vignola, with Vignola\u2019s 12-center volute \u2014",
          x=config.PLATE_W / 2, y=title_y + 6,
          font_size_mm=2.8, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    # Vertical budget.
    # Ionic order = pedestal (3D) + column (9D) + entablature (9/4 D)
    #             = 3 + 9 + 2.25 = 14.25 D.
    # Reserve top+bottom margins for title, subtitle, ground line, scale bar.
    draw_h = config.PLATE_H - 2 * config.FRAME_INSET - 44
    D = draw_h / 14.25
    dims = canon.Ionic(D=D)

    ground_y = config.PLATE_H - config.FRAME_INSET - 20
    center_x = config.PLATE_W / 2

    # Single column centered — gives us a much bigger D (capital detail!).
    col_xs = [center_x]

    # Pedestal
    peds = [elements.pedestal(cx, ground_y, dims) for cx in col_xs]
    for ped in peds:
        page.polyline(ped["outline"], stroke_width=config.STROKE_MEDIUM)

    top_of_ped_y = peds[0]["top_y"]

    # Column (silhouette + volutes) — collect ElementResult for validation.
    column_results = []
    for cx in col_xs:
        col_result = ionic_column_silhouette(dims, cx, top_of_ped_y,
                                             return_result=True)
        column_results.append(col_result)
        # Main silhouettes at MEDIUM; everything else (rules, volute spirals,
        # echinus) at ORNAMENT — matches the original idx<2 MEDIUM, else
        # ORNAMENT pattern exactly. The legacy order was:
        #   [R, L, cap_top, col_bot, plinth_top, shaft_top_rule, abacus_bot,
        #    *volute_polys, echinus_center]
        for sil in col_result.polylines.get("silhouette", []):
            page.polyline(sil, stroke_width=config.STROKE_MEDIUM)
        for rule in col_result.polylines.get("rules", []):
            page.polyline(rule, stroke_width=config.STROKE_ORNAMENT)
        for v in col_result.polylines.get("volutes", []):
            page.polyline(v, stroke_width=config.STROKE_ORNAMENT)
        for e in col_result.polylines.get("echinus", []):
            page.polyline(e, stroke_width=config.STROKE_ORNAMENT)

    top_of_cap_y = top_of_ped_y - dims.column_h

    # Entablature: span 3 D on each side of the (single) column axis so the
    # cornice oversails convincingly and enough dentil bays show.
    ent_left = center_x - 3.0 * D
    ent_right = center_x + 3.0 * D
    ent_result = ionic_entablature(ent_left, ent_right, top_of_cap_y, dims,
                                   return_result=True)

    fascia_polys = ent_result.polylines.get("fasciae", [])
    for pl in _dedup_polylines(fascia_polys):
        page.polyline(pl, stroke_width=config.STROKE_FINE)
    for d in ent_result.polylines.get("dentils", []):
        page.polyline(d, stroke_width=config.STROKE_ORNAMENT, close=True)

    # --- Shadow hatching --------------------------------------------------
    def hatch_shadow(shadow, *, shaft: bool = False) -> None:
        # Spacing: shafts get tight 0.35 mm, other surfaces 0.45-0.50 mm.
        if shaft:
            spacing = 0.35
        else:
            density_map = {"light": 0.55, "medium": 0.45, "dark": 0.45}
            spacing = density_map.get(shadow.density, 0.45)
        lines = hatching.parallel_hatch(shadow.polygon,
                                        angle_deg=shadow.angle_deg,
                                        spacing=spacing)
        for ln in lines:
            page.polyline(ln, stroke_width=config.STROKE_HATCH)

    for sh in ent_result.shadows:
        hatch_shadow(sh)
    for ped in peds:
        for sh in ped["shadows"]:
            hatch_shadow(sh)

    # --- Pedestal-cap top surface ----------------------------------------
    # The pedestal cornice is 1.75 M half-wide; the column plinth is
    # (7/12) D = 1.166 M half-wide. Between the two there's a horizontal
    # shelf on either side of the plinth. Without a shadow there, the eye
    # reads a 'gap'. Hatch the exposed cap-top at 45 deg (light).
    M = dims.M
    half_corn = 1.75 * M
    plinth_half = (7.0 / 6.0) * D / 2
    cap_top_thickness = M * 0.12
    for cx in col_xs:
        # Left overhang of the pedestal cap (visible top surface).
        if half_corn > plinth_half + 1e-3:
            left_cap_top = Polygon([
                (cx - half_corn, top_of_ped_y - cap_top_thickness),
                (cx - plinth_half, top_of_ped_y - cap_top_thickness),
                (cx - plinth_half, top_of_ped_y),
                (cx - half_corn, top_of_ped_y),
            ])
            for ln in hatching.parallel_hatch(left_cap_top,
                                              angle_deg=45.0, spacing=0.5):
                page.polyline(ln, stroke_width=config.STROKE_HATCH)
            right_cap_top = Polygon([
                (cx + plinth_half, top_of_ped_y - cap_top_thickness),
                (cx + half_corn, top_of_ped_y - cap_top_thickness),
                (cx + half_corn, top_of_ped_y),
                (cx + plinth_half, top_of_ped_y),
            ])
            for ln in hatching.parallel_hatch(right_cap_top,
                                              angle_deg=45.0, spacing=0.5):
                page.polyline(ln, stroke_width=config.STROKE_HATCH)

    # Column-shaft shadow (tight hatch). The silhouette helper doesn't return
    # one for Ionic; approximate it here as a narrow band on the shaded side
    # of the shaft (right side, lit from upper-left).
    r_lo = dims.lower_diam / 2
    r_up = dims.upper_diam / 2
    y_shaft_bot = top_of_ped_y - dims.base_h
    y_shaft_top = y_shaft_bot - dims.shaft_h
    for cx in col_xs:
        shaft_shadow = Polygon([
            (cx + r_lo - M * 0.30, y_shaft_bot),
            (cx + r_lo, y_shaft_bot),
            (cx + r_up, y_shaft_top),
            (cx + r_up - M * 0.24, y_shaft_top),
        ])
        for ln in hatching.parallel_hatch(shaft_shadow,
                                          angle_deg=80.0, spacing=0.35):
            page.polyline(ln, stroke_width=config.STROKE_HATCH)

    # Ground line — extends a little past the pedestal
    ground_half = 3.0 * D
    page.polyline([(center_x - ground_half, ground_y),
                   (center_x + ground_half, ground_y)],
                  stroke_width=config.STROKE_MEDIUM)

    # Scale bar
    cap_y = config.PLATE_H - config.FRAME_INSET - 6
    page.polyline([(config.PLATE_W / 2 - 25, cap_y),
                   (config.PLATE_W / 2 + 25, cap_y)],
                  stroke_width=config.STROKE_FINE)
    for i in range(6):
        x = config.PLATE_W / 2 - 25 + i * 10
        page.polyline([(x, cap_y - 1.5), (x, cap_y)],
                      stroke_width=config.STROKE_HAIRLINE)
    page.text("50 mm", x=config.PLATE_W / 2, y=cap_y + 4,
              font_size=2.4, anchor="middle")

    svg_path = str(page.save_svg("plate_ionic"))

    collected = {
        "order_results": column_results,
        "entablature_results": [("ionic", ent_result, col_xs)],
    }
    report = validate_plate_result("plate_ionic", collected)
    return svg_path, report


def build() -> str:
    """Legacy API — return only the SVG path."""
    svg_path, _ = build_validated()
    return svg_path


if __name__ == "__main__":
    print(build())
