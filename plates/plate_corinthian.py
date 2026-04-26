"""Plate — The Corinthian Order. Single-column elevation demonstration.

Elevation drawing showing: pedestal + Corinthian column (Attic base,
fluted shaft, acanthus-wrapped bell capital with helices, concave-sided
abacus with central fleuron) + full Corinthian entablature (three-fascia
architrave, plain frieze, cornice with dentils, modillions, caissoned
corona with rosettes, cymatium), cast shadow hatching, and a scale bar.
"""
from __future__ import annotations

from shapely.geometry import Polygon

import config
from engraving import canon, elements, hatching
from engraving.order_corinthian import corinthian_column_silhouette
from engraving.entablature_corinthian import corinthian_entablature
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

    title_y = config.FRAME_INSET + 6
    title(page, "THE  CORINTHIAN  ORDER",
          x=config.PLATE_W / 2, y=title_y,
          font_size_mm=5.0, anchor="middle",
          stroke_width=config.STROKE_FINE)
    title(page, "\u2014 after Vignola, with modillions and caissons \u2014",
          x=config.PLATE_W / 2, y=title_y + 5,
          font_size_mm=2.8, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    # Vertical budget.
    #   Total order = pedestal (10/3 D) + column (10 D) + entablature (10/4 D)
    #               = 3.333 + 10 + 2.5  =  15.833 D.
    top_margin = 14.0
    bottom_margin = 14.0
    draw_area_h = config.PLATE_H - 2 * config.FRAME_INSET - top_margin - bottom_margin
    D = draw_area_h / 15.833
    dims = canon.Corinthian(D=D)

    ground_y = config.PLATE_H - config.FRAME_INSET - bottom_margin
    center_x = config.PLATE_W / 2

    # Single column centered — doubles the effective D and lets the acanthus
    # wreath + helix spirals actually read at plate scale.
    col_xs = [center_x]

    # --- Pedestal ---------------------------------------------------------
    peds = [elements.pedestal(cx, ground_y, dims) for cx in col_xs]
    for ped in peds:
        page.polyline(ped["outline"], stroke_width=config.STROKE_MEDIUM)

    top_of_ped_y = peds[0]["top_y"]

    # --- Column -----------------------------------------------------------
    # The legacy path stroked the first 2 polys MEDIUM, the next 5 (rules)
    # FINE, and everything after (capital ornament) ORNAMENT. With
    # return_result=True we can do the same by layer name exactly.
    column_results = []
    for cx in col_xs:
        col_result = corinthian_column_silhouette(dims, cx, top_of_ped_y,
                                                  return_result=True)
        column_results.append(col_result)
        for sil in col_result.polylines.get("silhouette", []):
            page.polyline(sil, stroke_width=config.STROKE_MEDIUM)
        for rule in col_result.polylines.get("rules", []):
            page.polyline(rule, stroke_width=config.STROKE_FINE)
        # Layer-specific weights — at 9 leaves × ~15 polylines/leaf,
        # stroking everything at STROKE_ORNAMENT (0.18 mm) produces a
        # muddy black capital. The acanthus wreath should read as TONE;
        # the abacus, helices, and fleuron as LINE.
        for pl in col_result.polylines.get("abacus", []):
            page.polyline(pl, stroke_width=config.STROKE_FINE)
        for pl in col_result.polylines.get("helices", []):
            page.polyline(pl, stroke_width=config.STROKE_ORNAMENT)
        for pl in col_result.polylines.get("fleuron", []):
            page.polyline(pl, stroke_width=config.STROKE_ORNAMENT)
        for pl in col_result.polylines.get("caulicoli", []):
            page.polyline(pl, stroke_width=config.STROKE_HATCH)
        for pl in col_result.polylines.get("bell_guides", []):
            page.polyline(pl, stroke_width=config.STROKE_HATCH)
        # Acanthus is the densest layer; render it as hairline tone so
        # the reader's eye resolves the lobes as texture, not as
        # individual heavy lines.
        for pl in col_result.polylines.get("acanthus", []):
            page.polyline(pl, stroke_width=config.STROKE_HATCH)

    top_of_cap_y = top_of_ped_y - dims.column_h

    # --- Entablature ------------------------------------------------------
    # With one column axis, let the entablature span about 3.5 D on each
    # side so two or three modillion bays flank the central axis.
    ent_left = center_x - 3.5 * D
    ent_right = center_x + 3.5 * D
    ent_result = corinthian_entablature(ent_left, ent_right, top_of_cap_y,
                                        dims, col_xs, return_result=True)

    # Caissons for the shadow filter (same behaviour as before).
    caisson_polys = ent_result.polylines.get("caissons", [])
    caisson_bboxes = []
    for cais in caisson_polys:
        xs = [p[0] for p in cais]; ys = [p[1] for p in cais]
        caisson_bboxes.append((min(xs), min(ys), max(xs), max(ys)))

    def _is_caisson_interior(sh):
        try:
            sbx = sh.polygon.bounds
        except Exception:
            return False
        for bx in caisson_bboxes:
            if (abs(sbx[0] - bx[0]) < 1e-3 and abs(sbx[1] - bx[1]) < 1e-3
                    and abs(sbx[2] - bx[2]) < 1e-3 and abs(sbx[3] - bx[3]) < 1e-3):
                return True
        return False

    fascia_polys = ent_result.polylines.get("fasciae", [])
    for pl in _dedup_polylines(fascia_polys):
        page.polyline(pl, stroke_width=config.STROKE_FINE)

    for d in ent_result.polylines.get("dentils", []):
        page.polyline(d, stroke_width=config.STROKE_ORNAMENT, close=True)

    # Modillion outlines at FINE; their pendant acanthus (every 2nd entry)
    # at ORNAMENT so the leaves don't compete with the scroll outline.
    modillion_polys = ent_result.polylines.get("modillions", [])
    for idx, m in enumerate(modillion_polys):
        sw = config.STROKE_FINE if (idx % 2 == 0) else config.STROKE_ORNAMENT
        page.polyline(m, stroke_width=sw, close=True)

    # Caissons at ORNAMENT hairline.
    for c in caisson_polys:
        page.polyline(c, stroke_width=config.STROKE_ORNAMENT, close=True)

    # Rosettes — the ElementResult doesn't carry them in a polyline layer;
    # they live in metadata via count but the actual (center, radius)
    # tuples are only in the legacy dict. Re-invoke the builder in legacy
    # mode once to pick up the rosette list without perturbing the visual
    # output (same inputs → same rosettes).
    ent_legacy = corinthian_entablature(ent_left, ent_right, top_of_cap_y,
                                        dims, col_xs)
    for (center, radius) in ent_legacy["rosettes"]:
        page.circle(center[0], center[1], radius,
                    stroke_width=config.STROKE_ORNAMENT)

    # --- Shadow hatching --------------------------------------------------
    def hatch_shadow(shadow) -> None:
        density_map = {"light": 0.55, "medium": 0.50, "dark": 0.45}
        spacing = density_map.get(shadow.density, 0.50)
        lines = hatching.parallel_hatch(shadow.polygon,
                                        angle_deg=shadow.angle_deg,
                                        spacing=spacing)
        for ln in lines:
            page.polyline(ln, stroke_width=config.STROKE_HATCH)

    for sh in ent_result.shadows:
        if _is_caisson_interior(sh):
            continue  # let the caisson square + rosette speak for itself
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

    # --- Shaft shadow (not provided by the silhouette builder) -----------
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

    # --- Ground line ------------------------------------------------------
    ground_half = 4.0 * D
    page.polyline([(center_x - ground_half, ground_y),
                   (center_x + ground_half, ground_y)],
                  stroke_width=config.STROKE_MEDIUM)

    # --- Scale bar --------------------------------------------------------
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

    svg_path = str(page.save_svg("plate_corinthian"))

    collected = {
        "order_results": column_results,
        "entablature_results": [("corinthian", ent_result, col_xs)],
    }
    report = validate_plate_result("plate_corinthian", collected)
    return svg_path, report


def build() -> str:
    """Legacy API — return only the SVG path."""
    svg_path, _ = build_validated()
    return svg_path


if __name__ == "__main__":
    print(build())
