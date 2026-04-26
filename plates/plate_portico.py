"""Plate — tetrastyle Tuscan portico, elevation with cast shadows."""
from __future__ import annotations

import config
from engraving import elements, hatching, orders
from engraving.orders import tuscan_column_silhouette
from engraving.render import Page, frame
from engraving.typography import title
from engraving.validate.plates import validate_plate_result


def build_validated() -> tuple[str, "object"]:
    """Render + validate. Returns (svg_path, ValidationReport)."""
    page = Page()
    frame(page)

    title_y = config.FRAME_INSET + 8
    title(page, "A  TUSCAN  PORTICO",
          x=config.PLATE_W / 2, y=title_y,
          font_size_mm=5.0, anchor="middle",
          stroke_width=config.STROKE_FINE)
    title(page, "— after Vignola. Tetrastyle, eustyle intercolumniation —",
          x=config.PLATE_W / 2, y=title_y + 6,
          font_size_mm=2.8, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    # Pick a module that fits the plate comfortably.
    # Entablature + column + pedestal = 14 + 3.5 + 4 = 21.5 modules tall.
    # Plate interior (vertical): ~config.PLATE_H - 2*FRAME_INSET - title/caption ~ 155 mm
    # Choose M such that 21.5 M + pediment (span/2 * tan(14°)) fits.
    # Intercolumniation 4M, total width = 3*4M = 12M; half span ~6M -> pediment ~6M * 0.25 ~= 1.5M
    # Total vertical ~ 23M. So M ~= 6.7 mm.
    # Reserve 40 mm vertical: ~18 mm top (title + subtitle + clearance
    # to raking cornice) + ~16 mm bottom (scale bar).
    draw_area_h = config.PLATE_H - 2 * config.FRAME_INSET - 40
    M = draw_area_h / 23.0  # total vertical ≈ 23M (pedestal+col+ent+pediment)

    dims = orders.TuscanDims(D=2 * M)

    # Baseline: place ground_y so the pediment apex sits just under title.
    ground_y = config.PLATE_H - config.FRAME_INSET - 16  # room for a caption
    center_x = config.PLATE_W / 2

    portico = elements.tetrastyle_portico(center_x, ground_y, dims,
                                          intercolumniation_modules=4.0)

    # Collect ElementResult for each column by re-invoking the silhouette
    # builder with return_result=True (using the same cx/top_of_ped_y the
    # portico helper used internally). Visual rendering is unchanged —
    # this path is strictly additional bookkeeping for validation.
    top_of_ped_y = portico["pedestals"][0]["top_y"]
    column_results = [
        tuscan_column_silhouette(dims, cx, top_of_ped_y, return_result=True)
        for cx in portico["col_xs"]
    ]

    # --- Stroke everything ---
    # Ground line
    page.polyline(portico["ground"], stroke_width=config.STROKE_MEDIUM)

    # Pedestals
    for ped in portico["pedestals"]:
        page.polyline(ped["outline"], stroke_width=config.STROKE_MEDIUM, close=False)

    # Columns
    for col in portico["columns"]:
        for sil in col["silhouettes"]:
            page.polyline(sil, stroke_width=config.STROKE_MEDIUM)

    # Entablature polylines
    for pl in portico["entablature"]["polylines"]:
        page.polyline(pl, stroke_width=config.STROKE_FINE)
    # Dentils
    for d in portico["entablature"]["dentils"]:
        page.polyline(d, stroke_width=config.STROKE_HAIRLINE, close=True)

    # Pediment
    ped_el = portico["pediment"]
    page.polyline(ped_el["outer"], stroke_width=config.STROKE_MEDIUM)
    page.polyline(ped_el["inner"], stroke_width=config.STROKE_FINE)
    page.polyline(ped_el["bottom"], stroke_width=config.STROKE_MEDIUM)

    # --- Shadow hatching ---
    # Column-shaft shadows get tight 0.35 spacing; other soffits 0.50.
    # All hatch lines at STROKE_HATCH (0.12 mm) so they read as tone.
    def hatch_shadow(shadow, *, shaft: bool = False):
        if shaft:
            spacing = 0.35
        else:
            density_map = {"light": 0.55, "medium": 0.50, "dark": 0.45}
            spacing = density_map.get(shadow.density, 0.50)
        lines = hatching.parallel_hatch(shadow.polygon, angle_deg=shadow.angle_deg,
                                        spacing=spacing)
        for ln in lines:
            page.polyline(ln, stroke_width=config.STROKE_HATCH)

    for ped in portico["pedestals"]:
        for sh in ped["shadows"]:
            hatch_shadow(sh)
    for col in portico["columns"]:
        for sh in col["shadows"]:
            hatch_shadow(sh, shaft=True)
    for sh in portico["entablature"]["shadows"]:
        hatch_shadow(sh)
    for sh in ped_el["shadows"]:
        hatch_shadow(sh)

    # Caption: scale bar
    cap_y = config.PLATE_H - config.FRAME_INSET - 6
    page.polyline([(config.PLATE_W / 2 - 25, cap_y), (config.PLATE_W / 2 + 25, cap_y)],
                  stroke_width=config.STROKE_FINE)
    for i in range(6):
        x = config.PLATE_W / 2 - 25 + i * 10
        page.polyline([(x, cap_y - 1.5), (x, cap_y)], stroke_width=config.STROKE_HAIRLINE)
    page.text("50 mm", x=config.PLATE_W / 2, y=cap_y + 4,
              font_size=2.4, anchor="middle")

    svg_path = str(page.save_svg("plate_portico"))

    # Tuscan entablature (via elements.entablature) does not expose a
    # return_result API, so we only validate the columns. validate_plate_result
    # routes Tuscan order_results through TuscanValidation.
    collected = {"order_results": column_results}
    report = validate_plate_result("plate_portico", collected)
    return svg_path, report


def build() -> str:
    """Legacy API — return only the SVG path."""
    svg_path, _ = build_validated()
    return svg_path


if __name__ == "__main__":
    print(build())
