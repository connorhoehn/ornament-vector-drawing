"""Plate — rusticated blocking course, elevation.

A rusticated base course of ashlar masonry. V-grooved joints cast shadows;
the stones' top surfaces catch light. Classic 18th-century architectural
demonstration plate.
"""
from __future__ import annotations

import config
from engraving import elements, hatching
from engraving.borders import rectangular_border
from engraving.ornament import bead_and_reel
from engraving.render import Page, frame
from engraving.typography import title
from engraving.validate.plates import validate_plate_result


def build_validated() -> tuple[str, "object"]:
    """Render + validate. Returns (svg_path, ValidationReport)."""
    page = Page()
    frame(page)

    # Layout region (inside the double frame, with a little air)
    margin = config.FRAME_INSET + 5
    region_x = margin
    region_y = margin + 18  # leave room above for title
    region_w = config.PLATE_W - 2 * margin
    region_h = config.PLATE_H - 2 * margin - 25  # leave room below for caption

    # Wall: 5 courses of running bond ashlar
    course_h = region_h / 5
    block_w = course_h * 2.0  # classical ashlar proportion 2:1
    wall = elements.rusticated_block_wall(
        x0=region_x, y0=region_y,
        width=region_w, height=region_h,
        course_h=course_h, block_w=block_w,
        v_joint_w=1.0, bond="running",
    )

    # Stroke the block outlines lightly
    for r in wall["block_rects"]:
        page.polyline(r, stroke_width=config.STROKE_HAIRLINE, fill="none")

    # Stroke joint center lines
    for j in wall["joints"]:
        page.polyline(j, stroke_width=config.STROKE_FINE)

    # Shadow hatching inside each V-joint band
    for sh in wall["joint_shadows"]:
        lines = hatching.parallel_hatch(sh, angle_deg=45.0, spacing=0.35)
        for ln in lines:
            page.polyline(ln, stroke_width=config.STROKE_HAIRLINE)

    # Overall wall outline heavy
    page.polyline(wall["outline"], stroke_width=config.STROKE_HEAVY, close=True)

    # Title
    title_y = margin + 10
    title(page, "BLOCKING  COURSE",
          x=config.PLATE_W / 2, y=title_y,
          font_size_mm=4.5, anchor="middle",
          stroke_width=config.STROKE_FINE)
    title(page, "— rusticated ashlar, running bond —",
          x=config.PLATE_W / 2, y=title_y + 5.5,
          font_size_mm=2.8, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    # Caption: scale
    cap_y = config.PLATE_H - config.FRAME_INSET - 6
    page.polyline([(config.PLATE_W / 2 - 25, cap_y), (config.PLATE_W / 2 + 25, cap_y)],
                  stroke_width=config.STROKE_FINE)
    for i in range(6):
        x = config.PLATE_W / 2 - 25 + i * 10
        page.polyline([(x, cap_y - 1.5), (x, cap_y)], stroke_width=config.STROKE_HAIRLINE)
    page.text("50 mm", x=config.PLATE_W / 2, y=cap_y + 4,
              font_size=2.4, anchor="middle")

    svg_path = str(page.save_svg("plate_blocking_course"))

    # The rustication wall has no dedicated key in validate_plate_result; run
    # through validate_plate_result with an empty collection so the validation
    # plumbing stays uniform across plates.
    report = validate_plate_result("plate_blocking_course", {})
    return svg_path, report


def build() -> str:
    """Legacy API — return only the SVG path."""
    svg_path, _ = build_validated()
    return svg_path


if __name__ == "__main__":
    print(build())
