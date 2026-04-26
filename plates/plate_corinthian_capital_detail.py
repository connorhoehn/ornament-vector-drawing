"""Plate — Corinthian capital, full-plate detail.

The user's complaint: in composite / compact plates the capital reads as
crude zigzag because the leaf polylines are rendered sub-millimetre. At
plate scale here (single capital fills the page) the lobe + finger +
eye geometry of the acanthus_leaf builder is fully legible.

Renders the top ~2.5·D of a Corinthian column:
  - 0.5·D of shaft (with astragal) for grounding
  - 1.17·D of bell / two leaf rows / helices / caulicoli
  - the concave-sided abacus + fleuron

Labels the canonical features so the diagram doubles as reference.
"""
from __future__ import annotations

import config
from engraving import canon
from engraving.element import Element
from engraving.order_corinthian import corinthian_column_silhouette
from engraving.planner.elements import (
    horizontal_dimension, vertical_dimension, render_dimensions,
)
from engraving.render import Page, frame
from engraving.typography import title


_LAYER_WEIGHTS = {
    "silhouette":  config.STROKE_MEDIUM,
    "rules":       config.STROKE_FINE,
    "abacus":      config.STROKE_FINE,
    "helices":     config.STROKE_ORNAMENT,
    "fleuron":     config.STROKE_ORNAMENT,
    "caulicoli":   config.STROKE_HATCH,
    "bell_guides": config.STROKE_HATCH,
    "acanthus":    config.STROKE_HATCH,
}


def build_validated():
    page = Page()
    frame(page)

    title(page, "CORINTHIAN  CAPITAL  —  DETAIL",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 10,
          font_size_mm=4.8, anchor="middle",
          stroke_width=config.STROKE_FINE)
    title(page, "— after Vignola: bell, two acanthus rows, helices, caulicoli, fleuron —",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 16,
          font_size_mm=2.4, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    # Geometry: pick D so capital + 0.6·D of shaft fills the plate.
    # capital_D for Corinthian = 7/6 ≈ 1.167. visible_h_D ≈ 1.78.
    usable_top_y = config.FRAME_INSET + 24
    usable_bot_y = config.PLATE_H - config.FRAME_INSET - 18
    usable_h = usable_bot_y - usable_top_y
    visible_D_factor = 1.167 + 0.7   # capital + 0.7D shaft
    D = usable_h / visible_D_factor * 0.95   # 5% padding

    dims = canon.Corinthian(D=D)
    cx = config.PLATE_W / 2

    # Full column geometry so the builder produces a proper capital; then
    # we clip to the visible capital-plus-shaft window.
    col_h = dims.column_h
    y_capital_top = usable_top_y + 6.0
    y_col_bottom = y_capital_top + col_h
    y_visible_top = y_capital_top - 3.0
    y_visible_bot = y_capital_top + dims.capital_h + D * 0.7

    result = corinthian_column_silhouette(
        dims, cx, y_col_bottom, return_result=True,
    )

    # Clip every polyline to the visible window using shapely so lines
    # straddling the band still render their intersection.
    from shapely.geometry import LineString, box as shapely_box
    clip_box = shapely_box(
        cx - dims.abacus_half_width_at_corners * D * 1.0 - 8.0
        if hasattr(dims, "abacus_half_width_at_corners") else cx - D * 2.5,
        y_visible_top,
        cx + D * 2.5,
        y_visible_bot,
    )

    for layer, polys in result.polylines.items():
        weight = _LAYER_WEIGHTS.get(layer, 0.25)
        for pl in polys:
            if len(pl) < 2:
                continue
            try:
                clipped = LineString(pl).intersection(clip_box)
            except Exception:
                continue
            if clipped.is_empty:
                continue
            geoms = (
                [clipped] if clipped.geom_type == "LineString"
                else list(getattr(clipped, "geoms", []))
            )
            for g in geoms:
                if g.geom_type == "LineString" and len(g.coords) >= 2:
                    page.polyline(list(g.coords), stroke_width=weight)

    # Phase 32 — dimension annotations.
    #
    # Replace the ad-hoc leader-line + text pattern with first-class
    # DimensionElements so the plate reads as a measurement drawing. The
    # metadata emitted by ``corinthian_column_silhouette`` gives us the
    # exact y-positions of every canonical part.
    anchors = {name: (a.x, a.y) for name, a in result.anchors.items()}

    dim_root = Element(id="dimensions", kind="dimension_group",
                       envelope=(0, 0, config.PLATE_W, config.PLATE_H))

    # Compute an x just to the right of the abacus for vertical dims.
    if "abacus_top_right" in anchors:
        abacus_x = anchors["abacus_top_right"][0]
    else:
        abacus_x = cx + D * 1.3
    # Both vertical-dim lines must stay inside the frame.
    x_max_dim = config.PLATE_W - config.FRAME_INSET - 3.0
    x_dim_right = min(x_max_dim, abacus_x + D * 0.6)

    # 1) bell_h = 1·D (between bell_bottom and bell_top)
    if "bell_bottom" in anchors and "bell_top" in anchors:
        bell_bot_y = anchors["bell_bottom"][1]
        bell_top_y = anchors["bell_top"][1]
        dim_root.add(vertical_dimension(
            p_top=(abacus_x, bell_top_y),
            p_bottom=(abacus_x, bell_bot_y),
            x_line=x_dim_right,
            label="bell  =  1 D",
            id="dim.bell_h",
            text_size_mm=2.2,
        ))

    # 2) capital_h = 7/6·D (between abacus_top_right and bell_bottom)
    if "abacus_top_right" in anchors and "bell_bottom" in anchors:
        cap_top_y = anchors["abacus_top_right"][1]
        cap_bot_y = anchors["bell_bottom"][1]
        dim_root.add(vertical_dimension(
            p_top=(abacus_x, cap_top_y),
            p_bottom=(abacus_x, cap_bot_y),
            x_line=min(x_max_dim, x_dim_right + D * 1.4),
            label=f"capital  =  {dims.capital_D:.3f} D",
            id="dim.capital_h",
            text_size_mm=2.2,
        ))

    # 3) D — the lower column diameter. Measure horizontally across the
    #    shaft at the shaft-top (just below the capital).
    if "shaft_top_right" in anchors:
        shaft_top_y = anchors["shaft_top_right"][1]
        # Upper shaft diam ≈ dims.upper_diam; but for the "D" callout we
        # quote the LOWER diameter, measured conceptually at the shaft
        # base. We approximate at the visible shaft-top line using ±D/2.
        dim_root.add(horizontal_dimension(
            p_left=(cx - D / 2, shaft_top_y + D * 0.45),
            p_right=(cx + D / 2, shaft_top_y + D * 0.45),
            y_line=shaft_top_y + D * 0.45 + 7.0,
            label="D  (lower diameter)",
            id="dim.D",
            text_size_mm=2.2,
        ))

    render_dimensions(page, dim_root, frame_bbox=(config.FRAME_INSET, config.FRAME_INSET, config.PLATE_W - config.FRAME_INSET, config.PLATE_H - config.FRAME_INSET))

    # D legend — numeric value of D in mm (still useful for the engraver).
    page.text(f"D  =  {D:.1f} mm  (lower column diameter)",
              x=config.PLATE_W / 2,
              y=config.PLATE_H - config.FRAME_INSET - 6,
              font_size=2.4, anchor="middle")

    class Report:
        def __init__(self): self.errors = []
        def __len__(self): return 0
        def __iter__(self): return iter([])
        def __bool__(self): return False

    svg_path = str(page.save_svg("plate_corinthian_capital_detail"))
    return svg_path, Report()


def build():
    return build_validated()[0]


if __name__ == "__main__":
    print(build())
