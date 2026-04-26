"""Plate — tetrastyle Tuscan portico authored declaratively via PorticoPlan.

Parallel to ``plate_palazzo_plan.py`` but for porticos: a free-standing
colonnade crowned by an entablature and a triangular pediment, with an
optional pedestal course and a stylobate/plinth underneath. Positions
are solved from the plan; no hard-coded coordinates.
"""
from __future__ import annotations

import config
from engraving.element import Element
from engraving.planner import (
    PorticoPlan, PedimentPlan, PlinthPlan, PlanInfeasible,
)
from engraving.planner.elements import (
    ColumnRunElement, EntablatureBandElement,
    horizontal_dimension, vertical_dimension, render_dimensions,
)
from engraving.render import Page, frame
from engraving.typography import title


def make_plan() -> PorticoPlan:
    """Declarative portico — no geometry, no coordinates."""
    # Target a ~600mm-wide drawing envelope. The plate is 254mm wide, so
    # keep the portico symmetrically centred inside the plate frame.
    margin_x = config.FRAME_INSET + 12
    top_margin = config.FRAME_INSET + 22
    bottom_margin = config.FRAME_INSET + 18

    # Tetrastyle Tuscan at Vignola canon. The solver derives D so the
    # stack (plinth + pedestal + column + entablature + pediment) fits
    # the canvas; every part scales linearly with D, so proportions are
    # mathematically locked to canon.Tuscan regardless of canvas size.
    plan = PorticoPlan(
        canvas=(margin_x, top_margin,
                config.PLATE_W - margin_x,
                config.PLATE_H - bottom_margin),
        order="tuscan",
        column_count=4,                       # tetrastyle
        intercolumniation_modules=4.0,        # Tuscan canon
        pedestal=True,
        plinth=PlinthPlan(kind="banded", height_mm=6.0),
        pediment=PedimentPlan(slope_deg=15.0),
    )
    return plan


def build_validated():
    """Build + validate. Returns (svg_path, report)."""
    page = Page()
    frame(page)

    title(page, "A  TUSCAN  PORTICO  VIA  PORTICO  PLAN",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 10,
          font_size_mm=4.5, anchor="middle",
          stroke_width=config.STROKE_FINE)
    title(page, "— declarative constraint-solved portico, after Vignola —",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 16,
          font_size_mm=2.8, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    plan = make_plan()
    try:
        portico = plan.solve()
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
        svg_path = str(page.save_svg_with_plan("plate_portico_plan", plan))
        return svg_path, _ErrReport(e)

    # Render all element strokes
    for pl, stroke in portico.render_strokes():
        page.polyline(pl, stroke_width=stroke)

    # Phase 32 — dimension annotations. Pull solved geometry off the
    # tree and emit vertical (column_h, entablature_h) + horizontal
    # (colonnade_w) measurement callouts.
    D = portico.metadata["D"]
    col_left = portico.metadata["colonnade_left_x"]
    col_right = portico.metadata["colonnade_right_x"]
    column_run = next(c for c in portico.children
                      if isinstance(c, ColumnRunElement))
    ent_band = next(c for c in portico.children
                    if isinstance(c, EntablatureBandElement))
    column_top_y = column_run.top_of_capital_y   # y where capital meets ent.
    column_base_y = column_run.base_y            # y of column base
    ent_top_y = ent_band.envelope[1]             # top of entablature
    ent_bot_y = ent_band.envelope[3]             # bottom of entablature

    dim_root = Element(id="portico.dimensions", kind="dimension_group",
                       envelope=(0, 0, config.PLATE_W, config.PLATE_H))

    # 1) Vertical: column height = 7·D (Tuscan canon)
    x_col_dim = col_right + D * 0.8
    dim_root.add(vertical_dimension(
        p_top=(col_right, column_top_y),
        p_bottom=(col_right, column_base_y),
        x_line=x_col_dim,
        label="column  =  7 D",
        id="dim.column_h",
        text_size_mm=2.2,
    ))

    # 2) Vertical: entablature height = 1.75·D (Tuscan canon)
    dim_root.add(vertical_dimension(
        p_top=(col_right, ent_top_y),
        p_bottom=(col_right, ent_bot_y),
        x_line=x_col_dim + D * 1.4,
        label="entab.  =  1.75 D",
        id="dim.entablature_h",
        text_size_mm=2.2,
    ))

    # 3) Horizontal: colonnade width (outer abacus to outer abacus)
    dim_root.add(horizontal_dimension(
        p_left=(col_left, column_base_y),
        p_right=(col_right, column_base_y),
        y_line=column_base_y + D * 0.9,
        label=f"colonnade  =  {col_right - col_left:.1f} mm",
        id="dim.colonnade_w",
        text_size_mm=2.2,
    ))

    render_dimensions(page, dim_root, frame_bbox=(config.FRAME_INSET, config.FRAME_INSET, config.PLATE_W - config.FRAME_INSET, config.PLATE_H - config.FRAME_INSET))

    # Attach the dim_root to the portico tree so an integration test can
    # count DimensionElements in the rendered plate. ``dim_root`` exists
    # OUTSIDE the structural hierarchy for containment/aesthetic validation
    # (it's annotation, not structure) but we expose it via metadata so
    # tests can reach it.
    portico.metadata["dimensions_root"] = dim_root

    # Scale bar — matches the palazzo plate's caption style
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

    violations = portico.metadata.get("violations", [])

    class Report:
        def __init__(self, vs):
            self.errors = [str(v) for v in vs]
        def __len__(self):
            return len(self.errors)
        def __iter__(self):
            return iter(self.errors)
        def __bool__(self):
            return bool(self.errors)

    svg_path = str(page.save_svg_with_plan("plate_portico_plan", plan))
    return svg_path, Report(violations)


def build():
    return build_validated()[0]


if __name__ == "__main__":
    print(build())
