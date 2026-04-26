"""Doric column silhouette in elevation, after Ware's *American Vignola* (1903).

Mirrors the structure of `orders.tuscan_column_silhouette`. The Doric column
is 8D tall (vs Tuscan's 7D) at the same lower diameter, yielding a noticeably
stouter appearance. Its capital is plainer than the Tuscan — no astragal
between the necking and the echinus — but the shaft itself carries a small
astragal (bead) at its top, just below the necking.

Fluting and entablature belong to separate modules.
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


def doric_column_silhouette(dims: canon.Doric, cx: float, base_y: float,
                            *, return_result: bool = False):
    """Return polylines for a Doric column in elevation.

    base_y = bottom of column (top of pedestal). Column grows up (y decreases).
    cx    = column centerline x.

    Return order:
      [right_silhouette, left_silhouette, cap_top_rule, col_bot_rule,
       plinth_top_rule, shaft_top_rule, abacus_bot_rule]

    If ``return_result=True``, returns an :class:`ElementResult` with named
    anchors and categorized polyline layers. Otherwise (default) returns the
    legacy flat list of polylines for backward compatibility.
    """
    D = dims.D
    M = dims.M
    r_lo = D / 2            # = M
    r_up = dims.upper_diam / 2

    # ── Base (½D incl. cincture) ────────────────────────────────────────
    # Vignola's Doric base matches the Tuscan in outline: plinth, torus, fillet.
    base_h = dims.base_h
    plinth_h = 0.50 * base_h
    torus_h_nom = 0.35 * base_h
    fillet_base_h = 0.15 * base_h

    # Plinth half-width = 7/12 D (same as Tuscan via 7/6 D full width).
    plinth_half = (7.0 / 6.0) * D / 2

    # Torus radius: canonical ≈ 0.175 × base_h (so diameter = 0.35 × base_h),
    # but clamp so it doesn't overrun the plinth.
    torus_r = min(torus_h_nom / 2, plinth_half - r_lo - 0.02 * M)
    torus_h = 2 * torus_r
    # Any height forfeited by the torus clamp becomes extra fillet.
    fillet_base_h = base_h - plinth_h - torus_h

    y_col_bot = base_y
    y_plinth_top = y_col_bot - plinth_h
    y_torus_bot = y_plinth_top
    y_torus_top = y_torus_bot - torus_h
    y_base_top = y_torus_top - fillet_base_h

    # ── Shaft ───────────────────────────────────────────────────────────
    # Entasis convention (Vignola): bottom third cylindrical at r_lo, then
    # linear taper to r_up at the shaft top.
    shaft_break_y = y_base_top - dims.shaft_h / 3.0
    y_shaft_top = y_base_top - dims.shaft_h

    # Astragal (bead) at the very top of the shaft, below the necking.
    # Ware: astragal height ≈ 1/22 D, so radius ≈ 1/44 D.
    astragal_r = D / 44.0
    astragal_h = 2 * astragal_r

    y_astragal_top = y_shaft_top - astragal_h     # top of the bead
    # The bead sits on the upper-shaft diameter r_up. Its silhouette cuts
    # into the shaft's top limit by astragal_h — so the shaft proper terminates
    # a bead's height below the base of the necking.

    # ── Capital (½D) ────────────────────────────────────────────────────
    # Ware: Necking ⅙D, Echinus-and-bead ⅙D, Abacus ⅙D → ½D total.
    cap_h = dims.capital_h
    neck_h = cap_h / 3.0
    echinus_h = cap_h / 3.0
    abacus_h = cap_h - neck_h - echinus_h

    y_neck_top = y_astragal_top - neck_h
    y_echinus_top = y_neck_top - echinus_h
    y_cap_top = y_echinus_top - abacus_h

    # Echinus projects outward to the abacus edge.
    abacus_half = (7.0 / 6.0) * D / 2
    echinus_project = abacus_half - r_up

    # ── Build right silhouette bottom-to-top ────────────────────────────
    R: list[Point] = []
    # Plinth
    R.append((cx + plinth_half, y_col_bot))
    R.append((cx + plinth_half, y_plinth_top))
    # Step in to start of torus bulge
    R.append((cx + r_lo, y_plinth_top))
    # Torus: right-bulging semi-circle from bottom of torus band up to top
    tor_cy = y_torus_bot - torus_r
    R += _arc(cx + r_lo, tor_cy, torus_r, torus_r, math.pi / 2, -math.pi / 2, 25)
    # Fillet above torus, up to base top
    R.append((cx + r_lo, y_base_top))

    # Shaft: cylindrical ⅓, then tapered to r_up
    R.append((cx + r_lo, shaft_break_y))
    R.append((cx + r_up, y_shaft_top))

    # Astragal — small bead bulging right at the top of the shaft
    ast_cy = (y_shaft_top + y_astragal_top) / 2
    R += _arc(cx + r_up, ast_cy, astragal_r, astragal_r,
              math.pi / 2, -math.pi / 2, 13)

    # Necking — plain cylinder at r_up (no fillet top or bottom, Doric-plain)
    R.append((cx + r_up, y_neck_top))

    # Echinus — convex ellipse quarter from (cx+r_up, y_neck_top)
    # outward-and-up to (cx+r_up+echinus_project, y_echinus_top)
    R += _arc(cx + r_up, y_echinus_top, echinus_project, echinus_h,
              math.pi / 2, 0.0, 22)

    # Abacus (plain rectangular block)
    R.append((cx + abacus_half, y_echinus_top))
    R.append((cx + abacus_half, y_cap_top))

    L = mirror_path_x(R, cx)

    cap_top = [(cx - abacus_half, y_cap_top), (cx + abacus_half, y_cap_top)]
    col_bot = [(cx - plinth_half, y_col_bot), (cx + plinth_half, y_col_bot)]
    plinth_top = [(cx - plinth_half, y_plinth_top), (cx + plinth_half, y_plinth_top)]
    shaft_top_rule = [(cx - r_up, y_shaft_top), (cx + r_up, y_shaft_top)]
    abacus_bot = [(cx - abacus_half, y_echinus_top), (cx + abacus_half, y_echinus_top)]

    legacy = [R, L, cap_top, col_bot, plinth_top, shaft_top_rule, abacus_bot]
    if not return_result:
        return legacy

    result = ElementResult(kind="doric_column", dims_ref=dims)
    result.add_polylines("silhouette", [R, L])
    result.add_polylines("rules", [cap_top, col_bot, plinth_top,
                                   shaft_top_rule, abacus_bot])
    result.add_anchor("bottom_center", cx, y_col_bot, "attach")
    result.add_anchor("plinth_top_right", cx + plinth_half, y_plinth_top)
    result.add_anchor("plinth_top_left", cx - plinth_half, y_plinth_top)
    result.add_anchor("base_top_right", cx + r_lo, y_base_top)
    result.add_anchor("base_top_left", cx - r_lo, y_base_top)
    result.add_anchor("shaft_top_right", cx + r_up, y_shaft_top)
    result.add_anchor("shaft_top_left", cx - r_up, y_shaft_top)
    result.add_anchor("astragal_top", cx, y_astragal_top)
    result.add_anchor("abacus_bottom_right", cx + abacus_half, y_echinus_top)
    result.add_anchor("abacus_bottom_left", cx - abacus_half, y_echinus_top)
    result.add_anchor("abacus_top_right", cx + abacus_half, y_cap_top)
    result.add_anchor("abacus_top_left", cx - abacus_half, y_cap_top)
    result.add_anchor("top_center", cx, y_cap_top, "attach")
    result.add_anchor("axis", cx, (y_col_bot + y_cap_top) / 2, "axis")
    # Canonical heights per Ware: the astragal is the TOP of the shaft's
    # decoration (NOT part of the capital block). ``y_cap_top`` sits
    # ``astragal_h`` above the canonical capital top because the drawn bead
    # extends above ``y_shaft_top``; that extra bead height belongs to the
    # shaft's decoration, not to capital_h or column_h.
    result.metadata["base_h"] = y_col_bot - y_base_top
    result.metadata["shaft_h"] = y_base_top - y_shaft_top
    result.metadata["capital_h"] = y_astragal_top - y_cap_top
    result.metadata["column_h"] = (result.metadata["base_h"]
                                   + result.metadata["shaft_h"]
                                   + result.metadata["capital_h"])
    # ── Subdivisional metadata (for finer-grained validation) ───────────
    # Base: plinth → torus → fillet (same profile as Tuscan, Ware p.14).
    result.metadata["base_plinth_h"] = y_col_bot - y_plinth_top
    result.metadata["base_torus_h"] = y_torus_bot - y_torus_top
    result.metadata["base_fillet_h"] = y_torus_top - y_base_top
    # Capital: necking + echinus + abacus (each ⅓ of cap_h per Ware p.14).
    # Note: capital_h measures from y_astragal_top upward (astragal belongs
    # to shaft decoration), so subdivisions total capital_h.
    result.metadata["cap_neck_h"] = y_astragal_top - y_neck_top
    result.metadata["cap_echinus_h"] = y_neck_top - y_echinus_top
    result.metadata["cap_abacus_h"] = y_echinus_top - y_cap_top
    result.compute_bbox()
    return result


# ── Smoke test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import drawsvg as dw

    dims = canon.Doric(D=20)
    polys = doric_column_silhouette(dims, cx=50, base_y=200)

    # Canvas: 100 × 220 mm. Origin top-left, y-down (SVG convention).
    W, H = 100.0, 220.0
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

    d.save_svg("/tmp/doric_test.svg")
    print(f"Wrote /tmp/doric_test.svg — {len(polys)} polylines; "
          f"column height {dims.column_h:.1f} mm at D={dims.D} mm.")

    # Validation smoke test
    dims_v = canon.Doric(D=20.0)
    result = doric_column_silhouette(dims_v, 100.0, 200.0, return_result=True)
    assert result.kind == "doric_column"
    assert "bottom_center" in result.anchors
    assert "top_center" in result.anchors
    assert result.bbox != (0.0, 0.0, 0.0, 0.0)
    print(f"doric_column: {len(result.anchors)} anchors, bbox={result.bbox}, "
          f"{sum(len(v) for v in result.polylines.values())} polylines")
