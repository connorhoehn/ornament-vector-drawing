"""SVG authoring wrapper. Outputs at real physical size in mm.

The Page class writes SVGs whose width/height attributes are in mm so the file
prints 1:1. Stroke widths are also in mm, not viewBox units.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import drawsvg as dw

import config

Point = tuple[float, float]


class Page:
    """A physical-size SVG page. Coordinates are mm, origin top-left."""

    def __init__(self, width_mm: float = config.PLATE_W, height_mm: float = config.PLATE_H,
                 background: str = "white"):
        self.width = width_mm
        self.height = height_mm
        self.d = dw.Drawing(
            width=f"{width_mm}mm",
            height=f"{height_mm}mm",
            viewBox=f"0 0 {width_mm} {height_mm}",
        )
        if background:
            self.d.append(dw.Rectangle(0, 0, width_mm, height_mm, fill=background))

    # --- primitives -------------------------------------------------------
    def polyline(self, pts: Sequence[Point], stroke: str = "black",
                 stroke_width: float = config.STROKE_FINE,
                 fill: str = "none", close: bool = False,
                 linecap: str = "round", linejoin: str = "round") -> None:
        if len(pts) < 2:
            return
        flat: list[float] = []
        for x, y in pts:
            flat.extend([x, y])
        if close:
            el = dw.Lines(*flat, close=True, fill=fill, stroke=stroke,
                          stroke_width=stroke_width, stroke_linecap=linecap,
                          stroke_linejoin=linejoin)
        else:
            el = dw.Lines(*flat, close=False, fill=fill, stroke=stroke,
                          stroke_width=stroke_width, stroke_linecap=linecap,
                          stroke_linejoin=linejoin)
        self.d.append(el)

    def lines(self, segments: Iterable[tuple[Point, Point]], stroke: str = "black",
              stroke_width: float = config.STROKE_FINE) -> None:
        for p0, p1 in segments:
            self.d.append(dw.Line(p0[0], p0[1], p1[0], p1[1],
                                  stroke=stroke, stroke_width=stroke_width,
                                  stroke_linecap="round"))

    def rect(self, x: float, y: float, w: float, h: float,
             stroke: str = "black", stroke_width: float = config.STROKE_MEDIUM,
             fill: str = "none") -> None:
        self.d.append(dw.Rectangle(x, y, w, h, fill=fill, stroke=stroke,
                                   stroke_width=stroke_width))

    def circle(self, cx: float, cy: float, r: float, stroke: str = "black",
               stroke_width: float = config.STROKE_FINE, fill: str = "none") -> None:
        self.d.append(dw.Circle(cx, cy, r, fill=fill, stroke=stroke,
                                stroke_width=stroke_width))

    def text(self, s: str, x: float, y: float, font_size: float = 3.0,
             fill: str = "black", anchor: str = "middle") -> None:
        self.d.append(dw.Text(s, font_size=font_size, x=x, y=y, fill=fill,
                              text_anchor=anchor, font_family="serif"))

    # --- group / layer ---------------------------------------------------
    def group(self, *children) -> None:
        g = dw.Group()
        for c in children:
            g.append(c)
        self.d.append(g)

    # --- output ----------------------------------------------------------
    def save_svg(self, name: str) -> Path:
        path = config.OUT_DIR / (name if name.endswith(".svg") else f"{name}.svg")
        self.d.save_svg(str(path))
        return path

    def save_svg_with_plan(self, name: str, plan) -> Path:
        """Save the SVG with a FacadePlan embedded as <metadata> YAML.

        Allows the resulting file to be reloaded via
        :func:`engraving.planner.io.extract_plan_from_svg`.
        """
        from engraving.planner.io import embed_plan_in_svg

        svg_path = self.save_svg(name)
        text = Path(svg_path).read_text()
        text = embed_plan_in_svg(text, plan)
        Path(svg_path).write_text(text)
        return svg_path


def frame(page: Page, inset: float = config.FRAME_INSET,
          stroke_outer: float = config.STROKE_HEAVY,
          stroke_inner: float = config.STROKE_FINE,
          double_gap: float = 1.2) -> None:
    """Double-rule frame inset from the plate edge, period-standard."""
    x, y = inset, inset
    w, h = page.width - 2 * inset, page.height - 2 * inset
    page.rect(x, y, w, h, stroke="black", stroke_width=stroke_outer)
    page.rect(x + double_gap, y + double_gap,
              w - 2 * double_gap, h - 2 * double_gap,
              stroke="black", stroke_width=stroke_inner)
