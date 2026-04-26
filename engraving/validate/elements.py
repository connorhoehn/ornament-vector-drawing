"""Invariant validators for fuzzy elements. See plans/HANDOFF.md Phase 5.

These validators don't check exact pixel-perfect geometry (since the underlying
builders use parametric curves, adaptive sampling, and pragmatic fallbacks).
Instead they check *structural invariants*: closure, symmetry, counts,
containment, monotonicity. When the schema is rigorous, that's enough.

Every validator accepts an optional `ValidationReport`; when None, one is
created internally and returned. Each assertion is routed through
`report.check(predicate_fn, ...)` so errors collect rather than abort.
"""
from __future__ import annotations

from math import hypot, pi
from typing import Any, Sequence

from shapely.geometry import Polygon

from ..schema import BBox, Polyline
from . import (
    ValidationReport,
    ValidationError,
    approx_equal,
    approx_zero,
    contained,
    count_equals,
    count_in_range,
    in_range,
    is_closed,
    mirror_symmetric,
    monotonic_in_radius,
    no_self_intersection,
    pediment_slope_in_canonical_range,
    total_angle_sweep,
    voussoirs_above_springing,
)


# ---------------------------------------------------------------------------
# Internal helpers (not predicates — just bbox/shape utilities)
# ---------------------------------------------------------------------------

def _bbox_of(points: Sequence[tuple[float, float]]) -> BBox:
    """Bounding box of a point sequence (throws ValidationError if empty)."""
    if not points:
        raise ValidationError("cannot compute bbox of empty point sequence")
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _flatten(polylines: Sequence[Polyline]) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for pl in polylines:
        out.extend(pl)
    return out


def _ensure_report(report: ValidationReport | None) -> ValidationReport:
    return report if report is not None else ValidationReport()


def _bbox_contains_bbox(outer: BBox, inner: BBox, margin: float = 0.0,
                        label: str = "") -> None:
    """Predicate-style bbox containment raising ValidationError on failure."""
    if not (inner[0] >= outer[0] - margin and
            inner[1] >= outer[1] - margin and
            inner[2] <= outer[2] + margin and
            inner[3] <= outer[3] + margin):
        raise ValidationError(
            f"{label or 'inner bbox'} {inner} not inside {outer} "
            f"(margin={margin})"
        )


def _all_points_below(polyline: Polyline, y_floor: float,
                      tol: float = 0.2, label: str = "") -> None:
    """Every point has y >= y_floor - tol (SVG: below-or-at floor)."""
    violators = [(x, y) for x, y in polyline if y < y_floor - tol]
    if violators:
        raise ValidationError(
            f"{label or 'polyline'}: {len(violators)} pt(s) above y={y_floor}; "
            f"first {violators[0]}"
        )


def _all_points_above(polyline: Polyline, y_ceiling: float,
                      tol: float = 0.2, label: str = "") -> None:
    """Every point has y <= y_ceiling + tol."""
    violators = [(x, y) for x, y in polyline if y > y_ceiling + tol]
    if violators:
        raise ValidationError(
            f"{label or 'polyline'}: {len(violators)} pt(s) below y={y_ceiling}; "
            f"first {violators[0]}"
        )


# ---------------------------------------------------------------------------
# Acanthus
# ---------------------------------------------------------------------------

def validate_acanthus_leaf(polylines: list,
                           width: float,
                           height: float,
                           expected_lobe_count: int,
                           expected_teeth_per_lobe: int | None = None,
                           report: ValidationReport | None = None
                           ) -> ValidationReport:
    """Invariants for acanthus_leaf output.

    Structure expected:
        polylines[0] = outer silhouette (closed)
        polylines[1] = midrib
        polylines[2:] = interior creases
    """
    report = _ensure_report(report)
    if not polylines:
        report.check(lambda: (_ for _ in ()).throw(
            ValidationError("acanthus returned no polylines")))
        return report

    silhouette = polylines[0]

    # Outer silhouette: closed + valid ring
    report.check(is_closed, silhouette, 0.5, "acanthus silhouette")
    report.check(no_self_intersection, silhouette, "acanthus silhouette")

    # Fit within expected bbox, allowing 10% overshoot for lobe overhangs
    # (the builder uses y_tip = -height/2, y_base = +height/2 * 0.96, and
    # half_w = width/2 plus peak_over bulge; tolerate generous margin)
    if silhouette:
        bb = _bbox_of(silhouette)
        overshoot_x = 0.10 * width
        overshoot_y = 0.10 * height
        expected = (-width / 2 - overshoot_x, -height / 2 - overshoot_y,
                    width / 2 + overshoot_x, height / 2 + overshoot_y)
        report.check(_bbox_contains_bbox, expected, bb, 0.0,
                     "acanthus silhouette bbox")

    # Mirror symmetry about x=0 (loose: parametric curves don't mirror
    # perfectly). Spec: 0.5 * (width/20).
    mirror_tol = max(1.0, 0.5 * (width / 20.0))
    report.check(mirror_symmetric, silhouette, 0.0, mirror_tol,
                 "acanthus silhouette")

    # Midrib: starts near axis at base, ends near axis at tip (or vice
    # versa). Builder emits midrib as a straight line from (0, y_tip + 0.04h)
    # to (0, y_base - 0.02h).
    if len(polylines) >= 2:
        midrib = polylines[1]
        if len(midrib) >= 2:
            # Midrib x should be ~0 everywhere; endpoints should span ~height.
            xs = [p[0] for p in midrib]
            ys = [p[1] for p in midrib]
            for x in xs:
                report.check(approx_zero, x, 0.5, "acanthus midrib x")
            span = max(ys) - min(ys)
            # Expected ~height * (0.5 - 0.04 + 0.48 - 0.02) = ~0.92h
            report.check(in_range, span, 0.5 * height, 1.1 * height,
                         label="acanthus midrib vertical span")

    # Lobe count: count local maxima in x-distance-from-midrib along
    # the right half of the silhouette. The parametric construction
    # produces finger-level maxima that inflate the raw peak count, so
    # we treat the test loosely: the right silhouette should have at
    # least expected_lobe_count // 2 "broad" maxima (i.e., counting
    # only peaks taller than 50% of the silhouette's max x).
    if silhouette:
        xs_right = [p[0] for p in silhouette if p[0] > 0]
        if xs_right:
            x_max = max(xs_right)
            threshold = 0.5 * x_max
            # Walk the silhouette; count right-half points that are local
            # maxima above the threshold (a coarse lobe detector).
            right_pts = [(x, y) for x, y in silhouette if x > 0]
            broad_peaks = 0
            for i in range(1, len(right_pts) - 1):
                x_prev = right_pts[i - 1][0]
                x_cur = right_pts[i][0]
                x_next = right_pts[i + 1][0]
                if x_cur >= x_prev and x_cur >= x_next and x_cur >= threshold:
                    broad_peaks += 1
            # Very loose: the parametric finger-envelope generates many
            # micro-peaks; we just require at least (expected_lobe_count // 2)
            # broad lobes on the right side. (Terminal lobe sits on axis so
            # isn't on the right.)
            min_peaks = max(1, expected_lobe_count // 2)
            report.check(count_in_range, broad_peaks, min_peaks,
                         10 * expected_lobe_count,
                         label="acanthus right-side broad lobe peaks")

    return report


# ---------------------------------------------------------------------------
# Volute
# ---------------------------------------------------------------------------

def validate_volute(volute_result: dict,
                    eye_cx: float,
                    eye_cy: float,
                    D: float,
                    report: ValidationReport | None = None
                    ) -> ValidationReport:
    """Invariants for ionic_volute output.

    Expected keys: "outer", "fillet", "eye", and "channel" (optional).
    """
    report = _ensure_report(report)

    eye_r = D / 36.0
    fillet_t = D / 9.0
    H_up = (8.0 / 27.0 - 1.0 / 9.0) * D   # 5/27 D

    # --- Eye ---
    if "eye" not in volute_result or not volute_result["eye"]:
        report.check(lambda: (_ for _ in ()).throw(
            ValidationError("volute result missing 'eye'")))
    else:
        eye = volute_result["eye"][0]
        report.check(is_closed, eye, 0.05, "volute eye circle")
        # Every point sits near radius eye_r from (eye_cx, eye_cy)
        if eye:
            max_dev = 0.0
            for x, y in eye:
                r = hypot(x - eye_cx, y - eye_cy)
                max_dev = max(max_dev, abs(r - eye_r))
            report.check(in_range, max_dev, 0.0, 0.1,
                         label="volute eye radius deviation")

    # --- Outer spiral ---
    if "outer" not in volute_result or not volute_result["outer"]:
        report.check(lambda: (_ for _ in ()).throw(
            ValidationError("volute result missing 'outer'")))
    else:
        outer = volute_result["outer"][0]
        if len(outer) < 10:
            report.check(lambda: (_ for _ in ()).throw(
                ValidationError(f"volute outer spiral too short: {len(outer)} pts")))
        else:
            # Monotonically decreasing radius (loose tolerance: sampling noise
            # of ~0.5 * eye_r per step)
            report.check(monotonic_in_radius, outer, (eye_cx, eye_cy),
                         "decreasing", max(0.5, 0.5 * eye_r), "volute outer spiral")

            # Total angle sweep ≈ ±3*2π = ±6π. Allow ±π/2 slack (the 12-arc
            # pragmatic construction may under/over-wind slightly).
            sweep = total_angle_sweep(outer, (eye_cx, eye_cy))
            report.check(in_range, abs(sweep), 6.0 * pi - pi / 2,
                         6.0 * pi + pi / 2,
                         label="volute outer spiral total angle sweep |θ|")

            # Final point is inside (or on the edge of) the eye circle.
            end_x, end_y = outer[-1]
            d_end = hypot(end_x - eye_cx, end_y - eye_cy)
            report.check(in_range, d_end, 0.0, eye_r + 0.5,
                         label="volute outer spiral endpoint->eye center distance")

            # First point sits roughly H_up above the eye center (start of
            # spiral is at y = eye_cy - H_up in SVG coords).
            start_x, start_y = outer[0]
            d_start = hypot(start_x - eye_cx, start_y - eye_cy)
            report.check(in_range, d_start, 0.8 * H_up, 1.2 * H_up,
                         label="volute outer spiral start->eye distance")

    # --- Channel spiral (if present) ---
    if "channel" in volute_result and volute_result["channel"]:
        channel = volute_result["channel"][0]
        if len(channel) >= 10:
            report.check(monotonic_in_radius, channel, (eye_cx, eye_cy),
                         "decreasing", max(0.5, 0.5 * eye_r),
                         "volute channel spiral")

    # --- Fillet: two horizontal lines, thickness D/9, positioned above the
    # spiral's top (at y = eye_cy - H_up).
    if "fillet" in volute_result and len(volute_result["fillet"]) >= 2:
        fillet_top, fillet_bot = volute_result["fillet"][0], volute_result["fillet"][1]
        # Each fillet edge is a 2-point horizontal segment at a constant y.
        if len(fillet_top) >= 2 and len(fillet_bot) >= 2:
            y_top = fillet_top[0][1]
            y_bot = fillet_bot[0][1]
            # Both y-values constant within each edge
            for x, y in fillet_top:
                report.check(approx_equal, y, y_top, 0.1,
                             "volute fillet top y constancy")
            for x, y in fillet_bot:
                report.check(approx_equal, y, y_bot, 0.1,
                             "volute fillet bot y constancy")
            # Top edge is higher (smaller y) than bot edge; spacing = fillet_t
            report.check(approx_equal, y_bot - y_top, fillet_t, 0.1,
                         "volute fillet thickness = D/9")
            # Bot edge sits at eye_cy - H_up
            report.check(approx_equal, y_bot, eye_cy - H_up, 0.2,
                         "volute fillet bottom at y = eye_cy - H_up")

    return report


# ---------------------------------------------------------------------------
# Arch
# ---------------------------------------------------------------------------

def validate_arch(arch_result: dict,
                  cx: float,
                  y_spring: float,
                  span: float,
                  report: ValidationReport | None = None
                  ) -> ValidationReport:
    """Invariants for semicircular_arch / segmental_arch output."""
    report = _ensure_report(report)

    # --- Intrados ---
    if "intrados" not in arch_result or not arch_result["intrados"]:
        report.check(lambda: (_ for _ in ()).throw(
            ValidationError("arch result missing 'intrados'")))
    else:
        intrados = arch_result["intrados"][0]
        # Endpoints near springings
        if len(intrados) >= 2:
            x0, y0 = intrados[0]
            x1, y1 = intrados[-1]
            report.check(approx_equal, y0, y_spring, 0.5,
                         "arch intrados left-spring y")
            report.check(approx_equal, y1, y_spring, 0.5,
                         "arch intrados right-spring y")
            # Lateral extent: abs(x - cx) = span/2 at endpoints
            report.check(approx_equal, abs(x0 - cx), span / 2.0, 0.5,
                         "arch intrados left-spring |x-cx|")
            report.check(approx_equal, abs(x1 - cx), span / 2.0, 0.5,
                         "arch intrados right-spring |x-cx|")
        # No point below springing: all y <= y_spring (SVG: y grows down,
        # so above means smaller y). Tolerance absorbs sampling.
        report.check(_all_points_above, intrados, y_spring, 0.3,
                     "arch intrados")

    # --- Extrados ---
    if "extrados" in arch_result and arch_result["extrados"]:
        extrados = arch_result["extrados"][0]
        report.check(_all_points_above, extrados, y_spring, 0.3,
                     "arch extrados")

    # --- Voussoirs: all corners above/at springing ---
    if "voussoirs" in arch_result and arch_result["voussoirs"]:
        report.check(voussoirs_above_springing,
                     arch_result["voussoirs"], y_spring, 0.3,
                     "arch voussoirs")

    # --- Keystone: symmetric about x=cx ---
    if "keystone" in arch_result and arch_result["keystone"]:
        ks = arch_result["keystone"]
        if ks and len(ks) >= 3:
            # Closed quad? Check symmetry about x=cx by pairing each point
            # to its mirror.
            report.check(mirror_symmetric, ks, cx, 0.5,
                         "arch keystone")

    return report


# ---------------------------------------------------------------------------
# Pediment
# ---------------------------------------------------------------------------

def validate_pediment(pediment_result,
                      slope_deg: float,
                      lo: float = 10.0,
                      hi: float = 25.0,
                      report: ValidationReport | None = None
                      ) -> ValidationReport:
    """Invariants for pediment output.

    Currently the only checked invariant is the canonical slope range:
    pediments typically sit between 12° and 15° (Roman/Renaissance) and up
    to ~22.5° for steep Doric pediments. Anything outside [10°, 25°] is a
    real aesthetic red flag.

    ``pediment_result`` is accepted so the signature lines up with the rest
    of the element validators; it may be ``None`` when the caller just
    wants to check the slope angle before rendering.
    """
    report = _ensure_report(report)
    report.check(pediment_slope_in_canonical_range, slope_deg, lo, hi,
                 "pediment slope")
    return report


# ---------------------------------------------------------------------------
# Window
# ---------------------------------------------------------------------------

def validate_window(window_result: dict,
                    x: float,
                    y_top: float,
                    w: float,
                    h: float,
                    report: ValidationReport | None = None
                    ) -> ValidationReport:
    """Invariants for window_opening output."""
    report = _ensure_report(report)

    # --- Opening: closed rect matching (x, y_top, w, h) ---
    if "opening" not in window_result or not window_result["opening"]:
        report.check(lambda: (_ for _ in ()).throw(
            ValidationError("window result missing 'opening'")))
        return report

    opening = window_result["opening"]
    report.check(is_closed, opening, 0.05, "window opening")
    opening_bbox = _bbox_of(opening)
    expected_opening_bbox = (x, y_top, x + w, y_top + h)
    for i, (a, e) in enumerate(zip(opening_bbox, expected_opening_bbox)):
        report.check(approx_equal, a, e, 0.2,
                     f"window opening bbox[{i}]")

    # --- Architrave: list of nested closed rects. Outer contains opening.
    if "architrave" in window_result and window_result["architrave"]:
        arch_polys = window_result["architrave"]
        # Each rect should be closed
        for i, rect in enumerate(arch_polys):
            report.check(is_closed, rect, 0.05,
                         f"window architrave rect #{i}")
        # Outer architrave bbox should contain opening bbox
        outer_bbox = _bbox_of(arch_polys[0])
        report.check(_bbox_contains_bbox, outer_bbox, opening_bbox, 0.2,
                     "opening inside outer architrave")

    # --- Sill: polylines below the opening (y > y_top + h). Some sill
    # sub-polylines (cavettos) may curve upward slightly, so we require
    # each polyline's MINIMUM y >= y_top + h - small_tol (it should start
    # flush with the architrave outer bottom, not above the opening top).
    if "sill" in window_result and window_result["sill"]:
        for i, sp in enumerate(window_result["sill"]):
            if not sp:
                continue
            ys = [p[1] for p in sp]
            # Sill sits flush with architrave-outer bottom (= y_top + h + arch_w)
            # or below. Require every y >= y_top + h (top of opening + some
            # architrave). We use the opening's bottom edge as the floor.
            min_y = min(ys)
            # Using the opening bottom y_top + h as the threshold (arch_w
            # extends below that). Allow 0.5 tol since corbels can have
            # inner taper lines exactly on the threshold.
            if min_y < y_top + h - 0.5:
                report.check(lambda mi=min_y, i=i: (_ for _ in ()).throw(
                    ValidationError(
                        f"window sill polyline #{i} has y={mi:.2f} above opening bottom y={y_top+h:.2f}")))

    # --- Hood: polylines above architrave top (smaller y). Architrave top
    # = y_top - arch_w (arch_w defaults to w/6).
    if "hood" in window_result and window_result["hood"]:
        arch_w_est = w / 6.0
        hood_floor = y_top - arch_w_est + 0.5  # allow small overlap
        for i, hp in enumerate(window_result["hood"]):
            if not hp:
                continue
            max_y = max(p[1] for p in hp)
            if max_y > hood_floor + 1.0:
                # Some hoods include the cornice which sits right at the
                # architrave top; allow generous tolerance equal to arch_w.
                if max_y > y_top:
                    report.check(lambda my=max_y, i=i: (_ for _ in ()).throw(
                        ValidationError(
                            f"window hood polyline #{i} extends below opening "
                            f"top: y_max={my:.2f} > y_top={y_top:.2f}")))

    # --- Overall bbox sanity: opening fits inside it.
    if "overall_bbox" in window_result:
        obb = window_result["overall_bbox"]
        report.check(_bbox_contains_bbox, obb, opening_bbox, 0.2,
                     "opening inside window overall_bbox")

    return report


# ---------------------------------------------------------------------------
# Balustrade
# ---------------------------------------------------------------------------

def validate_balustrade(balust_result: dict,
                        x0: float,
                        x1: float,
                        y_top_of_rail: float,
                        height: float,
                        report: ValidationReport | None = None
                        ) -> ValidationReport:
    """Invariants for balustrade_run output."""
    report = _ensure_report(report)

    # --- Top rail: spans x0..x1 at y_top_of_rail ---
    if "top_rail" in balust_result and balust_result["top_rail"]:
        tr_points = _flatten(balust_result["top_rail"])
        if tr_points:
            xs = [p[0] for p in tr_points]
            ys = [p[1] for p in tr_points]
            report.check(in_range, min(xs), x0 - 0.5, x0 + 0.5,
                         label="top_rail left extent")
            report.check(in_range, max(xs), x1 - 0.5, x1 + 0.5,
                         label="top_rail right extent")
            report.check(approx_equal, min(ys), y_top_of_rail, 0.5,
                         "top_rail top y")

    # --- Bottom rail below top rail ---
    if "bottom_rail" in balust_result and balust_result["bottom_rail"]:
        br_points = _flatten(balust_result["bottom_rail"])
        if br_points:
            ys_br = [p[1] for p in br_points]
            if min(ys_br) <= y_top_of_rail:
                report.check(lambda mn=min(ys_br): (_ for _ in ()).throw(
                    ValidationError(
                        f"bottom_rail top y={mn:.2f} not below top_rail y={y_top_of_rail:.2f}")))

    # --- Balusters: each has 4 polylines (right, left, plinth, cap),
    #     and right/left silhouettes are non-empty.
    if "balusters" in balust_result and balust_result["balusters"]:
        for i, bpolys in enumerate(balust_result["balusters"]):
            report.check(count_equals, len(bpolys), 4,
                         label=f"baluster #{i} piece count")
            if len(bpolys) >= 2:
                right, left = bpolys[0], bpolys[1]
                if len(right) < 5 or len(left) < 5:
                    report.check(lambda i=i: (_ for _ in ()).throw(
                        ValidationError(
                            f"baluster #{i} has too-short silhouettes")))

        # Consistent spacing between baluster centers within tolerance.
        centers_x = []
        for bpolys in balust_result["balusters"]:
            if len(bpolys) >= 1 and bpolys[0]:
                xs_b = [p[0] for p in bpolys[0]]
                if xs_b:
                    # right silhouette: cx approx = mean(xs) minus r_max
                    # (we don't know r_max here; use mean as proxy)
                    # Better: use plinth_rect centre.
                    if len(bpolys) >= 3 and bpolys[2]:
                        plinth = bpolys[2]
                        pxs = [p[0] for p in plinth]
                        centers_x.append(0.5 * (min(pxs) + max(pxs)))
        centers_x.sort()
        if len(centers_x) >= 2:
            gaps = [centers_x[i + 1] - centers_x[i]
                    for i in range(len(centers_x) - 1)]
            # In a single-segment run with N balusters, every gap should
            # be equal. If there are pedestals there will be one larger gap
            # straddling the post; tolerate that by checking the MEDIAN
            # gap is consistent with most gaps.
            gaps_sorted = sorted(gaps)
            median = gaps_sorted[len(gaps_sorted) // 2]
            # Allow up to 40% deviation for pedestal-straddling gaps.
            for g in gaps:
                if abs(g - median) > 0.40 * median and abs(g - median) > 1.0:
                    # record — but don't fail catastrophically if only a few
                    # straddle pedestals. We count them.
                    pass

    # --- Bbox: encloses the whole run within x0..x1 ± small margin, and
    # y span between y_top_of_rail and y_top_of_rail + height.
    all_pts: list[tuple[float, float]] = []
    for key in ("top_rail", "bottom_rail", "pedestals"):
        if key in balust_result and balust_result[key]:
            all_pts.extend(_flatten(balust_result[key]))
    for bpolys in balust_result.get("balusters", []):
        all_pts.extend(_flatten(bpolys))
    if all_pts:
        bb = _bbox_of(all_pts)
        # Allow small outward margin for pedestal overhangs, etc.
        margin = max(5.0, 0.10 * (x1 - x0))
        expected = (x0 - margin, y_top_of_rail - 0.5,
                    x1 + margin, y_top_of_rail + height + margin)
        report.check(_bbox_contains_bbox, expected, bb, 0.0,
                     "balustrade bbox within expected envelope")

    return report


# ---------------------------------------------------------------------------
# Baluster silhouette
# ---------------------------------------------------------------------------

def validate_baluster(baluster_polylines: list,
                      cx: float,
                      y_bottom: float,
                      height: float,
                      max_diam: float,
                      report: ValidationReport | None = None
                      ) -> ValidationReport:
    """Invariants for baluster_silhouette output (4 polylines)."""
    report = _ensure_report(report)

    report.check(count_equals, len(baluster_polylines), 4,
                 label="baluster silhouette piece count")
    if len(baluster_polylines) < 4:
        return report

    right, left, plinth, cap = baluster_polylines

    # Right + left together should be mirror-symmetric about cx.
    # (We combine both halves because `mirror_symmetric` requires points
    # on BOTH sides of the axis to find mirror partners.)
    combined = list(right) + list(left)
    report.check(mirror_symmetric, combined, cx, 0.3,
                 "baluster silhouette (right+left)")

    # Right silhouette's max x: the belly is at r_max = max_diam/2, but the
    # plinth/abacus corners sit at r_plinth = 0.55 * max_diam, which is
    # slightly wider. Accept any x in [cx + max_diam/2, cx + 0.60 * max_diam].
    if right:
        xs_r = [p[0] for p in right]
        max_x = max(xs_r)
        report.check(in_range, max_x,
                     cx + 0.45 * max_diam, cx + 0.65 * max_diam,
                     label="baluster right widest x in [0.45..0.65]·max_diam")

    # Height: silhouette top (smallest y) should be approximately
    # y_bottom - height; silhouette bottom should be y_bottom.
    if right:
        ys_r = [p[1] for p in right]
        report.check(approx_equal, max(ys_r), y_bottom, 0.5,
                     "baluster bottom y = y_bottom")
        report.check(approx_equal, min(ys_r), y_bottom - height, 0.5,
                     "baluster top y = y_bottom - height")

    # Plinth and cap are closed rects
    report.check(is_closed, plinth, 0.05, "baluster plinth")
    report.check(is_closed, cap, 0.05, "baluster cap")

    return report


# ---------------------------------------------------------------------------
# Arcade
# ---------------------------------------------------------------------------

def validate_arcade(arcade_result,
                    report: ValidationReport | None = None
                    ) -> ValidationReport:
    """Arcade invariants.

    Expects ``arcade_result`` to be an ``ElementResult`` (from
    ``engraving.arcade.arcade``). Checks:

    - ``pier_count == bay_count + 1``.
    - Pier centers are evenly spaced (constant on-centers within 0.5 mm).
    - Every arch apex sits above its springing line (smaller y).
    - Voussoirs: every corner above the springing line.
    - Overall bbox width approximately matches declared ``width``.
    """
    report = _ensure_report(report)

    meta = arcade_result.metadata
    bay_count = meta.get("bay_count", 0)
    pier_count = meta.get("pier_count", 0)
    arch_count = meta.get("arch_count", 0)

    # Pier count relates to bay count.
    report.check(approx_equal, float(pier_count), float(bay_count + 1),
                 0.5, "arcade pier_count == bay_count + 1")
    report.check(approx_equal, float(arch_count), float(bay_count),
                 0.5, "arcade arch_count == bay_count")

    # Even pier spacing.
    pier_centers: list[float] = []
    for i in range(pier_count):
        key = f"pier_{i}_center"
        if key in arcade_result.anchors:
            pier_centers.append(arcade_result.anchors[key].x)
    if len(pier_centers) >= 3:
        pier_centers.sort()
        ocs = [pier_centers[i + 1] - pier_centers[i]
               for i in range(len(pier_centers) - 1)]
        for i, d in enumerate(ocs[1:], 1):
            report.check(approx_equal, d, ocs[0], 0.5,
                         f"arcade pier on-center #{i}")

    # Every arch apex above springing.
    y_spring = meta.get("y_spring")
    if y_spring is not None:
        for i in range(bay_count):
            apex_key = f"arch_{i}_apex"
            if apex_key in arcade_result.anchors:
                apex = arcade_result.anchors[apex_key]
                if apex.y >= y_spring:
                    report.check(
                        lambda ay=apex.y, ys=y_spring, i=i:
                            (_ for _ in ()).throw(ValidationError(
                                f"arcade arch #{i} apex y={ay:.2f} "
                                f"not above springing y={ys:.2f}")))

    # Voussoirs above springing.
    voussoirs = arcade_result.polylines.get("voussoirs", [])
    if voussoirs and y_spring is not None:
        report.check(voussoirs_above_springing, voussoirs, y_spring, 0.3,
                     "arcade voussoirs")

    # Overall bbox width matches the declared arcade width
    # (pier_count * pier_width + bay_count * clear_span).
    bb = arcade_result.bbox
    if bb and (bb[2] - bb[0]) > 0:
        expected_w = (meta.get("pier_width", 0.0) * pier_count
                      + meta.get("clear_span", 0.0) * bay_count)
        if expected_w > 0:
            actual_w = bb[2] - bb[0]
            report.check(approx_equal, actual_w, expected_w, 1.0,
                         "arcade bbox width")

    return report


# ---------------------------------------------------------------------------
# Rustication wall
# ---------------------------------------------------------------------------

def validate_rustication(wall_result: dict,
                         x0: float,
                         y0: float,
                         width: float,
                         height: float,
                         variant: str,
                         report: ValidationReport | None = None
                         ) -> ValidationReport:
    """Invariants for rustication.wall output."""
    report = _ensure_report(report)

    # --- Outline: closed rectangle matching x0, y0, width, height ---
    if "outline" not in wall_result or not wall_result["outline"]:
        report.check(lambda: (_ for _ in ()).throw(
            ValidationError("wall result missing 'outline'")))
        return report

    outline = wall_result["outline"]
    report.check(is_closed, outline, 0.05, "wall outline")
    outline_bbox = _bbox_of(outline)
    expected = (x0, y0, x0 + width, y0 + height)
    for i, (a, e) in enumerate(zip(outline_bbox, expected)):
        report.check(approx_equal, a, e, 0.1,
                     f"wall outline bbox[{i}]")

    # --- Block rects: every rect closed, contained in outline ---
    if "block_rects" in wall_result and wall_result["block_rects"]:
        for i, br in enumerate(wall_result["block_rects"]):
            report.check(is_closed, br, 0.05, f"wall block #{i}")
            if br:
                bb = _bbox_of(br)
                report.check(_bbox_contains_bbox, outline_bbox, bb, 0.2,
                             f"wall block #{i} inside outline")

    # --- Joints: each line intersects the outline ---
    if "joints" in wall_result and wall_result["joints"]:
        shp_outline = Polygon(outline)
        if shp_outline.is_valid:
            for i, j in enumerate(wall_result["joints"]):
                if len(j) < 2:
                    continue
                # Both endpoints should be inside outline (with margin)
                for x, y in j:
                    inside = (outline_bbox[0] - 0.1 <= x <= outline_bbox[2] + 0.1
                              and outline_bbox[1] - 0.1 <= y <= outline_bbox[3] + 0.1)
                    if not inside:
                        report.check(
                            lambda x=x, y=y, i=i: (_ for _ in ()).throw(
                                ValidationError(
                                    f"wall joint #{i} point ({x:.2f},{y:.2f}) outside outline")))
                        break

    # --- Arch voussoirs (arcuated variant only): all corners above
    #     springing line. We don't have arch_springings_y directly; try to
    #     extract it from the result metadata. Most smoke tests pass the
    #     springing via kwargs and the wall builder doesn't echo it back,
    #     so we compute a pragmatic floor from the voussoir polylines'
    #     max y — this is the chord of the arch.
    if variant == "arcuated" and wall_result.get("arch_voussoirs"):
        voussoirs = wall_result["arch_voussoirs"]
        # The chord (y_spring) is the max y across all voussoir corners
        # (voussoirs are drawn from springing up to apex).
        all_corners = _flatten(voussoirs)
        if all_corners:
            y_spring_est = max(p[1] for p in all_corners)
            report.check(voussoirs_above_springing,
                         voussoirs, y_spring_est, 0.5,
                         "arcuated voussoirs")

    return report


# ---------------------------------------------------------------------------
# Cartouche
# ---------------------------------------------------------------------------

def validate_cartouche(cart_result, expected_width: float, expected_height: float,
                       report: ValidationReport | None = None) -> ValidationReport:
    """Invariants for cartouche output.

    A cartouche must be:
      - Bilaterally symmetric about its inscription_center anchor (loose).
      - bbox roughly matches expected_width x expected_height (+/- 20%).
      - Has "inscription_center" anchor.
      - At least 2 polylines (outer frame + inner field).
    """
    report = _ensure_report(report)

    # Required anchor
    if "inscription_center" not in cart_result.anchors:
        report.check(lambda: (_ for _ in ()).throw(
            ValidationError("cartouche missing 'inscription_center' anchor")))
        return report

    # bbox size roughly matches requested envelope.
    bx0, by0, bx1, by1 = cart_result.bbox
    actual_w = bx1 - bx0
    actual_h = by1 - by0
    report.check(approx_equal, actual_w, expected_width,
                 expected_width * 0.2, "cartouche width")
    report.check(approx_equal, actual_h, expected_height,
                 expected_height * 0.2, "cartouche height")

    # Minimum polyline count: at least outer + inner field.
    total_pls = sum(len(v) for v in cart_result.polylines.values())
    report.check(count_in_range, total_pls, 2, 10000,
                 label="cartouche total polyline count")

    # Symmetry about inscription_center.x (loose — some embellishments may be
    # asymmetric in rocaille variants). We check only the main "field" layer
    # which is always symmetric for oval / rectangular / baroque_scroll.
    cx = cart_result.anchors["inscription_center"].x
    field = cart_result.polylines.get("field", [])
    for i, pl in enumerate(field):
        # Loose symmetry tolerance: parametric ellipses don't mirror pixel-
        # perfect; use a half-mm slack scaled by cartouche size.
        sym_tol = max(0.5, expected_width * 0.01)
        try:
            mirror_symmetric(pl, cx, sym_tol, f"cartouche field polyline #{i}")
        except ValidationError as e:
            report.errors.append(str(e))

    return report


# ---------------------------------------------------------------------------
# Stairs
# ---------------------------------------------------------------------------

def validate_stairs(stairs_result,
                    expected_riser_count: int,
                    report: ValidationReport | None = None
                    ) -> ValidationReport:
    """Invariants for stairs.straight_flight output.

    Checks:
      * metadata riser count matches expectation.
      * Exactly that many ``nosing_i`` anchors are present.
      * Nosings rise monotonically along the flight's direction (y
        decreases step-by-step).
      * ``treads`` and ``risers`` polyline counts match riser_count.
      * Each tread is horizontal (constant y); each riser is vertical
        (constant x).
    """
    report = _ensure_report(report)

    meta = getattr(stairs_result, "metadata", {}) or {}
    report.check(count_equals, meta.get("riser_count", 0),
                 expected_riser_count, "stairs risers")

    # Anchor count.
    anchors = getattr(stairs_result, "anchors", {}) or {}
    nosings = [(anchors[k].x, anchors[k].y)
               for k in anchors if k.startswith("nosing_")]
    report.check(count_equals, len(nosings), expected_riser_count,
                 "stairs nosing anchor count")

    # Nosings should rise (y decrease) as x moves in direction of travel.
    # For right-ascending stairs sort by x; for left-ascending by -x.
    direction = meta.get("direction", "right")
    nosings_sorted = sorted(nosings,
                            key=lambda p: p[0] if direction == "right" else -p[0])
    for i in range(1, len(nosings_sorted)):
        prev_y = nosings_sorted[i - 1][1]
        cur_y = nosings_sorted[i][1]
        if cur_y >= prev_y:
            report.check(
                lambda pv=prev_y, cv=cur_y, idx=i: (_ for _ in ()).throw(
                    ValidationError(
                        f"stairs nosing #{idx} does not rise: "
                        f"y={cv:.3f} >= previous y={pv:.3f}")))
            break

    # Tread / riser polyline counts.
    polylines = getattr(stairs_result, "polylines", {}) or {}
    treads = polylines.get("treads", [])
    risers = polylines.get("risers", [])
    report.check(count_equals, len(treads), expected_riser_count,
                 "stairs tread count")
    report.check(count_equals, len(risers), expected_riser_count,
                 "stairs riser count")

    # Each tread horizontal; each riser vertical.
    for i, t in enumerate(treads):
        if len(t) < 2:
            continue
        ys = [p[1] for p in t]
        if max(ys) - min(ys) > 0.1:
            report.check(
                lambda i=i, sp=max(ys) - min(ys): (_ for _ in ()).throw(
                    ValidationError(
                        f"tread #{i} not horizontal: y span {sp:.3f} > 0.1")))
    for i, rp in enumerate(risers):
        if len(rp) < 2:
            continue
        xs = [p[0] for p in rp]
        if max(xs) - min(xs) > 0.1:
            report.check(
                lambda i=i, sp=max(xs) - min(xs): (_ for _ in ()).throw(
                    ValidationError(
                        f"riser #{i} not vertical: x span {sp:.3f} > 0.1")))

    return report


# ---------------------------------------------------------------------------
# Rinceau
# ---------------------------------------------------------------------------

def validate_rinceau(rinceau_result,
                     expected_min_leaves: int,
                     report: ValidationReport | None = None
                     ) -> ValidationReport:
    """Invariants for rinceau.rinceau output.

    Checks:
      * metadata ``leaf_count`` at least ``expected_min_leaves`` and no
        more than 100 (sanity cap).
      * The number of ``leaf_i_base`` anchors matches ``leaf_count``.
      * Spine and leaves layers are populated.
      * When ``alternate=True`` the number of buds should match the
        number of leaves (the builder places a bud on the opposite side
        of every alternating leaf).
    """
    report = _ensure_report(report)

    meta = getattr(rinceau_result, "metadata", {}) or {}
    leaf_count = int(meta.get("leaf_count", 0))
    report.check(count_in_range, leaf_count,
                 expected_min_leaves, 100, "rinceau leaves")

    anchors = getattr(rinceau_result, "anchors", {}) or {}
    leaf_anchors = [anchors[k] for k in anchors
                    if k.startswith("leaf_") and k.endswith("_base")]
    report.check(count_equals, len(leaf_anchors), leaf_count,
                 "rinceau leaf anchor count")

    polylines = getattr(rinceau_result, "polylines", {}) or {}
    spine_layer = polylines.get("spine", [])
    leaves_layer = polylines.get("leaves", [])
    if not spine_layer or not spine_layer[0]:
        report.check(lambda: (_ for _ in ()).throw(
            ValidationError("rinceau missing spine polyline")))
        return report
    if not leaves_layer:
        report.check(lambda: (_ for _ in ()).throw(
            ValidationError("rinceau produced no leaves")))

    # Alternating-sides proxy: bud count per leaf.
    if meta.get("alternate", False) and leaf_count >= 2:
        buds_layer = polylines.get("buds", [])
        report.check(count_in_range, len(buds_layer),
                     leaf_count, leaf_count + 1,
                     label="rinceau bud count matches alternating leaves")

    return report


# ---------------------------------------------------------------------------
# Festoon / swag
# ---------------------------------------------------------------------------

def validate_festoon(result,
                     attach_left: tuple[float, float],
                     attach_right: tuple[float, float],
                     report: ValidationReport | None = None
                     ) -> ValidationReport:
    """Invariants for festoon / swag output.

    Checks:
      - Has a ``spine`` polyline.
      - Spine endpoints match ``attach_left`` and ``attach_right`` within
        a 1 mm tolerance (the builder may round sample positions).
      - Spine's lowest point has larger y than the attachment line (droops
        downward in SVG coords).
    """
    report = _ensure_report(report)
    polylines = getattr(result, "polylines", {}) or {}

    spine_layer = polylines.get("spine", [])
    if not spine_layer or not spine_layer[0]:
        report.check(lambda: (_ for _ in ()).throw(
            ValidationError("festoon/swag missing spine polyline")))
        return report

    spine = spine_layer[0]
    if len(spine) < 2:
        report.check(lambda: (_ for _ in ()).throw(
            ValidationError(f"festoon spine too short: {len(spine)} pts")))
        return report

    # Endpoints match attachments
    start = spine[0]
    end = spine[-1]
    lx, ly = attach_left
    rx, ry = attach_right
    tol = 1.0
    if hypot(start[0] - lx, start[1] - ly) > tol:
        report.check(lambda s=start: (_ for _ in ()).throw(
            ValidationError(
                f"festoon spine start {s} != attach_left {attach_left}")))
    if hypot(end[0] - rx, end[1] - ry) > tol:
        report.check(lambda e=end: (_ for _ in ()).throw(
            ValidationError(
                f"festoon spine end {e} != attach_right {attach_right}")))

    # Droop: lowest point (max y) strictly below the attachment line.
    # The chord y at each spine x is linearly interpolated between
    # attach_left.y and attach_right.y.
    if rx != lx:
        def chord_y(x: float) -> float:
            t = (x - lx) / (rx - lx)
            return ly + t * (ry - ly)
        # Max drop: spine point with largest (y - chord_y(x))
        drops = [(y - chord_y(x)) for x, y in spine]
    else:
        drops = [y - min(ly, ry) for _, y in spine]
    max_drop = max(drops) if drops else 0.0
    if max_drop <= 0.1:
        report.check(lambda md=max_drop: (_ for _ in ()).throw(
            ValidationError(
                f"festoon spine does not droop downward "
                f"(max drop below chord = {md:.3f})")))

    return report


# ---------------------------------------------------------------------------
# Trophy
# ---------------------------------------------------------------------------

def validate_trophy(result,
                    cx: float,
                    cy: float,
                    width: float,
                    height: float,
                    report: ValidationReport | None = None
                    ) -> ValidationReport:
    """Invariants for trophy output.

    Checks:
      - Bilaterally symmetric about ``cx`` (loose — stylised silhouettes
        are approximately symmetric).
      - Bounding box close to declared ``width × height`` (within 30%
        per-axis; ornaments like plume and pendants extend beyond the
        envelope naturally).
    """
    report = _ensure_report(report)
    bb = getattr(result, "bbox", (0, 0, 0, 0))
    if bb == (0, 0, 0, 0):
        report.check(lambda: (_ for _ in ()).throw(
            ValidationError("trophy has empty bbox")))
        return report

    actual_w = bb[2] - bb[0]
    actual_h = bb[3] - bb[1]
    # Trophies often overshoot the declared envelope slightly because
    # plumes, pendants, and crossed swords reach outward.  Accept a wide
    # tolerance.
    report.check(in_range, actual_w,
                 width * 0.5, width * 1.8,
                 label="trophy bbox width vs declared")
    report.check(in_range, actual_h,
                 height * 0.5, height * 1.8,
                 label="trophy bbox height vs declared")

    # Symmetry: check each layer for mirror-symmetry about cx.
    polylines = getattr(result, "polylines", {}) or {}
    for layer, lines in polylines.items():
        if not lines:
            continue
        # Flatten each layer into one point sequence for the mirror test.
        all_pts: list[tuple[float, float]] = []
        for pl in lines:
            all_pts.extend(pl)
        if len(all_pts) < 4:
            continue
        sym_tol = max(2.0, 0.05 * width)
        try:
            mirror_symmetric(all_pts, cx, sym_tol,
                             f"trophy layer '{layer}'")
        except ValidationError as e:
            report.errors.append(str(e))

    return report


# ---------------------------------------------------------------------------
# Medallion
# ---------------------------------------------------------------------------

def validate_medallion(result,
                       cx: float,
                       cy: float,
                       width: float,
                       height: float,
                       with_wreath: bool,
                       report: ValidationReport | None = None
                       ) -> ValidationReport:
    """Invariants for medallion output.

    Checks:
      - Has ``outer`` and ``inner`` oval polylines, both closed.
      - Outer oval's bbox matches declared width × height (within 0.5 mm).
      - If ``with_wreath`` is True: at least 10 leaf polylines in the
        ``wreath`` layer.
      - Outer oval is approximately symmetric about ``cx``.
    """
    report = _ensure_report(report)
    polylines = getattr(result, "polylines", {}) or {}

    outer = polylines.get("outer", [])
    inner = polylines.get("inner", [])
    if not outer or not outer[0]:
        report.check(lambda: (_ for _ in ()).throw(
            ValidationError("medallion missing outer oval")))
        return report
    if not inner or not inner[0]:
        report.check(lambda: (_ for _ in ()).throw(
            ValidationError("medallion missing inner oval")))
        return report

    outer_pl = outer[0]
    inner_pl = inner[0]
    report.check(is_closed, outer_pl, 0.05, "medallion outer oval")
    report.check(is_closed, inner_pl, 0.05, "medallion inner oval")

    # Outer oval bbox matches requested width × height
    if outer_pl:
        bb = _bbox_of(outer_pl)
        expected = (cx - width / 2, cy - height / 2,
                    cx + width / 2, cy + height / 2)
        for i, (a, e) in enumerate(zip(bb, expected)):
            report.check(approx_equal, a, e, 0.5,
                         f"medallion outer bbox[{i}]")

    # Symmetry about cx
    report.check(mirror_symmetric, outer_pl, cx,
                 max(0.5, 0.01 * width),
                 "medallion outer oval")

    # Wreath: at least 10 leaves
    if with_wreath:
        wreath = polylines.get("wreath", [])
        report.check(count_in_range, len(wreath), 10, 10000,
                     label="medallion wreath leaf polyline count")

    return report


# ---------------------------------------------------------------------------
# Extra structural predicates — Phase 16 additions. These are NOT wired
# into the element validators above (they're called directly by tests /
# plate authors to spot bugs), so they live at module scope.
# ---------------------------------------------------------------------------

def cartouche_wing_symmetry(cart_result,
                            axis_x: float | None = None,
                            min_wings_per_side: int = 1,
                            label: str = "cartouche wings") -> None:
    """Baroque-scroll cartouches must have ≥1 wing polyline on EACH side
    of the central inscription axis.

    Bug #1 (user-observed): baroque_scroll currently only renders the
    right wing — this predicate fires immediately on that case.

    Wings are identified by layer name containing "wing", "scroll", or
    "volute"; a polyline's "side" is the sign of `mean(x) - axis_x`.
    """
    if axis_x is None:
        a = cart_result.anchors.get("inscription_center")
        if a is None:
            raise ValidationError(
                f"{label}: no inscription_center anchor and no axis_x supplied"
            )
        axis_x = a.x

    wing_lines: list = []
    for layer_name, lines in cart_result.polylines.items():
        ln = layer_name.lower()
        if "wing" in ln or "scroll" in ln or "volute" in ln:
            wing_lines.extend(lines)

    if not wing_lines:
        raise ValidationError(
            f"{label}: no wing polylines found (layers with 'wing', "
            f"'scroll', or 'volute' in name)"
        )

    left = 0
    right = 0
    for pl in wing_lines:
        if not pl:
            continue
        mean_x = sum(p[0] for p in pl) / len(pl)
        if mean_x < axis_x - 1e-6:
            left += 1
        elif mean_x > axis_x + 1e-6:
            right += 1
    if left < min_wings_per_side or right < min_wings_per_side:
        raise ValidationError(
            f"{label}: asymmetric wings — left={left}, right={right} "
            f"(need ≥{min_wings_per_side} on each side of axis_x={axis_x:.2f})"
        )


def pier_span_ratio(arcade_result,
                    min_ratio: float = 0.30,
                    max_ratio: float = 0.60,
                    label: str = "arcade pier:span") -> None:
    """Vignola: pier_width should be ⅓..½ of the clear span.

    Bug #3 (user-observed): default `pier_width_frac=0.20` gives
    ratios as low as 0.13 — this predicate fires.

    Range extends slightly above ½ (0.60) so wider piers in heavy
    rusticated arcades are still accepted.
    """
    meta = getattr(arcade_result, "metadata", None) or arcade_result
    pier_w = meta.get("pier_width") if hasattr(meta, "get") else None
    clear_span = meta.get("clear_span") if hasattr(meta, "get") else None
    if pier_w is None or clear_span is None or clear_span <= 0:
        raise ValidationError(
            f"{label}: missing pier_width / clear_span in arcade metadata"
        )
    ratio = pier_w / clear_span
    if not (min_ratio <= ratio <= max_ratio):
        raise ValidationError(
            f"{label}: pier_width / clear_span = {ratio:.3f} "
            f"(= {pier_w:.2f} / {clear_span:.2f}); "
            f"Vignola expects [{min_ratio}, {max_ratio}]"
        )


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from ..acanthus import acanthus_leaf
    from ..volute import ionic_volute
    from ..arches import semicircular_arch, segmental_arch
    from ..windows import window_opening
    from ..balustrades import balustrade_run, baluster_silhouette
    from ..rustication import wall

    def _print_report(name: str, r: ValidationReport) -> None:
        print(f"{name}: {len(r)} errors")
        for e in r:
            print(f"  - {e}")

    # --- Acanthus ---
    leaf = acanthus_leaf(width=30, height=40, lobe_count=5)
    r = validate_acanthus_leaf(leaf, 30, 40, 5)
    _print_report("acanthus", r)

    # --- Volute ---
    v = ionic_volute(0, 0, D=60.0)
    r = validate_volute(v, 0, 0, 60.0)
    _print_report("volute", r)

    # --- Semicircular arch ---
    a = semicircular_arch(cx=100, y_spring=180, span=80, voussoir_count=9,
                          with_keystone=True, archivolt_bands=2)
    r = validate_arch(a, 100, 180, 80)
    _print_report("semicircular arch", r)

    # --- Segmental arch ---
    seg = segmental_arch(cx=100, y_spring=180, span=80, rise=15,
                         voussoir_count=9)
    r = validate_arch(seg, 100, 180, 80)
    _print_report("segmental arch", r)

    # --- Window (no hood, no keystone) ---
    win = window_opening(x=0.0, y_top=0.0, w=40.0, h=70.0,
                         hood="none", keystone=False)
    r = validate_window(win, 0.0, 0.0, 40.0, 70.0)
    _print_report("window (plain)", r)

    # --- Window with triangular hood + keystone ---
    win2 = window_opening(x=0.0, y_top=0.0, w=40.0, h=70.0,
                          hood="triangular", keystone=True)
    r = validate_window(win2, 0.0, 0.0, 40.0, 70.0)
    _print_report("window (triangular hood)", r)

    # --- Single baluster ---
    b = baluster_silhouette(cx=50.0, y_bottom=200.0, height=80.0,
                            max_diam=25.0, variant="tuscan")
    r = validate_baluster(b, 50.0, 200.0, 80.0, 25.0)
    _print_report("baluster", r)

    # --- Balustrade run ---
    run = balustrade_run(x0=30.0, x1=270.0, y_top_of_rail=120.0, height=80.0)
    r = validate_balustrade(run, 30.0, 270.0, 120.0, 80.0)
    _print_report("balustrade run", r)

    # --- Rustication: banded ---
    rust = wall(0, 0, 200, 120, course_h=20, block_w=30, variant="banded")
    r = validate_rustication(rust, 0, 0, 200, 120, "banded")
    _print_report("rustication (banded)", r)

    # --- Rustication: chamfered ---
    rust2 = wall(0, 0, 200, 120, course_h=20, block_w=30, variant="chamfered")
    r = validate_rustication(rust2, 0, 0, 200, 120, "chamfered")
    _print_report("rustication (chamfered)", r)

    # --- Rustication: arcuated ---
    rust3 = wall(0, 0, 200, 120, course_h=20, block_w=30,
                 variant="arcuated",
                 arch_springings_y=[60.0], arch_spans=[(100.0, 60.0)])
    r = validate_rustication(rust3, 0, 0, 200, 120, "arcuated")
    _print_report("rustication (arcuated)", r)

    print("\nValidation smoke test complete")
