"""Plate — The Composite Order. Single-column Scamozzi-variant demonstration.

Elevation drawing showing: pedestal + Composite column (Corinthian-style
acanthus below, Ionic-style large scrolls above — the hybrid character) +
full Composite entablature (architrave with fasciae, frieze, cornice with
dentils, modillions, caissoned corona with rosettes), with cast shadow
hatching and a scale bar.

Per Ware's *American Vignola*: "the chief proportions [of the Composite
Order] are the same as the Corinthian Order." For v1 we use the Corinthian
entablature builder as-is (swapping only the dims instance, so dentil and
modillion rhythms match Corinthian). The column remains `canon.Composite`
so the capital retains its four-faced Scamozzi scrolls.
"""
from __future__ import annotations

import math

from shapely.geometry import Polygon

import config
from engraving import canon, elements, hatching
from engraving.order_composite import composite_column_silhouette
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

    title_y = config.FRAME_INSET + 8
    title(page, "THE  COMPOSITE  ORDER",
          x=config.PLATE_W / 2, y=title_y,
          font_size_mm=5.0, anchor="middle",
          stroke_width=config.STROKE_FINE)
    title(page, "\u2014 after Scamozzi, with Vignola\u2019s entablature \u2014",
          x=config.PLATE_W / 2, y=title_y + 6,
          font_size_mm=2.8, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    # Vertical budget. Total Composite order (ped + col + ent) =
    # 10/3 + 10 + 10/4 = 15.833 D. Same as Corinthian.
    top_margin = 22.0
    bottom_margin = 22.0
    draw_area_h = config.PLATE_H - 2 * config.FRAME_INSET - top_margin - bottom_margin
    D = draw_area_h / 15.833
    dims = canon.Composite(D=D)

    ground_y = config.PLATE_H - config.FRAME_INSET - bottom_margin
    center_x = config.PLATE_W / 2

    # Single column centered.
    col_xs = [center_x]

    peds = [elements.pedestal(cx, ground_y, dims) for cx in col_xs]
    for ped in peds:
        page.polyline(ped["outline"], stroke_width=config.STROKE_MEDIUM)

    top_of_ped_y = peds[0]["top_y"]

    # The legacy path used the flat polylines list where idx<2 = silhouette,
    # idx<7 = rules, idx>=7 = capital ornament. With return_result=True we
    # can walk the categorized layers instead and stroke at the same weights.
    column_results = []
    for cx in col_xs:
        col_result = composite_column_silhouette(dims, cx, top_of_ped_y,
                                                 return_result=True)
        column_results.append(col_result)
        for sil in col_result.polylines.get("silhouette", []):
            page.polyline(sil, stroke_width=config.STROKE_MEDIUM)
        for rule in col_result.polylines.get("rules", []):
            page.polyline(rule, stroke_width=config.STROKE_FINE)
        # Per-layer ornament weights so the capital reads as lacework, not
        # a mass. Dense tone layers (acanthus, caulicoli, bell_guides) at
        # HATCH so they resolve as texture; LINE layers (abacus, volutes,
        # echinus, helices, fleuron) at ORNAMENT.
        ornament_weights = {
            "acanthus":    config.STROKE_HATCH,
            "caulicoli":   config.STROKE_HATCH,
            "bell_guides": config.STROKE_HATCH,
            "helices":     config.STROKE_ORNAMENT,
            "fleuron":     config.STROKE_ORNAMENT,
            "volutes":     config.STROKE_ORNAMENT,
            "echinus":     config.STROKE_ORNAMENT,
            "abacus":      config.STROKE_FINE,
        }
        for layer_name in ("acanthus", "caulicoli", "echinus", "volutes",
                           "abacus", "fleuron", "helices", "bell_guides"):
            sw = ornament_weights.get(layer_name, config.STROKE_ORNAMENT)
            for pl in col_result.polylines.get(layer_name, []):
                page.polyline(pl, stroke_width=sw)

    top_of_cap_y = top_of_ped_y - dims.column_h

    # Entablature: use the Corinthian entablature builder.
    ent_left = center_x - 3.5 * D
    ent_right = center_x + 3.5 * D
    ent_dims = canon.Corinthian(D=dims.D)
    ent_result = corinthian_entablature(ent_left, ent_right, top_of_cap_y,
                                        ent_dims, col_xs, return_result=True)

    # Caisson-shadow filter (same as Corinthian plate).
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

    modillion_polys = ent_result.polylines.get("modillions", [])
    for idx, m in enumerate(modillion_polys):
        sw = config.STROKE_FINE if (idx % 2 == 0) else config.STROKE_ORNAMENT
        page.polyline(m, stroke_width=sw, close=True)

    for c in caisson_polys:
        page.polyline(c, stroke_width=config.STROKE_ORNAMENT, close=True)

    # Rosettes (center, radius) tuples are only available in the legacy dict
    # — re-invoke the builder with the same inputs to collect them without
    # perturbing visual output.
    ent_legacy = corinthian_entablature(ent_left, ent_right, top_of_cap_y,
                                        ent_dims, col_xs)
    # Rosettes — engraved 6-petal + ring + centre disc — all at ORNAMENT.
    for (rcx, rcy), rr in ent_legacy["rosettes"]:
        ring_pts = []
        for i in range(37):
            t = 2 * math.pi * i / 36
            ring_pts.append((rcx + rr * math.cos(t), rcy + rr * math.sin(t)))
        page.polyline(ring_pts, stroke_width=config.STROKE_ORNAMENT)
        inner_r = rr * 0.25
        disc_pts = []
        for i in range(25):
            t = 2 * math.pi * i / 24
            disc_pts.append((rcx + inner_r * math.cos(t),
                             rcy + inner_r * math.sin(t)))
        page.polyline(disc_pts, stroke_width=config.STROKE_ORNAMENT)
        for k in range(6):
            t = 2 * math.pi * k / 6
            page.polyline(
                [(rcx + inner_r * math.cos(t), rcy + inner_r * math.sin(t)),
                 (rcx + rr * 0.85 * math.cos(t),
                  rcy + rr * 0.85 * math.sin(t))],
                stroke_width=config.STROKE_ORNAMENT,
            )

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
            continue
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

    # --- Shaft shadow ----------------------------------------------------
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
    ground_half = 4.0 * D
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

    svg_path = str(page.save_svg("plate_composite"))

    # Column uses canon.Composite → Composite validator.
    # Entablature uses the Corinthian builder with canon.Corinthian dims, so
    # validate it as a Corinthian entablature.
    collected = {
        "order_results": column_results,
        "entablature_results": [("corinthian", ent_result, col_xs)],
    }
    report = validate_plate_result("plate_composite", collected)
    return svg_path, report


def build() -> str:
    """Legacy API — return only the SVG path."""
    svg_path, _ = build_validated()
    return svg_path


if __name__ == "__main__":
    print(build())
