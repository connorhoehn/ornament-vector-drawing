"""Plate — a running acanthus rinceau frieze, after Raphael's Loggias.

Two horizontal rinceaux span the plate width: a coarser frieze above and
a denser, finer variant below. This showcases the rinceau module at
plate scale, with differentiated stroke weights for spine / silhouette /
creases / buds (the classical engraver's hierarchy).
"""
from __future__ import annotations

import config
from engraving.render import Page, frame
from engraving.rinceau import rinceau, sinusoidal_spine
from engraving.typography import title
from engraving.validate.plates import validate_plate_result


def build_validated() -> tuple[str, "object"]:
    """Render + validate. Returns (svg_path, ValidationReport)."""
    page = Page()
    frame(page)

    # --- Titles ----------------------------------------------------------
    title_y = config.FRAME_INSET + 8
    title(page, "A  RINCEAU  FRIEZE",
          x=config.PLATE_W / 2, y=title_y,
          font_size_mm=5.0, anchor="middle",
          stroke_width=config.STROKE_FINE)
    title(page, "— after Raphael\u2019s Loggias —",
          x=config.PLATE_W / 2, y=title_y + 5.5,
          font_size_mm=2.8, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    # --- Geometry --------------------------------------------------------
    # Inset the rinceau runs inside the frame with a healthy margin so
    # leaf turnovers never kiss the rule.
    margin = config.FRAME_INSET + 10
    x0 = margin
    x1 = config.PLATE_W - margin

    # Top rinceau: coarser leaves, taller amplitude — the "hero" run.
    y_top = config.PLATE_H * 0.40
    spine_top = sinusoidal_spine(
        x0=x0, x1=x1, y0=y_top,
        amplitude=12.0, period=50.0, steps=400,
    )
    r_top = rinceau(spine_top, leaf_size=14.0,
                    spacing_frac=1.3, alternate=True)

    # Bottom rinceau: denser, finer — a "contrast" run sitting below.
    y_bot = config.PLATE_H * 0.65
    spine_bot = sinusoidal_spine(
        x0=x0, x1=x1, y0=y_bot,
        amplitude=8.0, period=35.0, steps=400,
    )
    r_bot = rinceau(spine_bot, leaf_size=9.0,
                    spacing_frac=1.3, alternate=True)

    # --- Between-band caption -------------------------------------------
    mid_y = (y_top + y_bot) / 2.0
    page.text("Spine: sinusoidal;  leaves alternating.",
              x=config.PLATE_W / 2, y=mid_y,
              font_size=2.4, anchor="middle")

    # --- Draw each rinceau with layered stroke weights ------------------
    # The rinceau ElementResult returns per-leaf polylines in groups of
    # len(proto): the FIRST polyline in each group is the closed leaf
    # silhouette; all subsequent polylines are interior creases (midrib +
    # fingers). We pull the prototype length from the metadata-agnostic
    # reconstruction: polylines['leaves'] has leaf_count * proto_len
    # entries.
    def draw_rinceau(r) -> None:
        # Spine: medium weight.
        for pl in r.polylines.get("spine", []):
            page.polyline(pl, stroke_width=config.STROKE_MEDIUM)

        leaves = r.polylines.get("leaves", [])
        leaf_count = r.metadata.get("leaf_count", 0)
        if leaf_count > 0 and leaves:
            proto_len = len(leaves) // leaf_count
        else:
            proto_len = 1
        # Iterate each leaf group: polyline 0 = silhouette (fine),
        # polylines 1..N = creases (hairline).
        for g in range(leaf_count):
            base = g * proto_len
            silhouette = leaves[base] if base < len(leaves) else None
            if silhouette is not None:
                page.polyline(silhouette,
                              stroke_width=config.STROKE_FINE)
            for k in range(1, proto_len):
                idx = base + k
                if idx < len(leaves):
                    page.polyline(leaves[idx],
                                  stroke_width=config.STROKE_HAIRLINE)

        # Buds: ornament weight.
        for pl in r.polylines.get("buds", []):
            page.polyline(pl, stroke_width=config.STROKE_ORNAMENT)

    draw_rinceau(r_top)
    draw_rinceau(r_bot)

    # --- Scale bar -------------------------------------------------------
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

    svg_path = str(page.save_svg("plate_rinceau"))

    # No orders/entablatures/facades — empty report.
    report = validate_plate_result("plate_rinceau", {})
    return svg_path, report


def build() -> str:
    """Legacy API — return only the SVG path."""
    svg_path, _ = build_validated()
    return svg_path


if __name__ == "__main__":
    print(build())
