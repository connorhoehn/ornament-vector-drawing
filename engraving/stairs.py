"""Stairs in elevation. Straight flights with optional flanking balustrades.

A flight of stairs in elevation is a zigzag of treads (horizontals) and
risers (verticals). This module draws straight runs — classical "flights"
between two landings — with the right-angle step profile seen in every
architectural pattern book from Palladio through Ware.

Proportions follow Georgian practice as reported by Ware (American Vignola,
pp. 56-57): a comfortable tread runs roughly 10-11 inches (~260-280 mm)
with a 7 inch (~178 mm) riser, the two related by the Blondel rule
``2·riser + tread ≈ 25 inches (635 mm)``.  Callers typically pass
``tread=28``/``riser=18`` for a reduced-scale reference drawing.

Coordinate convention: elevation view, Y increases downward (SVG).
``y_bottom`` is the level of the first riser's foot.  As steps rise, each
tread/riser moves upward (decreasing y) by ``riser``.
"""
from __future__ import annotations

import math
from typing import Literal

from .balustrades import balustrade_run, baluster_silhouette
from .geometry import Point, Polyline, line
from .schema import ElementResult


def straight_flight(x0: float, y_bottom: float, riser_count: int,
                    tread: float, riser: float,
                    direction: Literal["right", "left"] = "right",
                    with_balustrade: bool = True,
                    with_handrail: bool = True,
                    handrail_height: float = 90.0) -> ElementResult:
    """A linear flight of N steps.

    Parameters
    ----------
    x0, y_bottom
        Starting corner (bottom of the first riser) in millimetres.  For
        a right-ascending flight this is the bottom-left corner of the
        flight; for a left-ascending flight it is the bottom-right corner.
    riser_count
        Number of risers (== number of treads).  N risers means the top
        of the flight sits ``N * riser`` above the bottom and ``N * tread``
        horizontally from the start.
    tread, riser
        Individual step dimensions (mm).  Classical Georgian practice:
        11 inch tread (~280 mm) and 7 inch riser (~178 mm).
    direction
        ``"right"`` — stairs ascend to the right (x increasing as y
        decreases).  ``"left"`` — mirrored: stairs ascend to the left.
    with_balustrade
        If True, a flanking balustrade run is placed on the outer (open)
        side of the flight: a pedestal block at the start and at the top,
        with one baluster per step.
    with_handrail
        If True, a continuous sloped handrail is drawn at
        ``handrail_height`` above each nosing.
    handrail_height
        Height of the handrail above each tread nosing in mm.  Default
        90 mm reads at drawing scale as a 900 mm residential handrail.

    Returns
    -------
    ElementResult with:
        kind = "straight_flight"
        polylines layers: ``treads``, ``risers``, ``stringer``,
                          ``balusters``, ``handrail``
        anchors: ``bottom_left``, ``top_right`` (or their mirrored
                 counterparts for ``direction="left"``);
                 ``nosing_0`` ... ``nosing_{N-1}`` — the front edge of
                 each tread, numbered bottom-up (``nosing_0`` is at the
                 first step, ``nosing_{N-1}`` at the top).
        metadata: ``riser_count``, ``tread``, ``riser``, ``direction``.
    """
    # Direction sign: +1 for right-ascending, -1 for left-ascending.
    sx = 1 if direction == "right" else -1

    # ------------------------------------------------------------------
    # Step geometry — zigzag walk from the bottom up.
    # ------------------------------------------------------------------
    # Step i (0-indexed, i=0 is the lowest):
    #   riser i:  vertical from (x0 + i*dx, y_bottom - i*riser)
    #                     up to (x0 + i*dx, y_bottom - (i+1)*riser)
    #   tread i:  horizontal from top-of-riser-i out to
    #                              (x0 + (i+1)*dx, y_bottom - (i+1)*riser)
    dx = sx * tread

    risers: list[Polyline] = []
    treads: list[Polyline] = []
    nosings: list[Point] = []   # front-edge corner of each tread (outer edge)
    stringer_pts: list[Point] = [(x0, y_bottom)]

    for i in range(riser_count):
        x_left = x0 + i * dx
        x_right = x0 + (i + 1) * dx
        y_bot = y_bottom - i * riser
        y_top = y_bottom - (i + 1) * riser

        risers.append([(x_left, y_bot), (x_left, y_top)])
        treads.append([(x_left, y_top), (x_right, y_top)])

        # The "nosing" is the outer corner of the tread — where the tread
        # top meets the next riser (or the run's end).  For right-going
        # flights that is x_right; for left-going flights, x_right is less
        # than x_left, and the nosing still sits at (x_right, y_top).
        nosings.append((x_right, y_top))

        # Stringer zigzag: up the riser, across the tread.
        stringer_pts.append((x_left, y_top))
        stringer_pts.append((x_right, y_top))

    # Top of flight.
    top_x = x0 + riser_count * dx
    top_y = y_bottom - riser_count * riser

    # ------------------------------------------------------------------
    # Assemble ElementResult.
    # ------------------------------------------------------------------
    result = ElementResult(
        kind="straight_flight",
        polylines={
            "treads": treads,
            "risers": risers,
            "stringer": [stringer_pts],
        },
        metadata={
            "riser_count": riser_count,
            "tread": tread,
            "riser": riser,
            "direction": direction,
        },
    )

    # Anchors.  Use right-/left-naming consistent with the sense of the
    # flight: the "bottom" anchor is always at the foot of the first
    # riser; the "top" anchor is at the landing the stairs reach.
    if direction == "right":
        result.add_anchor("bottom_left", x0, y_bottom, role="corner")
        result.add_anchor("top_right", top_x, top_y, role="corner")
    else:
        result.add_anchor("bottom_right", x0, y_bottom, role="corner")
        result.add_anchor("top_left", top_x, top_y, role="corner")

    for i, (nx, ny) in enumerate(nosings):
        result.add_anchor(f"nosing_{i}", nx, ny, role="corner")

    # ------------------------------------------------------------------
    # Handrail — a sloped line at uniform height above the nosings.
    # ------------------------------------------------------------------
    if with_handrail and nosings:
        # Handrail starts above the first nosing (top of the first tread)
        # and runs to above the last nosing.  We offset each endpoint
        # straight up (negative y) by handrail_height so the rail stays
        # parallel to the pitch line.
        first_nose = nosings[0]
        last_nose = nosings[-1]
        hr_start = (first_nose[0] - 0.5 * dx, first_nose[1] - handrail_height)
        hr_end = (last_nose[0], last_nose[1] - handrail_height)
        result.polylines["handrail"] = [line(hr_start, hr_end, steps=2)]

    # ------------------------------------------------------------------
    # Balustrade flanking the open (outer) side.
    # ------------------------------------------------------------------
    # Each nosing gets one baluster standing on its tread.  The baluster
    # height equals ``handrail_height`` minus the rail's own thickness so
    # the cap tucks under the sloping rail.
    baluster_polys: list[Polyline] = []
    if with_balustrade and nosings:
        # Baluster height must reach the handrail underside at the baluster's
        # x.  The rail passes through each nosing at ``handrail_height``
        # above the tread, sloping at -riser/tread.  The baluster sits
        # 0.35*dx back (toward the prior nosing), where the rail — going up
        # toward the nosing — is 0.35*riser HIGHER above the tread.  So
        # ``bal_h = handrail_height - 0.35*riser`` makes baluster top meet
        # rail underside with no gap.  Width proportion stays at Ware's
        # h ≈ 3 × max_diam.
        bal_h = handrail_height - 0.35 * riser
        max_diam = bal_h / 3.0
        for (nx, ny) in nosings:
            # Baluster stands on the tread 0.35*dx back from the nosing —
            # far enough from the edge not to read as a carpenter's error.
            cx_b = nx - 0.35 * dx
            baluster_polys.extend(
                baluster_silhouette(cx_b, ny, bal_h, max_diam,
                                    variant="tuscan")
            )
        result.polylines["balusters"] = baluster_polys

    # ------------------------------------------------------------------
    # Bounding box.
    # ------------------------------------------------------------------
    result.compute_bbox()
    return result


# --------------------------------------------------------------------------
# Smoke test
# --------------------------------------------------------------------------

def _smoke_test() -> None:
    import drawsvg as dw

    from .preview import render_svg_to_png

    stairs = straight_flight(x0=20, y_bottom=180, riser_count=10,
                             tread=28, riser=18,
                             with_balustrade=True, with_handrail=True)

    # Canvas sized so the top of the flight and its last baluster fit.
    # The top of the flight sits at y = 180 - 10*18 = 0; balusters above
    # the top nosing extend to y ≈ -72 (bal_h = 72).  We translate the
    # drawing downward by 90 mm so nothing is clipped.
    canvas_w, canvas_h = 360, 320
    d = dw.Drawing(canvas_w, canvas_h, origin=(0, 0))
    d.append(dw.Rectangle(0, 0, canvas_w, canvas_h, fill="white"))
    y_offset = 100.0
    for layer in stairs.polylines.values():
        for pl in layer:
            if not pl:
                continue
            # Shift down by y_offset so the top balusters clear the top
            # of the canvas.
            shifted = [c for pt in pl for c in (pt[0], pt[1] + y_offset)]
            d.append(dw.Lines(*shifted,
                              close=False, fill='none',
                              stroke='black', stroke_width=0.25))
    d.save_svg('/tmp/stairs_test.svg')
    render_svg_to_png('/tmp/stairs_test.svg',
                      '/tmp/stairs_test.png', dpi=200)
    print("Wrote /tmp/stairs_test.svg and /tmp/stairs_test.png")
    print(f"riser_count={stairs.metadata['riser_count']}, "
          f"nosings={sum(1 for k in stairs.anchors if k.startswith('nosing_'))}")
    print(f"bbox={stairs.bbox}")


if __name__ == "__main__":
    _smoke_test()
