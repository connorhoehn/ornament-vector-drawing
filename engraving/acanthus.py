"""Acanthus leaf drawn by geometric construction, after I. Page,
*Guide for Drawing the Acanthus* (1886), Plates 1-4.

Page's method builds the leaf step by step from a small geometric armature:

    Plate 1 -- the "diagram".  An ogival bounding rectangle; a central axis
    A (top, tip) to B (bottom, base).  The axis is divided by horizontal
    bands into N equal steps.  From the base point B, lines radiate out to
    every intersection of (horizontal band x vertical axis offset D).  These
    radiating lines are the "stamina" -- they tell us where the CENTRES of
    the lobe arcs live.

    Plate 2 -- the "exterior".  On each horizontal band, on each side of
    the axis, draw a D-shaped arc (a loop leaving the axis, swinging
    outward, and returning to the axis one band down).  Each D is the
    envelope of one lobe.  Successive lobes step down the axis.  The
    terminal lobe sits on the axis itself near the tip.

    Plate 3 -- the "raffles".  Each D-envelope is subdivided into a few
    curved "fingers" (typically 3 for minor lobes, 5 for mid/base lobes).
    A small teardrop "eye" sits at the base of every lobe where it leaves
    the axis.  Fingers are cups: each is a shallow outward arc whose tip
    touches the envelope.  Between finger tips the edge scallops INWARD
    (concave, not a chevron).

    Plate 4 -- the "dentata".  Tooth detail on the finger edges; left for
    renderers -- at the scale we draw at, the finger cups themselves read
    as the serration.

This module builds the polylines for Plates 2-3 as a single closed
silhouette plus the midrib crease.  All primary curves are circular arcs;
Beziers appear only as minor connecting segments where the arc geometry
does not close (e.g., the axis-stem at the base).
"""
from __future__ import annotations

import math
from typing import Callable, Sequence

from .geometry import (Point, Polyline, arc, cubic_bezier, line,
                       mirror_path_x, translate_path)


# ---------------------------------------------------------------------------
# Motif registry (replaceable-unit hook)
# ---------------------------------------------------------------------------
# This module originally owned a tiny private registry.  The plugin system in
# ``engraving.plugins`` is the authoritative one now; the helpers below are
# thin back-compat shims so older callers that do
# ``from engraving.acanthus import register_motif`` keep working.

from . import plugins as _plugins  # noqa: E402


def register_motif(name: str,
                   fn: Callable[..., list[Polyline]]) -> None:
    """Register a motif generator under ``name``.

    Back-compat wrapper around :func:`engraving.plugins.register_motif`
    that preserves the "just a callable" API older modules were written
    against.
    """
    _plugins.register_motif(name, fn=fn)


def get_motif(name: str) -> Callable[..., list[Polyline]]:
    """Return the callable registered under ``name``.

    Raises ``KeyError`` if the slot is empty or only holds an SVG plugin
    (not a callable).  Callers that want to transparently pick up SVG
    overrides should use :func:`engraving.plugins.get_motif_or_default`
    instead.
    """
    entry = _plugins.get_motif(name)
    if not entry or entry.get("fn") is None:
        raise KeyError(name)
    return entry["fn"]


# ---------------------------------------------------------------------------
# Small arc helpers.  Everything downstream is circles-through-two-points.
# ---------------------------------------------------------------------------


def _arc_through_three(p0: Point, p1: Point, p2: Point,
                       steps: int = 24) -> Polyline:
    """Polyline of the circular arc through p0, p1, p2 (in that order).

    Page's construction repeatedly names two "known" points on an arc (the
    springing and landing points) and one point on its curve -- this is the
    natural way to tell the student "this arc passes here".  The computed
    centre is the circumcentre of the three points; if they are collinear
    we fall back to a straight segment.
    """
    ax, ay = p0
    bx, by = p1
    cx, cy = p2
    d = 2.0 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        # Collinear: Page would never allow this, but be defensive.
        return line(p0, p2, steps=max(2, steps))
    ux = ((ax * ax + ay * ay) * (by - cy)
          + (bx * bx + by * by) * (cy - ay)
          + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx)
          + (bx * bx + by * by) * (ax - cx)
          + (cx * cx + cy * cy) * (bx - ax)) / d
    r = math.hypot(ax - ux, ay - uy)
    a0 = math.atan2(ay - uy, ax - ux)
    a1 = math.atan2(by - uy, bx - ux)
    a2 = math.atan2(cy - uy, cx - ux)
    # Choose the sweep direction that visits a1 between a0 and a2.
    def norm(a: float, base: float) -> float:
        # Unwrap `a` to lie in (base - pi, base + pi].
        while a - base > math.pi:
            a -= 2 * math.pi
        while a - base <= -math.pi:
            a += 2 * math.pi
        return a
    a1n = norm(a1, a0)
    a2n = norm(a2, a0)
    # If a1 is not strictly between a0 and a2, flip the sweep by choosing
    # the long way around.  Equivalent to forcing monotone parameterization.
    if not (min(a0, a2n) <= a1n <= max(a0, a2n)):
        if a2n > a0:
            a2n -= 2 * math.pi
        else:
            a2n += 2 * math.pi
    ts = [a0 + (a2n - a0) * i / (steps - 1) for i in range(steps)]
    return [(ux + r * math.cos(t), uy + r * math.sin(t)) for t in ts]


def _arc_through_two_with_radius(p0: Point, p1: Point, r: float,
                                 bulge_sign: int = 1,
                                 steps: int = 16) -> Polyline:
    """Arc from p0 to p1 of signed radius r.  bulge_sign picks which side.

    Used to draw a lobe envelope when we know the two endpoints on the
    axis (springing and landing) and the intended radius -- this is the
    compass-opening-and-swing move from Plate 2.
    """
    mx = 0.5 * (p0[0] + p1[0])
    my = 0.5 * (p0[1] + p1[1])
    dx = p1[0] - p0[0]
    dy = p1[1] - p0[1]
    d = math.hypot(dx, dy)
    if d < 1e-9:
        return [p0]
    # Perpendicular unit vector (rotated +90 in screen coords).
    px, py = -dy / d, dx / d
    # Half-chord; ensure radius is at least half the chord.
    h = d * 0.5
    if r < h:
        r = h * 1.001
    # Distance from midpoint to centre along the perpendicular.
    off = math.sqrt(max(0.0, r * r - h * h))
    cx = mx + px * off * bulge_sign
    cy = my + py * off * bulge_sign
    a0 = math.atan2(p0[1] - cy, p0[0] - cx)
    a1 = math.atan2(p1[1] - cy, p1[0] - cx)
    # Sweep short way around (an envelope less than a semicircle in Page).
    while a1 - a0 > math.pi:
        a1 -= 2 * math.pi
    while a1 - a0 < -math.pi:
        a1 += 2 * math.pi
    ts = [a0 + (a1 - a0) * i / (steps - 1) for i in range(steps)]
    return [(cx + r * math.cos(t), cy + r * math.sin(t)) for t in ts]


# ---------------------------------------------------------------------------
# Construction of one right-side lobe
# ---------------------------------------------------------------------------


def _build_right_lobe(root: Point,
                      tip: Point,
                      land: Point,
                      fingers: int,
                      turnover: float,
                      include_return: bool = True) -> Polyline:
    """Right-side lobe outline, traced root -> (fingers along envelope) ->
    tip (with optional turnover) -> [land].

    Construction:
      - `root`  :   springing point (axis or on the previous lobe's tip)
      - `tip`   :   outermost point of the lobe envelope
      - `land`  :   where the lobe's underside meets the next root
      - upper envelope arc: circular arc root->tip, bulging up-and-out
      - fingers: `fingers` small cup-arcs tiling the upper envelope.  Each
        finger's tip sits on the envelope; between fingers the outline
        scallops inward along concave arcs (NOT chevrons).
      - turnover: at `tip`, a small counter-arc curling back, radius
        proportional to `turnover * envelope_chord`.
      - lower envelope arc: shorter, tip->land, bulging gently outward
        (only drawn when `include_return` is True; when chaining shingled
        lobes we skip the underside because it's hidden by the lobe above).

    Geometric meaning of the key dimensions:
      * the chord root-tip is the "radiating stamen" line from Plate 1
      * the envelope radius is set so the arc sags outward by roughly
        1/3 of the chord length -- this is Page's "raffle" fullness.
    """
    # --- Upper envelope -----------------------------------------------------
    # We parameterize the envelope by its "sagitta" -- the outward bulge at
    # the midpoint of the chord -- because that corresponds to what the
    # student sees on the page (how full the lobe is).
    rx, ry = root
    tx, ty = tip
    chord = math.hypot(tx - rx, ty - ry)
    # Sagitta is ~0.28 * chord; fuller lobes read more organic.
    sag = chord * 0.28
    # From chord `c` and sagitta `s`, the radius is (c^2/4 + s^2) / (2s).
    r_env_up = (chord * chord / 4.0 + sag * sag) / (2.0 * sag)
    # Upper envelope bulges UP-AND-OUT from the chord.  In SVG coords where
    # y grows down, "up" means negative dy; bulge_sign=+1 on right side.
    up_env = _arc_through_two_with_radius(root, tip, r_env_up,
                                          bulge_sign=+1, steps=8 * fingers + 2)

    # --- Fingers ------------------------------------------------------------
    # Each finger occupies a slice of the envelope.  The finger TIP sits on
    # the envelope at parameter (i + 0.5) / fingers; the two valleys between
    # successive fingers are the envelope arc points at parameters
    # i / fingers (i = 1..fingers-1).  The OUTER outline of the finger is a
    # small arc that bulges slightly past the envelope (the "cup lip"); the
    # BETWEEN-finger notch is a concave arc with small depth.
    outline: Polyline = [root]
    def env_at(s: float) -> Point:
        """Point on the upper envelope at fractional arc parameter s in [0,1]."""
        idx = max(0, min(len(up_env) - 1, int(round(s * (len(up_env) - 1)))))
        return up_env[idx]

    # Extra cup lip = how far the finger tip pokes past the envelope.
    # Scales with chord so the finger reads at any leaf size.
    cup_lip = chord * 0.04
    # Notch depth = how far inward the valley between fingers pulls back.
    notch_depth = chord * 0.06

    for i in range(fingers):
        # Finger i: valley_left -> tip -> (valley_right will be consumed
        # by the next finger's valley_left).
        s_left = i / fingers
        s_right = (i + 1) / fingers
        s_mid = (i + 0.5) / fingers
        vl = env_at(s_left)
        vr = env_at(s_right)
        mid = env_at(s_mid)
        # Outward unit normal at mid: away from the chord's midpoint.  We
        # compute it by subtracting the chord midpoint from mid.
        cmx = 0.5 * (rx + tx)
        cmy = 0.5 * (ry + ty)
        nx = mid[0] - cmx
        ny = mid[1] - cmy
        nl = math.hypot(nx, ny) or 1.0
        nx /= nl
        ny /= nl
        # Finger tip sits slightly OUTSIDE the envelope along this normal.
        ftip = (mid[0] + nx * cup_lip, mid[1] + ny * cup_lip)
        # Valley between this finger and the previous one: pulled INWARD
        # along the same normal by notch_depth.  We only draw the notch
        # before the 2nd..Nth finger; the very first notch is the root.
        if i == 0:
            # First finger rises directly from the root.  Draw arc from
            # root to ftip through a point between them on the envelope.
            via = env_at(s_left + (s_mid - s_left) * 0.5)
            outline += _arc_through_three(root, via, ftip, steps=8)[1:]
        else:
            # Valley: concave dip just inside the envelope.
            dip = (vl[0] - nx * notch_depth, vl[1] - ny * notch_depth)
            # Outline: from the previous finger tip, dip into the valley,
            # then rise to this finger tip.  Two short arcs.
            prev_ftip = outline[-1]
            outline += _arc_through_three(prev_ftip, dip, ftip, steps=6)[1:]

    # --- Turnover at tip ----------------------------------------------------
    # A small curl of the leaf's tip back on itself -- classical "cane curl".
    # Radius = turnover * chord * 0.3.  Curl starts at the last finger tip
    # (which is very close to `tip`) and swings outward-then-back to a
    # point just below `tip` on the envelope.
    if turnover > 0 and fingers > 0:
        last_ftip = outline[-1]
        # Direction from tip back toward root along the chord.
        chord_ux = (rx - tx) / (chord or 1.0)
        chord_uy = (ry - ty) / (chord or 1.0)
        # Perpendicular pointing OUT of the chord (same sense as envelope bulge).
        perp_x = -chord_uy
        perp_y = chord_ux
        curl_r = turnover * chord * 0.18
        # Curl tip: just past `tip`, pushed outward.
        curl_out = (tip[0] + perp_x * curl_r,
                    tip[1] + perp_y * curl_r)
        # Curl-back landing: back on the envelope a little inboard of tip.
        curl_back = (tip[0] + chord_ux * curl_r * 1.6,
                     tip[1] + chord_uy * curl_r * 1.6)
        outline += _arc_through_three(last_ftip, curl_out, curl_back,
                                      steps=10)[1:]

    # --- Lower envelope (return) --------------------------------------------
    # Only rendered when the caller wants an isolated lobe outline.  When
    # we shingle lobes (normal case), the underside of each lobe is
    # hidden behind the lobe above, so we omit this segment and the walk
    # continues from `tip` directly into the next lobe's root.
    if include_return:
        chord_down = math.hypot(land[0] - tip[0], land[1] - tip[1])
        if chord_down > 1e-6:
            sag_down = chord_down * 0.18
            r_env_dn = (chord_down * chord_down / 4.0 + sag_down * sag_down) / (2.0 * sag_down)
            down_env = _arc_through_two_with_radius(tip, land, r_env_dn,
                                                    bulge_sign=+1, steps=14)
            outline += down_env[1:]
    return outline


# ---------------------------------------------------------------------------
# Leaf assembly
# ---------------------------------------------------------------------------


def _parametric_acanthus_leaf(width: float, height: float,
                              lobe_count: int = 5,
                              fingers_per_lobe: int | None = None,
                              turnover: float = 0.25,
                              variant: str = "corinthian",
                              teeth_per_lobe: int | None = None
                              ) -> list[Polyline]:
    """Acanthus leaf by Page's geometric construction, tip UP.

    Local frame: origin at leaf centre, y grows downward (SVG convention).
    Tip at y = -height/2, base at y = +height/2.

    Args:
        width, height: bounding-box size in mm.
        lobe_count: number of right-side lobes (the leaf has the same on
            left, plus a terminal lobe on the axis).  3, 5, or 7 reads as
            a young, standard, or mature leaf.
        fingers_per_lobe: small curved "fingers" within each lobe
            (Page's "raffles").  Default: 3 for the smallest lobes at the
            top, 5 for the largest at the base.  A single int forces all
            lobes to use that count.
        turnover: magnitude of the cane-curl at each lobe tip, [0, 0.5].
        variant: "corinthian" (plumper, squatter) or "rinceau" (slimmer).
        teeth_per_lobe: legacy alias for fingers_per_lobe (kept for
            backward compatibility with older callers).

    Returns:
        Polylines, in order:
          [silhouette_closed, midrib_line, *interior_creases]
    """
    if lobe_count not in (3, 5, 7):
        raise ValueError("lobe_count must be 3, 5, or 7")
    if variant not in ("corinthian", "rinceau"):
        raise ValueError("variant must be 'corinthian' or 'rinceau'")
    # Back-compat: teeth_per_lobe is the old parameter name.
    if fingers_per_lobe is None:
        fingers_per_lobe = teeth_per_lobe if teeth_per_lobe is not None else 5
    turnover = max(0.0, min(0.5, float(turnover)))

    # ------------------------------------------------------------------
    # Plate 1 armature: axis, horizontal bands, radiating stamen lines.
    # ------------------------------------------------------------------
    # Axis runs from TIP (y_tip) at top to BASE (y_base) at bottom.
    y_tip = -height * 0.50
    y_base = +height * 0.48   # reserve a hair for a stem stub
    axis_len = y_base - y_tip

    # Page subdivides the axis into (lobe_count + 1) bands.  The j-th band
    # (j=1..lobe_count) is where lobe j sits.  Band 0 is the terminal
    # region up at the tip.
    bands = lobe_count + 1
    def y_at_band(j: float) -> float:
        return y_tip + axis_len * (j / bands)

    # Each lobe j has:
    #   root_y = axis height at band j
    #   land_y = axis height at band j+1 (for the next lobe below)
    # The lobe's TIP is outward from the midrib; its x is bounded by the
    # ogival silhouette of Plate 1.  We approximate that silhouette as a
    # half-cosine: the leaf is widest near the middle-low bands and
    # narrows sharply near the tip and gently near the base.
    half_w = width * 0.5
    def silhouette_half(y: float) -> float:
        """Half-width of the ogival outline at axis y."""
        # Param t in [0,1] from tip (0) to base (1).
        t = (y - y_tip) / axis_len if axis_len else 0.0
        # Peak near t ~= 0.7, fall off to 0.05 at tip and ~0.75 at base.
        # Use a product of two cosine-style shape functions.
        # f_tip rises from 0 at t=0 -> 1 by t=0.5
        f_tip = math.sin(min(1.0, t * 1.6) * math.pi / 2)
        # f_base falls from 1 at t=0.7 to ~0.85 at t=1
        f_base = 1.0 - 0.15 * max(0.0, (t - 0.7) / 0.3)
        shape = f_tip * f_base
        # Corinthian variant -- slightly squatter, plumper.
        if variant == "corinthian":
            shape *= 1.0
        else:
            shape *= 0.95
        return half_w * shape

    # Fingers per lobe: if caller passed an int, use it for all lobes;
    # otherwise taper from 3 (top) -> fingers_per_lobe (base).
    def fingers_for(i: int) -> int:
        # i = 1..lobe_count, i=1 topmost, i=lobe_count at the base.
        base_n = fingers_per_lobe
        # Top lobe: at most 3 fingers (it's small and foreshortened).
        if i == 1:
            return max(2, min(3, base_n))
        if i == 2 and lobe_count >= 5:
            return max(3, min(base_n, base_n))
        return base_n

    # ------------------------------------------------------------------
    # Assemble the RIGHT side of the silhouette as a walk along the
    # ogival envelope, modulated by finger cups and inter-lobe notches.
    # ------------------------------------------------------------------
    # Conceptual model (distilled from Plates 1-3):
    #   1. The LEAF envelope is a smooth ogival curve from base to tip
    #      (Plate 1's outer contour).  We call this the "envelope".
    #   2. Along the envelope, successive LOBES occupy bands of the axis.
    #      Each lobe covers roughly `axis_len / bands` of the vertical
    #      range.  Lobes are stacked tip-upward.
    #   3. Within each lobe band, the outline FINGERS outward: it
    #      alternates between outward cup peaks (finger tips) and inward
    #      notches (valleys between fingers).  Cup peaks sit ON the
    #      envelope; valleys pull INWARD a bit.
    #   4. BETWEEN successive lobes, a deeper NOTCH pulls further inward
    #      toward the axis -- the "eye" or springing point where one
    #      lobe tucks behind the next.
    #
    # Walking the right side from base to tip: we generate a sequence of
    # (x, y) points at alternating PEAK and VALLEY positions along the
    # envelope, then connect successive points with short circular arcs
    # (convex outward for a finger cup, concave inward for a valley or
    # inter-lobe notch).

    right_side: Polyline = []
    stem_half = half_w * 0.10
    base_right = (stem_half, y_base)
    right_side.append(base_right)

    # Lobe parameters: vertical bands, one per lobe.  Lobe i covers the
    # axis range [y_lobe_top(i), y_lobe_bot(i)] with i=1 TOPMOST.
    # The side-lobes occupy bands 1..lobe_count; terminal is band 0.
    # We generate the walk for i = lobe_count (base) up to i = 0 (tip).
    def lobe_range(i: int) -> tuple[float, float]:
        """y range of lobe i on the axis: (y_top, y_bot) with y_top < y_bot."""
        if i == 0:
            # Terminal lobe: from band 1 up to the axis tip.
            return (y_tip, y_at_band(1))
        return (y_at_band(i - 1), y_at_band(i))

    # Crease data: collected alongside the walk so creases sit inside
    # each rendered lobe.
    lobe_geometry: list[dict] = []  # {root, tip, span}

    # Walk from base up to tip, lobe by lobe.
    #
    # We stop at i=1 (topmost SIDE lobe) and let the "Final terminus"
    # block below close the walk into the axis tip.  The i=0 "terminal
    # lobe" shares the same vertical band as lobe 1 (y_at_band(0)==y_tip
    # and y_at_band(1) is their common y_bot), and `silhouette_half(y)`
    # is a function of y alone -- so when lobe 0 was processed it retraced
    # lobe 1's finger positions, producing duplicate segments that
    # shapely reports as self-intersection.  The terminal "lobe" in
    # Page's construction is really just the leaf tip; we render it via
    # the arc that closes the walk to (0, y_tip).
    for i in range(lobe_count, 0, -1):
        y_top, y_bot = lobe_range(i)
        n_fingers = fingers_for(i)
        # The lobe's tip is where its tallest finger rises.  The lobe
        # tip sits on the envelope at y ≈ y_top + a small offset.
        lobe_tip_y = y_top + (y_bot - y_top) * 0.05
        lobe_tip_x = silhouette_half(lobe_tip_y) if i > 0 else 0.0
        # The lobe's root on the axis is at y_bot, slightly off-axis.
        lobe_root_y = y_bot
        lobe_root_x = half_w * (0.02 if i > 0 else 0.0)
        lobe_geometry.append({
            "root": (lobe_root_x, lobe_root_y),
            "tip": (lobe_tip_x, lobe_tip_y),
            "span": (y_top, y_bot),
        })

        # ---- Fingers along the lobe's outer edge ----
        # Distribute n_fingers along the lobe's y-range.  For each
        # finger, generate a peak (on envelope) and a preceding valley
        # (inward of envelope).  Fingers are drawn in y DESCENDING order
        # (walking up the page), because right_side grows from base to tip.
        #
        # Peak positions: y = y_bot - (k + 0.5) * (y_bot - y_top) / n_fingers
        # for k = 0..n_fingers-1.  The valley BEFORE peak k sits at
        # y = y_bot - k * (y_bot - y_top) / n_fingers, pulled inward.
        span = y_bot - y_top
        # Finger peak push: finger tip sits past the envelope so the
        # scallops clearly read as individual cups.  Between-finger
        # valley pulls inward by about the same amount.
        peak_over = half_w * 0.045
        valley_depth = half_w * 0.04
        # Between-lobe (inter-lobe) notch: a pronounced dip that reaches
        # roughly 35-50% of the way from the envelope toward the axis.
        # Page's Plate 3 shows these as bold, almost-semicircular tucks
        # that clearly separate one lobe from the next.  Deeper for lobes
        # near the base, shallower near the tip.
        interlobe_frac = 0.45 if i >= lobe_count - 1 else 0.35
        interlobe_depth = silhouette_half(y_bot) * interlobe_frac

        # First point on this lobe: a notch AT y_bot (the lobe root),
        # which serves as the transition FROM the lobe below (or from the
        # stem if this is the first lobe).
        if i == lobe_count:
            # Bottom lobe: sweep the stem up and outward to the lobe's
            # first valley point, tracing a smooth concave arc (the base
            # shoulder) so the leaf "springs" from its stem.
            root_pt = (silhouette_half(y_bot), y_bot)
            # Bridge goes: stem top -> shoulder (offset outward) -> root.
            shoulder = (silhouette_half(y_bot + span * 0.4) * 0.85,
                        y_bot + span * 0.4)
            right_side += _arc_through_three(base_right, shoulder,
                                             root_pt, steps=10)[1:]
        else:
            # Not the bottom lobe: we arrived from the previous (lower)
            # lobe's topmost finger.  Draw a SHALLOW inter-lobe notch: a
            # concave dip just inboard of the envelope at y_bot, not all
            # the way to the axis.  The envelope point for this lobe's
            # first finger is at y_bot - span/(2n), so the notch sits
            # between the last peak and the first peak of the new lobe.
            last_pt = right_side[-1]
            notch_env_x = silhouette_half(y_bot)
            notch_pt = (notch_env_x - interlobe_depth, y_bot)
            # Concave arc from last_pt in and down to notch_pt.
            nmid = (0.5 * (last_pt[0] + notch_pt[0]) - interlobe_depth * 0.15,
                    0.5 * (last_pt[1] + notch_pt[1]))
            right_side += _arc_through_three(last_pt, nmid,
                                             notch_pt, steps=6)[1:]

        # ---- Generate fingers for this lobe ----
        # Work in descending y (walking upward along the leaf silhouette).
        for k in range(n_fingers):
            # Valley before finger k (for k>0): at y_bot - k * span / n.
            # Peak at y_bot - (k+0.5) * span / n.
            if k > 0:
                y_valley = y_bot - k * span / n_fingers
                env_x = silhouette_half(y_valley)
                valley_pt = (env_x - valley_depth, y_valley)
                # Concave arc inward from previous point to valley_pt.
                prev = right_side[-1]
                vmid = (0.5 * (prev[0] + valley_pt[0]) - valley_depth * 0.2,
                        0.5 * (prev[1] + valley_pt[1]))
                right_side += _arc_through_three(prev, vmid,
                                                 valley_pt, steps=5)[1:]
            y_peak = y_bot - (k + 0.5) * span / n_fingers
            env_x_peak = silhouette_half(y_peak)
            # Clip x so the outer silhouette can't overshoot the declared
            # bbox.  The validator allows up to 10% overshoot; we stay
            # inside an 8% margin so rounding never pokes past.  This
            # matters most for lobe_count=7 where the ogival half-width
            # naturally grows past half_w at the widest band.
            env_x_peak = min(env_x_peak, half_w * 1.08 - peak_over)
            peak_pt = (env_x_peak + peak_over, y_peak)
            # Convex arc outward from previous point to peak_pt: small cup.
            #
            # The original implementation chose a "via" midpoint for
            # _arc_through_three that was nearly collinear with prev/peak
            # when prev was inboard (first finger after a notch or after
            # the turnover curl).  The circumcircle fit then chose the
            # long way round, dipping the outline below the previous
            # valley and self-crossing the incoming concave arc.
            # We now use _arc_through_two_with_radius with a small
            # sagitta and pick the bulge side that points OUTWARD from
            # the midrib (positive x-component).  That keeps the arc
            # monotone in x for any chord length, and never overshoots
            # the intended peak_pt in y so it can't cross the preceding
            # or following segments.
            prev = right_side[-1]
            chord_px = peak_pt[0] - prev[0]
            chord_py = peak_pt[1] - prev[1]
            chord_pl = math.hypot(chord_px, chord_py) or 1e-6
            # Sagitta: a shallow outward push.  Cap at a fraction of the
            # chord so long chords (notch -> first finger) stay gentle
            # while short chords (valley -> peak) still curve visibly.
            sag_p = min(peak_over * 0.3, chord_pl * 0.2)
            r_peak = (chord_pl * chord_pl / 4.0 + sag_p * sag_p) / (2.0 * sag_p)
            # _arc_through_two_with_radius places the centre on the side
            # picked by bulge_sign; the arc bulges to the opposite side,
            # i.e. along (dy/|c|, -dx/|c|) * bulge_sign.  We want the
            # bulge direction to have a positive x-component so the arc
            # curves outward from the midrib.
            bulge_x_sign_pos = chord_py / chord_pl  # x-component of sign=+1 bulge
            bulge_sign = +1 if bulge_x_sign_pos >= 0 else -1
            right_side += _arc_through_two_with_radius(
                prev, peak_pt, r_peak,
                bulge_sign=bulge_sign, steps=6)[1:]

        # ---- Turnover: small cane-curl past the topmost finger ----
        # Before the inter-lobe notch (or at the terminal tip), push one
        # more little arc outward-and-up to simulate the classical curl.
        # Radius proportional to span * turnover so it scales with lobe size.
        if turnover > 0 and i > 0:
            prev = right_side[-1]
            curl_r = span * turnover * 0.25
            # A small outward bump above the last finger tip.
            bump = (prev[0] + curl_r * 0.5, prev[1] - curl_r * 0.7)
            right_side += _arc_through_three(prev,
                                             (prev[0] + curl_r * 0.15,
                                              prev[1] - curl_r * 0.3),
                                             bump, steps=4)[1:]

    # Final terminus: walk the last point back toward the axis and up to tip.
    tip_pt = (0.0, y_tip)
    last_pt = right_side[-1]
    if not _near(last_pt, tip_pt):
        mid_final = (last_pt[0] * 0.4, 0.5 * (last_pt[1] + y_tip) - height * 0.005)
        right_side += _arc_through_three(last_pt, mid_final,
                                         tip_pt, steps=6)[1:]

    # ------------------------------------------------------------------
    # Mirror the right side across x=0 to make the left side.
    # ------------------------------------------------------------------
    left_side = mirror_path_x(list(reversed(right_side)), 0.0)

    # Stitch: right_side ends at the tip (0, y_tip); left_side starts at
    # the tip (mirrored, same point), ends at the base-left.
    silhouette: Polyline = list(right_side)
    if left_side and _near(silhouette[-1], left_side[0]):
        silhouette += left_side[1:]
    else:
        silhouette += left_side
    # Close the base: if the first and last points are not identical,
    # add a straight segment along the base.
    if not _near(silhouette[0], silhouette[-1]):
        silhouette.append(silhouette[0])

    # ------------------------------------------------------------------
    # Midrib: the central axis from just below tip to just above base.
    # ------------------------------------------------------------------
    midrib = line((0.0, y_tip + height * 0.04),
                  (0.0, y_base - height * 0.02),
                  steps=2)

    # ------------------------------------------------------------------
    # Interior creases: at each side-lobe root, a short RADIAL vein from
    # the axis outward into the middle of the lobe.  This is Page's
    # "stamen" line from Plate 1.  We do NOT draw the teardrop "eye"
    # closed shape here -- at small scales it reads as noise.  The
    # venation is the geometric skeleton that gives the leaf internal
    # structure in carving.
    # ------------------------------------------------------------------
    creases: list[Polyline] = []
    for lg in lobe_geometry:
        if lg["tip"][0] == 0.0:
            continue   # terminal lobe -- crease is the midrib itself
        root_y = lg["root"][1]
        tip_x, tip_y = lg["tip"]
        # Crease from a point just off the axis at the root out to ~60%
        # of the way toward the tip.  This matches Plate 1's stamen line.
        start = (half_w * 0.015, root_y - axis_len * 0.01)
        end = (tip_x * 0.55, 0.5 * (root_y + tip_y))
        creases.append(line(start, end, steps=2))
        creases.append(mirror_path_x(line(start, end, steps=2), 0.0))

    return [silhouette, midrib, *creases]


def _near(a: Point, b: Point, tol: float = 1e-6) -> bool:
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


# ---------------------------------------------------------------------------
# v2 — discrete-lobe construction (Phase 42)
# ---------------------------------------------------------------------------
# The v1 builder above walked one continuous ogival outline with raffle peaks
# along its edge. At carving scales (20–30 mm leaves) that reads as a teardrop
# with a fringed outline — not as acanthus. Canonical acanthus (Page 1886
# Plate 4; Vignola; Corinthian capital plates in Ware) is composed of N
# DISCRETE lobes stacked up the midrib, each with its own serrated edge,
# its own tip curl, and a visible "eye" gap to the next lobe. The
# construction below models exactly that.
#
# Each lobe has:
#   root        — where the lobe's outer edge leaves the midrib
#   tip         — the lobe's outermost point, extended up-and-out
#   return      — where the lobe's outer edge meets the midrib again,
#                 above the root (the lobe's base tucks behind the lobe
#                 stacked above it)
#   raffles     — N peaks pushed perpendicular-out along the outer curve,
#                 with valleys between them
#   turnover    — a small cane-curl at the tip (classical recurve)
#
# The leaf silhouette is the UNION of all lobe outlines + a small terminal
# lobe at the axis tip. Because each lobe is its own polyline, the inter-
# lobe eyes are literal gaps in the drawing, not a subtle dip in a
# continuous curve.


def _quad_bezier(p0: Point, p1: Point, p2: Point, steps: int = 16) -> Polyline:
    """Quadratic Bezier polyline from p0 through control p1 to p2."""
    pts: Polyline = []
    for i in range(steps):
        t = i / (steps - 1)
        u = 1 - t
        x = u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0]
        y = u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1]
        pts.append((x, y))
    return pts


def _raffle_walk(base: Polyline, sign: int, count: int,
                 peak_amp: float, valley_amp: float,
                 samples: int | None = None) -> Polyline:
    """Walk ``base`` and perturb it perpendicularly with a sinusoidal raffle:
    ``count`` outward peaks of amplitude ``peak_amp`` separated by inward
    valleys of amplitude ``valley_amp``. The endpoints of ``base`` are
    preserved as anchors (zero offset). ``sign`` picks the outward side.

    The wave is sampled densely so the emitted polyline reads as smooth
    scallops rather than sharp zigzags — that was the single most
    visible bug in the v1 construction.
    """
    if count <= 0 or len(base) < 3:
        return list(base)
    if samples is None:
        samples = max(4 * count + 12, 24)

    cum = [0.0]
    for i in range(1, len(base)):
        cum.append(cum[-1] + math.hypot(base[i][0] - base[i - 1][0],
                                         base[i][1] - base[i - 1][1]))
    total = cum[-1]
    if total < 1e-6:
        return list(base)

    def sample(t: float) -> tuple[Point, tuple[float, float]]:
        target = t * total
        for i in range(len(cum) - 1):
            if cum[i + 1] >= target - 1e-9:
                a, b = base[i], base[i + 1]
                seg_len = cum[i + 1] - cum[i]
                lt = (target - cum[i]) / seg_len if seg_len > 1e-9 else 0.0
                pt = (a[0] + (b[0] - a[0]) * lt,
                      a[1] + (b[1] - a[1]) * lt)
                tdx = b[0] - a[0]
                tdy = b[1] - a[1]
                tl = math.hypot(tdx, tdy) or 1.0
                tdx /= tl
                tdy /= tl
                nx, ny = -tdy, tdx
                if sign * nx < 0:
                    nx, ny = -nx, -ny
                return pt, (nx, ny)
        return base[-1], (float(sign), 0.0)

    # Wave parameters:
    #   ``count`` peaks within the interior [t_lo, t_hi] of the curve;
    #   outside that range offset tapers to zero so endpoints are anchors.
    t_lo, t_hi = 0.04, 0.96
    out: Polyline = []
    for k in range(samples):
        t = k / (samples - 1)
        pt, (nx, ny) = sample(t)
        if t <= t_lo or t >= t_hi:
            out.append(pt)
            continue
        tr = (t - t_lo) / (t_hi - t_lo)
        # sin(count * π * tr) — peaks at (2k+1)/(2*count), valleys between.
        wave = math.sin(count * math.pi * tr)
        # Taper near the endpoints so the first/last peaks aren't clipped.
        taper = math.sin(math.pi * tr)   # 0 at tr=0,1; 1 at tr=0.5
        if wave > 0:
            offset = peak_amp * wave * taper
        else:
            offset = valley_amp * wave * taper
        out.append((pt[0] + nx * offset, pt[1] + ny * offset))
    return out


def _build_lobe(root: Point, tip: Point, return_pt: Point,
                raffle_count: int, turnover: float,
                sign: int) -> Polyline:
    """One side-lobe outline: root → raffled outer curve → tip → curl →
    plain return curve → return_pt. Open polyline.
    """
    rx, ry = root
    tx, ty = tip
    zx, zy = return_pt

    # Outer base curve: quadratic bezier from root up-and-out to tip.
    # Control point pushed perpendicular-outward from the chord so the
    # curve bows CONVEXLY (away from the midrib) no matter the chord's
    # tilt. A small extra upward bias gives each lobe its springing
    # thrust.
    chord_out = math.hypot(tx - rx, ty - ry) or 1e-6
    cx_dir = (tx - rx) / chord_out
    cy_dir = (ty - ry) / chord_out
    # Outward perpendicular to the chord, aligned with ``sign`` (+1 = right).
    perp_x = -cy_dir
    perp_y = cx_dir
    if sign * perp_x < 0:
        perp_x, perp_y = -perp_x, -perp_y
    mid_out = (0.5 * (rx + tx), 0.5 * (ry + ty))
    bulge_out = chord_out * 0.32
    ctrl_out = (mid_out[0] + perp_x * bulge_out,
                mid_out[1] + perp_y * bulge_out - chord_out * 0.05)
    outer_base = _quad_bezier(root, ctrl_out, tip, steps=4 * raffle_count + 12)

    # Apply raffles to the outer base.
    outer = _raffle_walk(outer_base, sign=sign, count=raffle_count,
                         peak_amp=chord_out * 0.09,
                         valley_amp=chord_out * 0.055)

    # Turnover curl at tip: three points that peel back outward-and-up,
    # producing the classical "cane curl".
    if turnover > 0:
        curl_r = chord_out * turnover * 0.22
        # Direction from root toward tip (unit).
        dx = (tx - rx) / chord_out
        dy = (ty - ry) / chord_out
        # Outward normal at tip (perpendicular to chord, sign-aligned).
        nx, ny = -dy, dx
        if sign * nx < 0:
            nx, ny = -nx, -ny
        curl_peak = (tx + nx * curl_r * 1.1 + dx * curl_r * 0.1,
                     ty + ny * curl_r * 1.1 - curl_r * 0.6)
        curl_end = (tx + nx * curl_r * 0.55 - dx * curl_r * 0.2,
                    ty + ny * curl_r * 0.55 - curl_r * 0.25)
        outer = outer + [curl_peak, curl_end]

    # Return curve: from end-of-curl back to return_pt, with a gentle
    # outward bulge and a small number of under-serrations.
    last = outer[-1]
    chord_ret = math.hypot(zx - last[0], zy - last[1]) or 1e-6
    mid_ret = (0.5 * (last[0] + zx), 0.5 * (last[1] + zy))
    bulge_ret = chord_ret * 0.12
    ctrl_ret = (mid_ret[0] + sign * bulge_ret, mid_ret[1])
    return_base = _quad_bezier(last, ctrl_ret, return_pt,
                                steps=max(6, raffle_count + 4))
    ret = _raffle_walk(return_base, sign=sign,
                       count=max(1, raffle_count // 2),
                       peak_amp=chord_ret * 0.05,
                       valley_amp=chord_ret * 0.025)

    return outer + ret[1:]


def _lobe_outer_edge(root: Point, tip: Point, raffle_count: int,
                     turnover: float, sign: int) -> Polyline:
    """Just the outer edge of a lobe: root → raffled curve → tip → curl.
    Used to build the composite silhouette by walking outer edges only
    (skipping the return-to-midrib portion which would introduce
    non-monotone x-walk and break the silhouette outline).
    """
    rx, ry = root
    tx, ty = tip
    chord_out = math.hypot(tx - rx, ty - ry) or 1e-6
    cx_dir = (tx - rx) / chord_out
    cy_dir = (ty - ry) / chord_out
    perp_x = -cy_dir
    perp_y = cx_dir
    if sign * perp_x < 0:
        perp_x, perp_y = -perp_x, -perp_y
    mid_out = (0.5 * (rx + tx), 0.5 * (ry + ty))
    bulge_out = chord_out * 0.32
    ctrl_out = (mid_out[0] + perp_x * bulge_out,
                mid_out[1] + perp_y * bulge_out - chord_out * 0.05)
    outer_base = _quad_bezier(root, ctrl_out, tip, steps=4 * raffle_count + 12)
    outer = _raffle_walk(outer_base, sign=sign, count=raffle_count,
                         peak_amp=chord_out * 0.09,
                         valley_amp=chord_out * 0.055)
    if turnover > 0:
        curl_r = chord_out * turnover * 0.22
        dx = cx_dir
        dy = cy_dir
        nx, ny = -dy, dx
        if sign * nx < 0:
            nx, ny = -nx, -ny
        curl_peak = (tx + nx * curl_r * 1.1 + dx * curl_r * 0.1,
                     ty + ny * curl_r * 1.1 - curl_r * 0.6)
        curl_end = (tx + nx * curl_r * 0.55 - dx * curl_r * 0.2,
                    ty + ny * curl_r * 0.55 - curl_r * 0.25)
        outer = outer + [curl_peak, curl_end]
    return outer


def _build_terminal_lobe(y_top_band: float, y_tip: float,
                         half_w: float, raffle_count: int,
                         turnover: float = 0.25) -> Polyline:
    """Small terminal lobe that caps the axis tip. Symmetric: root at the
    top of the side-lobe band, sweeping up over the tip and back down.
    """
    term_h = y_top_band - y_tip   # negative in SVG-y since tip < band
    # Build right half: root_r (on midrib, at y_top_band) → outer right
    # along an outward arc → tip.
    root_r = (half_w * 0.08, y_top_band)
    root_l = (-half_w * 0.08, y_top_band)
    tip_pt = (0.0, y_tip)

    # Right half as a raffled lobe, tiny.
    right = _build_lobe(root_r, (half_w * 1.05, y_top_band + term_h * 0.55),
                        tip_pt, raffle_count=max(2, raffle_count),
                        turnover=turnover, sign=+1)
    # Left half as a raffled lobe, tiny.
    left = _build_lobe(tip_pt, (-half_w * 1.05, y_top_band + term_h * 0.55),
                       root_l, raffle_count=max(2, raffle_count),
                       turnover=turnover, sign=-1)
    # Right starts at root_r, ends at tip_pt. Left starts at tip_pt, ends at root_l.
    # But _build_lobe(root, tip, return_pt, ...) for left: root=tip_pt(top),
    # return=root_l — that walks from tip back down to root_l on the left
    # side. Polyline is open.
    return right + left[1:]


def _acanthus_leaf_lobed(width: float, height: float,
                         lobe_count: int = 5,
                         fingers_per_lobe: int | None = None,
                         turnover: float = 0.3,
                         variant: str = "corinthian",
                         teeth_per_lobe: int | None = None
                         ) -> list[Polyline]:
    """Acanthus leaf as N discrete lobes around a central midrib.

    Each side of the leaf carries ``lobe_count`` lobes. Each lobe is its own
    polyline running from a root point on the midrib, out to a tip, back
    to a return point on the midrib above the root (so the lobe's base
    tucks behind the lobe above it). Inter-lobe gaps are the visible
    midrib segments between successive lobes — the canonical "eyes".

    The construction reads as acanthus at scales from ~10 mm (capital
    ornament) up to ~150 mm (frieze panels).

    Returns polylines in order:
      [midrib, *(per-lobe outer+return), *veins, terminal]
    """
    if lobe_count not in (3, 5, 7):
        raise ValueError("lobe_count must be 3, 5, or 7")
    if variant not in ("corinthian", "rinceau"):
        raise ValueError("variant must be 'corinthian' or 'rinceau'")
    if fingers_per_lobe is None:
        fingers_per_lobe = teeth_per_lobe if teeth_per_lobe is not None else 4
    turnover = max(0.0, min(0.5, float(turnover)))

    half_w = width * 0.5
    y_tip = -height * 0.5
    y_base = +height * 0.5
    axis_len = y_base - y_tip
    tip_reserve = axis_len * 0.06
    stem_reserve = axis_len * 0.06
    y_top_band = y_tip + tip_reserve
    y_bot_band = y_base - stem_reserve
    band_len = y_bot_band - y_top_band
    slot = band_len / lobe_count   # vertical slot assigned to each lobe

    # Each lobe anchors in a narrow range on the midrib centered at
    # ``anchor_y(i)``. From there its outline sweeps UP-and-OUT, with the
    # tip projected roughly one slot-length above the anchor — so each
    # lobe's tip overlaps the territory of the lobe above it, producing
    # the canonical shingled stack. Root and return points bracket the
    # anchor; the short midrib segment between the return of lobe (i)
    # and the root of lobe (i-1) is the visible "eye".
    def anchor_y(i: int) -> float:
        return y_top_band + slot * (i - 0.5)

    def y_root(i: int) -> float:
        return anchor_y(i) + slot * 0.22

    def y_return(i: int) -> float:
        return anchor_y(i) - slot * 0.22

    def tip_of(i: int, sign: int) -> Point:
        ac = anchor_y(i)
        # Ogival width-scale: narrow at top, full at i ≈ 0.65·N, slightly
        # narrowed again at the base so the leaf springs from a clear stem.
        frac = i / lobe_count
        shape = 1.0 - ((frac - 0.62) / 0.62) ** 2 * 0.55
        shape = max(0.35, min(1.0, shape))
        if variant == "rinceau":
            shape *= 0.88
        xlobe = sign * half_w * shape
        # Tip pushes ~1.5 slots above the anchor so each lobe is tall
        # and narrow with a distinct thrust — the lobe becomes a
        # flame-shape, not a horizontal bar. At N=5 this means each
        # lobe overlaps the next one up by about 50% vertically, which
        # reads as proper shingling.
        y_push = slot * (1.55 if i > 1 else 1.0)
        ylobe = ac - y_push
        return (xlobe, ylobe)

    polys: list[Polyline] = []

    # Midrib: thin line along x=0 from just below the axis tip down to
    # just above the stem stub. The terminal lobe covers the tip region.
    midrib = [(0.0, y_top_band + axis_len * 0.005),
              (0.0, y_base - stem_reserve * 0.2)]

    lobe_outlines: list[Polyline] = []
    right_outer_edges: list[Polyline] = []   # for silhouette walk
    veins: list[Polyline] = []

    # Raffle counts taper: top lobe gets fewer (it's small), middle/bottom
    # lobes get the full count.
    def raffles_for(i: int) -> int:
        if i == 1:
            return max(2, fingers_per_lobe - 1)
        return fingers_per_lobe

    for i in range(1, lobe_count + 1):
        yr = y_root(i)
        yz = y_return(i)
        r_raff = raffles_for(i)
        for sign in (+1, -1):
            root_pt = (sign * half_w * 0.02, yr)
            return_pt = (sign * half_w * 0.02, yz)
            tip_pt = tip_of(i, sign)
            lobe_outlines.append(
                _build_lobe(root_pt, tip_pt, return_pt,
                            raffle_count=r_raff, turnover=turnover,
                            sign=sign))
            if sign == +1:
                right_outer_edges.append(
                    _lobe_outer_edge(root_pt, tip_pt,
                                     raffle_count=r_raff,
                                     turnover=turnover, sign=+1))
            # Vein: short straight crease from root to ~55% of the way
            # toward the tip. Reads as the branching vein of each lobe.
            vein_end = (root_pt[0] + (tip_pt[0] - root_pt[0]) * 0.55,
                        root_pt[1] + (tip_pt[1] - root_pt[1]) * 0.55)
            veins.append(line(root_pt, vein_end, steps=2))

    # Terminal lobe.
    term_half = half_w * min(0.35, 0.22 + 0.03 * lobe_count)
    terminal = _build_terminal_lobe(y_top_band, y_tip, term_half,
                                     raffle_count=max(2, fingers_per_lobe - 2),
                                     turnover=turnover * 0.7)

    # Build a composite closed silhouette that walks right-side lobes'
    # outer edges (bottom to top), across the terminal, and mirrors to
    # the left side. This preserves the old [silhouette, midrib, ...]
    # contract so ``validate_acanthus_leaf`` can count broad-lobe peaks
    # and any CSG clipping that uses polylines[0] gets a valid ring.
    silhouette = _compose_silhouette(right_outer_edges, terminal, y_base,
                                      stem_reserve, half_w)

    return [silhouette, midrib, *lobe_outlines, *veins, terminal]


def _compose_silhouette(right_outer_edges: list[Polyline],
                        terminal: Polyline,
                        y_base: float, stem_reserve: float,
                        half_w: float) -> Polyline:
    """Closed silhouette: a simple tip-to-tip walk with valleys between
    each pair of adjacent tips. One broad peak per lobe tip + one for
    the terminal; mirror-symmetric by construction.

    This is a CONTRACT polyline for validate_acanthus_leaf — it's not
    the visible rendering. The true serrated leaf is drawn by the lobe
    outlines and veins that follow in the return list.
    """
    # Extract tips: right-outer-edge's maximum-x point is the tip of
    # that lobe.
    tips: list[Point] = []
    for outer in right_outer_edges:
        if not outer:
            continue
        tip = max(outer, key=lambda p: p[0])
        tips.append(tip)
    # Terminal tip: top-most (min-y) point of the terminal, clamped to x=0.
    if terminal:
        term_tip_y = min(p[1] for p in terminal)
    else:
        term_tip_y = y_base - stem_reserve * 2

    stem_x = max(0.5, half_w * 0.06)
    y_stem_top = y_base - stem_reserve * 0.7

    # Right side walk, base → tip:
    right: Polyline = [(stem_x, y_base), (stem_x, y_stem_top)]
    if tips:
        # tips are ordered top-lobe-first (i=1..N). For base-up walk,
        # reverse to go bottom → top.
        tips_bu = list(reversed(tips))
        for i, tip in enumerate(tips_bu):
            # Valley before this tip: midway in y between previous point
            # and this tip, pulled in by ~30%.
            prev = right[-1]
            valley_y = 0.5 * (prev[1] + tip[1])
            valley_x = max(stem_x, 0.65 * tip[0])
            right.append((valley_x, valley_y))
            right.append(tip)
    # Close toward terminal: valley + terminal tip at (0, y_top).
    prev = right[-1]
    term_valley_y = 0.5 * (prev[1] + term_tip_y)
    term_valley_x = max(stem_x, 0.35 * prev[0])
    right.append((term_valley_x, term_valley_y))
    right.append((0.0, term_tip_y))

    # Mirror.
    left: Polyline = [(-x, y) for (x, y) in reversed(right)]
    pts = right + left[1:]
    if pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts


# ---------------------------------------------------------------------------
# Public wrapper -- dispatches through the motif plugin system
# ---------------------------------------------------------------------------


def acanthus_leaf(width: float, height: float,
                  lobe_count: int = 5,
                  fingers_per_lobe: int | None = None,
                  turnover: float = 0.25,
                  variant: str = "corinthian",
                  teeth_per_lobe: int | None = None
                  ) -> list[Polyline]:
    """Public acanthus leaf API.

    Dispatches through :func:`engraving.plugins.get_motif_or_default`
    so that a hand-drawn ``motifs/acanthus_leaf.svg`` (or any other
    SVG/callable registered under the name ``"acanthus_leaf"``)
    transparently overrides the parametric construction below.

    All parameters are forwarded to :func:`_parametric_acanthus_leaf`
    when no plugin is present; SVG plugins only receive ``width`` and
    ``height`` (the other parameters are structural knobs for the
    parametric builder and have no meaning for a pre-drawn motif).
    """
    return _plugins.get_motif_or_default(
        "acanthus_leaf",
        default_fn=_acanthus_leaf_lobed,
        width=width,
        height=height,
        lobe_count=lobe_count,
        fingers_per_lobe=fingers_per_lobe,
        turnover=turnover,
        variant=variant,
        teeth_per_lobe=teeth_per_lobe,
    )


# ---------------------------------------------------------------------------
# Small terminal acanthus (caulicoli tops, rinceau punctuation)
# ---------------------------------------------------------------------------


def _parametric_acanthus_tip(size: float, **kwargs) -> list[Polyline]:
    """Parametric miniature acanthus; see :func:`acanthus_tip`."""
    lobe_count = kwargs.pop("lobe_count", 3)
    fingers = kwargs.pop("fingers_per_lobe",
                         kwargs.pop("teeth_per_lobe", 3))
    turnover = kwargs.pop("turnover", 0.35)
    variant = kwargs.pop("variant", "corinthian")
    # Route through the public ``acanthus_leaf`` so the SVG-plugin hook
    # applies here too -- a dropped-in ``acanthus_leaf.svg`` becomes the
    # tip automatically without a second plugin file.
    return acanthus_leaf(width=size, height=size,
                         lobe_count=lobe_count,
                         fingers_per_lobe=fingers,
                         turnover=turnover, variant=variant)


def acanthus_tip(size: float, **kwargs) -> list[Polyline]:
    """Small terminal acanthus for caulicoli tops.  3-lobe miniature.

    Dispatches through the plugin system under the name
    ``"acanthus_tip"`` so an ``acanthus_tip.svg`` can replace the
    parametric default independently of the main leaf.
    """
    return _plugins.get_motif_or_default(
        "acanthus_tip",
        default_fn=_parametric_acanthus_tip,
        size=size,
        width=size,
        height=size,
        **kwargs,
    )


# Register the geometric defaults so external callers can resolve via name.
# ``register_motif`` delegates to ``engraving.plugins`` which preserves any
# SVG plugin loaded at import time (``svg_path`` wins in
# ``get_motif_or_default``).
register_motif("acanthus_leaf", _acanthus_leaf_lobed)
register_motif("acanthus_tip", _parametric_acanthus_tip)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


def _render_to_svg(polys: list[Polyline], out_path: str,
                    width: float, height: float,
                    margin: float = 6.0) -> str:
    import drawsvg as dw
    canvas_w = width + 2 * margin
    canvas_h = height + 2 * margin
    cx, cy = canvas_w / 2, canvas_h / 2
    d = dw.Drawing(canvas_w, canvas_h, origin=(0, 0))
    d.append(dw.Rectangle(0, 0, canvas_w, canvas_h, fill="white"))
    for poly in polys:
        shifted = translate_path(poly, cx, cy)
        path = dw.Path(stroke="black", stroke_width=0.25, fill="none")
        if not shifted:
            continue
        x0, y0 = shifted[0]
        path.M(x0, y0)
        for x, y in shifted[1:]:
            path.L(x, y)
        d.append(path)
    d.save_svg(out_path)
    return out_path


def _smoke_test() -> list[str]:
    from .preview import render_svg_to_png
    outs = []
    for n in (3, 5, 7):
        # 60 x 90 mm leaf at 300 dpi = readable preview of the fingers.
        w, h = 60.0, 90.0
        polys = acanthus_leaf(width=w, height=h, lobe_count=n,
                              fingers_per_lobe=5, turnover=0.25,
                              variant="corinthian")
        svg = f"/tmp/acanthus_v2_{n}.svg"
        png = f"/tmp/acanthus_v2_{n}.png"
        _render_to_svg(polys, svg, w, h, margin=8.0)
        render_svg_to_png(svg, png, dpi=300)
        outs.append(png)
    return outs


if __name__ == "__main__":
    for p in _smoke_test():
        print(f"Wrote {p}")
