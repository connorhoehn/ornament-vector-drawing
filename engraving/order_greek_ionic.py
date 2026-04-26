"""Greek Ionic column silhouette + capital in elevation, after Ware's
*American Vignola* (1903) pp. 33-36 — Erechtheion proportions.

Differences from Roman/Vignola Ionic (`engraving.order_ionic`):
  - No pedestal — the column springs directly from the stylobate.
  - Attic base (same plinth/torus/scotia/torus/fillet profile as Roman).
  - Volute uses the same Holm 12-center schema.
  - Necking is plain in v1 (Greek examples often carry a palmette band).
"""
from __future__ import annotations

import math

from . import canon
from .geometry import Point, Polyline, mirror_path_x
from .schema import ElementResult
from .volute import ionic_volute


def _arc(cx: float, cy: float, rx: float, ry: float,
         t0: float, t1: float, n: int) -> Polyline:
    pts: list[Point] = []
    for i in range(n):
        t = t0 + (t1 - t0) * (i / (n - 1))
        pts.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
    return pts


def greek_ionic_column_silhouette(dims: canon.GreekIonic, cx: float,
                                  base_y: float,
                                  *, return_result: bool = False):
    """Return polylines for a Greek Ionic column in elevation.

    base_y = bottom of column (top of stylobate). cx = centerline.
    """
    D = dims.D
    r_lo = D / 2
    r_up = dims.upper_diam / 2

    # ── Attic base (½D) ────────────────────────────────────────────────
    base_h = dims.base_h
    plinth_h = 0.30 * base_h
    lower_torus_h = 0.18 * base_h
    scotia_h = 0.18 * base_h
    upper_torus_h = 0.22 * base_h
    fillet_base_h = base_h - plinth_h - lower_torus_h - scotia_h - upper_torus_h

    plinth_half = (7.0 / 6.0) * D / 2
    torus_r_lower = 0.5 * lower_torus_h
    torus_r_upper = 0.5 * upper_torus_h
    lower_torus_bulge = min(torus_r_lower, plinth_half - r_lo - 0.005 * D)
    upper_torus_bulge = min(torus_r_upper, plinth_half - r_lo - 0.015 * D)
    scotia_depth = 0.035 * D

    y_col_bot = base_y
    y_plinth_top = y_col_bot - plinth_h
    y_lower_torus_top = y_plinth_top - lower_torus_h
    y_scotia_top = y_lower_torus_top - scotia_h
    y_upper_torus_top = y_scotia_top - upper_torus_h
    y_base_top = y_upper_torus_top - fillet_base_h

    # ── Shaft ──────────────────────────────────────────────────────────
    shaft_break_y = y_base_top - dims.shaft_h / 3.0
    y_shaft_top = y_base_top - dims.shaft_h

    astragal_r = D / 44.0
    astragal_h = 2 * astragal_r
    y_astragal_top = y_shaft_top - astragal_h

    # ── Capital (⅔D) ───────────────────────────────────────────────────
    cap_h = dims.capital_h
    abacus_h = cap_h / 6.0
    abacus_half = (7.0 / 6.0) * D / 2

    y_cap_top = y_astragal_top - cap_h
    y_abacus_bot = y_cap_top + abacus_h

    echinus_project = D / 9.0
    echinus_top_y = y_abacus_bot
    echinus_bot_y = y_astragal_top

    eye_x_right = cx + r_up + echinus_project
    eye_x_left = cx - r_up - echinus_project
    eye_y = y_abacus_bot + D / 3.0

    # ── Right silhouette, bottom-to-top ────────────────────────────────
    R: list[Point] = []
    R.append((cx + plinth_half, y_col_bot))
    R.append((cx + plinth_half, y_plinth_top))
    R.append((cx + r_lo, y_plinth_top))
    l_tor_cy = y_plinth_top - torus_r_lower
    R += _arc(cx + r_lo, l_tor_cy,
              lower_torus_bulge, torus_r_lower,
              math.pi / 2, -math.pi / 2, 22)
    sc_cy = (y_lower_torus_top + y_scotia_top) / 2
    sc_half_h = (y_lower_torus_top - y_scotia_top) / 2
    R += _arc(cx + r_lo, sc_cy,
              scotia_depth, sc_half_h,
              -math.pi / 2, -3 * math.pi / 2, 22)
    u_tor_cy = y_scotia_top - torus_r_upper
    R += _arc(cx + r_lo, u_tor_cy,
              upper_torus_bulge, torus_r_upper,
              math.pi / 2, -math.pi / 2, 22)
    R.append((cx + r_lo, y_base_top))

    R.append((cx + r_lo, shaft_break_y))
    R.append((cx + r_up, y_shaft_top))

    ast_cy = (y_shaft_top + y_astragal_top) / 2
    R += _arc(cx + r_up, ast_cy, astragal_r, astragal_r,
              math.pi / 2, -math.pi / 2, 13)

    echinus_ry = (echinus_bot_y - echinus_top_y)
    R += _arc(cx + r_up, echinus_top_y,
              echinus_project, echinus_ry,
              math.pi / 2, 0.0, 20)

    R.append((cx + abacus_half, y_abacus_bot))
    R.append((cx + abacus_half, y_cap_top))

    L = mirror_path_x(R, cx)

    cap_top = [(cx - abacus_half, y_cap_top), (cx + abacus_half, y_cap_top)]
    col_bot = [(cx - plinth_half, y_col_bot), (cx + plinth_half, y_col_bot)]
    plinth_top = [(cx - plinth_half, y_plinth_top),
                  (cx + plinth_half, y_plinth_top)]
    shaft_top_rule = [(cx - r_up, y_shaft_top), (cx + r_up, y_shaft_top)]
    abacus_bot = [(cx - abacus_half, y_abacus_bot),
                  (cx + abacus_half, y_abacus_bot)]

    legacy: list[Polyline] = [R, L, cap_top, col_bot, plinth_top,
                              shaft_top_rule, abacus_bot]

    # ── Volutes ────────────────────────────────────────────────────────
    vr = ionic_volute(eye_x_right, eye_y, D,
                      direction="right", include_channel=True)
    vl = ionic_volute(eye_x_left, eye_y, D,
                      direction="left", include_channel=True)

    volute_polys: list[Polyline] = []
    for key in ("outer", "channel", "eye"):
        for pl in vl.get(key, []):
            volute_polys.append(pl)
    for key in ("outer", "channel", "eye"):
        for pl in vr.get(key, []):
            volute_polys.append(pl)

    echinus_span_half = eye_x_right - cx
    echinus_center_ry = eye_y - echinus_top_y
    echinus_center = _arc(cx, eye_y,
                          echinus_span_half, echinus_center_ry,
                          math.pi, 2 * math.pi, 40)

    legacy.extend(volute_polys)
    legacy.append(echinus_center)

    if not return_result:
        return legacy

    result = ElementResult(kind="greek_ionic_column", dims_ref=dims)
    result.add_polylines("silhouette", [R, L])
    result.add_polylines("rules", [cap_top, col_bot, plinth_top,
                                   shaft_top_rule, abacus_bot])
    result.add_polylines("volutes", volute_polys)
    result.add_polylines("echinus", [echinus_center])
    result.add_anchor("bottom_center", cx, y_col_bot, "attach")
    result.add_anchor("plinth_top_right", cx + plinth_half, y_plinth_top)
    result.add_anchor("plinth_top_left", cx - plinth_half, y_plinth_top)
    result.add_anchor("base_top_right", cx + r_lo, y_base_top)
    result.add_anchor("base_top_left", cx - r_lo, y_base_top)
    result.add_anchor("shaft_top_right", cx + r_up, y_shaft_top)
    result.add_anchor("shaft_top_left", cx - r_up, y_shaft_top)
    result.add_anchor("astragal_top", cx, y_astragal_top)
    result.add_anchor("echinus_top", cx, echinus_top_y)
    result.add_anchor("abacus_bottom_right", cx + abacus_half, y_abacus_bot)
    result.add_anchor("abacus_bottom_left", cx - abacus_half, y_abacus_bot)
    result.add_anchor("abacus_top_right", cx + abacus_half, y_cap_top)
    result.add_anchor("abacus_top_left", cx - abacus_half, y_cap_top)
    result.add_anchor("top_center", cx, y_cap_top, "attach")
    result.add_anchor("axis", cx, (y_col_bot + y_cap_top) / 2, "axis")
    result.add_anchor("volute_eye_right", eye_x_right, eye_y, "center")
    result.add_anchor("volute_eye_left", eye_x_left, eye_y, "center")
    result.metadata["base_h"] = y_col_bot - y_base_top
    result.metadata["shaft_h"] = y_base_top - y_shaft_top
    result.metadata["capital_h"] = y_astragal_top - y_cap_top
    result.metadata["column_h"] = (result.metadata["base_h"]
                                   + result.metadata["shaft_h"]
                                   + result.metadata["capital_h"])
    result.metadata["num_volutes"] = 2
    # ── Subdivisional metadata (for finer-grained validation) ───────────
    # Attic base: plinth → lower torus → scotia → upper torus → fillet
    # (Ware pp.33-36, Erechtheion profile).
    result.metadata["base_plinth_h"] = y_col_bot - y_plinth_top
    result.metadata["base_lower_torus_h"] = y_plinth_top - y_lower_torus_top
    result.metadata["base_scotia_h"] = y_lower_torus_top - y_scotia_top
    result.metadata["base_upper_torus_h"] = y_scotia_top - y_upper_torus_top
    result.metadata["base_torus_h"] = (
        result.metadata["base_lower_torus_h"]
        + result.metadata["base_upper_torus_h"])
    result.metadata["base_fillet_h"] = y_upper_torus_top - y_base_top
    # Capital: volute/echinus zone + abacus.
    result.metadata["cap_volute_h"] = y_astragal_top - y_abacus_bot
    result.metadata["cap_echinus_h"] = y_astragal_top - y_abacus_bot
    result.metadata["cap_abacus_h"] = y_abacus_bot - y_cap_top
    result.compute_bbox()
    return result


# ── Smoke test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import drawsvg as dw

    dims = canon.GreekIonic(D=24)
    polys = greek_ionic_column_silhouette(dims, cx=100, base_y=220)

    W, H = 200.0, 250.0
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
    d.save_svg("/tmp/greek_ionic_test.svg")
    print(f"Wrote /tmp/greek_ionic_test.svg — {len(polys)} polylines; "
          f"column height {dims.column_h:.1f} mm at D={dims.D} mm.")
