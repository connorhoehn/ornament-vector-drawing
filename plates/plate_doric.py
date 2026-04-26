"""Plate — The Doric Order. Two-column Mutulary Doric demonstration.

Elevation drawing showing: pedestals + Doric columns + full mutulary
entablature (architrave, frieze with triglyphs & metopes, cornice with
mutules & guttae), with cast shadow hatching and a scale bar.
"""
from __future__ import annotations

from shapely.geometry import Polygon

import config
from engraving import canon, elements, hatching
from engraving.order_doric import doric_column_silhouette
from engraving.entablature_doric import doric_entablature
from engraving.render import Page, frame
from engraving.typography import title
from engraving.validate.plates import validate_plate_result


def _dedup_polylines(polylines):
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
    title(page, "THE  DORIC  ORDER",
          x=config.PLATE_W / 2, y=title_y,
          font_size_mm=5.0, anchor="middle",
          stroke_width=config.STROKE_FINE)
    title(page, "\u2014 after Vignola, Mutulary variant \u2014",
          x=config.PLATE_W / 2, y=title_y + 6,
          font_size_mm=2.8, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    # Vertical budget. Total order (ped + col + ent) = 8/3 + 8 + 2 = 12.667 D.
    top_margin = 22.0
    bottom_margin = 22.0
    draw_area_h = config.PLATE_H - 2 * config.FRAME_INSET - top_margin - bottom_margin
    D = draw_area_h / 12.667
    dims = canon.Doric(D=D)

    ground_y = config.PLATE_H - config.FRAME_INSET - bottom_margin
    center_x = config.PLATE_W / 2

    # Two columns — Doric NEEDS this to show the triglyph rhythm.
    spacing = 5.0 * D
    col_xs = [center_x - spacing / 2, center_x + spacing / 2]

    peds = [elements.pedestal(cx, ground_y, dims) for cx in col_xs]
    for ped in peds:
        page.polyline(ped["outline"], stroke_width=config.STROKE_MEDIUM)

    top_of_ped_y = peds[0]["top_y"]

    # Columns — collect ElementResult for validation while stroking.
    column_results = []
    for cx in col_xs:
        col_result = doric_column_silhouette(dims, cx, top_of_ped_y,
                                             return_result=True)
        column_results.append(col_result)
        sils = col_result.polylines.get("silhouette", [])
        rules = col_result.polylines.get("rules", [])
        for sil in sils:
            page.polyline(sil, stroke_width=config.STROKE_MEDIUM)
        for rule in rules:
            page.polyline(rule, stroke_width=config.STROKE_FINE)

    top_of_cap_y = top_of_ped_y - dims.column_h

    # Entablature
    ent_left = col_xs[0] - D
    ent_right = col_xs[-1] + D
    ent_result = doric_entablature(ent_left, ent_right, top_of_cap_y, dims,
                                   col_xs, return_result=True)

    # Stroke fascia polylines (dedup since several horizontal/vertical edges
    # overlap on the architrave/frieze/cornice band seams).
    fascia_polys = ent_result.polylines.get("fasciae", [])
    for pl in _dedup_polylines(fascia_polys):
        page.polyline(pl, stroke_width=config.STROKE_FINE)
    for t in ent_result.polylines.get("triglyphs", []):
        page.polyline(t, stroke_width=config.STROKE_FINE, close=True)
    for m in ent_result.polylines.get("metopes", []):
        page.polyline(m, stroke_width=config.STROKE_ORNAMENT, close=True)
    for mu in ent_result.polylines.get("mutules", []):
        page.polyline(mu, stroke_width=config.STROKE_FINE, close=True)
    # Guttae — both the mutule stipple (many) and the regula drops. All
    # dropped to ORNAMENT so the stipple reads as texture, not blobs.
    for g in ent_result.polylines.get("guttae", []):
        page.polyline(g, stroke_width=config.STROKE_ORNAMENT, close=True)

    # --- Shadow hatching --------------------------------------------------
    def hatch_shadow(shadow) -> None:
        # Triglyph V-channel shadows are tall narrow verticals; give them
        # slightly tighter spacing than a flat soffit.
        density_map = {"light": 0.55, "medium": 0.50, "dark": 0.45}
        spacing = density_map.get(shadow.density, 0.50)
        # Tighten the V-channel channel to 0.40 mm so it reads as shade
        # rather than stripes.
        if shadow.angle_deg > 80 and shadow.density == "dark":
            spacing = 0.40
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

    # --- Pedestal-cap top surface hatch ----------------------------------
    M = dims.M
    half_corn = 1.75 * M
    plinth_half = (7.0 / 6.0) * D / 2
    cap_top_thickness = M * 0.12
    for cx in col_xs:
        if half_corn > plinth_half + 1e-3:
            for side in (-1, +1):
                x_inner = cx + side * plinth_half
                x_outer = cx + side * half_corn
                xs = sorted([x_inner, x_outer])
                poly = Polygon([
                    (xs[0], top_of_ped_y - cap_top_thickness),
                    (xs[1], top_of_ped_y - cap_top_thickness),
                    (xs[1], top_of_ped_y),
                    (xs[0], top_of_ped_y),
                ])
                for ln in hatching.parallel_hatch(poly, angle_deg=45.0,
                                                  spacing=0.5):
                    page.polyline(ln, stroke_width=config.STROKE_HATCH)

    # --- Shaft shadow (tight hatch) --------------------------------------
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

    # Ground line
    ground_half = spacing / 2 + 2.5 * D
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

    svg_path = str(page.save_svg("plate_doric"))

    collected = {
        "order_results": column_results,
        "entablature_results": [("doric", ent_result, col_xs)],
    }
    report = validate_plate_result("plate_doric", collected)
    return svg_path, report


def build() -> str:
    """Legacy API — return only the SVG path."""
    svg_path, _ = build_validated()
    return svg_path


if __name__ == "__main__":
    print(build())
