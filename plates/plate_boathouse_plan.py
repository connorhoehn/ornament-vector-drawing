"""Plate — McKim-Mead-White style boathouse authored declaratively via
BoathousePlan.

Parallel to ``plate_palazzo_plan.py`` and ``plate_portico_plan.py`` but
for a boathouse: a tall ground-floor run of arched boat bays where crew
shells launch, a clerestory upper story, a gabled shingle roof with deep
eaves and exposed rafter tails. Positions are solved from the plan; no
hard-coded coordinates.
"""
from __future__ import annotations

import config
from engraving.element import Element
from engraving.planner import (
    BoathousePlan, RoofPlan, PlinthPlan, PlanInfeasible,
)
from engraving.planner.elements import (
    horizontal_dimension, vertical_dimension, render_dimensions,
)
from engraving.render import Page, frame
from engraving.typography import title


def make_plan() -> BoathousePlan:
    """Declarative boathouse — no geometry, no coordinates."""
    margin_x = config.FRAME_INSET + 8
    top_margin = config.FRAME_INSET + 18
    bottom_margin = config.FRAME_INSET + 14

    # Three arched boat bays on the ground; five clerestory windows
    # above; gabled shingle roof at ~22° slope with 6mm eave overhang.
    # The solver derives every dimension from the canvas + these inputs.
    plan = BoathousePlan(
        canvas=(margin_x, top_margin,
                config.PLATE_W - margin_x,
                config.PLATE_H - bottom_margin),
        bay_count=3,
        bay_kind="arched",
        has_upper_story=True,
        upper_story_window_count=5,
        roof=RoofPlan(slope_deg=22.0, overhang_mm=6.0,
                       has_shingle_hatch=True, gable_end=True),
        plinth=PlinthPlan(kind="banded", height_mm=6.0, projection_mm=1.2),
    )
    return plan


def build_validated():
    """Build + validate. Returns (svg_path, report)."""
    page = Page()
    frame(page)

    title(page, "A  BOATHOUSE  VIA  BOATHOUSE  PLAN",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 8,
          font_size_mm=4.5, anchor="middle",
          stroke_width=config.STROKE_FINE)
    title(page, "— declarative constraint-solved boathouse, after McKim Mead & White —",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 14,
          font_size_mm=2.8, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    plan = make_plan()
    try:
        boathouse = plan.solve()
    except PlanInfeasible as e:
        page.text(f"PLAN INFEASIBLE: {e.reason}",
                  x=config.PLATE_W / 2, y=config.PLATE_H / 2,
                  font_size=3.0, anchor="middle", fill="red")

        class _ErrReport:
            def __init__(self, err):
                self.errors = [str(err)]
            def __len__(self): return len(self.errors)
            def __iter__(self): return iter(self.errors)
            def __bool__(self): return bool(self.errors)
        svg_path = str(page.save_svg_with_plan("plate_boathouse_plan", plan))
        return svg_path, _ErrReport(e)

    # Render all element strokes
    for pl, stroke in boathouse.render_strokes():
        page.polyline(pl, stroke_width=stroke)

    # Phase 32 — dimension annotations: boat-bay height, roof slope,
    # clerestory width and overall envelope.
    children = {c.kind: c for c in boathouse.children}
    canvas_left, canvas_top, canvas_right, canvas_bottom = plan.canvas
    dim_root = Element(id="boathouse.dimensions", kind="dimension_group",
                        envelope=(0, 0, config.PLATE_W, config.PLATE_H))

    # Vertical: total building height along the right. x_dim clamped
    # inside the frame so the extension line + label don't exit.
    x_dim = min(config.PLATE_W - config.FRAME_INSET - 3.0,
                canvas_right + 5.0)
    dim_root.add(vertical_dimension(
        p_top=(canvas_right, canvas_top),
        p_bottom=(canvas_right, canvas_bottom),
        x_line=x_dim,
        label=f"total  =  {canvas_bottom - canvas_top:.0f} mm",
        id="dim.total_h",
        text_size_mm=2.0,
    ))

    # Horizontal: overall canvas width below the facade. y clamped.
    y_dim_h = min(config.PLATE_H - config.FRAME_INSET - 12.0,
                  canvas_bottom + 6.0)
    dim_root.add(horizontal_dimension(
        p_left=(canvas_left, canvas_bottom),
        p_right=(canvas_right, canvas_bottom),
        y_line=y_dim_h,
        label=f"facade  =  {canvas_right - canvas_left:.0f} mm",
        id="dim.facade_w",
        text_size_mm=2.0,
    ))

    # Roof slope callout — show the design slope from the plan.
    dim_root.metadata["roof_slope_label"] = f"roof slope {plan.roof.slope_deg:.1f}°"

    render_dimensions(page, dim_root, frame_bbox=(config.FRAME_INSET, config.FRAME_INSET, config.PLATE_W - config.FRAME_INSET, config.PLATE_H - config.FRAME_INSET))
    boathouse.metadata["dimensions_root"] = dim_root

    # Scale bar — matches the portico/palazzo plate caption style
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

    violations = boathouse.metadata.get("violations", [])

    class Report:
        def __init__(self, vs):
            self.errors = [str(v) for v in vs]
        def __len__(self):
            return len(self.errors)
        def __iter__(self):
            return iter(self.errors)
        def __bool__(self):
            return bool(self.errors)

    svg_path = str(page.save_svg_with_plan("plate_boathouse_plan", plan))
    return svg_path, Report(violations)


def build():
    return build_validated()[0]


if __name__ == "__main__":
    print(build())
