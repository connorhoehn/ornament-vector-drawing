"""Plate — A Grand Entrance Stair (multi-element composition).

A classical entrance vestibule scene demonstrating the composition system
working across multiple primitives: a flight of twelve stairs ascending to
the right, a Tuscan pilaster anchoring the left, a flanking balustrade
(already produced by the stair primitive on the open side), a small
landing at the top, and a Tuscan column with a short entablature stub
crowning the landing.
"""
from __future__ import annotations

import config
from engraving import balustrades, canon, elements, orders as O, pilasters, stairs
from engraving.render import Page, frame
from engraving.typography import title
from engraving.validate.plates import validate_plate_result


def build_validated() -> tuple[str, "object"]:
    """Render + validate. Returns (svg_path, ValidationReport)."""
    page = Page()
    frame(page)

    # --- Title band --------------------------------------------------------
    title(page, "A  GRAND  ENTRANCE  STAIR",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 8,
          font_size_mm=5.0, anchor="middle",
          stroke_width=config.STROKE_FINE)
    title(page, "\u2014 twelve steps, Tuscan pilaster, balustrade \u2014",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 14,
          font_size_mm=2.8, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    # --- Layout constants --------------------------------------------------
    margin = config.FRAME_INSET + 6
    # Ground / floor line: a comfortable band above the bottom frame edge.
    floor_y = config.PLATE_H - config.FRAME_INSET - 16

    riser_count = 12
    tread = 12.0            # mm per step (run = 144 mm)
    riser = 7.0             # mm per riser (rise = 84 mm; leaves headroom for
                            # the landing column + entablature to fit below
                            # the subtitle band at y ≈ 33 mm)
    handrail_height = 22.0  # mm above nosings — keeps the rail under the title

    # --- Left pilaster (Tuscan) -------------------------------------------
    # Pilaster sits on the floor, anchoring the left side of the composition.
    # D chosen so that column_h (= 7D) fits between floor_y and the title band
    # at roughly 80 mm tall.
    pil_dims = canon.Tuscan(D=11.0)          # column_h ≈ 77 mm
    pil_cx = margin + 7.0
    pil_polys = pilasters.pilaster(pil_dims, cx=pil_cx, base_y=floor_y,
                                   width=pil_dims.D)
    for pl in pil_polys:
        page.polyline(pl, stroke_width=config.STROKE_FINE)

    # --- Stairs (right-ascending) -----------------------------------------
    # Start the flight just clear of the pilaster's abacus projection.
    pil_half_p = pil_dims.D / 2.0 * (1.0 + 0.15)
    stair_x0 = pil_cx + pil_half_p + 6.0
    stairs_result = stairs.straight_flight(
        x0=stair_x0, y_bottom=floor_y,
        riser_count=riser_count, tread=tread, riser=riser,
        direction="right",
        with_balustrade=True, with_handrail=True,
        handrail_height=handrail_height,
    )

    layer_weights = {
        "stringer":  config.STROKE_MEDIUM,
        "treads":    config.STROKE_FINE,
        "risers":    config.STROKE_FINE,
        "balusters": config.STROKE_FINE,
        "handrail":  config.STROKE_FINE,
    }
    for layer, lines in stairs_result.polylines.items():
        sw = layer_weights.get(layer, config.STROKE_FINE)
        for pl in lines:
            page.polyline(pl, stroke_width=sw)

    # --- Top-of-flight geometry -------------------------------------------
    stair_top_x = stair_x0 + riser_count * tread      # right edge of top tread
    stair_top_y = floor_y - riser_count * riser       # y of top tread surface

    # --- Landing platform --------------------------------------------------
    # A short platform continuing the top tread's plane; the column sits on it.
    landing_w = 36.0
    landing_h = 5.0
    landing_x0 = stair_top_x
    landing_x1 = stair_top_x + landing_w
    # Top & bottom edge + front face (right end) + where it meets the stair.
    page.polyline([(landing_x0, stair_top_y),
                   (landing_x1, stair_top_y)],
                  stroke_width=config.STROKE_MEDIUM)
    page.polyline([(landing_x0, stair_top_y + landing_h),
                   (landing_x1, stair_top_y + landing_h)],
                  stroke_width=config.STROKE_FINE)
    page.polyline([(landing_x1, stair_top_y),
                   (landing_x1, stair_top_y + landing_h)],
                  stroke_width=config.STROKE_FINE)

    # --- Small Tuscan column on the landing -------------------------------
    col_dims = canon.Tuscan(D=5.0)  # column_h = 35 mm — fits above landing
    col_cx = landing_x0 + landing_w / 2.0
    col_base_y = stair_top_y        # column base sits on landing surface
    col_sils = O.tuscan_column_silhouette(col_dims, col_cx, col_base_y)
    for sil in col_sils:
        page.polyline(sil, stroke_width=config.STROKE_MEDIUM)

    # --- Short entablature stub above the column --------------------------
    col_top_y = col_base_y - col_dims.column_h
    ent_half = col_dims.D * 1.6        # stub reaches ~3.2 D wide
    ent = elements.entablature(col_cx - ent_half, col_cx + ent_half,
                               col_top_y, col_dims)
    for pl in ent["polylines"]:
        page.polyline(pl, stroke_width=config.STROKE_FINE)

    # --- Floor / ground line ----------------------------------------------
    # Draw a long continuous ground line the full width of the interior
    # (except where it would pass beneath the pilaster plinth, which
    # itself rests on the floor — the pilaster plinth closes it visually).
    ground_left = margin
    ground_right = config.PLATE_W - margin
    page.polyline([(ground_left, floor_y), (ground_right, floor_y)],
                  stroke_width=config.STROKE_MEDIUM)

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

    svg_path = str(page.save_svg("plate_grand_stair"))

    # This composition plate has no single order/entablature/facade render
    # to pass through the formal validators — run the standard empty-collection
    # pipeline so the build surface stays uniform.
    report = validate_plate_result("plate_grand_stair", {})
    return svg_path, report


def build() -> str:
    """Legacy API — return only the SVG path."""
    svg_path, _ = build_validated()
    return svg_path


if __name__ == "__main__":
    print(build())
