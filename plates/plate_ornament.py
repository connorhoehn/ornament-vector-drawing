"""Plate — a showcase of ornamental elements: festoons, trophies, medallions.

A single landscape plate with three rows:

  1. Top:    a wide leaf festoon spanning the plate between two knots.
  2. Middle: four trophies (martial / musical / scientific / naval).
  3. Bottom: three medallions (plain / wreath / wreath + ribbon).

Each row has a caption underneath.  Stroke weights follow the engraver's
hierarchy: silhouettes at fine, interior creases at hairline, and trophy
main masses (shields, lyres, globes, anchors) at medium for visual
weight.
"""
from __future__ import annotations

import config
from engraving import festoon, medallion, trophy
from engraving.render import Page, frame
from engraving.typography import title
from engraving.validate.plates import validate_plate_result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _draw_festoon(page: Page, f) -> None:
    """Festoon: spine + leaves/fruit silhouette at fine; knots at fine."""
    for pl in f.polylines.get("spine", []):
        page.polyline(pl, stroke_width=config.STROKE_FINE)
    for pl in f.polylines.get("elements", []):
        page.polyline(pl, stroke_width=config.STROKE_FINE)
    for pl in f.polylines.get("knots", []):
        page.polyline(pl, stroke_width=config.STROKE_FINE)


def _draw_trophy(page: Page, t) -> None:
    """Trophy main masses at medium; fine details at fine."""
    # Main-mass layers per style — the "hero" object gets medium weight.
    MAIN_LAYERS = {"shield", "lyre", "globe", "anchor"}
    for layer, lines in t.polylines.items():
        weight = (config.STROKE_MEDIUM if layer in MAIN_LAYERS
                  else config.STROKE_FINE)
        for pl in lines:
            page.polyline(pl, stroke_width=weight)


def _draw_medallion(page: Page, m) -> None:
    """Frame/ribbon at fine; wreath leaves at hairline."""
    for layer, lines in m.polylines.items():
        if layer == "wreath":
            weight = config.STROKE_HAIRLINE
        else:
            weight = config.STROKE_FINE
        for pl in lines:
            page.polyline(pl, stroke_width=weight)


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def build_validated() -> tuple[str, "object"]:
    """Render + validate. Returns (svg_path, ValidationReport)."""
    page = Page()
    frame(page)

    # --- Titles ----------------------------------------------------------
    title(page, "ORNAMENTAL  ELEMENTS",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 8,
          font_size_mm=5.0, anchor="middle",
          stroke_width=config.STROKE_FINE)
    title(page, "\u2014 festoons, trophies, medallions \u2014",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 14,
          font_size_mm=2.8, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    margin = config.FRAME_INSET + 6
    interior_top = config.FRAME_INSET + 22
    interior_bot = config.PLATE_H - config.FRAME_INSET - 18
    interior_h = interior_bot - interior_top
    row_h = interior_h / 3.0

    # --- Row 1: festoon --------------------------------------------------
    # Place the spine near the top of the top-third row; droop hangs into
    # the rest of the band.
    fest_y = interior_top + row_h * 0.30
    f = festoon.festoon(
        attach_left=(margin + 5, fest_y),
        attach_right=(config.PLATE_W - margin - 5, fest_y),
        droop=16, style="leaf", element_count=9,
    )
    _draw_festoon(page, f)
    # Festoon caption sits just under the spine's attachment line, above
    # the drooping leaves — keeps it clear of the central motif clutter.
    page.text("festoon (leaf style)",
              x=config.PLATE_W / 2,
              y=fest_y - 3,
              font_size=2.5, anchor="middle")

    # --- Row 2: four trophies --------------------------------------------
    trophy_y = interior_top + row_h + row_h * 0.45
    trophy_w = 32.0
    trophy_h = 44.0
    trophy_styles = ["martial", "musical", "scientific", "naval"]
    # Spread 4 columns evenly across interior width.
    band_x0 = margin + trophy_w / 2
    band_x1 = config.PLATE_W - margin - trophy_w / 2
    step = (band_x1 - band_x0) / (len(trophy_styles) - 1)
    trophy_xs = [band_x0 + i * step for i in range(len(trophy_styles))]

    for cx, style in zip(trophy_xs, trophy_styles):
        t = trophy.trophy(cx=cx, cy=trophy_y,
                          width=trophy_w, height=trophy_h, style=style)
        _draw_trophy(page, t)
        page.text(style,
                  x=cx, y=trophy_y + trophy_h / 2 + 7,
                  font_size=2.5, anchor="middle")

    # --- Row 3: three medallions -----------------------------------------
    # Sit the medallions a touch LOW in the third band so the outward-
    # projecting wreath leaves (which extend past the 50x32 envelope by
    # ~leaf_size) clear the trophy captions above.
    med_y = interior_top + row_h * 2 + row_h * 0.55
    med_w = 44.0
    med_h = 32.0
    med_configs = [
        ("plain",            False, False),
        ("with wreath",      True,  False),
        ("wreath + ribbon",  True,  True),
    ]
    # Column centers at 1/6, 1/2, 5/6 of the interior band.
    mband_x0 = margin + med_w / 2
    mband_x1 = config.PLATE_W - margin - med_w / 2
    mstep = (mband_x1 - mband_x0) / (len(med_configs) - 1)
    med_xs = [mband_x0 + i * mstep for i in range(len(med_configs))]

    for cx, (label, ww, wr) in zip(med_xs, med_configs):
        m = medallion.medallion(cx=cx, cy=med_y,
                                width=med_w, height=med_h,
                                with_wreath=ww, with_ribbon=wr)
        _draw_medallion(page, m)
        # Caption just below the medallion envelope; ribbon pendants are
        # allowed to hang past (they are asymmetric and short).
        page.text(label,
                  x=cx, y=med_y + med_h / 2 + 6,
                  font_size=2.5, anchor="middle")

    # --- Scale bar -------------------------------------------------------
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

    svg_path = str(page.save_svg("plate_ornament"))

    # No orders/entablatures/facades — empty collected dict.
    report = validate_plate_result("plate_ornament", {})
    return svg_path, report


def build() -> str:
    """Legacy API — return only the SVG path."""
    svg_path, _ = build_validated()
    return svg_path


if __name__ == "__main__":
    print(build())
