"""Plate — Dury-Carondelet-inspired 3-story palazzo schematic.

Ground floor: rusticated arcuated base. Piano nobile: Ionic pilasters with
pedimented windows. Upper story: plain windows. Balustraded parapet.

This is the hero deliverable: a generated building schematic at 1:1 print size.
"""
from __future__ import annotations

import config
from engraving import facade
from engraving.render import Page, frame
from engraving.typography import title
from engraving.validate.plates import validate_plate_result


def _build_impl() -> tuple[str, "object", "object"]:
    """Internal: render + validate + construct Scene.

    Returns (svg_path, ValidationReport, Scene).
    """
    page = Page()
    frame(page)

    title_y = config.FRAME_INSET + 8
    title(page, "PALAZZO ELEVATION — 3 STORIES",
          x=config.PLATE_W / 2, y=title_y,
          font_size_mm=4.5, anchor="middle",
          stroke_width=config.STROKE_FINE)
    title(page, "— rusticated arcuated ground, Ionic piano nobile, balustraded parapet —",
          x=config.PLATE_W / 2, y=title_y + 5,
          font_size_mm=2.6, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    # Facade fills the interior with margins for title + scale bar.
    margin_x = config.FRAME_INSET + 6
    top_margin = config.FRAME_INSET + 18
    bottom_margin = config.FRAME_INSET + 16
    facade_w = config.PLATE_W - 2 * margin_x
    facade_h_budget = config.PLATE_H - top_margin - bottom_margin

    # Story heights: piano nobile tallest, ground rusticated, upper plainest.
    # Ratio roughly 1.0 : 1.4 : 0.85 : 0.25 (ground : piano nobile : top : parapet)
    total_ratio = 1.0 + 1.4 + 0.85 + 0.25
    unit = facade_h_budget / total_ratio
    h_ground = unit * 1.0
    h_piano = unit * 1.4
    h_top = unit * 0.85
    h_parapet = unit * 0.25

    base_y = top_margin + facade_h_budget  # ground line at bottom of facade area

    # Classical opening-size hierarchy (Vignola/Palladio convention). Widths
    # descend as you go up the facade; heights follow piano-nobile-is-tallest
    # rule. All three scale off bay_pitch so they fit their bay.
    bay_pitch = facade_w / 5

    w_ground = bay_pitch * 0.52   # ground-floor arch: widest (public level)
    w_piano  = bay_pitch * 0.42   # piano nobile: narrower
    w_upper  = bay_pitch * 0.32   # upper story: smallest

    h_ground_op = h_ground * 0.68
    h_piano_op  = h_piano  * 0.62   # but TALLEST absolute value (piano nobile)
    h_upper_op  = h_top    * 0.50

    # Central door bay — wider and taller
    w_door  = bay_pitch * 0.72
    h_door  = h_ground * 0.82

    # Five bays, central bay is the entry door.
    bays = [
        facade.Bay(
            openings=[
                facade.Opening(kind="arch_window", width=w_ground, height=h_ground_op),
                facade.Opening(kind="window", width=w_piano, height=h_piano_op, hood="triangular", has_keystone=True),
                facade.Opening(kind="window", width=w_upper, height=h_upper_op, hood="cornice"),
            ],
            pilaster_order="ionic",
            pilaster_width=5.0,
        ),
        facade.Bay(
            openings=[
                facade.Opening(kind="arch_window", width=w_ground, height=h_ground_op),
                facade.Opening(kind="window", width=w_piano, height=h_piano_op, hood="segmental", has_keystone=True),
                facade.Opening(kind="window", width=w_upper, height=h_upper_op, hood="cornice"),
            ],
        ),
        facade.Bay(
            openings=[
                facade.Opening(kind="arch_door", width=w_door, height=h_door),
                facade.Opening(kind="window", width=w_piano * 1.05, height=h_piano_op * 1.03, hood="triangular", has_keystone=True),
                facade.Opening(kind="window", width=w_upper, height=h_upper_op, hood="cornice"),
            ],
            pilaster_order="ionic",
            pilaster_width=5.0,
        ),
        facade.Bay(
            openings=[
                facade.Opening(kind="arch_window", width=w_ground, height=h_ground_op),
                facade.Opening(kind="window", width=w_piano, height=h_piano_op, hood="segmental", has_keystone=True),
                facade.Opening(kind="window", width=w_upper, height=h_upper_op, hood="cornice"),
            ],
        ),
        facade.Bay(
            openings=[
                facade.Opening(kind="arch_window", width=w_ground, height=h_ground_op),
                facade.Opening(kind="window", width=w_piano, height=h_piano_op, hood="triangular", has_keystone=True),
                facade.Opening(kind="window", width=w_upper, height=h_upper_op, hood="cornice"),
            ],
            pilaster_order="ionic",
            pilaster_width=5.0,
        ),
    ]

    # Substantial ashlar stones on the ground floor: course_h = h_ground / 2
    # gives two visible courses (instead of 4), and block_w = course_h * 2.0
    # keeps the blocks in a roughly 1:2 aspect ratio — chunky Renaissance
    # ashlar rather than fine brickwork.
    course_h_ground = h_ground / 2.0
    block_w_ground = course_h_ground * 2.0

    stories = [
        facade.Story(height=h_ground,
                     wall={"variant": "arcuated",
                           "course_h": course_h_ground,
                           "block_w": block_w_ground,
                           "v_joint_w": 0.9},
                     string_course_height=1.8),
        # Piano nobile: smooth ashlar, Ionic pilasters flank each bay.
        facade.Story(height=h_piano, wall="smooth", has_order="ionic",
                     string_course_height=1.8),
        # Upper story: smooth too. Rustication is ground-floor only in
        # classical practice; the string course above already marks the
        # story division.
        facade.Story(height=h_top, wall="smooth", string_course_height=1.5),
    ]

    parapet = {"type": "balustrade", "height": h_parapet}

    f = facade.Facade(
        width=facade_w,
        stories=stories,
        bays=bays,
        base_y=base_y,
        parapet=parapet,
    )
    f.layout()
    result = f.render()

    # Shift rendered geometry to sit inside the plate margins. Iterate over
    # ``layers`` (not the flat ``polylines`` list) so we can stroke each
    # category at its recommended weight: wall outlines medium, block-
    # interior joints hairline, architraves medium, voussoirs fine, etc.
    x_offset = margin_x
    layer_draw_order = [
        "wall_blocks",
        "wall_joints",
        "wall_voussoirs",
        "wall_outlines",
        "string_courses",
        "pilasters",
        "windows",
        "arches",
        "parapet",
    ]
    for layer_name in layer_draw_order:
        layer = result["layers"].get(layer_name)
        if not layer:
            continue
        weight = layer.get("weight", config.STROKE_FINE)
        for pl in layer.get("polylines", []):
            shifted = [(x + x_offset, y) for x, y in pl]
            page.polyline(shifted, stroke_width=weight)

    # Scale bar
    cap_y = config.PLATE_H - config.FRAME_INSET - 6
    page.polyline([(config.PLATE_W / 2 - 25, cap_y), (config.PLATE_W / 2 + 25, cap_y)],
                  stroke_width=config.STROKE_FINE)
    for i in range(6):
        x = config.PLATE_W / 2 - 25 + i * 10
        page.polyline([(x, cap_y - 1.5), (x, cap_y)], stroke_width=config.STROKE_HAIRLINE)
    page.text("50 mm", x=config.PLATE_W / 2, y=cap_y + 4, font_size=2.4, anchor="middle")

    svg_path = str(page.save_svg("plate_schematic"))

    collected = {"facade": (f, result)}
    report = validate_plate_result("plate_schematic", collected)

    # Scene-graph validation: populate a Scene from the rendered facade and
    # run cross-story / cross-bay structural constraints, appending any
    # errors to the plate's report with a [scene] prefix.
    scene = f.to_scene(result)
    scene_report = scene.validate()
    report.errors.extend([f"[scene] {e}" for e in scene_report])
    return svg_path, report, scene


def build_validated() -> tuple[str, "object"]:
    """Render + validate. Returns (svg_path, ValidationReport)."""
    svg_path, report, _scene = _build_impl()
    return svg_path, report


def build_validated_with_scene() -> tuple[str, "object"]:
    """Render + build a Scene. Returns (svg_path, Scene).

    Used by the ``debug`` CLI subcommand to overlay constraint failures.
    """
    svg_path, _report, scene = _build_impl()
    return svg_path, scene


def build() -> str:
    """Legacy API — return only the SVG path."""
    svg_path, _ = build_validated()
    return svg_path


if __name__ == "__main__":
    print(build())
