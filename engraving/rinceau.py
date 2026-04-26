"""Rinceau scrolls — running acanthus along a path.

A rinceau is the signature running ornament of the Italian Renaissance:
a sinuous spine (often a sinusoid, log-spiral, or s-curve) along which
stylised acanthus leaves sprout at regular intervals, alternating sides.
Small buds or rosettes punctuate the spine between lobes.  See Raphael's
Vatican Loggia pilasters, Perugino's grotesques, or the pilaster panels
of the Certosa di Pavia for the canonical examples.

Construction:
    1. A spine path (polyline) — typically a sinusoid or log-spiral —
       supplied by the caller.
    2. Resample the spine at uniform arc-length spacing so that the
       leaves are evenly distributed regardless of the spine's shape.
    3. At each station compute the local tangent direction.
    4. Place an acanthus leaf whose base sits on the spine, rotated so
       the leaf's midrib is perpendicular to the tangent, and pushed
       slightly toward the attaching side (alternating ±).  Each leaf
       curls back toward the direction of travel.
    5. Drop small bud polygons at every other station on the spine
       between leaves as classical punctuation.

The output conforms to the common :class:`ElementResult` contract so
that rinceaux can be validated and composed like any other element.
"""
from __future__ import annotations

import math
from typing import List

from .acanthus import acanthus_leaf
from .geometry import (Point, Polyline, arc, path_length, resample_path,
                       translate_path)
from .schema import ElementResult


# --------------------------------------------------------------------------
# Spine generators
# --------------------------------------------------------------------------

def sinusoidal_spine(x0: float, x1: float, y0: float,
                     amplitude: float, period: float,
                     steps: int = 200) -> list[Point]:
    """Sinusoidal spine from x0 to x1 at mean y0.

    ``amplitude`` is the peak-to-baseline offset; ``period`` is the full
    wavelength along x.  ``steps`` controls polyline density — higher
    for rinceaux with many leaves per wavelength.
    """
    pts: list[Point] = []
    for i in range(steps):
        t = i / (steps - 1) if steps > 1 else 0.0
        x = x0 + (x1 - x0) * t
        y = y0 + amplitude * math.sin(2 * math.pi * (x - x0) / period)
        pts.append((x, y))
    return pts


# --------------------------------------------------------------------------
# Small 2D helpers local to this module
# --------------------------------------------------------------------------

def _rotate_pts(pts: list[Point], theta: float,
                cx: float = 0.0, cy: float = 0.0) -> list[Point]:
    c, s = math.cos(theta), math.sin(theta)
    out: list[Point] = []
    for x, y in pts:
        dx, dy = x - cx, y - cy
        out.append((cx + c * dx - s * dy, cy + s * dx + c * dy))
    return out


def _tangent_at(spine: list[Point], idx: int) -> tuple[float, float]:
    """Unit tangent at spine[idx] using central differences with endpoint fallback."""
    n = len(spine)
    if n < 2:
        return (1.0, 0.0)
    if idx <= 0:
        a, b = spine[0], spine[1]
    elif idx >= n - 1:
        a, b = spine[-2], spine[-1]
    else:
        a, b = spine[idx - 1], spine[idx + 1]
    dx, dy = b[0] - a[0], b[1] - a[1]
    L = math.hypot(dx, dy) or 1.0
    return (dx / L, dy / L)


def _bud(cx: float, cy: float, r: float) -> Polyline:
    """A tiny closed circle as a spine bud / rosette placeholder."""
    pts = arc(cx, cy, r, 0.0, 2.0 * math.pi, steps=18)
    # Close it.
    if pts:
        pts.append(pts[0])
    return pts


# --------------------------------------------------------------------------
# Main builder
# --------------------------------------------------------------------------

def rinceau(spine: list[Point], leaf_size: float,
            spacing_frac: float = 1.5,
            alternate: bool = True) -> ElementResult:
    """Generate a running acanthus rinceau along a spine.

    Parameters
    ----------
    spine
        Central curve as a polyline.  Any smooth path works: sinusoids,
        log-spirals, s-curves.  For best results supply at least ~100
        points per expected leaf station so the tangent estimates are
        smooth.
    leaf_size
        Target leaf bounding size (both width and height) in mm.  The
        leaf's tip-to-base distance is this value; its width is taken
        to be 0.8 × leaf_size so that a rinceau reads slimmer than a
        capital's acanthus.
    spacing_frac
        Arc-length gap between leaf stations expressed as a fraction of
        ``leaf_size``.  The classical "half-a-leaf" look comes from
        values around 1.3–1.7; smaller values pack leaves tightly.
    alternate
        If True (default), leaves alternate sides of the spine — the
        signature Renaissance rhythm.  If False, every leaf sprouts on
        the same side, which reads as a linear frieze of leaves rather
        than a true rinceau.

    Returns
    -------
    ElementResult with:
        kind = "rinceau"
        polylines layers: ``spine``, ``leaves``, ``buds``
        anchors: ``start``, ``end``, ``leaf_0_base`` … ``leaf_{N-1}_base``
        metadata: ``leaf_count``, ``spacing`` (arc-length), ``alternate``
    """
    result = ElementResult(
        kind="rinceau",
        polylines={"spine": [list(spine)], "leaves": [], "buds": []},
        metadata={"leaf_count": 0,
                  "spacing": leaf_size * spacing_frac,
                  "alternate": alternate},
    )

    if len(spine) < 2:
        result.compute_bbox()
        return result

    # ------------------------------------------------------------------
    # Arc-length resample: uniform stations along the spine.
    # ------------------------------------------------------------------
    station_spacing = leaf_size * spacing_frac
    total_len = path_length(spine)
    if station_spacing <= 0 or total_len <= 0:
        result.compute_bbox()
        return result

    stations = resample_path(spine, station_spacing)
    # Drop endpoints — leaves that sit exactly on the endpoints overhang.
    # We keep at most the interior stations.  For a length of L and step s
    # we get about L/s + 1 samples; strip the two endpoints if we have at
    # least three stations so leaves have a full wavelength of spine to
    # lean into on either side.
    if len(stations) >= 3:
        interior_stations = stations[1:-1]
    else:
        interior_stations = stations

    if not interior_stations:
        result.compute_bbox()
        return result

    # Build a dense spine so we can read tangent direction accurately at
    # each station without being thrown off by coarse sampling of the
    # caller's input.
    dense_spine = resample_path(spine, max(total_len / 400.0, 0.25))

    def nearest_idx(pt: Point) -> int:
        """Index into dense_spine closest to pt."""
        best_i = 0
        best_d = float("inf")
        for i, q in enumerate(dense_spine):
            d = (q[0] - pt[0]) ** 2 + (q[1] - pt[1]) ** 2
            if d < best_d:
                best_d = d
                best_i = i
        return best_i

    # ------------------------------------------------------------------
    # Generate a prototype leaf once; we'll rotate/translate it per
    # station.  The acanthus leaf is built tip-up in its local frame
    # (tip at y = -h/2, base at y = +h/2).
    # ------------------------------------------------------------------
    # Rinceau leaves read better slimmer than a capital's acanthus, so
    # width is slightly less than height.
    leaf_w = leaf_size * 0.8
    leaf_h = leaf_size
    proto = acanthus_leaf(width=leaf_w, height=leaf_h,
                          lobe_count=3, fingers_per_lobe=3,
                          turnover=0.35, variant="rinceau")

    # ------------------------------------------------------------------
    # Stamp one leaf per station.
    # ------------------------------------------------------------------
    leaves_layer: list[Polyline] = []
    buds_layer: list[Polyline] = []
    leaf_count = 0

    for i, (sx, sy) in enumerate(interior_stations):
        # Tangent direction (travel direction) at the station.
        t_idx = nearest_idx((sx, sy))
        tx, ty = _tangent_at(dense_spine, t_idx)

        # Perpendicular to the spine; picking the sign places the leaf
        # on one side of the spine or the other.  In SVG coords the
        # perpendicular (+tx, +ty) -> (-ty, +tx) points "left of travel"
        # (i.e., above a rightward-travelling spine since y grows down).
        side = +1 if (not alternate or i % 2 == 0) else -1
        nx, ny = -ty * side, tx * side

        # The leaf's base sits on the spine; its tip extends outward
        # along (nx, ny).  In the leaf's local frame tip-up means the
        # tip is at angle -pi/2 (local +y is downward, so "up" = -y).
        # We therefore want the leaf's local +y axis (base direction)
        # to point toward the spine (i.e., opposite to (nx, ny)), and
        # its local -y axis (tip direction) to point along (nx, ny).
        # The rotation angle theta is the angle from (0, 1) — the leaf's
        # local base direction — to (-nx, -ny).
        theta = math.atan2(-nx, -ny) - math.atan2(0.0, 1.0)
        # Also tilt the leaf so its tip curls BACK against direction of
        # travel: add a small angular bias toward -tangent.
        curl_bias = math.radians(18.0)
        # Alternate leaves curl in opposite absolute directions so the
        # "curl back" reads on each side.  When side=-1 we negate the
        # bias so the tip again trails the travel direction.
        theta += curl_bias * side

        # Push the leaf base slightly off-spine along (nx, ny) so the
        # silhouette does not double up on the spine line.  This offset
        # is small — a fraction of leaf_size — enough to read as an
        # attachment stem.
        base_offset = leaf_size * 0.08
        ox = sx + nx * base_offset
        oy = sy + ny * base_offset

        # Transform each polyline: rotate about origin, translate to
        # (ox, oy).  The leaf's local base is at y = +leaf_h/2, so after
        # rotation the base point sits on the spine (at (ox, oy) + rot(0, h/2)).
        # To have the attachment point actually ON (sx, sy) we translate
        # so that the rotated (0, +h/2) lands on (sx, sy): translate by
        # (sx, sy) - rot(0, h/2).
        base_local = (0.0, leaf_h / 2.0)
        rb = _rotate_pts([base_local], theta)[0]
        t_dx = sx - rb[0]
        t_dy = sy - rb[1]

        for pl in proto:
            if not pl:
                continue
            rot = _rotate_pts(list(pl), theta)
            placed = [(x + t_dx, y + t_dy) for x, y in rot]
            leaves_layer.append(placed)

        result.add_anchor(f"leaf_{leaf_count}_base", sx, sy, role="attach")
        leaf_count += 1

        # Between-leaf bud: a small rosette on the opposite side of the
        # spine (only when alternating; otherwise skip so the ornament
        # doesn't clutter on the unoccupied side).
        if alternate:
            bud_nx, bud_ny = -ty * -side, tx * -side
            bud_r = leaf_size * 0.08
            bud_cx = sx + bud_nx * (leaf_size * 0.22)
            bud_cy = sy + bud_ny * (leaf_size * 0.22)
            buds_layer.append(_bud(bud_cx, bud_cy, bud_r))

    result.polylines["leaves"] = leaves_layer
    result.polylines["buds"] = buds_layer
    result.metadata["leaf_count"] = leaf_count

    # Start / end anchors (spine endpoints).
    result.add_anchor("start", spine[0][0], spine[0][1], role="corner")
    result.add_anchor("end", spine[-1][0], spine[-1][1], role="corner")

    result.compute_bbox()
    return result


# --------------------------------------------------------------------------
# Smoke test
# --------------------------------------------------------------------------

def _smoke_test() -> None:
    import drawsvg as dw

    from .preview import render_svg_to_png

    spine = sinusoidal_spine(x0=20, x1=260, y0=100,
                             amplitude=15, period=60)
    r = rinceau(spine, leaf_size=12, spacing_frac=1.5, alternate=True)

    d = dw.Drawing(280, 200, origin=(0, 0))
    d.append(dw.Rectangle(0, 0, 280, 200, fill="white"))
    for layer in r.polylines.values():
        for pl in layer:
            if not pl:
                continue
            d.append(dw.Lines(*[c for pt in pl for c in pt],
                              close=False, fill='none',
                              stroke='black', stroke_width=0.2))
    d.save_svg('/tmp/rinceau_test.svg')
    render_svg_to_png('/tmp/rinceau_test.svg',
                      '/tmp/rinceau_test.png', dpi=200)
    print("Wrote /tmp/rinceau_test.svg and /tmp/rinceau_test.png")
    print(f"leaf_count={r.metadata['leaf_count']}, bbox={r.bbox}")


if __name__ == "__main__":
    _smoke_test()
