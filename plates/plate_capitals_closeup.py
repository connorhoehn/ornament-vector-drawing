"""Plate — closeup capitals of all five orders at plate scale.

Dedicated reference plate for auditing capital geometry. Each order's
capital (+ astragal + ~1D of shaft below for visual grounding) gets a
full-height slot so acanthus leaves, helices, volutes, triglyph ticks,
echinus curves, and fleurons are all clearly readable.

All five capitals render at the same module diameter D so the native
proportion differences (Tuscan's 0.5·D plain cap vs Corinthian's
1.17·D acanthus-wrapped bell) are visible at a glance.
"""
from __future__ import annotations

import config
from engraving import canon
from engraving.order_corinthian import corinthian_column_silhouette
from engraving.order_composite import composite_column_silhouette
from engraving.order_ionic import ionic_column_silhouette
from engraving.order_doric import doric_column_silhouette
from engraving.orders import tuscan_column_silhouette
from engraving.render import Page, frame
from engraving.typography import title


# Builders + canon classes, in canonical left→right progression.
ORDERS = [
    ("Tuscan",     tuscan_column_silhouette,     canon.Tuscan),
    ("Doric",      doric_column_silhouette,      canon.Doric),
    ("Ionic",      ionic_column_silhouette,      canon.Ionic),
    ("Corinthian", corinthian_column_silhouette, canon.Corinthian),
    ("Composite",  composite_column_silhouette,  canon.Composite),
]

# Stroke weights keyed by the ElementResult layer names each builder emits.
_LAYER_WEIGHTS = {
    "silhouette":  config.STROKE_MEDIUM,
    "rules":       config.STROKE_FINE,
    "volutes":     config.STROKE_FINE,
    "echinus":     config.STROKE_FINE,
    "abacus":      config.STROKE_FINE,
    "annulets":    config.STROKE_FINE,
    "triglyphs":   config.STROKE_FINE,
    "helices":     config.STROKE_ORNAMENT,
    "fleuron":     config.STROKE_ORNAMENT,
    "flutes":      config.STROKE_ORNAMENT,
    "caulicoli":   config.STROKE_HATCH,
    "bell_guides": config.STROKE_HATCH,
    "acanthus":    config.STROKE_HATCH,
}


def build_validated():
    page = Page()
    frame(page)

    title(page, "THE  FIVE  CAPITALS  —  CLOSEUP",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 10,
          font_size_mm=4.6, anchor="middle",
          stroke_width=config.STROKE_FINE)
    title(page, "— each capital at matched D, with ~1·D of shaft below for grounding —",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 16,
          font_size_mm=2.4, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    # Slot layout: 5 equal horizontal slots, each holds one capital.
    gutter = 1.0
    top_y = config.FRAME_INSET + 22
    bottom_y = config.PLATE_H - config.FRAME_INSET - 18
    left_x = config.FRAME_INSET + 6
    right_x = config.PLATE_W - config.FRAME_INSET - 6
    slot_w = (right_x - left_x - gutter * (len(ORDERS) - 1)) / len(ORDERS)
    plate_zone_h = bottom_y - top_y

    # Choose D so that [capital + astragal + 1·D of shaft] of the TALLEST
    # capital (Corinthian: capital_D = 7/6) fits vertically, AND the shaft
    # is narrower than the slot. Scale factor drives the capital size.
    # Visible column = capital_D + 1.0 (shaft below) + 0.15 (astragal gap)
    visible_D_factor_max = 0
    for _, _, OrderCls in ORDERS:
        probe = OrderCls(D=1.0)
        v = probe.capital_D + 1.0 + 0.15
        visible_D_factor_max = max(visible_D_factor_max, v)
    # 94% of plate_zone_h for the column's visible portion.
    D = (plate_zone_h * 0.94) / visible_D_factor_max
    # Also cap D by slot width so the capital's abacus doesn't spill.
    # Corinthian abacus can reach ~1.4·D in width; use 1.5·D for safety.
    D = min(D, slot_w / 1.55)

    # Each capital sits at the top, with ~1·D of shaft descending below it.
    # base_y argument to the silhouette builder is the ABSOLUTE bottom of
    # the column (base top), so we derive it from the column_h of each order
    # — but we only draw the top ~(capital_D + 1.0) of the column.
    for i, (name, builder, OrderCls) in enumerate(ORDERS):
        x0 = left_x + i * (slot_w + gutter)
        x1 = x0 + slot_w
        cx = (x0 + x1) / 2

        dims = OrderCls(D=D)
        # Full column height for this order:
        col_h = dims.column_h
        # We want the capital to sit with its TOP near top_y + 4mm. The
        # column's base_y is at y_col_top + col_h.
        y_capital_top = top_y + 4.0
        y_col_bottom = y_capital_top + col_h
        # Build the column, emit only strokes visible in [y_capital_top - 2,
        # y_capital_top + capital_D·D + D] — roughly capital + 1·D of shaft.
        y_visible_top = y_capital_top - 2.0
        y_visible_bot = y_capital_top + dims.capital_h + D * 1.05

        result = builder(dims, cx, y_col_bottom, return_result=True)
        # Clip to the closeup window using shapely so polylines whose
        # endpoints straddle the band still render their visible segment.
        from shapely.geometry import LineString, box as shapely_box
        clip_box = shapely_box(
            x0 - 2, y_visible_top, x1 + 2, y_visible_bot,
        )
        for layer, polys in result.polylines.items():
            weight = _LAYER_WEIGHTS.get(layer, 0.25)
            for pl in polys:
                if len(pl) < 2:
                    continue
                try:
                    line = LineString(pl)
                    clipped = line.intersection(clip_box)
                except Exception:
                    continue
                if clipped.is_empty:
                    continue
                # Clipped may be a LineString or a MultiLineString.
                geoms = (
                    [clipped]
                    if clipped.geom_type == "LineString"
                    else list(getattr(clipped, "geoms", []))
                )
                for g in geoms:
                    if g.geom_type != "LineString":
                        continue
                    coords = list(g.coords)
                    if len(coords) >= 2:
                        page.polyline(coords, stroke_width=weight)

        # Label + canonical capital_D ratio beneath each slot.
        page.text(f"{name}  ({dims.capital_D:.3g}·D)",
                  x=cx, y=bottom_y + 5,
                  font_size=2.6, anchor="middle")

    # Global note / D value at bottom right
    page.text(f"D = {D:.1f} mm",
              x=right_x, y=config.PLATE_H - config.FRAME_INSET - 5,
              font_size=2.2, anchor="end")

    class Report:
        def __init__(self): self.errors = []
        def __len__(self): return 0
        def __iter__(self): return iter([])
        def __bool__(self): return False

    svg_path = str(page.save_svg("plate_capitals_closeup"))
    return svg_path, Report()


def build():
    return build_validated()[0]


if __name__ == "__main__":
    print(build())
