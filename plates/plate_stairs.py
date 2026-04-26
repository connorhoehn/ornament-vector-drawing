"""Plate — A straight flight of twelve steps.

Demonstrates ``engraving.stairs.straight_flight`` with Tuscan balusters and
a continuous sloped handrail.  Shadow hatches at each inside corner (where
the riser meets the tread below) read as the cast shadow of the nosing
above.
"""
from __future__ import annotations

from shapely.geometry import Polygon

import config
from engraving import hatching
from engraving.render import Page, frame
from engraving.stairs import straight_flight
from engraving.typography import title
from engraving.validate.plates import validate_plate_result


def build_validated() -> tuple[str, "object"]:
    """Render + validate. Returns (svg_path, ValidationReport)."""
    page = Page()
    frame(page)

    # --- Title band --------------------------------------------------------
    title(page, "A  STRAIGHT  FLIGHT  OF  TWELVE  STEPS",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 8,
          font_size_mm=5.0, anchor="middle",
          stroke_width=config.STROKE_FINE)
    title(page, "\u2014 with Tuscan balusters and continuous handrail \u2014",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 14,
          font_size_mm=2.8, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    # --- Flight geometry ---------------------------------------------------
    # The landscape 10x8 plate leaves ~216 mm width and ~165 mm height inside
    # the frame.  With 12 risers and balusters + handrail above the top
    # nosing, the riser pair (tread=22, riser=14) called out in the original
    # brief (run=264, rise=168) does not actually fit the landscape
    # interior — we compress the steps proportionally and shorten the
    # handrail a touch so the top baluster does not clip the title band.
    riser_count = 12
    tread = 15.0      # mm — was 22, compressed to fit 12 steps in 216 mm
    riser = 9.0       # mm — was 14, compressed to match classical 2R+T
    handrail_height = 30.0   # mm — was 90, reduced so the top end of the
                             # sloped rail clears the title band

    direction = "right"
    total_run = riser_count * tread   # 180 mm
    total_rise = riser_count * riser  # 108 mm

    # Horizontal centering: place the flight's bottom-left x0 so the full run
    # is centered across the usable page width.
    usable_x0 = config.FRAME_INSET + 3
    usable_w = config.PLATE_W - 2 * (config.FRAME_INSET + 3)
    x0 = usable_x0 + (usable_w - total_run) / 2.0

    # Vertical placement: the flight occupies the lower ~2/3 of the interior.
    # y_bottom sits a few mm above the caption strip.
    caption_band_top = config.PLATE_H - config.FRAME_INSET - 12
    y_bottom = caption_band_top - 4.0

    result = straight_flight(
        x0=x0, y_bottom=y_bottom, riser_count=riser_count,
        tread=tread, riser=riser,
        direction=direction,
        with_balustrade=True, with_handrail=True,
        handrail_height=handrail_height,
    )

    # --- Stroke layers -----------------------------------------------------
    layer_weights = {
        "stringer":  config.STROKE_MEDIUM,
        "treads":    config.STROKE_FINE,
        "risers":    config.STROKE_FINE,
        "balusters": config.STROKE_FINE,
        "handrail":  config.STROKE_FINE,
    }
    for layer, lines in result.polylines.items():
        sw = layer_weights.get(layer, config.STROKE_FINE)
        for pl in lines:
            page.polyline(pl, stroke_width=sw)

    # --- Ground line -------------------------------------------------------
    # Extend a short ground-line at the foot of the flight, clamped to the
    # interior of the frame.
    ground_left = max(config.FRAME_INSET + 4.0, x0 - tread * 1.2)
    page.polyline(
        [(ground_left, y_bottom), (x0, y_bottom)],
        stroke_width=config.STROKE_MEDIUM,
    )

    # --- Shadow hatches ----------------------------------------------------
    # At each inside corner (riser i foot meets tread i-1 surface) the
    # overhanging nosing casts a small triangular shadow.  For a
    # right-ascending flight that corner sits at (x_left_i, y_top_{i-1}).
    # We build a tiny right triangle there and parallel-hatch it at ~10°.
    shadow_polys: list[Polygon] = []
    shadow_run = tread * 0.35       # horizontal penetration of shadow
    shadow_drop = riser * 0.55      # vertical penetration of shadow
    for i in range(1, riser_count):
        x_left_i = x0 + i * tread
        y_top_prev = y_bottom - i * riser   # = y_top_{i-1}
        tri = Polygon([
            (x_left_i,                    y_top_prev),
            (x_left_i + shadow_run,       y_top_prev),
            (x_left_i,                    y_top_prev - shadow_drop),
        ])
        shadow_polys.append(tri)

    for poly in shadow_polys:
        lines = hatching.parallel_hatch(poly, angle_deg=10.0, spacing=0.45)
        for ln in lines:
            page.polyline(ln, stroke_width=config.STROKE_HATCH)

    # --- Scale bar ---------------------------------------------------------
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

    svg_path = str(page.save_svg("plate_stairs"))

    # Stairs don't map to the order/entablature/facade buckets — pass an
    # empty collection through the validator so the plumbing stays uniform.
    report = validate_plate_result("plate_stairs", {})
    return svg_path, report


def build() -> str:
    """Legacy API — return only the SVG path."""
    svg_path, _ = build_validated()
    return svg_path


if __name__ == "__main__":
    print(build())
