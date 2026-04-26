"""Plate — an arcade, an iconic classical element.

A five-bay semicircular arcade on square piers. Could represent the ground
floor of a palazzo, a cloister walk, or an aqueduct section.
"""
from __future__ import annotations

import config
from engraving.arcade import arcade
from engraving.render import Page, frame
from engraving.typography import title
from engraving.validate.plates import validate_plate_result


def build_validated() -> tuple[str, "object"]:
    """Render + validate. Returns (svg_path, ValidationReport)."""
    page = Page()
    frame(page)

    title(page, "AN  ARCADE  OF  FIVE  BAYS",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 8,
          font_size_mm=5.0, anchor="middle",
          stroke_width=config.STROKE_FINE)
    title(page, "— semicircular, after Vignola —",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 14,
          font_size_mm=2.8, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    # Arcade geometry: size the elevation so each bay's aspect is classical
    # (opening ≈ 2:1 tall:wide). For a 5-bay arcade across most of the
    # page width, that means a height proportional to the clear-span.
    margin = config.FRAME_INSET + 15
    width = config.PLATE_W - 2 * margin
    bay_count = 5
    pier_count = bay_count + 1
    pier_width_frac = 0.32
    bay_pitch = width / pier_count           # ≈ 35.8 mm
    clear_span = bay_pitch * (1 - pier_width_frac)
    # Classical Vignola proportion: total arcade height ≈ clear_span × 2.5
    # (pier clear = 2.0 clear_span; arch rise = clear_span/2; plus base
    # course and small margin).
    height = clear_span * 2.5 + 8.0
    x0 = margin
    # Vertically center the arcade within the available page area below
    # the title band.
    title_band_bot = config.FRAME_INSET + 20
    caption_band_top = config.PLATE_H - config.FRAME_INSET - 15
    usable = caption_band_top - title_band_bot
    y_base = title_band_bot + (usable + height) / 2.0

    result = arcade(x0=x0, y_base=y_base, width=width, height=height,
                    bay_count=bay_count, arch_type="semicircular",
                    pier_width_frac=pier_width_frac, with_keystones=True,
                    with_entablature=True)

    # Stroke with layered weights — heavier strokes for load-bearing /
    # enclosing elements, lighter for voussoir joints and molding edges.
    layer_weights = {
        "base_course": config.STROKE_MEDIUM,
        "piers":       config.STROKE_MEDIUM,
        "imposts":     config.STROKE_FINE,
        "arches":      config.STROKE_MEDIUM,
        "voussoirs":   config.STROKE_FINE,
        "keystones":   config.STROKE_FINE,
        "entablature": config.STROKE_FINE,
    }
    for layer, lines in result.polylines.items():
        sw = layer_weights.get(layer, config.STROKE_FINE)
        for pl in lines:
            page.polyline(pl, stroke_width=sw)

    # Scale bar (50 mm total, 10 mm tick spacing)
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

    svg_path = str(page.save_svg("plate_arcade"))

    # No order/entablature/facade in this plate — validate_plate_result
    # simply returns an empty ValidationReport.
    report = validate_plate_result("plate_arcade", {})
    return svg_path, report


def build() -> str:
    """Legacy API — return only the SVG path."""
    svg_path, _ = build_validated()
    return svg_path


if __name__ == "__main__":
    print(build())
