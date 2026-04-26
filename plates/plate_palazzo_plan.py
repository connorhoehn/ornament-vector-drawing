"""Plate — 3-story palazzo authored declaratively via FacadePlan.

This is the first plate in the new overhaul pipeline. Instead of hard-coded
coordinates, we describe the facade as intent (stories, bays, openings) and
let the planner solve the positions. If the plan is infeasible (arches
would overflow their story, upper windows wider than lower, etc.), the
solver raises PlanInfeasible BEFORE any geometry is drawn.
"""
from __future__ import annotations

import config
from engraving.element import Element
from engraving.planner import (
    FacadePlan, StoryPlan, BayPlan, OpeningPlan, ParapetPlan, PilasterPlan,
    PlinthPlan, PlanInfeasible,
)
from engraving.planner.elements import (
    horizontal_dimension, vertical_dimension, render_dimensions,
)
from engraving.render import Page, frame
from engraving.typography import title


def make_plan() -> FacadePlan:
    """The palazzo intent. Declarative; no coordinates."""
    # Phase 22 Part 3: nudge the canvas inset a touch wider so the corner
    # quoin stacks have room at each outer edge without crowding the frame.
    margin_x = config.FRAME_INSET + 10
    top_margin = config.FRAME_INSET + 22
    bottom_margin = config.FRAME_INSET + 16

    plan = FacadePlan(
        canvas=(margin_x, top_margin,
                config.PLATE_W - margin_x,
                config.PLATE_H - bottom_margin),
        stories=[
            # Ground story: rusticated arcade with engaged Doric piers
            # between each bay — this is what gives the bottom its
            # weight and matches the McKim Municipal Building precedent.
            StoryPlan(height_ratio=1.3, wall="arcuated",
                      has_order="doric",
                      min_height_mm=40, label="ground"),
            # Piano nobile: a CLEAN smooth ashlar field lets the Ionic
            # pilasters and window surrounds carry the story. The earlier
            # bossed_smooth banding fought the windows for attention.
            # Penn Station and the NYC Municipal Building both treat the
            # piano nobile as a quiet backdrop for the order.
            StoryPlan(height_ratio=1.4, wall="smooth",
                      has_order="ionic", label="piano_nobile"),
            StoryPlan(height_ratio=0.85, wall="smooth",
                      label="attic"),
        ],
        bays=[],
        parapet=ParapetPlan(kind="balustrade", height_ratio=0.25,
                             baluster_variant="tuscan"),
        # A continuous stylobate / water-table under the ground story.
        # ``projection_mm`` steps the plinth OUT past the wall line on
        # both sides so the upper wall reads as sitting ON the plinth,
        # not flush with it — the Municipal Building precedent.
        plinth=PlinthPlan(kind="banded", height_mm=7.0, projection_mm=1.2),
        with_quoins=True,
        quoin_width_mm=8.0,
    )
    # Bays: 5 total, central slightly wider to read as the entry
    for i in range(5):
        if i == 2:
            plan.bays.append(BayPlan(
                openings=[
                    OpeningPlan(kind="arch_door", width_frac=0.55,
                                 height_frac=0.40, has_keystone=True),
                    # Central piano-nobile window: height_frac tuned so
                    # the rect + triangular hood + sill all fit inside
                    # the story after Phase-31 empirical coefficients.
                    OpeningPlan(kind="window", width_frac=0.42,
                                 height_frac=0.50, hood="triangular",
                                 has_keystone=True),
                    OpeningPlan(kind="window", width_frac=0.30,
                                 height_frac=0.40, hood="cornice"),
                ],
                pilasters=PilasterPlan(order="ionic", width_frac=0.08),
                width_weight=1.2, label="entry",
            ))
        else:
            plan.bays.append(BayPlan(
                openings=[
                    OpeningPlan(kind="arch_window", width_frac=0.55,
                                 height_frac=0.25, has_keystone=True),
                    OpeningPlan(kind="window", width_frac=0.38,
                                 height_frac=0.46,
                                 hood="triangular" if i % 2 == 0 else "segmental",
                                 has_keystone=True),
                    OpeningPlan(kind="window", width_frac=0.30,
                                 height_frac=0.40, hood="cornice"),
                ],
                pilasters=PilasterPlan(order="ionic", width_frac=0.08),
                label=f"bay_{i}",
            ))
    return plan


def build_validated():
    """Build + validate. Returns (svg_path, report)."""
    page = Page()
    frame(page)

    title(page, "PALAZZO VIA FACADE PLAN",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 10,
          font_size_mm=4.5, anchor="middle",
          stroke_width=config.STROKE_FINE)
    title(page, "— declarative constraint-solved facade —",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 16,
          font_size_mm=2.8, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    plan = make_plan()
    try:
        facade = plan.solve()
    except PlanInfeasible as e:
        # Surface the error on the plate itself for debugging
        page.text(f"PLAN INFEASIBLE: {e.reason}",
                  x=config.PLATE_W / 2, y=config.PLATE_H / 2,
                  font_size=3.0, anchor="middle", fill="red")
        return str(page.save_svg_with_plan("plate_palazzo_plan", plan)), type("Report", (), {
            "errors": [str(e)]
        })()

    # Render all element strokes
    for pl, stroke in facade.render_strokes():
        page.polyline(pl, stroke_width=stroke)

    # Phase 32 — dimension annotations. Pull solved story heights and
    # overall canvas width straight off the tree and emit vertical and
    # horizontal measurement callouts flanking the facade.
    stories_by_idx = {}
    for n in facade.descendants():
        if n.kind == "story":
            idx = int(n.id.rsplit("_", 1)[1])
            stories_by_idx[idx] = n
    canvas_left = plan.canvas[0]
    canvas_right = plan.canvas[2]
    canvas_bottom = plan.canvas[3]

    dim_root = Element(id="facade.dimensions", kind="dimension_group",
                        envelope=(0, 0, config.PLATE_W, config.PLATE_H))

    # Vertical: each story height along the RIGHT edge, stacked. The
    # canvas's left margin is too narrow for an outside dim line; the
    # right side has comfortable gap to the frame, and putting all
    # vertical dims on one side reads as a single measurement column.
    story_labels = {0: "ground", 1: "piano nobile", 2: "attic"}
    x_dim = min(config.PLATE_W - config.FRAME_INSET - 3.0,
                canvas_right + 5.0)
    for i, story in stories_by_idx.items():
        _, y_top, _, y_bot = story.envelope
        h_mm = y_bot - y_top
        dim_root.add(vertical_dimension(
            p_top=(canvas_right, y_top),
            p_bottom=(canvas_right, y_bot),
            x_line=x_dim,
            label=f"{story_labels.get(i, f'story {i}')}  {h_mm:.0f} mm",
            id=f"dim.story_{i}_h",
            text_size_mm=2.0,
        ))

    # Horizontal: overall facade width at the bottom of the canvas.
    # Clamp y_dim_h inside the frame so the label stays on-plate; the
    # scale bar sits below this dimension line by config.
    y_dim_h = min(config.PLATE_H - config.FRAME_INSET - 12.0,
                  canvas_bottom + 10.0)
    dim_root.add(horizontal_dimension(
        p_left=(canvas_left, canvas_bottom),
        p_right=(canvas_right, canvas_bottom),
        y_line=y_dim_h,
        label=f"facade  =  {canvas_right - canvas_left:.0f} mm",
        id="dim.facade_w",
        text_size_mm=2.0,
    ))

    render_dimensions(page, dim_root, frame_bbox=(config.FRAME_INSET, config.FRAME_INSET, config.PLATE_W - config.FRAME_INSET, config.PLATE_H - config.FRAME_INSET))
    facade.metadata["dimensions_root"] = dim_root

    # Scale bar
    cap_y = config.PLATE_H - config.FRAME_INSET - 6
    page.polyline([(config.PLATE_W/2 - 25, cap_y),
                    (config.PLATE_W/2 + 25, cap_y)],
                   stroke_width=config.STROKE_FINE)
    for i in range(6):
        x = config.PLATE_W/2 - 25 + i * 10
        page.polyline([(x, cap_y - 1.5), (x, cap_y)],
                       stroke_width=config.STROKE_HAIRLINE)
    page.text("50 mm", x=config.PLATE_W/2, y=cap_y + 4,
              font_size=2.4, anchor="middle")

    # Return the plan's violations as the report
    violations = facade.metadata.get("violations", [])
    class Report:
        def __init__(self, vs):
            self.errors = [str(v) for v in vs]
        def __len__(self):
            return len(self.errors)
        def __iter__(self):
            return iter(self.errors)
        def __bool__(self):
            return bool(self.errors)
    return str(page.save_svg_with_plan("plate_palazzo_plan", plan)), Report(violations)


def build():
    return build_validated()[0]


if __name__ == "__main__":
    print(build())
