"""Export pipeline: SVG → optimized SVG → PDF.

The pipeline has three stages:
  1. RAW SVG — what plate builders produce (what's in out/plate_*.svg today)
  2. OPTIMIZED SVG — merged contiguous strokes, reordered for pen-path efficiency
  3. PDF — 1:1 physical dimensions preserved, ready for printing on A4/Letter

vpype handles stages 1 -> 2. For 2 -> 3, we use a browser-based print-to-PDF via
Playwright (which we already have) because it preserves mm dimensions reliably.
"""
from __future__ import annotations

import subprocess
from pathlib import Path


def optimize_svg(input_svg: str | Path, output_svg: str | Path | None = None,
                 tolerance: float = 0.05) -> Path:
    """Merge contiguous segments and sort paths via vpype.

    The `linemerge`, `linesort`, and `linesimplify` pipeline removes duplicates,
    merges collinear segments, and optimizes the drawing order to minimize
    plotter pen-travel distance.

    Raises RuntimeError if vpype is not available or the command fails.
    """
    from shutil import which
    input_svg = Path(input_svg).resolve()
    output_svg = (Path(output_svg).resolve() if output_svg
                  else input_svg.with_suffix(".opt.svg"))

    project_root = Path(__file__).parent.parent
    candidate = project_root / ".venv" / "bin" / "vpype"
    vpype_exe = which("vpype") or (str(candidate) if candidate.exists() else None)
    if not vpype_exe:
        raise RuntimeError(
            "vpype not available (install failed on Python 3.14 due to shapely/GEOS)"
        )

    # Pipeline: read -> merge (dedupe collinear) -> simplify -> sort -> write
    cmd = [
        vpype_exe,
        "read", str(input_svg),
        "linemerge", "--tolerance", str(tolerance),
        "linesimplify", "--tolerance", str(tolerance),
        "linesort",
        "write", str(output_svg),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"vpype failed: {result.stderr}")
    return output_svg


def svg_to_pdf(input_svg: str | Path, output_pdf: str | Path | None = None,
               preserve_mm: bool = True) -> Path:
    """Convert an SVG to PDF using Playwright (preserves mm dimensions).

    The plate SVG declares width/height in mm and a viewBox in mm-units, so
    placing it as an <object> at its natural size renders 1:1 on a print page
    sized to match the plate.
    """
    from playwright.sync_api import sync_playwright

    input_svg = Path(input_svg).resolve()
    output_pdf = (Path(output_pdf).resolve() if output_pdf
                  else input_svg.with_suffix(".pdf"))

    # Read the SVG to extract width/height in mm so we can set @page size to
    # match. Falls back to config.PLATE_W / PLATE_H if parsing fails.
    import re
    import config as _config
    try:
        text = input_svg.read_text()
        w_m = re.search(r'width="([\d.]+)mm"', text)
        h_m = re.search(r'height="([\d.]+)mm"', text)
        width_mm = float(w_m.group(1)) if w_m else _config.PLATE_W
        height_mm = float(h_m.group(1)) if h_m else _config.PLATE_H
    except Exception:
        width_mm, height_mm = _config.PLATE_W, _config.PLATE_H

    # Inline the SVG (rather than <object data="file://...">) so Playwright
    # doesn't fight same-origin / object-embedding issues.
    svg_text = input_svg.read_text()
    # Strip any XML declaration so it can be embedded inside HTML body
    svg_text = re.sub(r"<\?xml[^?]*\?>", "", svg_text).strip()

    html = f"""<!doctype html>
<html><head>
<meta charset="UTF-8">
<style>
@page {{ size: {width_mm}mm {height_mm}mm; margin: 0; }}
html, body {{ margin: 0; padding: 0; }}
svg {{ display: block; width: {width_mm}mm; height: {height_mm}mm; }}
</style>
</head><body>
{svg_text}
</body></html>"""
    html_path = input_svg.with_suffix(".print.html")
    html_path.write_text(html, encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_context().new_page()
        page.goto(f"file://{html_path}")
        try:
            page.wait_for_load_state("networkidle", timeout=5000)
        except Exception:
            pass
        # Use CSS @page size so mm dimensions are preserved faithfully.
        page.pdf(
            path=str(output_pdf),
            print_background=True,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            prefer_css_page_size=True,
        )
        browser.close()

    html_path.unlink(missing_ok=True)
    return output_pdf


def concat_pdfs(pdf_paths: list[Path], output_pdf: str | Path) -> Path:
    """Concatenate multiple PDFs into a single bound-book PDF."""
    try:
        from pypdf import PdfWriter, PdfReader
    except ImportError:
        subprocess.run([str(Path(__file__).parent.parent / ".venv/bin/pip"),
                        "install", "pypdf", "--quiet"])
        from pypdf import PdfWriter, PdfReader

    writer = PdfWriter()
    for p in pdf_paths:
        reader = PdfReader(str(p))
        for page in reader.pages:
            writer.add_page(page)
    output_pdf = Path(output_pdf).resolve()
    with open(output_pdf, "wb") as f:
        writer.write(f)
    return output_pdf


def render_plate_to_print(svg_path: str | Path,
                          optimize: bool = True,
                          export_pdf: bool = True) -> dict:
    """Full pipeline for one plate: optimize SVG + export PDF.

    Returns dict with:
      "input_svg": original
      "optimized_svg": after vpype (or original if optimize=False / vpype missing)
      "pdf": PDF path (if export_pdf)
    """
    svg_path = Path(svg_path)
    result: dict = {"input_svg": svg_path}
    if optimize:
        try:
            opt = optimize_svg(svg_path)
            result["optimized_svg"] = opt
        except RuntimeError as e:
            print(f"  vpype optimization failed: {e}; using original SVG")
            result["optimized_svg"] = svg_path
    else:
        result["optimized_svg"] = svg_path
    if export_pdf:
        pdf = svg_to_pdf(result["optimized_svg"])
        result["pdf"] = pdf
    return result
