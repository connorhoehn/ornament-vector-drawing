"""Text as vector polylines. fonttools converts OTF/TTF glyph outlines to
polylines we can stroke like any other engraving element.

Target fonts (in order of authenticity for 18th-c. engraving):
  1. IM Fell family (Brill Type House) -- closest to real period
  2. EB Garamond -- Renaissance -> Baroque feel
  3. Caslon -- common English period
  4. Bodoni -- late 18th century

At runtime we scan the system font dirs and pick the first available from that
fallback list. macOS stock gives us BigCaslon / Bodoni / Didot / Times New Roman.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Iterable, Sequence

from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTCollection, TTFont

from engraving.geometry import Point, Polyline

# --- font discovery ---------------------------------------------------------

# Ordered by authenticity for classical-plate engraving. First match wins.
# We accept .ttf / .otf / .ttc. For .ttc (font collection) we use fontNumber=0.
_FONT_PREFERENCES: tuple[tuple[str, ...], ...] = (
    # IM Fell / EB Garamond / Caslon (Adobe/Google) if installed locally.
    ("IM_FELL_English_Roman.otf", "IM FELL English Roman.otf",
     "IMFellEnglish-Regular.ttf"),
    ("EBGaramond-Regular.ttf", "EBGaramond12-Regular.otf",
     "EB Garamond.ttf"),
    ("Caslon.ttf", "AdobeCaslonPro-Regular.otf", "BigCaslon.ttf"),
    ("Bodoni 72.ttc", "Bodoni72-Book.ttf", "Bodoni 72 Book.ttf"),
    ("Didot.ttc",),
    ("Times New Roman.ttf", "Times.ttc", "Georgia.ttf"),
)

_FONT_SEARCH_DIRS: tuple[Path, ...] = (
    Path.home() / "Library" / "Fonts",
    Path("/Library/Fonts"),
    Path("/System/Library/Fonts/Supplemental"),
    Path("/System/Library/Fonts"),
)


def _scan_fonts() -> Path | None:
    """Walk preference tiers; return the first font file that exists on disk."""
    for tier in _FONT_PREFERENCES:
        for name in tier:
            for d in _FONT_SEARCH_DIRS:
                p = d / name
                if p.exists():
                    return p
    return None


# Cache at import time (module-level). Re-scan-safe: still just a disk stat.
_DEFAULT_FONT_PATH: Path | None = _scan_fonts()


def default_font_path() -> Path:
    """Return the best-available period-appropriate font on this machine."""
    if _DEFAULT_FONT_PATH is None:
        raise FileNotFoundError(
            "No fallback font found. Install IM Fell, EB Garamond, Caslon, "
            "Bodoni, or ensure Times New Roman is present."
        )
    return _DEFAULT_FONT_PATH


# --- font loading / caching -------------------------------------------------


@lru_cache(maxsize=8)
def _load_ttfont(path_str: str) -> TTFont:
    """Open a font file (or the first face of a TTC) and cache it."""
    p = Path(path_str)
    if p.suffix.lower() == ".ttc":
        return TTFont(str(p), fontNumber=0)
    return TTFont(str(p))


# --- curve flattening -------------------------------------------------------


def _flatten_quad(p0: Point, p1: Point, p2: Point, steps: int = 12) -> list[Point]:
    """Sample a quadratic Bezier (TTF native) at `steps+1` points."""
    out: list[Point] = []
    for i in range(1, steps + 1):
        t = i / steps
        omt = 1.0 - t
        x = omt * omt * p0[0] + 2 * omt * t * p1[0] + t * t * p2[0]
        y = omt * omt * p0[1] + 2 * omt * t * p1[1] + t * t * p2[1]
        out.append((x, y))
    return out


def _flatten_cubic(p0: Point, p1: Point, p2: Point, p3: Point,
                   steps: int = 16) -> list[Point]:
    """Sample a cubic Bezier (OTF native) at `steps+1` points."""
    out: list[Point] = []
    for i in range(1, steps + 1):
        t = i / steps
        omt = 1.0 - t
        b0 = omt ** 3
        b1 = 3 * omt ** 2 * t
        b2 = 3 * omt * t * t
        b3 = t ** 3
        x = b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0]
        y = b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1]
        out.append((x, y))
    return out


def _split_qcurve_tto_quads(curr: Point, ctrls: Sequence[Point],
                            end: Point) -> list[tuple[Point, Point, Point]]:
    """TrueType qCurveTo takes N off-curve points + one on-curve endpoint.
    Consecutive off-curve points have an implied on-curve at their midpoint.
    Return an explicit list of (p0, ctrl, p1) quadratic segments.
    """
    pts = [curr, *ctrls, end]
    # On-curve anchors: first, last, and midpoints between successive ctrls.
    segs: list[tuple[Point, Point, Point]] = []
    p0 = pts[0]
    for i in range(1, len(pts) - 1):
        c = pts[i]
        if i < len(pts) - 2:
            nxt = pts[i + 1]
            mid = ((c[0] + nxt[0]) / 2.0, (c[1] + nxt[1]) / 2.0)
            segs.append((p0, c, mid))
            p0 = mid
        else:
            segs.append((p0, c, pts[-1]))
    return segs


# --- recorder -> polylines --------------------------------------------------


def _contours_from_pen(pen_value) -> list[list[Point]]:
    """Walk RecordingPen commands, flatten curves, return one polyline per
    contour. Font units, y-up (native)."""
    contours: list[list[Point]] = []
    current: list[Point] = []
    curr_pt: Point = (0.0, 0.0)
    start_pt: Point = (0.0, 0.0)

    for op, args in pen_value:
        if op == "moveTo":
            if current:
                contours.append(current)
            curr_pt = args[0]
            start_pt = curr_pt
            current = [curr_pt]
        elif op == "lineTo":
            pt = args[0]
            current.append(pt)
            curr_pt = pt
        elif op == "qCurveTo":
            # All points in args; last is the endpoint. If last is None it's
            # a TrueType all-off-curve loop (rare); skip gracefully.
            if args[-1] is None:
                # Closed quadratic loop: first midpoint as start; skip.
                continue
            end = args[-1]
            ctrls = list(args[:-1])
            for p0, c, p1 in _split_qcurve_tto_quads(curr_pt, ctrls, end):
                current.extend(_flatten_quad(p0, c, p1, steps=12))
            curr_pt = end
        elif op == "curveTo":
            # Cubic: N-1 off-curves + 1 on-curve (usually 2+1).
            pts = [curr_pt, *args]
            # For standard cubics args is (c1, c2, end).
            if len(args) == 3:
                c1, c2, end = args
                current.extend(_flatten_cubic(curr_pt, c1, c2, end, steps=16))
                curr_pt = end
            else:
                # Non-standard; walk in threes.
                for i in range(1, len(pts), 3):
                    p0 = pts[i - 1]
                    c1, c2, end = pts[i], pts[i + 1], pts[i + 2]
                    current.extend(_flatten_cubic(p0, c1, c2, end, steps=16))
                    curr_pt = end
        elif op == "closePath":
            if current and current[0] != current[-1]:
                current.append(current[0])
            if current:
                contours.append(current)
            current = []
            curr_pt = start_pt
        elif op == "endPath":
            if current:
                contours.append(current)
            current = []

    if current:
        contours.append(current)
    return contours


# --- public API -------------------------------------------------------------


def _resolve_font(font_path: Path | None) -> TTFont:
    if font_path is None:
        font_path = default_font_path()
    return _load_ttfont(str(font_path))


def kerned_advance(glyphs: list, spacing: float = 0.0) -> list[float]:
    """Compute per-glyph x-advances (in mm) using the font's kern table.

    glyphs: list of (glyph_name, advance_mm, ttfont) tuples produced internally
    by text_paths. Returned list has one entry per glyph, giving the *offset*
    from the string origin at which that glyph's own coordinate frame starts.
    """
    if not glyphs:
        return []

    advances: list[float] = []
    cursor = 0.0
    kern_pairs: dict[tuple[str, str], float] = {}

    # Pull kern table once; all glyphs share the same font in practice.
    _, _, ttfont = glyphs[0]
    upem = ttfont["head"].unitsPerEm
    if "kern" in ttfont:
        try:
            for table in ttfont["kern"].kernTables:
                kern_pairs.update(table.kernTable)
        except Exception:
            # Some fonts have non-format-0 kern tables fonttools can't read.
            kern_pairs = {}

    # Scale factor: mm per font-unit. Use the first glyph that has a positive
    # native advance; all glyphs in the same call share a consistent scale
    # because text_paths builds adv_mm = native_adv * scale.
    mm_per_unit = 0.0
    for name, adv_mm, tt in glyphs:
        native_adv = tt["hmtx"][name][0] if name in tt["hmtx"].metrics else 0
        if native_adv > 0:
            mm_per_unit = adv_mm / native_adv
            break
    if mm_per_unit == 0.0:
        # Fallback: nominal em-scaling assumed to be 1 upem per character.
        mm_per_unit = 1.0 / upem

    prev_name: str | None = None
    for name, adv_mm, _tt in glyphs:
        if prev_name is not None:
            k_units = kern_pairs.get((prev_name, name), 0)
            cursor += k_units * mm_per_unit
        advances.append(cursor)
        cursor += adv_mm + spacing
        prev_name = name

    return advances


def text_paths(text: str, font_size_mm: float, font_path: Path | None = None,
               anchor: str = "start", baseline_y: float = 0.0,
               letter_spacing: float = 0.0) -> list[Polyline]:
    """Convert a text string to a list of polylines representing the glyph outlines.

    font_size_mm: cap height in mm (NOT em-height; ~70% of em).
    anchor: "start" | "middle" | "end" -- where baseline_y's x origin is.
    letter_spacing: extra mm between characters (positive widens).

    Every glyph contributes one or more closed polylines (outer + holes).
    Strokes are drawn as OUTLINES, not filled -- so they show as thin line
    letterforms suitable for engraving.
    """
    if not text:
        return []

    ttfont = _resolve_font(font_path)
    upem = ttfont["head"].unitsPerEm
    cmap = ttfont.getBestCmap()
    glyph_set = ttfont.getGlyphSet()
    hmtx = ttfont["hmtx"]

    # Cap height: prefer OS/2 sCapHeight; fall back to ascender; fall back to
    # 70% of upem. Everything scales so that cap_height -> font_size_mm.
    cap_height_units = 0
    if "OS/2" in ttfont:
        cap_height_units = getattr(ttfont["OS/2"], "sCapHeight", 0) or 0
    if not cap_height_units and "hhea" in ttfont:
        cap_height_units = int(ttfont["hhea"].ascent * 0.72)
    if not cap_height_units:
        cap_height_units = int(upem * 0.70)
    scale = font_size_mm / cap_height_units

    # Collect (name, advance_mm) per character; unknown chars fall back to
    # '.notdef' (glyph id 0) or are silently skipped if that's also missing.
    entries: list[tuple[str, float, TTFont]] = []
    for ch in text:
        name = cmap.get(ord(ch))
        if name is None:
            # Try .notdef; else skip
            if ".notdef" in glyph_set:
                name = ".notdef"
            else:
                continue
        native_adv = hmtx[name][0] if name in hmtx.metrics else upem // 2
        adv_mm = native_adv * scale
        entries.append((name, adv_mm, ttfont))

    if not entries:
        return []

    offsets = kerned_advance(entries, spacing=letter_spacing)
    total_width = offsets[-1] + entries[-1][1]

    if anchor == "middle":
        x_origin = -total_width / 2.0
    elif anchor == "end":
        x_origin = -total_width
    else:  # "start"
        x_origin = 0.0

    polylines: list[Polyline] = []
    for (name, adv_mm, _tt), x_off in zip(entries, offsets):
        pen = RecordingPen()
        glyph = glyph_set[name]
        glyph.draw(pen)
        contours_native = _contours_from_pen(pen.value)
        gx = x_origin + x_off
        for contour in contours_native:
            # Font y is up, baseline=0. SVG y is down. Flip y.
            pl: Polyline = [
                (gx + px * scale, baseline_y - py * scale)
                for (px, py) in contour
            ]
            if len(pl) >= 2:
                polylines.append(pl)

    return polylines


def title(page, text: str, x: float, y: float, font_size_mm: float = 5.0,
          font_path: Path | None = None, stroke_width: float = 0.25,
          anchor: str = "middle") -> None:
    """Stroke the glyph polylines on a page (replacement for page.text(...))."""
    pls = text_paths(text, font_size_mm=font_size_mm, font_path=font_path,
                     anchor=anchor, baseline_y=0.0)
    for pl in pls:
        shifted = [(px + x, py + y) for (px, py) in pl]
        page.polyline(shifted, stroke="black", stroke_width=stroke_width,
                      fill="none", close=False)


def baseline_grid(x0: float, y0: float, x1: float, y1: float,
                  line_height_mm: float) -> list[float]:
    """Return baseline y-values for N lines filling the region [y0, y1]."""
    if line_height_mm <= 0:
        return []
    ys: list[float] = []
    y = y0 + line_height_mm  # first baseline sits one line-height down
    while y <= y1 + 1e-9:
        ys.append(y)
        y += line_height_mm
    return ys


# --- smoke test -------------------------------------------------------------


if __name__ == "__main__":
    import drawsvg as dw

    font = default_font_path()
    print(f"Using font: {font}")

    glyphs = text_paths("THE TUSCAN ORDER", font_size_mm=8.0, anchor="middle")
    print(f"Polylines: {len(glyphs)}")
    if glyphs:
        xs = [p[0] for pl in glyphs for p in pl]
        ys = [p[1] for pl in glyphs for p in pl]
        print(f"x range: {min(xs):.2f} .. {max(xs):.2f}")
        print(f"y range: {min(ys):.2f} .. {max(ys):.2f}")

    # Physical-size page: 200mm x 30mm so preview.render_svg_to_png maps
    # 1 user unit -> 1 CSS mm -> 3.7795 px at 96 DPI.
    W, H = 200, 30
    d = dw.Drawing(width=f"{W}mm", height=f"{H}mm",
                   viewBox=f"0 0 {W} {H}")
    d.append(dw.Rectangle(0, 0, W, H, fill="white"))
    # Shift text so its middle sits at x=100, baseline y=20.
    for pl in glyphs:
        pts = [(px + 100, py + 20) for (px, py) in pl]
        flat = [c for pt in pts for c in pt]
        d.append(dw.Lines(*flat, close=False, fill="none",
                          stroke="black", stroke_width=0.25))
    d.save_svg("/tmp/typography_test.svg")
    print("SVG: /tmp/typography_test.svg")

    try:
        from engraving.preview import render_svg_to_png
        render_svg_to_png("/tmp/typography_test.svg",
                          "/tmp/typography_test.png", dpi=300)
        print("PNG: /tmp/typography_test.png")
    except Exception as e:
        print(f"PNG render skipped: {e}")
