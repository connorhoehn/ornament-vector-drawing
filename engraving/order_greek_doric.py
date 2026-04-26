"""Greek Doric column silhouette in elevation, after Ware's *American
Vignola* (1903) pp. 33-36 — Parthenon proportions.

Differences from Roman Doric (`engraving.order_doric`):
  - No base: the shaft rises directly from the stylobate (`base_y`).
  - Capital carries 3-5 annulet rings at the base of the echinus.
  - Echinus projects more dramatically (the "squashed cushion" profile).
  - Abacus is a plain unmolded block.
  - Column is stouter (5.5 D vs 8 D).

Fluting and entablature are separate concerns (this file only builds the
column silhouette plus the annulet rules).
"""
from __future__ import annotations

import math

from . import canon
from .geometry import Point, Polyline, mirror_path_x
from .schema import ElementResult


def _arc(cx: float, cy: float, rx: float, ry: float,
         t0: float, t1: float, n: int) -> Polyline:
    pts: list[Point] = []
    for i in range(n):
        t = t0 + (t1 - t0) * (i / (n - 1))
        pts.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
    return pts


def greek_doric_column_silhouette(dims: canon.GreekDoric, cx: float,
                                  base_y: float,
                                  *, return_result: bool = False):
    """Return polylines for a Greek Doric column in elevation.

    base_y = bottom of column (top of stylobate). Column grows up
    (y decreases in SVG coords). cx = column centerline x.

    If ``return_result=True``, returns an :class:`ElementResult` with named
    anchors and categorized polyline layers. Otherwise returns the legacy
    flat list of polylines.
    """
    D = dims.D
    r_lo = D / 2
    r_up = dims.upper_diam / 2

    # ── No base — shaft sits directly on stylobate ─────────────────────
    y_shaft_bot = base_y
    # Shaft height = column_h - capital_h (base_h = 0)
    shaft_h = dims.shaft_h
    y_shaft_top = y_shaft_bot - shaft_h

    # Entasis: cylindrical first third, then taper to r_up.
    shaft_break_y = y_shaft_bot - shaft_h / 3.0

    # ── Capital ─────────────────────────────────────────────────────────
    cap_h = dims.capital_h
    # Annulets occupy a tight band at the base of the capital; the echinus
    # ("squashed cushion") bulges above them; a plain abacus blocks the top.
    # The annulet band is deliberately kept small so the eye reads the
    # shaft flowing continuously into the echinus rather than seeing a blank
    # cylinder-extension above the flutes. Roughly: annulets ~8% of capital,
    # echinus ~55%, abacus ~37% — tuned to plate scale.
    annulet_h_total = 0.08 * cap_h
    echinus_h = 0.55 * cap_h
    abacus_h = cap_h - annulet_h_total - echinus_h

    y_annulets_bot = y_shaft_top
    y_annulets_top = y_annulets_bot - annulet_h_total
    y_echinus_top = y_annulets_top - echinus_h
    y_cap_top = y_echinus_top - abacus_h       # == y_shaft_top - cap_h

    echinus_project = dims.echinus_projection_D * D
    # Abacus of Greek Doric is plain and squares up slightly outside the
    # echinus' widest point — a small pad keeps the block reading as a block.
    abacus_half = r_up + echinus_project + 0.05 * D

    # ── Build right silhouette, bottom-to-top ──────────────────────────
    R: list[Point] = [
        (cx + r_lo, y_shaft_bot),          # column springs from stylobate
        (cx + r_lo, shaft_break_y),
        (cx + r_up, y_shaft_top),
    ]
    # Annulets region: cylindrical at r_up.
    R.append((cx + r_up, y_annulets_top))
    # Echinus — dramatic convex quarter-ellipse outward and up.
    # The arc center sits at y_echinus_top so the ellipse's bottom-right
    # corner touches (cx+r_up, y_annulets_top) and its outer extreme reaches
    # (cx+r_up+echinus_project, y_echinus_top). Using y_annulets_top as the
    # arc center (the previous behavior) sent the echinus DOWNWARD into the
    # shaft because SVG y points down, so sin(pi/2)·ry ADDS to y.
    R += _arc(cx + r_up, y_echinus_top,
              echinus_project, echinus_h,
              math.pi / 2, 0.0, 22)
    # Abacus plain block.
    R.append((cx + abacus_half, y_echinus_top))
    R.append((cx + abacus_half, y_cap_top))

    L = mirror_path_x(R, cx)

    # Annulet rules — thin horizontal rulings between the shaft and echinus.
    annulet_rules: list[Polyline] = []
    for i in range(dims.annulet_count):
        frac = (i + 1) / (dims.annulet_count + 1)
        y = y_annulets_bot - annulet_h_total * frac
        annulet_rules.append([(cx - r_up, y), (cx + r_up, y)])

    cap_top = [(cx - abacus_half, y_cap_top), (cx + abacus_half, y_cap_top)]
    col_bot = [(cx - r_lo, y_shaft_bot), (cx + r_lo, y_shaft_bot)]
    abacus_bot = [(cx - abacus_half, y_echinus_top),
                  (cx + abacus_half, y_echinus_top)]
    shaft_top_rule = [(cx - r_up, y_shaft_top), (cx + r_up, y_shaft_top)]

    legacy = [R, L, cap_top, col_bot, abacus_bot, shaft_top_rule]
    legacy.extend(annulet_rules)
    if not return_result:
        return legacy

    result = ElementResult(kind="greek_doric_column", dims_ref=dims)
    result.add_polylines("silhouette", [R, L])
    result.add_polylines("rules", [cap_top, col_bot, abacus_bot,
                                   shaft_top_rule])
    result.add_polylines("annulets", annulet_rules)
    result.add_anchor("bottom_center", cx, y_shaft_bot, "attach")
    result.add_anchor("shaft_top_right", cx + r_up, y_shaft_top)
    result.add_anchor("shaft_top_left", cx - r_up, y_shaft_top)
    result.add_anchor("abacus_bottom_right", cx + abacus_half, y_echinus_top)
    result.add_anchor("abacus_bottom_left", cx - abacus_half, y_echinus_top)
    result.add_anchor("abacus_top_right", cx + abacus_half, y_cap_top)
    result.add_anchor("abacus_top_left", cx - abacus_half, y_cap_top)
    result.add_anchor("top_center", cx, y_cap_top, "attach")
    result.add_anchor("axis", cx, (y_shaft_bot + y_cap_top) / 2, "axis")
    result.metadata["base_h"] = 0.0
    result.metadata["shaft_h"] = y_shaft_bot - y_shaft_top
    result.metadata["capital_h"] = y_shaft_top - y_cap_top
    result.metadata["column_h"] = y_shaft_bot - y_cap_top
    result.metadata["num_annulets"] = dims.annulet_count
    # ── Subdivisional metadata (for finer-grained validation) ───────────
    # No base (column springs from stylobate). Capital: annulets + echinus
    # + abacus (Ware pp.33-36).
    result.metadata["cap_annulet_h"] = y_annulets_bot - y_annulets_top
    result.metadata["cap_echinus_h"] = y_annulets_top - y_echinus_top
    result.metadata["cap_abacus_h"] = y_echinus_top - y_cap_top
    result.compute_bbox()
    return result


# ── Smoke test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import drawsvg as dw

    dims = canon.GreekDoric(D=24)
    polys = greek_doric_column_silhouette(dims, cx=60, base_y=200)

    W, H = 120.0, 220.0
    d = dw.Drawing(width=f"{W}mm", height=f"{H}mm",
                   viewBox=f"0 0 {W} {H}")
    d.append(dw.Rectangle(0, 0, W, H, fill="white"))
    for poly in polys:
        if len(poly) < 2:
            continue
        flat: list[float] = []
        for x, y in poly:
            flat.extend([x, y])
        d.append(dw.Lines(*flat, close=False, fill="none",
                          stroke="black", stroke_width=0.25,
                          stroke_linecap="round", stroke_linejoin="round"))
    d.save_svg("/tmp/greek_doric_test.svg")
    print(f"Wrote /tmp/greek_doric_test.svg — {len(polys)} polylines; "
          f"column height {dims.column_h:.1f} mm at D={dims.D} mm.")
