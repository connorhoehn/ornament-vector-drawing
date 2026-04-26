"""Plate — one acanthus leaf at full plate scale.

Diagnostic: shows the exact output of ``engraving.acanthus.acanthus_leaf``
at ~160mm tall so every lobe + finger is readable. The plate is a pure
test of the leaf-builder geometry.
"""
from __future__ import annotations

import config
from engraving import acanthus
from engraving.render import Page, frame
from engraving.typography import title


def build_validated():
    page = Page()
    frame(page)

    title(page, "ACANTHUS  LEAF  —  DETAIL",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 10,
          font_size_mm=4.6, anchor="middle",
          stroke_width=config.STROKE_FINE)
    title(page, "— single leaf, lobe_count=5, teeth_per_lobe=4 —",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 16,
          font_size_mm=2.6, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    # Fill the plate: width ≈ 100mm, height ≈ 150mm.
    leaf_w = 100.0
    leaf_h = 150.0
    cx = config.PLATE_W / 2
    tip_y = config.FRAME_INSET + 26        # tip at top of plate
    base_y = tip_y + leaf_h                # root at bottom

    polys = acanthus.acanthus_leaf(
        width=leaf_w, height=leaf_h,
        lobe_count=5, teeth_per_lobe=4,
    )
    # Offset leaf so its tip is at (cx, tip_y). The builder returns
    # centred at (0, 0) with y axis pointing up; translate accordingly.
    # Leaf's local coords span roughly x ∈ [-w/2, w/2] and y ∈ [-h/2, h/2]
    # with tip at top (negative y in the rendered leaf, or positive?
    # Let's translate leaf into page coords by putting leaf-center at
    # (cx, (tip_y + base_y) / 2) and flipping y so leaf "grows up".
    center_y = (tip_y + base_y) / 2
    for pl in polys:
        # Flip y so leaf's natural up = page's up (smaller y).
        shifted = [(cx + x, center_y - y) for (x, y) in pl]
        page.polyline(shifted, stroke_width=config.STROKE_MEDIUM)

    page.text(
        f"leaf width {leaf_w:.0f} mm  ×  height {leaf_h:.0f} mm",
        x=config.PLATE_W / 2,
        y=config.PLATE_H - config.FRAME_INSET - 6,
        font_size=2.4, anchor="middle",
    )

    class Report:
        def __init__(self): self.errors = []
        def __len__(self): return 0
        def __iter__(self): return iter([])
        def __bool__(self): return False

    svg_path = str(page.save_svg("plate_acanthus_leaf_detail"))
    return svg_path, Report()


def build():
    return build_validated()[0]


if __name__ == "__main__":
    print(build())
