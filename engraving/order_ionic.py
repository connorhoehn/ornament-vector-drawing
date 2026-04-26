"""Ionic column silhouette + capital in elevation, after Ware's *American
Vignola* (1903), pp. 15-18.

The Ionic column is 9D tall at lower diameter D. Its canonical subdivisions:
  - Base    : ½D   (Attic base: plinth, lower torus, scotia, upper torus, fillet)
  - Shaft   : 9D − ½D − ⅔D = 7⅚D   (linear entasis from bottom third up)
  - Capital : ⅔D   (two volutes flanking an echinus, thin abacus on top)

This module mirrors the structure of `order_doric.doric_column_silhouette` and
returns the same 7-rule polyline tuple, with the volutes appended afterwards so
the caller can stroke them alongside the rest of the silhouette.

Fluting and entablature belong to separate modules.
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


def ionic_column_silhouette(dims: canon.Ionic, cx: float, base_y: float,
                            *, return_result: bool = False):
    """Return polylines for an Ionic column in elevation.

    base_y = bottom of column (top of pedestal). Column grows up (y decreases).
    cx    = column centerline x.

    Return order:
      [right_silhouette, left_silhouette, cap_top_rule, col_bot_rule,
       plinth_top_rule, shaft_top_rule, abacus_bot_rule,
       ...volute polylines (outer L, channel L, eye L, outer R, channel R, eye R, echinus)]

    If ``return_result=True``, returns an :class:`ElementResult` with named
    anchors and categorized polyline layers. Otherwise (default) returns the
    legacy flat list of polylines for backward compatibility.
    """
    D = dims.D
    M = dims.M
    r_lo = D / 2            # = M
    r_up = dims.upper_diam / 2

    # ── Base (Attic base, ½D) ──────────────────────────────────────────
    # Classic Attic profile bottom-to-top:
    #   plinth → lower torus → scotia → upper torus → fillet
    base_h = dims.base_h
    plinth_h = 0.30 * base_h
    lower_torus_h = 0.18 * base_h
    scotia_h = 0.18 * base_h
    upper_torus_h = 0.22 * base_h
    fillet_base_h = base_h - plinth_h - lower_torus_h - scotia_h - upper_torus_h

    plinth_half = (7.0 / 6.0) * D / 2                 # 7/12 D
    torus_r_lower = 0.5 * lower_torus_h
    torus_r_upper = 0.5 * upper_torus_h
    # Torus "bulge" past the shaft face — how far the torus outer edge sits
    # beyond r_lo. We pick the bulge so the torus half-width lands between the
    # shaft face and the plinth face: conventionally r_lo + ~0.02D.
    lower_torus_bulge = min(torus_r_lower, plinth_half - r_lo - 0.005 * D)
    upper_torus_bulge = min(torus_r_upper, plinth_half - r_lo - 0.015 * D)
    # Scotia projection (how deep it bites into the column silhouette). It
    # recedes between the two tori — its outer edge sits at the shaft face.
    scotia_outer_x = cx + r_lo                         # edge it returns to
    scotia_depth = 0.035 * D                           # inward bite from r_lo

    y_col_bot = base_y
    y_plinth_top = y_col_bot - plinth_h
    y_lower_torus_top = y_plinth_top - lower_torus_h
    y_scotia_top = y_lower_torus_top - scotia_h
    y_upper_torus_top = y_scotia_top - upper_torus_h
    y_base_top = y_upper_torus_top - fillet_base_h

    # ── Shaft ──────────────────────────────────────────────────────────
    # Linear entasis: bottom ⅓ cylindrical at r_lo, then linear taper to r_up.
    shaft_break_y = y_base_top - dims.shaft_h / 3.0
    y_shaft_top = y_base_top - dims.shaft_h

    # Small astragal (bead) terminating the shaft, just below the capital.
    astragal_r = D / 44.0
    astragal_h = 2 * astragal_r
    y_astragal_top = y_shaft_top - astragal_h

    # ── Capital (⅔D) ───────────────────────────────────────────────────
    cap_h = dims.capital_h
    abacus_h = cap_h / 6.0                             # thin abacus, ⅙ of cap
    # Abacus width: 7/6 D per Ware (matches Tuscan/Doric abacus width).
    abacus_half = (7.0 / 6.0) * D / 2

    y_cap_top = y_astragal_top - cap_h
    y_abacus_bot = y_cap_top + abacus_h                # abacus occupies top ⅙

    # Echinus projects out slightly past the upper shaft face. ≈ 1/9 D.
    echinus_project = D / 9.0
    echinus_outer_x_right = cx + r_up + echinus_project
    # Echinus rises from below the abacus down to the shaft astragal — use an
    # ellipse quarter from the shaft face up to just under the abacus.
    echinus_top_y = y_abacus_bot
    echinus_bot_y = y_astragal_top

    # Volute eye position: horizontally at the edge of (shaft + echinus
    # projection); vertically 1/3 D below the abacus bottom.
    eye_x_right = cx + r_up + echinus_project
    eye_x_left = cx - r_up - echinus_project
    eye_y = y_abacus_bot + D / 3.0

    # ── Build right silhouette bottom-to-top ───────────────────────────
    R: list[Point] = []
    # Plinth
    R.append((cx + plinth_half, y_col_bot))
    R.append((cx + plinth_half, y_plinth_top))
    # Step inward to the base of the lower torus
    R.append((cx + r_lo, y_plinth_top))
    # Lower torus — right-bulging semi-circle
    l_tor_cy = y_plinth_top - torus_r_lower
    R += _arc(cx + r_lo, l_tor_cy,
              lower_torus_bulge, torus_r_lower,
              math.pi / 2, -math.pi / 2, 22)
    # Scotia — concave bite: ellipse from (cx+r_lo, y_lower_torus_top)
    # inward to (cx+r_lo-scotia_depth, midpoint) and back out to
    # (cx+r_lo, y_scotia_top). We sweep a half-ellipse inward.
    sc_cy = (y_lower_torus_top + y_scotia_top) / 2
    sc_half_h = (y_lower_torus_top - y_scotia_top) / 2
    R += _arc(cx + r_lo, sc_cy,
              scotia_depth, sc_half_h,
              -math.pi / 2, -3 * math.pi / 2, 22)
    # After the scotia arc we land at (cx+r_lo, y_scotia_top).
    # Upper torus — right-bulging semi-circle
    u_tor_cy = y_scotia_top - torus_r_upper
    R += _arc(cx + r_lo, u_tor_cy,
              upper_torus_bulge, torus_r_upper,
              math.pi / 2, -math.pi / 2, 22)
    # Fillet above the upper torus up to the base top.
    R.append((cx + r_lo, y_base_top))

    # Shaft: cylindrical third, then tapered to r_up
    R.append((cx + r_lo, shaft_break_y))
    R.append((cx + r_up, y_shaft_top))

    # Astragal — small bead at the top of the shaft
    ast_cy = (y_shaft_top + y_astragal_top) / 2
    R += _arc(cx + r_up, ast_cy, astragal_r, astragal_r,
              math.pi / 2, -math.pi / 2, 13)

    # Echinus — shallow convex ovolo from the shaft face up and outward to
    # just below the abacus at the volute-eye horizontal.
    echinus_ry = (echinus_bot_y - echinus_top_y)       # positive height
    R += _arc(cx + r_up, echinus_top_y,
              echinus_project, echinus_ry,
              math.pi / 2, 0.0, 20)

    # Abacus — thin rectangular block at the top of the capital.
    R.append((cx + abacus_half, y_abacus_bot))
    R.append((cx + abacus_half, y_cap_top))

    L = mirror_path_x(R, cx)

    cap_top = [(cx - abacus_half, y_cap_top), (cx + abacus_half, y_cap_top)]
    col_bot = [(cx - plinth_half, y_col_bot), (cx + plinth_half, y_col_bot)]
    plinth_top = [(cx - plinth_half, y_plinth_top), (cx + plinth_half, y_plinth_top)]
    shaft_top_rule = [(cx - r_up, y_shaft_top), (cx + r_up, y_shaft_top)]
    abacus_bot = [(cx - abacus_half, y_abacus_bot), (cx + abacus_half, y_abacus_bot)]

    legacy: list[Polyline] = [R, L, cap_top, col_bot, plinth_top,
                              shaft_top_rule, abacus_bot]

    # ── Volutes ────────────────────────────────────────────────────────
    # Right volute (winds clockwise into the eye from above)
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

    # Echinus center curve — a shallow bump visible between the two volutes.
    # Draw a gentle arc spanning from eye to eye at the echinus's top
    # horizontal, dipping down slightly at the middle. A segment of an ellipse
    # works well: from (eye_x_left, eye_y) up-over to (eye_x_right, eye_y)
    # with its apex at (cx, echinus_top_y + small rise).
    echinus_span_half = eye_x_right - cx
    # Apex rises above eye_y by (eye_y - echinus_top_y) — i.e. the echinus
    # arc bridges the tops of the two eyes, cresting at its upper face.
    echinus_center_ry = eye_y - echinus_top_y
    echinus_center = _arc(cx, eye_y,
                          echinus_span_half, echinus_center_ry,
                          math.pi, 2 * math.pi, 40)

    legacy.extend(volute_polys)
    legacy.append(echinus_center)

    if not return_result:
        return legacy

    result = ElementResult(kind="ionic_column", dims_ref=dims)
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
    result.metadata["num_volutes"] = 2
    # ── Subdivisional metadata (for finer-grained validation) ───────────
    # Attic base: plinth → lower torus → scotia → upper torus → fillet
    # (Ware p.18).
    result.metadata["base_plinth_h"] = y_col_bot - y_plinth_top
    result.metadata["base_lower_torus_h"] = y_plinth_top - y_lower_torus_top
    result.metadata["base_scotia_h"] = y_lower_torus_top - y_scotia_top
    result.metadata["base_upper_torus_h"] = y_scotia_top - y_upper_torus_top
    result.metadata["base_torus_h"] = (  # lower + upper combined
        result.metadata["base_lower_torus_h"]
        + result.metadata["base_upper_torus_h"])
    result.metadata["base_fillet_h"] = y_upper_torus_top - y_base_top
    # Capital: volutes zone (the echinus spans from astragal_top up to
    # abacus bottom; volutes occupy the same vertical span) + abacus.
    result.metadata["cap_volute_h"] = y_astragal_top - y_abacus_bot
    result.metadata["cap_echinus_h"] = y_astragal_top - y_abacus_bot
    result.metadata["cap_abacus_h"] = y_abacus_bot - y_cap_top
    result.compute_bbox()
    return result


# ── Smoke test ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    import drawsvg as dw

    dims = canon.Ionic(D=24)
    polys = ionic_column_silhouette(dims, cx=100, base_y=220)

    # Canvas: 200 × 250 mm.
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

    d.save_svg("/tmp/ionic_test.svg")
    print(f"Wrote /tmp/ionic_test.svg — {len(polys)} polylines; "
          f"column height {dims.column_h:.1f} mm at D={dims.D} mm.")

    # Validation smoke test
    dims_v = canon.Ionic(D=20.0)
    result = ionic_column_silhouette(dims_v, 100.0, 200.0, return_result=True)
    assert result.kind == "ionic_column"
    assert "bottom_center" in result.anchors
    assert "top_center" in result.anchors
    assert result.bbox != (0.0, 0.0, 0.0, 0.0)
    print(f"ionic_column: {len(result.anchors)} anchors, bbox={result.bbox}, "
          f"{sum(len(v) for v in result.polylines.values())} polylines")

    # Render to PNG via Playwright for visual inspection.
    try:
        from engraving.preview import render_svg_to_png
        out_png = render_svg_to_png('/tmp/ionic_test.svg',
                                    '/tmp/ionic_test.png', dpi=150)
        print(f"Wrote {out_png}")
    except Exception as exc:
        print(f"PNG preview skipped: {exc!r}")
