"""Classical order silhouette builders. Proportions come from `canon.py`.

This module is responsible for turning canonical fraction data into polylines
for elevation drawings. One silhouette builder per order. Tuscan is complete;
Doric / Ionic / Corinthian / Composite arrive in Days 3–13.
"""
from __future__ import annotations

import math
from typing import Sequence

from . import canon
from .geometry import Point, Polyline, mirror_path_x
from .schema import ElementResult


# ─── Re-export canonical dataclasses with historical names ────────────────
# Old code referenced `TuscanDims` with just an `M` field. The new `Tuscan`
# class from canon.py is richer (takes D, exposes all fractions). Provide a
# thin wrapper for the old API while we migrate call sites.

TuscanDims = canon.Tuscan  # backwards-friendly alias


def tuscan_dims_for_height(column_h_mm: float) -> canon.Tuscan:
    """Derive a Tuscan order from desired column height (column_h = 7D)."""
    D = column_h_mm / canon.Tuscan().column_D
    return canon.Tuscan(D=D)


# ─── Shared helpers ──────────────────────────────────────────────────────

def _arc(cx: float, cy: float, rx: float, ry: float,
         t0: float, t1: float, n: int) -> Polyline:
    pts: list[Point] = []
    for i in range(n):
        t = t0 + (t1 - t0) * (i / (n - 1))
        pts.append((cx + rx * math.cos(t), cy + ry * math.sin(t)))
    return pts


# ─── Tuscan ──────────────────────────────────────────────────────────────

def tuscan_column_silhouette(dims: canon.Tuscan, cx: float, base_y: float,
                             *, return_result: bool = False):
    """Return polylines for a Tuscan column in elevation.

    base_y = bottom of column (top of pedestal). Column grows up (y decreases).
    cx    = column centerline x.

    If ``return_result=True``, returns an :class:`ElementResult` with named
    anchors and categorized polyline layers. Otherwise (default) returns the
    legacy flat list of polylines for backward compatibility.
    """
    D = dims.D
    M = dims.M
    r_lo = D / 2            # = M
    r_up = dims.upper_diam / 2

    # Base (Ware: ½D incl. cincture). Subdivide per Vignola Tuscan:
    # plinth 0.5 × base_h, torus 0.35 × base_h, fillet 0.15 × base_h
    base_h = dims.base_h
    plinth_h = 0.50 * base_h
    plinth_half = dims.plinth_width_D * D / 2       # 7/6 D / 2 = 7/12 D
    # Torus radius is whichever is smaller: canonical bulge, or what fits in plinth.
    torus_r = min(0.175 * base_h, plinth_half - r_lo - 0.02 * M)
    torus_h = 2 * torus_r
    fillet_base_h = base_h - plinth_h - torus_h

    y_col_bot = base_y
    y_plinth_top = y_col_bot - plinth_h
    y_torus_bot = y_plinth_top
    y_torus_top = y_torus_bot - torus_h
    y_base_top = y_torus_top - fillet_base_h

    # Shaft
    shaft_break_y = y_base_top - dims.shaft_h / 3.0   # entasis begins ⅓ up
    y_shaft_top = y_base_top - dims.shaft_h

    # Capital (Ware: ½D). Subdivide: neck 0.35, astragal 0.08, echinus 0.27, abacus 0.30.
    cap_h = dims.capital_h
    neck_h = 0.35 * cap_h
    astragal_h = 0.08 * cap_h
    echinus_h = 0.27 * cap_h
    abacus_h = cap_h - neck_h - astragal_h - echinus_h

    y_neck_top = y_shaft_top - neck_h
    y_astragal_top = y_neck_top - astragal_h
    y_echinus_top = y_astragal_top - echinus_h
    y_cap_top = y_echinus_top - abacus_h

    astragal_r = astragal_h / 2
    echinus_project = dims.M * 0.35                   # how far outward echinus curves
    abacus_half = dims.abacus_width_D * D / 2         # 7/6 D / 2 = 7/12 D

    # ── Build right silhouette bottom-to-top ─────────────────────────
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

    # Shaft (entasis)
    R.append((cx + r_lo, shaft_break_y))
    R.append((cx + r_up, y_shaft_top))

    # Necking (plain cylinder at r_up)
    R.append((cx + r_up, y_neck_top))
    # Astragal — small bead bulging right
    ast_cy = (y_neck_top + y_astragal_top) / 2
    R += _arc(cx + r_up, ast_cy, astragal_r, astragal_r, math.pi / 2, -math.pi / 2, 13)
    # Echinus — ellipse quarter from (cx+r_up, y_astragal_top) → (cx+r_up+project, y_echinus_top)
    R += _arc(cx + r_up, y_echinus_top, echinus_project, echinus_h,
              math.pi / 2, 0.0, 20)
    # Abacus
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

    result = ElementResult(kind="tuscan_column", dims_ref=dims)
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
    result.add_anchor("abacus_bottom_right", cx + abacus_half, y_echinus_top)
    result.add_anchor("abacus_bottom_left", cx - abacus_half, y_echinus_top)
    result.add_anchor("abacus_top_right", cx + abacus_half, y_cap_top)
    result.add_anchor("abacus_top_left", cx - abacus_half, y_cap_top)
    result.add_anchor("top_center", cx, y_cap_top, "attach")  # entablature sits here
    result.add_anchor("axis", cx, (y_col_bot + y_cap_top) / 2, "axis")
    result.metadata["column_h"] = y_col_bot - y_cap_top
    result.metadata["base_h"] = y_col_bot - y_base_top
    result.metadata["capital_h"] = y_shaft_top - y_cap_top
    result.metadata["shaft_h"] = y_base_top - y_shaft_top
    # ── Subdivisional metadata (for finer-grained validation) ───────────
    # Base: plinth → torus → fillet (Vignola Tuscan, Ware p.10).
    result.metadata["base_plinth_h"] = y_col_bot - y_plinth_top
    result.metadata["base_torus_h"] = y_torus_bot - y_torus_top
    result.metadata["base_fillet_h"] = y_torus_top - y_base_top
    # Capital: necking → astragal → echinus → abacus (Ware p.10).
    result.metadata["cap_neck_h"] = y_shaft_top - y_neck_top
    result.metadata["cap_astragal_h"] = y_neck_top - y_astragal_top
    result.metadata["cap_echinus_h"] = y_astragal_top - y_echinus_top
    result.metadata["cap_abacus_h"] = y_echinus_top - y_cap_top
    result.compute_bbox()
    return result
