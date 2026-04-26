"""Plate — the five classical orders as distyle porticos, side by side.

Mirrors the comparative convention of Vignola's Regole plates: each
order drawn as a small pedimented distyle temple front, all on a shared
baseline, so the native proportions (column_h = 7D for Tuscan up to 10D
for Corinthian) are visible at a glance.

Built entirely from ``PorticoPlan`` — each order's proportions flow
directly from ``canon.py``. No hand-tuned dimensions.
"""
from __future__ import annotations

import config
from engraving.planner import (
    PorticoPlan, PedimentPlan, PlinthPlan, PlanInfeasible,
)
from engraving.render import Page, frame
from engraving.typography import title


ORDER_NAMES = ["Tuscan", "Doric", "Ionic", "Corinthian", "Composite"]
ORDER_KEYS  = ["tuscan", "doric", "ionic", "corinthian", "composite"]


def build_validated():
    """Render the five-orders comparison plate."""
    page = Page()
    frame(page)

    title(page, "THE  FIVE  ORDERS",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 10,
          font_size_mm=4.8, anchor="middle",
          stroke_width=config.STROKE_FINE)
    title(page, "— each as a distyle pedimented portico, after Vignola —",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 16,
          font_size_mm=2.8, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    # Split the plate horizontally into 5 equal columns. Each order gets
    # its own PorticoPlan with a narrow canvas — the solver derives D so
    # the stack fits, preserving canonical proportions within that slot.
    gutter = 1.0
    top_y = config.FRAME_INSET + 22
    bottom_y = config.PLATE_H - config.FRAME_INSET - 14
    left_x = config.FRAME_INSET + 8
    right_x = config.PLATE_W - config.FRAME_INSET - 8

    slot_w = (right_x - left_x - gutter * (len(ORDER_KEYS) - 1)) / len(ORDER_KEYS)

    all_violations = []
    for i, key in enumerate(ORDER_KEYS):
        x0 = left_x + i * (slot_w + gutter)
        x1 = x0 + slot_w
        plan = PorticoPlan(
            canvas=(x0, top_y, x1, bottom_y),
            order=key,
            column_count=2,                      # distyle — smallest viable
            intercolumniation_modules=3.0,       # systyle
            pedestal=True,
            plinth=PlinthPlan(kind="banded", height_mm=2.5),
            pediment=PedimentPlan(slope_deg=13.5),
        )
        try:
            portico = plan.solve()
        except PlanInfeasible as e:
            page.text(f"{ORDER_NAMES[i]}: {e.reason}",
                      x=(x0 + x1) / 2, y=(top_y + bottom_y) / 2,
                      font_size=2.2, anchor="middle", fill="red")
            all_violations.append(f"{ORDER_NAMES[i]}: {e}")
            continue
        for pl, stroke in portico.render_strokes():
            page.polyline(pl, stroke_width=stroke)
        # Order label under each portico.
        page.text(ORDER_NAMES[i],
                  x=(x0 + x1) / 2, y=bottom_y + 5,
                  font_size=2.6, anchor="middle")
        all_violations.extend(portico.metadata.get("violations", []))

    # Scale bar.
    cap_y = config.PLATE_H - config.FRAME_INSET - 4
    page.polyline([(config.PLATE_W/2 - 25, cap_y),
                   (config.PLATE_W/2 + 25, cap_y)],
                  stroke_width=config.STROKE_FINE)
    for j in range(6):
        x = config.PLATE_W/2 - 25 + j * 10
        page.polyline([(x, cap_y - 1.2), (x, cap_y)],
                      stroke_width=config.STROKE_HAIRLINE)
    page.text("50 mm", x=config.PLATE_W/2, y=cap_y + 3.2,
              font_size=2.2, anchor="middle")

    class Report:
        def __init__(self, vs):
            self.errors = [str(v) for v in vs]
        def __len__(self): return len(self.errors)
        def __iter__(self): return iter(self.errors)
        def __bool__(self): return bool(self.errors)

    svg_path = str(page.save_svg("plate_five_orders_porticos"))
    return svg_path, Report(all_violations)


def build():
    return build_validated()[0]


if __name__ == "__main__":
    print(build())
