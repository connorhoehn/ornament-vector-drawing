"""Plate 01 — bare framed plate. Day-1 sanity check."""
from __future__ import annotations

import config
from engraving.render import Page, frame
from engraving.validate.plates import validate_plate_result


def build_validated() -> tuple[str, "object"]:
    """Render + validate. Returns (svg_path, ValidationReport)."""
    page = Page()
    frame(page)
    # Tiny scale bar bottom-left for print-size verification
    x0 = config.FRAME_INSET + 4
    y0 = config.PLATE_H - config.FRAME_INSET - 4
    page.polyline([(x0, y0), (x0 + 50, y0)], stroke_width=config.STROKE_FINE)
    for i in range(6):
        page.polyline([(x0 + i * 10, y0 - 1.5), (x0 + i * 10, y0)],
                      stroke_width=config.STROKE_HAIRLINE)
    page.text("50 mm", x0 + 25, y0 + 4, font_size=2.4, anchor="middle")
    svg_path = str(page.save_svg("plate_01"))
    # plate_01 has no orders/entablatures/facades — empty report.
    report = validate_plate_result("plate_01", {})
    return svg_path, report


def build() -> str:
    """Legacy API — return only the SVG path."""
    svg_path, _ = build_validated()
    return svg_path


if __name__ == "__main__":
    out = build()
    print(out)
