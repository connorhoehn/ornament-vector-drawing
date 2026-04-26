"""Headless Playwright rendering of SVG files to PNG for visual inspection.

Usage:
    from engraving.preview import render_svg_to_png
    render_svg_to_png("out/plate_01.svg", "out/plate_01.png", dpi=150)

The DPI controls pixel resolution. Physical dimensions (mm) are preserved in the
SVG itself, so the PNG pixel dims reflect how the plate would print at that DPI.
"""
from __future__ import annotations

from pathlib import Path


def render_svg_to_png(svg_path: str | Path, png_path: str | Path, dpi: int = 150,
                      background: str = "white") -> Path:
    """Render an SVG to PNG via headless Chromium at the requested DPI."""
    from playwright.sync_api import sync_playwright

    svg_path = Path(svg_path).resolve()
    png_path = Path(png_path).resolve()
    png_path.parent.mkdir(parents=True, exist_ok=True)

    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><style>
  html, body {{ margin: 0; padding: 0; background: {background}; }}
  /* SVG with mm width/height will size in CSS mm; Chromium maps 1 CSS mm = 3.7795 CSS px. */
  svg {{ display: block; }}
</style></head><body>
  <object type="image/svg+xml" data="file://{svg_path}"></object>
</body></html>"""

    html_path = svg_path.with_suffix(".preview.html")
    html_path.write_text(html, encoding="utf-8")

    device_scale = dpi / 96.0  # browser default is 96 px/in; scale for target DPI

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(device_scale_factor=device_scale)
        page = context.new_page()
        page.goto(f"file://{html_path}")
        # Give the object tag a beat to load its SVG.
        page.wait_for_load_state("networkidle", timeout=5000)
        # Screenshot the object's bounding box (the rendered SVG).
        obj = page.locator("object")
        box = obj.bounding_box()
        if box is None:
            # Fall back to full page if <object> didn't measure.
            page.screenshot(path=str(png_path), omit_background=False, full_page=True)
        else:
            page.screenshot(path=str(png_path), clip=box)
        browser.close()

    html_path.unlink(missing_ok=True)
    return png_path


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python -m engraving.preview <in.svg> [out.png] [dpi]")
        sys.exit(2)
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".png")
    dpi = int(sys.argv[3]) if len(sys.argv) > 3 else 150
    out = render_svg_to_png(src, dst, dpi=dpi)
    print(out)
