"""Facade composition validators — structural rules over the rendered facade dict.

Hierarchical architectural rules after Ware's *American Vignola* and the
classical tradition: rustication belongs on the ground floor, openings must
clear wall blocks, pilasters must align with the story order, etc. These
validators light up bugs in the facade rendering pipeline without fixing
them — Phase 6 handles fixes.

Usage
-----
    from engraving.validate.composition import validate_facade_render
    f = facade.Facade(...)
    f.layout()
    result = f.render()
    report = validate_facade_render(f, result)
    if report.errors:
        print("Validation errors:")
        for e in report:
            print(f"  - {e}")

Two entry points:
  * ``validate_facade_composition`` — pre-render checks on the spec.
  * ``validate_facade_render``      — post-render checks on the output dict.
"""
from __future__ import annotations

from typing import Any

from shapely.geometry import box as shp_box

from ..facade import Bay, Facade, Opening, Story
from ..schema import BBox, ElementResult
from . import (ValidationReport, aligned_vertical, approx_equal, contained,
               opening_cleared_from_wall, voussoirs_above_springing)


KNOWN_ORDERS = {"tuscan", "doric", "ionic", "corinthian", "composite"}
RUSTICATED_VARIANTS = {"arcuated", "vermiculated", "rock_faced", "chamfered"}


# ──────────────────────────────────────────────────────────────────────────
# Cross-order relative proportions
# ──────────────────────────────────────────────────────────────────────────
# Canonical column-height ratios (in column_D). Each pair is (a, b) with
# the expected ``column_h(a) / column_h(b)`` at matched D.
EXPECTED_HEIGHT_RATIOS: dict[tuple[str, str], float] = {
    ("doric", "tuscan"): 8.0 / 7.0,
    ("ionic", "doric"): 9.0 / 8.0,
    ("corinthian", "ionic"): 10.0 / 9.0,
    ("composite", "corinthian"): 1.0,
    ("composite", "ionic"): 10.0 / 9.0,
    ("doric", "greek_doric"): 8.0 / 5.5,
    ("ionic", "greek_ionic"): 1.0,
}


def _order_kind(result: ElementResult) -> str:
    """Strip the ``_column`` suffix from an ``ElementResult.kind``."""
    kind = result.kind or ""
    if kind.endswith("_column"):
        return kind[: -len("_column")]
    return kind


def validate_relative_column_heights(
        a_result: ElementResult,
        b_result: ElementResult,
        expected_ratio: float | None = None,
        tol: float = 0.05,
        report: ValidationReport | None = None,
) -> ValidationReport:
    """Cross-order proportion check.

    ``a_result`` and ``b_result`` must have been built with the SAME D.
    Their rendered ``column_h`` ratio should equal
    ``a.dims_ref.column_D / b.dims_ref.column_D`` (or an explicit
    ``expected_ratio`` if supplied).
    """
    if report is None:
        report = ValidationReport()

    a_kind = _order_kind(a_result)
    b_kind = _order_kind(b_result)

    if expected_ratio is None:
        a_dims = a_result.dims_ref
        b_dims = b_result.dims_ref
        if a_dims is None or b_dims is None:
            report.errors.append(
                f"orders {a_kind} and {b_kind} missing dims_ref — "
                f"relative-height comparison invalid"
            )
            return report
        if a_dims.D != b_dims.D:
            report.errors.append(
                f"orders {a_kind} (D={a_dims.D}) and {b_kind} (D={b_dims.D}) "
                f"have different D values — relative-height comparison invalid"
            )
            return report
        expected_ratio = a_dims.column_D / b_dims.column_D

    a_h = a_result.metadata.get("column_h")
    b_h = b_result.metadata.get("column_h")
    if a_h is None or b_h is None or b_h == 0:
        report.errors.append(
            f"orders {a_kind} and {b_kind} missing metadata.column_h — "
            f"relative-height comparison invalid"
        )
        return report

    actual_ratio = a_h / b_h
    report.check(approx_equal, actual_ratio, expected_ratio, tol,
                 label=f"{a_kind}/{b_kind} column_h ratio")
    return report


def validate_comparative_plate(
        order_results: list[ElementResult],
        report: ValidationReport | None = None,
) -> ValidationReport:
    """Validate a list of order results rendered side-by-side at the same D.

    All ``(a, b)`` pairs in :data:`EXPECTED_HEIGHT_RATIOS` whose order-kinds
    are present in ``order_results`` are checked. Results must share a common
    ``D``; a mixed-D plate is flagged as an error before per-pair checks run.
    """
    if report is None:
        report = ValidationReport()

    if not order_results:
        return report

    # Verify all use the same D.
    Ds = {r.dims_ref.D for r in order_results if r.dims_ref is not None}
    if len(Ds) > 1:
        report.errors.append(
            f"comparative plate has mixed D values: {sorted(Ds)}"
        )
        return report

    by_kind = {_order_kind(r): r for r in order_results}
    for (a_kind, b_kind), expected in EXPECTED_HEIGHT_RATIOS.items():
        if a_kind in by_kind and b_kind in by_kind:
            validate_relative_column_heights(
                by_kind[a_kind], by_kind[b_kind],
                expected_ratio=expected, tol=0.05, report=report,
            )
    return report


def validate_pediment_slope_angle(
        apex: tuple[float, float],
        left_spring: tuple[float, float],
        right_spring: tuple[float, float],
        lo_deg: float = 12.0,
        hi_deg: float = 15.0,
        tol_deg: float = 3.0,
        report: ValidationReport | None = None,
) -> ValidationReport:
    """Vignola/Palladio: classical pediment slope is 12–15°.

    Computes the rake slope from one springing anchor to the apex;
    requires symmetric slopes within ±0.5° (anything else indicates a
    skew in the pediment geometry). Flags the pediment if either slope
    falls outside ``[lo_deg - tol_deg, hi_deg + tol_deg]``.
    """
    import math as _math
    if report is None:
        report = ValidationReport()

    def _slope(sp):
        dx = abs(apex[0] - sp[0])
        dy = abs(apex[1] - sp[1])
        if dx == 0:
            return 90.0
        return _math.degrees(_math.atan2(dy, dx))

    left_slope = _slope(left_spring)
    right_slope = _slope(right_spring)

    if abs(left_slope - right_slope) > 0.5:
        report.errors.append(
            f"pediment slopes asymmetric: left={left_slope:.2f}° "
            f"vs right={right_slope:.2f}° (skew > 0.5°)"
        )

    mean_slope = 0.5 * (left_slope + right_slope)
    if not (lo_deg - tol_deg <= mean_slope <= hi_deg + tol_deg):
        report.errors.append(
            f"pediment slope {mean_slope:.2f}° outside canonical "
            f"[{lo_deg}°, {hi_deg}°] (±{tol_deg}° tolerance)"
        )
    return report


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

def _wall_variant(story: Story) -> str:
    """Return the rustication variant name for a Story.wall spec."""
    spec = story.wall
    if isinstance(spec, str):
        return spec
    return spec.get("variant", "smooth")


def _story_bounds(facade: Facade) -> list[tuple[float, float]]:
    """Mirror Facade.render()'s story-bounds computation: bottom-up, y shrinks.

    Returns a list of ``(y_bot, y_top)`` with ``y_bot > y_top`` (SVG coords).
    """
    bounds: list[tuple[float, float]] = []
    y_cursor = facade.base_y
    for story in facade.stories:
        y_bot = y_cursor
        y_top = y_cursor - story.height
        bounds.append((y_bot, y_top))
        y_cursor = y_top
    return bounds


def _opening_bbox(op: Opening, axis_x: float, y_bot: float,
                  story_h: float) -> BBox | None:
    """Approximate the opening's rendered bbox using the same math as
    ``facade._opening_footprint`` (minus halo padding).

    Returned as (x_min, y_min, x_max, y_max) with y increasing downward.
    """
    if op.kind == "blank":
        return None

    half = op.width / 2.0
    if op.kind in ("window", "door", "niche"):
        sill_margin = story_h * 0.08
        y_opening_bot = y_bot - sill_margin
        y_opening_top = y_opening_bot - op.height
        return (axis_x - half, y_opening_top, axis_x + half, y_opening_bot)

    if op.kind in ("arch_window", "arch_door"):
        sill_margin = story_h * 0.04 if op.kind == "arch_door" else story_h * 0.10
        y_opening_bot = y_bot - sill_margin
        y_spring = y_opening_bot - op.height
        # Semicircular apex sits ``half`` above the springing.
        y_apex = y_spring - half
        return (axis_x - half, y_apex, axis_x + half, y_opening_bot)

    return None


# ──────────────────────────────────────────────────────────────────────────
# Story-level rules
# ──────────────────────────────────────────────────────────────────────────

def validate_story_layout(facade: Facade, report: ValidationReport) -> None:
    """Heights positive, orders valid, rustication on ground only, piano
    nobile conventions."""
    if not facade.stories:
        report.errors.append("facade has no stories")
        return

    for i, story in enumerate(facade.stories):
        if story.height <= 0:
            report.errors.append(
                f"story[{i}] has non-positive height {story.height}"
            )
        if story.has_order and story.has_order not in KNOWN_ORDERS:
            report.errors.append(
                f"story[{i}].has_order '{story.has_order}' not recognised "
                f"(known: {sorted(KNOWN_ORDERS)})"
            )
        variant = _wall_variant(story)
        if variant in RUSTICATED_VARIANTS and i != 0:
            report.errors.append(
                f"story[{i}] uses rusticated variant '{variant}' but is not "
                f"the ground floor (convention: rustication is ground-only)"
            )

    # Piano nobile convention: the ordered story SHOULD NOT be the top story
    # and SHOULD be among the tallest.
    ordered_indices = [i for i, s in enumerate(facade.stories) if s.has_order]
    if ordered_indices:
        top_index = len(facade.stories) - 1
        heights = [s.height for s in facade.stories]
        max_h = max(heights)
        for oi in ordered_indices:
            if oi == top_index and len(facade.stories) > 1:
                report.errors.append(
                    f"story[{oi}] is the ordered (piano nobile) story but is "
                    f"also the top story (convention: piano nobile is not at top)"
                )
            # "Among the tallest": within 20% of the max height.
            if facade.stories[oi].height < max_h * 0.8:
                report.errors.append(
                    f"story[{oi}] is the ordered (piano nobile) story but "
                    f"height {facade.stories[oi].height} is well below the "
                    f"tallest story ({max_h}); piano nobile should be tallest"
                )


# ──────────────────────────────────────────────────────────────────────────
# Bay-level rules
# ──────────────────────────────────────────────────────────────────────────

def validate_bay_layout(facade: Facade, report: ValidationReport) -> None:
    """Every bay has one opening per story, bays are left-to-right, axes
    within the facade width."""
    n_stories = len(facade.stories)
    for i, bay in enumerate(facade.bays):
        if len(bay.openings) != n_stories:
            report.errors.append(
                f"bay[{i}] has {len(bay.openings)} openings; expected {n_stories}"
            )
        if bay.pilaster_order and bay.pilaster_order not in KNOWN_ORDERS:
            report.errors.append(
                f"bay[{i}].pilaster_order '{bay.pilaster_order}' not recognised"
            )

    axes = [b.axis_x for b in facade.bays]
    if axes != sorted(axes):
        report.errors.append(f"bay axes not left-to-right monotonic: {axes}")

    # Axes within the facade's usable width (with margins).
    margin = facade.width * facade.margin_frac
    for i, bay in enumerate(facade.bays):
        if bay.axis_x < margin - 0.5 or bay.axis_x > facade.width - margin + 0.5:
            report.errors.append(
                f"bay[{i}] axis_x={bay.axis_x:.2f} outside usable range "
                f"[{margin:.2f}, {facade.width - margin:.2f}]"
            )

    # Opening hierarchy: widths should DESCEND going up (ground widest,
    # upper story smallest). Classical Vignola/Palladio convention.
    # A ~2x spread is expected and correct; don't flag it. Only flag
    # when an upper story is WIDER than a lower story, which is a bug.
    for i, bay in enumerate(facade.bays):
        widths = [op.width for op in bay.openings
                  if op.kind != "blank" and op.width > 0]
        if len(widths) < 2:
            continue
        for k in range(1, len(widths)):
            if widths[k] > widths[k - 1] + 0.5:  # upper wider than lower
                report.errors.append(
                    f"bay[{i}] story[{k}] opening width {widths[k]:.1f} > "
                    f"story[{k-1}] width {widths[k-1]:.1f} — upper openings "
                    f"should be narrower than lower (classical hierarchy)"
                )


def validate_pilaster_order_match(facade: Facade,
                                  report: ValidationReport) -> None:
    """A bay's pilaster_order must match any story's has_order (no Ionic
    pilasters on a Corinthian story)."""
    for si, story in enumerate(facade.stories):
        if not story.has_order:
            continue
        for bi, bay in enumerate(facade.bays):
            if bay.pilaster_order and bay.pilaster_order != story.has_order:
                report.errors.append(
                    f"bay[{bi}] pilaster_order '{bay.pilaster_order}' does not "
                    f"match story[{si}] order '{story.has_order}'"
                )


def validate_arched_openings_in_arcuated_stories(facade: Facade,
                                                 report: ValidationReport) -> None:
    """arch_window/arch_door openings belong in an arcuated (or otherwise
    arch-marked) story."""
    for si, story in enumerate(facade.stories):
        variant = _wall_variant(story)
        for bi, bay in enumerate(facade.bays):
            if si >= len(bay.openings):
                continue
            op = bay.openings[si]
            if op.kind in ("arch_window", "arch_door") and variant != "arcuated":
                report.errors.append(
                    f"bay[{bi}] story[{si}] has arched opening '{op.kind}' but "
                    f"story wall variant is '{variant}' (expected 'arcuated')"
                )


# ──────────────────────────────────────────────────────────────────────────
# Wall / render-level rules
# ──────────────────────────────────────────────────────────────────────────

def validate_wall_clips_openings(facade: Facade, render_result: dict,
                                 report: ValidationReport) -> None:
    """wall_blocks must not intersect opening interiors (clip step's job).

    For each (story, bay) with a non-blank opening, estimate the opening's
    bbox from ``(bay.axis_x, story_bounds[si], opening.width, opening.height)``
    and run ``opening_cleared_from_wall`` against wall_blocks whose polylines
    lie in this story's y-range.
    """
    layers = render_result.get("layers", {})
    wall_blocks = layers.get("wall_blocks", {}).get("polylines", [])
    if not wall_blocks:
        return  # smooth walls only — nothing to validate

    bounds = _story_bounds(facade)

    for si, story in enumerate(facade.stories):
        y_bot, y_top = bounds[si]
        story_h = y_bot - y_top
        # wall_blocks for this story: any polyline with at least one point in
        # the half-open y range (y_top ≤ y ≤ y_bot + tiny slop).
        slop = 0.5
        story_blocks: list[list] = []
        for bp in wall_blocks:
            if not bp:
                continue
            ys = [p[1] for p in bp]
            if min(ys) <= y_bot + slop and max(ys) >= y_top - slop:
                # This polyline intersects this story's vertical band.
                story_blocks.append(bp)
        if not story_blocks:
            continue

        for bi, bay in enumerate(facade.bays):
            if si >= len(bay.openings):
                continue
            op = bay.openings[si]
            if op.kind == "blank":
                continue
            obbox = _opening_bbox(op, bay.axis_x, y_bot, story_h)
            if obbox is None:
                continue
            # Shrink the opening slightly to avoid counting blocks that merely
            # kiss the opening edge (from rusticated jamb detail).
            x0, y0, x1, y1 = obbox
            shrink = min(1.0, op.width * 0.05)
            inner = (x0 + shrink, y0 + shrink, x1 - shrink, y1 - shrink)
            if inner[0] >= inner[2] or inner[1] >= inner[3]:
                continue
            report.check(
                opening_cleared_from_wall,
                inner, story_blocks,
                label=f"story[{si}] bay[{bi}] opening",
            )


def validate_joints_clip_openings(facade: Facade, render_result: dict,
                                  report: ValidationReport) -> None:
    """wall_joints must not cross opening interiors."""
    from shapely.geometry import LineString
    layers = render_result.get("layers", {})
    joints = layers.get("wall_joints", {}).get("polylines", [])
    if not joints:
        return

    bounds = _story_bounds(facade)

    for si, story in enumerate(facade.stories):
        y_bot, y_top = bounds[si]
        story_h = y_bot - y_top
        for bi, bay in enumerate(facade.bays):
            if si >= len(bay.openings):
                continue
            op = bay.openings[si]
            if op.kind == "blank":
                continue
            obbox = _opening_bbox(op, bay.axis_x, y_bot, story_h)
            if obbox is None:
                continue
            x0, y0, x1, y1 = obbox
            shrink = min(1.0, op.width * 0.05)
            inner_bbox = (x0 + shrink, y0 + shrink, x1 - shrink, y1 - shrink)
            if inner_bbox[0] >= inner_bbox[2] or inner_bbox[1] >= inner_bbox[3]:
                continue
            opening_rect = shp_box(*inner_bbox)
            offenders = 0
            for jp in joints:
                if len(jp) < 2:
                    continue
                try:
                    line = LineString(jp)
                except Exception:
                    continue
                if not line.intersects(opening_rect):
                    continue
                inter = line.intersection(opening_rect)
                # Allow tiny kisses at the edges; count real crossings.
                if getattr(inter, "length", 0.0) > 0.5:
                    offenders += 1
            if offenders:
                report.errors.append(
                    f"story[{si}] bay[{bi}] opening has {offenders} wall_joint "
                    f"line(s) crossing its interior"
                )


def validate_smooth_walls_have_no_blocks(facade: Facade, render_result: dict,
                                         report: ValidationReport) -> None:
    """Smooth stories should emit only the outer wall rectangle — no block
    grid in their y-range."""
    layers = render_result.get("layers", {})
    wall_blocks = layers.get("wall_blocks", {}).get("polylines", [])
    if not wall_blocks:
        return
    bounds = _story_bounds(facade)
    for si, story in enumerate(facade.stories):
        if _wall_variant(story) != "smooth":
            continue
        y_bot, y_top = bounds[si]
        # Any block whose ys lie entirely within this smooth story is a bug.
        for bp in wall_blocks:
            if not bp:
                continue
            ys = [p[1] for p in bp]
            if min(ys) >= y_top - 0.5 and max(ys) <= y_bot + 0.5:
                report.errors.append(
                    f"story[{si}] is smooth but wall_blocks contains a "
                    f"polyline within its y-range [{y_top:.1f}, {y_bot:.1f}]"
                )
                break  # one report per story is enough


def validate_voussoirs(facade: Facade, render_result: dict,
                       report: ValidationReport) -> None:
    """Every voussoir corner must sit at or above its arch's springing line
    (SVG: y ≤ y_spring)."""
    layers = render_result.get("layers", {})
    wall_vous = layers.get("wall_voussoirs", {}).get("polylines", [])
    if not wall_vous:
        return

    bounds = _story_bounds(facade)
    for si, story in enumerate(facade.stories):
        if _wall_variant(story) != "arcuated":
            continue
        y_bot, y_top = bounds[si]
        story_h = y_bot - y_top
        # Compute a springing estimate per bay by mirroring facade._opening_footprint.
        # The worst springing (highest y, i.e. deepest) bounds what voussoirs
        # can legally occupy.
        springings: list[float] = []
        for bay in facade.bays:
            if si >= len(bay.openings):
                continue
            op = bay.openings[si]
            if op.kind not in ("arch_window", "arch_door"):
                continue
            sill_margin = story_h * 0.04 if op.kind == "arch_door" else story_h * 0.10
            y_opening_bot = y_bot - sill_margin
            y_spring = y_opening_bot - op.height
            springings.append(y_spring)
        if not springings:
            continue
        # Restrict check to voussoir polylines within this story's band.
        story_vous = []
        for vp in wall_vous:
            if not vp:
                continue
            ys = [p[1] for p in vp]
            if min(ys) >= y_top - 1.0 and max(ys) <= y_bot + 1.0:
                story_vous.append(vp)
        if not story_vous:
            continue
        # A voussoir is above-spring if ALL its points have y ≤ y_spring_worst.
        # Use the deepest (largest) springing, so a voussoir below that is a bug.
        y_spring_worst = max(springings)
        report.check(
            voussoirs_above_springing,
            story_vous, y_spring_worst, tol=2.0,
            label=f"story[{si}] wall_voussoirs",
        )


def validate_string_courses(facade: Facade, render_result: dict,
                            report: ValidationReport) -> None:
    """At least N-1 string courses for N stories (minus any with
    string_course_height == 0)."""
    layers = render_result.get("layers", {})
    courses = layers.get("string_courses", {}).get("polylines", [])
    # Each course emits 2 polylines (outline + rule). Count *entries* instead.
    entries = layers.get("string_courses", {}).get("entries", [])
    n_courses = len(entries) if entries else len(courses) // 2
    # Expected: one per upper story with nonzero height.
    expected = sum(1 for i, s in enumerate(facade.stories)
                   if i > 0 and s.string_course_height > 0)
    if n_courses < expected:
        report.errors.append(
            f"only {n_courses} string course(s) rendered, expected {expected} "
            f"(one per upper story with string_course_height > 0)"
        )


def validate_parapet(facade: Facade, render_result: dict,
                     report: ValidationReport) -> None:
    """If facade declares a parapet, the parapet layer should have polylines
    and start at or above the top-story's top."""
    if facade.parapet is None:
        return
    layers = render_result.get("layers", {})
    parapet_polys = layers.get("parapet", {}).get("polylines", [])
    if not parapet_polys:
        report.errors.append(
            f"facade declares parapet {facade.parapet} but parapet layer is empty"
        )
        return

    # Parapet should begin at (or above) the top of the top story.
    facade_top_y = facade.base_y - sum(s.height for s in facade.stories)
    ys = [p[1] for pl in parapet_polys for p in pl]
    if ys:
        bottom_of_parapet = max(ys)
        if bottom_of_parapet < facade_top_y - 1.0:
            report.errors.append(
                f"parapet bottom y={bottom_of_parapet:.2f} floats above facade "
                f"top y={facade_top_y:.2f} (parapet should sit on top of top story)"
            )


def validate_pilasters_present_on_ordered_stories(
        facade: Facade, render_result: dict,
        report: ValidationReport) -> None:
    """On each story with ``has_order`` set, every bay with a matching
    ``pilaster_order`` should have pilaster polylines at that story's
    y-range."""
    layers = render_result.get("layers", {})
    pil_entries = layers.get("pilasters", {}).get("entries", [])
    if not pil_entries and not any(
            s.has_order for s in facade.stories):
        return

    bounds = _story_bounds(facade)
    for si, story in enumerate(facade.stories):
        if not story.has_order:
            continue
        y_bot, y_top = bounds[si]
        for bi, bay in enumerate(facade.bays):
            if not bay.pilaster_order:
                continue
            # Find at least one pil entry at this bay's axis within this story.
            hit = False
            for ent in pil_entries:
                ax = ent.get("axis_x")
                if ax is None:
                    continue
                if abs(ax - bay.axis_x) > 0.5:
                    continue
                polys = ent.get("polylines") or []
                for pl in polys:
                    if not pl:
                        continue
                    ys = [p[1] for p in pl]
                    if min(ys) < y_bot + 1.0 and max(ys) > y_top - 1.0:
                        hit = True
                        break
                if hit:
                    break
            if not hit:
                report.errors.append(
                    f"story[{si}] (order={story.has_order}) bay[{bi}] "
                    f"declares pilaster_order='{bay.pilaster_order}' but no "
                    f"pilaster polylines found at axis_x={bay.axis_x:.2f} "
                    f"within y=[{y_top:.1f}, {y_bot:.1f}]"
                )


# ──────────────────────────────────────────────────────────────────────────
# Top-level entry points
# ──────────────────────────────────────────────────────────────────────────

def validate_facade_composition(facade: Facade) -> ValidationReport:
    """Pre-render: validate the declarative Facade spec."""
    r = ValidationReport()
    validate_story_layout(facade, r)
    validate_bay_layout(facade, r)
    validate_pilaster_order_match(facade, r)
    validate_arched_openings_in_arcuated_stories(facade, r)
    return r


def validate_facade_render(facade: Facade,
                           render_result: dict) -> ValidationReport:
    """Post-render: run pre-render checks + render-dependent checks."""
    r = validate_facade_composition(facade)
    validate_wall_clips_openings(facade, render_result, r)
    validate_joints_clip_openings(facade, render_result, r)
    validate_smooth_walls_have_no_blocks(facade, render_result, r)
    validate_voussoirs(facade, render_result, r)
    validate_string_courses(facade, render_result, r)
    validate_parapet(facade, render_result, r)
    validate_pilasters_present_on_ordered_stories(facade, render_result, r)
    return r


# ──────────────────────────────────────────────────────────────────────────
# Smoke test
# ──────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from ..facade import Bay, Facade, Opening, Story

    # Build the schematic-style facade.
    bays = [Bay(openings=[
                Opening(kind="arch_window", width=20, height=40),
                Opening(kind="window", width=20, height=50, hood="triangular"),
                Opening(kind="window", width=20, height=35, hood="cornice"),
            ], pilaster_order="ionic", pilaster_width=5) for _ in range(5)]
    stories = [
        Story(height=70, wall={"variant": "arcuated",
                                "course_h": 20, "block_w": 40}),
        Story(height=90, wall="smooth", has_order="ionic"),
        Story(height=55, wall="smooth"),
    ]
    f = Facade(width=400, stories=stories, bays=bays, base_y=300,
               parapet={"type": "balustrade", "height": 18})
    f.layout()

    # --- Pre-render validation ---
    r1 = validate_facade_composition(f)
    print(f"Pre-render: {len(r1)} errors")
    for e in r1:
        print(f"  - {e}")

    # --- Post-render validation ---
    result = f.render()
    r2 = validate_facade_render(f, result)
    print(f"\nPost-render: {len(r2)} errors")
    for e in r2:
        print(f"  - {e}")

    # --- Deliberately bad facade: rustication on upper story ---
    bad_stories = [
        Story(height=70, wall="smooth"),
        Story(height=90, wall={"variant": "arcuated"}),  # WRONG
        Story(height=55, wall="smooth"),
    ]
    bad_bays = [Bay(openings=[
                    Opening(kind="window", width=20, height=40),
                    Opening(kind="arch_window", width=20, height=50),
                    Opening(kind="window", width=20, height=35),
                ], pilaster_order="ionic", pilaster_width=5)
                for _ in range(5)]
    bad_f = Facade(width=400, stories=bad_stories, bays=bad_bays, base_y=300)
    bad_f.layout()
    r3 = validate_facade_composition(bad_f)
    print(f"\nBad facade: {len(r3)} errors (expected >=1)")
    for e in r3:
        print(f"  - {e}")
    assert len(r3) >= 1, "should catch rustication on upper story"

    print("\nFacade validation OK")
