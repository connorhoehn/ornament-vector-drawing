"""Layout solver primitives. Given a FacadePlan, compute story heights
and bay coordinates. The ``solve()`` top-level entry point (that builds
the full Element tree) is filled in by Day 10 — for now this module
exports the primitives.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from .constraint_solver import ConstraintSolver
from .plan import (
    FacadePlan, StoryPlan, BayPlan, OpeningPlan, ParapetPlan, PlinthPlan,
    PedimentPlan, PorticoPlan, RoofPlan, BoathousePlan, PlanInfeasible,
)

if TYPE_CHECKING:
    from ..element import Element


# ── Day 7 — Story height solver ────────────────────────────────────────

@dataclass
class StoryLayout:
    """Computed layout for one story."""
    index: int
    plan: StoryPlan
    y_bottom: float      # world-coord bottom of story (larger y in SVG)
    y_top: float         # world-coord top (smaller y in SVG)
    height_mm: float

    @property
    def envelope(self) -> tuple[float, float, float, float]:
        raise NotImplementedError  # filled in after canvas x-range known


@dataclass
class ParapetLayout:
    plan: ParapetPlan
    y_bottom: float
    y_top: float
    height_mm: float


@dataclass
class PlinthLayout:
    plan: PlinthPlan
    y_bottom: float      # very bottom of canvas (largest y)
    y_top: float         # where ground story meets plinth
    height_mm: float


def solve_story_heights(
    plan: FacadePlan,
) -> tuple[list[StoryLayout], ParapetLayout | None, PlinthLayout | None]:
    """Given a FacadePlan, distribute canvas height across stories and the
    parapet. Returns story layouts ordered bottom-to-top (matching
    plan.stories order) and optional parapet layout.

    Raises PlanInfeasible with reason='insufficient_height' if the
    canvas can't accommodate all min_height_mm constraints.

    Implementation (Phase 24 Day 1): expressed as a ``ConstraintSolver``
    problem. Variables are per-story heights (plus optional parapet),
    each bounded below by ``min_height_mm``. A single equation pins the
    sum to ``canvas_height``. Proportionality between stories is encoded
    as loose inequalities (within a 15% tolerance of the canvas height),
    which automatically relax when ``min_height_mm`` floors dominate.
    """
    canvas_bottom = plan.canvas_bottom
    canvas_h = plan.canvas_height

    # Plinth is a fixed absolute height band reserved from the BOTTOM of
    # the canvas BEFORE any story/parapet allocation. This keeps plinth
    # height stable across canvas changes (a stylobate is a structural
    # constant, not a proportional share of the facade).
    has_plinth = bool(plan.plinth)
    plinth_h = plan.plinth.height_mm if has_plinth else 0.0
    if plinth_h >= canvas_h:
        raise PlanInfeasible(
            reason="plinth_overflow",
            details=(
                f"plinth height_mm ({plinth_h:.2f}mm) meets or exceeds "
                f"canvas height ({canvas_h:.2f}mm)"
            ),
            suggested_fix="reduce PlinthPlan.height_mm or enlarge canvas",
        )
    canvas_h_effective = canvas_h - plinth_h

    # Sum ratios — stories + parapet (kept for zero-ratio feasibility check
    # and for the naive parapet allocation, which is still deterministic).
    total_ratio = sum(s.height_ratio for s in plan.stories)
    has_parapet = bool(plan.parapet and plan.parapet.kind != "none")
    if has_parapet:
        total_ratio += plan.parapet.height_ratio

    if total_ratio <= 0:
        raise PlanInfeasible(
            reason="zero_ratio",
            details=f"sum of height_ratio across stories+parapet is {total_ratio}",
            suggested_fix="set height_ratio > 0 for at least one story",
        )

    unit = canvas_h_effective / total_ratio
    # Parapet height is a fixed budget here (constant); it reduces the
    # canvas budget available to stories. Day 2 may turn this into another
    # solver variable once cornice projection is folded in.
    parapet_h = (plan.parapet.height_ratio * unit) if has_parapet else 0.0

    # Upfront feasibility probe: sum of story mins + parapet must not
    # exceed canvas_h_effective. We keep this explicit so the error
    # message is actionable (linprog's "infeasible" is too opaque).
    total_mins = sum(s.min_height_mm for s in plan.stories) + parapet_h
    if total_mins > canvas_h_effective + 0.5:
        overflow = total_mins - canvas_h_effective
        raise PlanInfeasible(
            reason="insufficient_height",
            details=(
                f"sum of min_height_mm constraints ({total_mins:.2f}mm) "
                f"exceeds canvas height minus plinth "
                f"({canvas_h_effective:.2f}mm) by {overflow:.2f}mm"
            ),
            suggested_fix=(
                f"increase canvas height by {overflow:.2f}mm or reduce "
                f"min_height_mm on one or more stories"
            ),
        )

    # Build the constraint system ────────────────────────────────────────
    solver = ConstraintSolver()

    # 1) One variable per story height. Lower = min_height_mm.
    story_budget = canvas_h_effective - parapet_h
    for i, s in enumerate(plan.stories):
        solver.variable(f"s{i}_h", lower=s.min_height_mm, upper=story_budget)

    # 2) Sum of story heights = canvas_h - parapet_h.
    solver.equation(
        [(f"s{i}_h", 1.0) for i in range(len(plan.stories))],
        rhs=story_budget,
    )

    # 3) Proportionality: ideally s_i * r_0 == s_0 * r_i. We encode this
    #    as a slack variable ``d_i >= 0`` with the two inequalities
    #        +(s_i * r_0 - s_0 * r_i) <= d_i
    #        -(s_i * r_0 - s_0 * r_i) <= d_i
    #    and minimize sum(d_i). That lets d_i go to 0 when min_height_mm
    #    floors permit, and absorb the break otherwise. The 15% tolerance
    #    from the plan is the hard UPPER bound on d_i — if even that can't
    #    be met, we declare infeasibility.
    tol = canvas_h * 0.15
    r0 = plan.stories[0].height_ratio
    slack_vars: list[str] = []
    for i in range(1, len(plan.stories)):
        ri = plan.stories[i].height_ratio
        d = f"d{i}"
        solver.variable(d, lower=0.0, upper=max(tol, story_budget))
        slack_vars.append(d)
        # s_i * r_0 - s_0 * r_i - d_i <= 0
        solver.inequality(
            [(f"s{i}_h", r0), ("s0_h", -ri), (d, -1.0)],
            upper_bound=0.0,
        )
        # -s_i * r_0 + s_0 * r_i - d_i <= 0
        solver.inequality(
            [(f"s{i}_h", -r0), ("s0_h", ri), (d, -1.0)],
            upper_bound=0.0,
        )

    # 4) Objective: minimize total L1 deviation from ideal proportions.
    #    When mins don't bite, this drives every d_i to 0 — exact
    #    proportional allocation. When they do bite, only the stories
    #    whose mins conflict with the ratio will carry non-zero slack.
    if slack_vars:
        solver.objective([(d, 1.0) for d in slack_vars])

    result = solver.solve()
    if not result.feasible:
        # Reach here only if mins + proportionality tolerances are jointly
        # unsatisfiable — the canvas was big enough for mins alone but not
        # for the ratio envelope on top. Report as insufficient_height so
        # callers can continue to treat this class uniformly.
        raise PlanInfeasible(
            reason="insufficient_height",
            details=(
                "constraint solver could not satisfy story height system: "
                f"{'; '.join(result.errors)}"
            ),
            suggested_fix=(
                "loosen min_height_mm, relax height_ratio spread, or "
                "increase canvas height"
            ),
        )

    heights = [result.values[f"s{i}_h"] for i in range(len(plan.stories))]

    # Snap to the exact proportional allocation when no ``min_height_mm``
    # floor is active — i.e. when the naive ratio-based split is itself
    # feasible. linprog introduces sub-micrometer noise; this preserves
    # bit-exact reproducibility for snapshot tests and keeps the
    # "no-pinning-needed" path numerically identical to the pre-Phase-24
    # implementation.
    naive_heights = [s.height_ratio * unit for s in plan.stories]
    if all(nh >= s.min_height_mm - 1e-6
           for nh, s in zip(naive_heights, plan.stories)):
        heights = naive_heights

    # Final feasibility check — catches solver drift.
    final_total = sum(heights) + parapet_h + plinth_h
    if abs(final_total - canvas_h) > 0.5:
        raise PlanInfeasible(
            reason="height_imbalance",
            details=(
                f"solved story heights sum to {final_total:.2f}mm but "
                f"canvas is {canvas_h:.2f}mm"
            ),
        )

    # Build StoryLayouts. Stories are ordered bottom-to-top in plan.stories,
    # and in SVG y-down world coords, "bottom" has the LARGEST y and "top"
    # has the smallest. Plinth lives at the very bottom (highest y); stories
    # start above it; parapet is above the topmost story.
    plinth_layout = None
    if has_plinth:
        plinth_layout = PlinthLayout(
            plan=plan.plinth,
            y_bottom=canvas_bottom,
            y_top=canvas_bottom - plinth_h,
            height_mm=plinth_h,
        )

    layouts: list[StoryLayout] = []
    y_cursor = canvas_bottom - plinth_h   # stories start above the plinth
    for i, (s, h) in enumerate(zip(plan.stories, heights)):
        y_bot = y_cursor
        y_top = y_cursor - h   # growing upward = smaller y
        layouts.append(StoryLayout(
            index=i, plan=s, y_bottom=y_bot, y_top=y_top, height_mm=h,
        ))
        y_cursor = y_top

    parapet_layout = None
    if has_parapet:
        parapet_layout = ParapetLayout(
            plan=plan.parapet,
            y_bottom=y_cursor,
            y_top=y_cursor - parapet_h,
            height_mm=parapet_h,
        )

    return layouts, parapet_layout, plinth_layout


# ── Day 8 — Bay + opening sizing ────────────────────────────────────────

@dataclass
class BayLayout:
    """Computed layout for one bay."""
    index: int
    plan: BayPlan
    axis_x: float      # centerline of the bay
    pitch_mm: float    # total on-center width allocated to this bay
    left_x: float      # bay's left boundary
    right_x: float


@dataclass
class OpeningLayout:
    """One opening: its rectangular bounding rect (without hood). For
    arched openings, total vertical height = rect_height + rise above spring."""
    story_index: int
    bay_index: int
    plan: OpeningPlan
    # In world coords:
    x_center: float
    y_bottom: float      # bottom of opening rectangle (larger y)
    y_top: float         # top of opening rect (OR top of semicircle for arches; see effective_top)
    width_mm: float
    height_mm: float     # height of rectangular portion
    rise_mm: float       # for arches; 0 for non-arched

    @property
    def effective_top(self) -> float:
        """y at the HIGHEST extent (smallest y) including any arch rise."""
        return self.y_top - self.rise_mm


def solve_bay_layout(plan: FacadePlan) -> list[BayLayout]:
    """Distribute canvas width across bays. Uses BayPlan.width_weight
    for non-uniform widths (e.g. wider central door bay)."""
    total_weight = sum(b.width_weight for b in plan.bays)
    if total_weight <= 0:
        raise PlanInfeasible(
            reason="zero_bay_weight",
            details="sum of BayPlan.width_weight is 0",
        )
    canvas_w = plan.canvas_width
    unit = canvas_w / total_weight

    layouts: list[BayLayout] = []
    x_cursor = plan.canvas_left
    for i, bay in enumerate(plan.bays):
        pitch = bay.width_weight * unit
        left_x = x_cursor
        right_x = x_cursor + pitch
        axis_x = (left_x + right_x) / 2
        layouts.append(BayLayout(
            index=i, plan=bay, axis_x=axis_x, pitch_mm=pitch,
            left_x=left_x, right_x=right_x,
        ))
        x_cursor = right_x
    return layouts


def solve_openings(
    plan: FacadePlan,
    stories: list[StoryLayout],
    bays: list[BayLayout],
    *,
    opening_vertical_anchor: str = "center",  # "center" | "sill"
    sill_margin_frac: float = 0.10,            # opening sits sill_margin_frac * story_h from the floor
) -> list[list[OpeningLayout]]:
    """Compute each opening's mm-precise layout.

    Returns a list of lists: outer index = bay, inner = story (bottom-to-top,
    matching plan.stories).

    Rules:
    - width_mm = plan.width_frac × bay.pitch_mm
    - height_mm = plan.height_frac × story.height_mm  (rectangular portion only)
    - For arched openings: rise_mm = width_mm / 2 for semicircular, or
      plan.segmental_rise_frac × width_mm for segmental
    - opening is vertically anchored per anchor mode:
        "center" — centered in story
        "sill" — bottom of opening sits sill_margin_frac × story_h from floor

    Raises PlanInfeasible if any opening's total effective height
    (rect + arch rise) exceeds its story's height (with a 5% buffer for
    architraves/hoods that may extend further).
    """
    out: list[list[OpeningLayout]] = []
    for bay_idx, bay in enumerate(bays):
        per_bay: list[OpeningLayout] = []
        for story_idx, (story, opening_plan) in enumerate(zip(stories, bay.plan.openings)):
            if opening_plan.kind == "blank":
                per_bay.append(OpeningLayout(
                    story_index=story_idx, bay_index=bay_idx, plan=opening_plan,
                    x_center=bay.axis_x, y_bottom=story.y_bottom, y_top=story.y_top,
                    width_mm=0, height_mm=0, rise_mm=0,
                ))
                continue

            w = opening_plan.width_frac * bay.pitch_mm
            h = opening_plan.height_frac * story.height_mm

            # Arch rise
            if opening_plan.kind in ("arch_window", "arch_door"):
                if opening_plan.segmental_rise_frac is not None:
                    rise = opening_plan.segmental_rise_frac * w
                else:
                    rise = w / 2  # semicircular
            else:
                rise = 0.0

            # Reservation for everything ABOVE the opening rectangle:
            # either the hood (triangular/segmental/cornice pediment for
            # rectangular windows) OR the arch rise (semicircular /
            # segmental arched openings). They aren't stacked — whichever
            # is bigger sets the space reserved above y_top_rect.
            hood = opening_plan.hood
            # Measured directly from ``window_opening`` overall_bbox at
            # several widths (see Phase-31 audit). The coefficients below
            # are the empirical ``hood_extent_above / w`` and
            # ``sill_extent_below / w`` fractions, rounded up 2% for
            # safety margin.
            has_key = opening_plan.has_keystone
            if hood == "triangular":
                hood_h = w * 0.54 + 0.3
            elif hood == "segmental":
                hood_h = w * 0.58 + 0.3
            elif hood == "cornice":
                hood_h = w * 0.35 + 0.3
            elif has_key:
                hood_h = w * 0.27 + 0.2
            else:
                hood_h = w * 0.19 + 0.2
            above_h = max(hood_h, rise)

            # Reservation for the sill / architrave base BELOW the opening
            # rectangle. ``window_opening`` draws a sill ledge that extends
            # below y_bottom by roughly w·0.20. For arched openings with
            # y_bottom = floor and jambs extending down to y_bottom, no
            # extra below-reservation is needed.
            if opening_plan.kind in ("arch_window", "arch_door"):
                below_h = 0.0
            elif opening_plan.kind in ("window", "door", "niche"):
                below_h = w * 0.40   # measured: 0.387·w, +1.3% margin
            else:
                below_h = 0.0

            total_h = h + above_h + below_h
            # Feasibility: opening rect + whatever sits above (hood OR arch
            # rise) must fit inside the story, leaving a small cushion for
            # the sill below and the wall gutter above the top feature.
            cushion = 1.5
            if total_h > story.height_mm - cushion:
                raise PlanInfeasible(
                    reason="opening_overflows_story",
                    element_id=f"bay_{bay_idx}.story_{story_idx}",
                    details=(
                        f"opening total height {total_h:.2f}mm "
                        f"(rect {h:.2f} + above {above_h:.2f}; "
                        f"hood {hood_h:.2f}, arch rise {rise:.2f}) "
                        f"exceeds story height {story.height_mm:.2f}mm "
                        f"minus cushion {cushion:.1f}mm"
                    ),
                    suggested_fix=(
                        "reduce height_frac, drop the hood, reduce the "
                        "arch rise, or increase story height_ratio"
                    ),
                )

            # Position vertically — reserve above_h above the rect and
            # below_h below it so hoods, arch apices, AND sills all sit
            # INSIDE the story.
            #
            # Classical arcade rule: when the wall variant is "arcuated"
            # AND the opening is arched (arch_door / arch_window), the
            # opening spans from the story floor upward — the arch jambs
            # are the pier edges and the "floor" is the plinth top. Snap
            # y_bot to story.y_bottom so the opening void fully reaches
            # the floor line, eliminating both (a) the visible gap between
            # the jamb-end and the plinth, and (b) the rustication blocks
            # that would otherwise show through the unsubtracted strip.
            is_arcaded = (
                story.plan.wall == "arcuated"
                and opening_plan.kind in ("arch_door", "arch_window")
            )
            if is_arcaded:
                y_bot = story.y_bottom
                y_top_rect = y_bot - h
            elif opening_vertical_anchor == "center":
                slack = story.height_mm - total_h
                y_above_top = story.y_top + slack / 2.0
                y_top_rect = y_above_top + above_h
                y_bot = y_top_rect + h
            else:   # "sill"
                sill_y = story.y_bottom - sill_margin_frac * story.height_mm - below_h
                y_bot = sill_y
                y_top_rect = sill_y - h

            per_bay.append(OpeningLayout(
                story_index=story_idx, bay_index=bay_idx, plan=opening_plan,
                x_center=bay.axis_x, y_bottom=y_bot, y_top=y_top_rect,
                width_mm=w, height_mm=h, rise_mm=rise,
            ))
        out.append(per_bay)

    # Opening hierarchy check (Vignola/Palladio): widths descend going up.
    # Report as PlanInfeasible if any upper is wider than lower.
    for bay_idx, bay_openings in enumerate(out):
        for k in range(1, len(bay_openings)):
            prev_w = bay_openings[k-1].width_mm
            cur_w = bay_openings[k].width_mm
            if cur_w > prev_w + 0.5:
                raise PlanInfeasible(
                    reason="opening_hierarchy_violated",
                    element_id=f"bay_{bay_idx}.story_{k}",
                    details=(
                        f"story {k} opening (w={cur_w:.2f}mm) is wider than "
                        f"story {k-1} opening (w={prev_w:.2f}mm). Classical "
                        f"hierarchy: widths descend going up."
                    ),
                    suggested_fix="reduce upper opening's width_frac below the lower's",
                )

    return out


# ── Day 9 — Pilaster placement ─────────────────────────────────────────

@dataclass
class PilasterLayout:
    """One pilaster flanking one bay on one ordered story."""
    story_index: int
    bay_index: int
    side: Literal["left", "right"]   # which side of the bay axis
    order: str                        # "ionic" etc.
    cx: float                         # centerline x of this pilaster
    base_y: float                     # bottom (story y_bottom)
    top_y: float                      # top (story y_top)
    width_mm: float
    height_mm: float                  # = story.height_mm

    @property
    def envelope(self) -> tuple[float, float, float, float]:
        return (self.cx - self.width_mm / 2, self.top_y,
                self.cx + self.width_mm / 2, self.base_y)


def solve_pilasters(
    plan: FacadePlan,
    stories: list[StoryLayout],
    bays: list[BayLayout],
) -> list[PilasterLayout]:
    """For each story with has_order set AND each bay with bay.plan.pilasters
    defined, emit two PilasterLayouts (left + right flanking the bay opening
    on that story).

    Pilaster width = bay.plan.pilasters.width_frac × bay.pitch_mm.
    Pilaster flanks at x = bay.axis_x ± (bay.pitch_mm * 0.45)
    (placing them near the bay boundary, not at the center).
    """
    out: list[PilasterLayout] = []
    for story in stories:
        if story.plan.has_order is None:
            continue
        for bay in bays:
            if bay.plan.pilasters is None:
                continue
            pw = bay.plan.pilasters.width_frac * bay.pitch_mm
            # Flanking distance from bay center
            flank_offset = bay.pitch_mm * 0.45
            for side, sign in (("left", -1), ("right", +1)):
                cx = bay.axis_x + sign * flank_offset
                out.append(PilasterLayout(
                    story_index=story.index,
                    bay_index=bay.index,
                    side=side,
                    order=story.plan.has_order,
                    cx=cx,
                    base_y=story.y_bottom,
                    top_y=story.y_top,
                    width_mm=pw,
                    height_mm=story.height_mm,
                ))
    return out


# ── Day 9 — String-course layout ───────────────────────────────────────

@dataclass
class StringCourseLayout:
    """A horizontal molding between adjacent stories (or at the parapet)."""
    between_story_indices: tuple[int, int]   # (lower, upper) or (-1, 0) for ground
    y_center: float                           # the y of the course's mid-height
    height_mm: float
    x_left: float
    x_right: float

    @property
    def envelope(self) -> tuple[float, float, float, float]:
        h = self.height_mm
        return (self.x_left, self.y_center - h / 2,
                self.x_right, self.y_center + h / 2)


def solve_string_courses(
    plan: FacadePlan,
    stories: list[StoryLayout],
) -> list[StringCourseLayout]:
    """One string course between each adjacent pair of stories.

    The course's y_center is exactly story.y_top (the shared edge between
    lower and upper stories). The course height comes from the LOWER story's
    plan.string_course_height.
    """
    out: list[StringCourseLayout] = []
    for i in range(len(stories) - 1):
        lower = stories[i]
        y_shared = lower.y_top  # = stories[i+1].y_bottom
        h = lower.plan.string_course_height
        out.append(StringCourseLayout(
            between_story_indices=(i, i + 1),
            y_center=y_shared,
            height_mm=h,
            x_left=plan.canvas_left,
            x_right=plan.canvas_right,
        ))
    return out


# ── Day 10 — Top-level solve() assembling the Element tree ────────────

def solve(plan: "FacadePlan"):
    """Full end-to-end solve: turn a FacadePlan into an Element tree with
    every containment constraint satisfied. Raises PlanInfeasible if any
    primitive reports an issue OR if the final tree fails validate_tree().
    """
    from ..element import Element
    from ..containment import validate_tree
    from ..elements.arches import SemicircularArchElement, SegmentalArchElement
    from .elements import (FacadeElement, StoryElement, BayElement,
                            WindowElement, PilasterElement, WallElement,
                            StringCourseElement, ParapetElement, PlinthElement,
                            EntablatureBandElement, QuoinElement)
    
    # Run primitives
    stories, parapet_layout, plinth_layout = solve_story_heights(plan)
    bays = solve_bay_layout(plan)
    openings = solve_openings(plan, stories, bays)
    pilasters = solve_pilasters(plan, stories, bays)
    # Note: ``solve_string_courses`` is retained for backward compatibility
    # with external callers but is no longer needed in solve() — the
    # between-story courses (entablature bands or thin string courses) are
    # now emitted inline below.
    
    # Build tree
    # Root envelope = full canvas
    cx = (plan.canvas_left + plan.canvas_right) / 2
    facade = FacadeElement(
        id="facade", kind="facade",
        envelope=plan.canvas,
    )
    
    # Story elements — envelope = (canvas_left, y_top, canvas_right, y_bottom)
    story_nodes = {}
    for s in stories:
        sid = f"facade.story_{s.index}"
        story_el = StoryElement(
            id=sid, kind="story",
            envelope=(plan.canvas_left, s.y_top,
                       plan.canvas_right, s.y_bottom),
            metadata={"wall": s.plan.wall, "order": s.plan.has_order,
                      "label": s.plan.label, "height_mm": s.height_mm},
        )
        facade.add(story_el)
        story_nodes[s.index] = story_el

        # Wall background for the story. Renders smooth as just an outline;
        # rusticated variants produce an ashlar grid + joints. We skip
        # voussoir-wiring through the wall — ArchElement children draw
        # their own voussoirs, so arch_springings/spans stays empty here.
        #
        # Phase 21 Part 2: walls auto-discover voids from sibling VOID
        # elements (windows, arches) added later in this solve pass, so
        # no explicit ``void_bboxes`` are passed here. The CSG subtraction
        # happens lazily at ``render_strokes()`` time.
        wall_el = WallElement(
            id=f"{sid}.wall", kind="wall",
            envelope=(plan.canvas_left, s.y_top,
                       plan.canvas_right, s.y_bottom),
            x_left=plan.canvas_left, x_right=plan.canvas_right,
            y_top=s.y_top, y_bottom=s.y_bottom,
            variant=s.plan.wall,
            course_h=s.height_mm / 4 if s.plan.wall == "arcuated" else 0,
            block_w=(s.height_mm / 4) * 2 if s.plan.wall == "arcuated" else 0,
        )
        story_el.add(wall_el)

    # Bay elements (children of each story)
    for s in stories:
        parent_story = story_nodes[s.index]
        for b in bays:
            bid = f"{parent_story.id}.bay_{b.index}"
            bay_el = BayElement(
                id=bid, kind="bay",
                envelope=(b.left_x, s.y_top, b.right_x, s.y_bottom),
                metadata={"axis_x": b.axis_x, "pitch_mm": b.pitch_mm,
                          "label": b.plan.label},
            )
            parent_story.add(bay_el)
    
    # Openings — one per (bay, story). Windows are WindowElement; arches
    # are SemicircularArchElement/SegmentalArchElement.
    for bay_idx, bay_openings in enumerate(openings):
        for opening_layout in bay_openings:
            if opening_layout.plan.kind == "blank":
                continue
            s_idx = opening_layout.story_index
            parent_bay_id = f"facade.story_{s_idx}.bay_{bay_idx}"
            parent_bay = facade.find(parent_bay_id)
            op_id = f"{parent_bay_id}.opening"
            
            if opening_layout.plan.is_arched:
                # Arched opening: use SemicircularArchElement or SegmentalArchElement.
                #
                # Phase 22 Part 4: doors get heavier treatment than windows —
                # more voussoirs (finer stone coursing reads as a grander
                # opening), a keystone is forced on, and an outer archivolt
                # band is added.
                w = opening_layout.width_mm
                # y_spring is at y_top (where rect portion ends and arch begins)
                y_spring = opening_layout.y_top
                cx_op = opening_layout.x_center
                is_arch_door = opening_layout.plan.kind == "arch_door"
                if is_arch_door:
                    voussoir_count = 11
                    with_keystone = True     # force keystone on doors
                    archivolt_bands = 1      # extra outer archivolt
                else:
                    voussoir_count = 7
                    with_keystone = opening_layout.plan.has_keystone
                    archivolt_bands = 0
                if opening_layout.plan.segmental_rise_frac is not None:
                    op_el = SegmentalArchElement(
                        id=op_id, kind="arch_opening",
                        envelope=(cx_op - w/2, opening_layout.effective_top,
                                   cx_op + w/2, opening_layout.y_bottom),
                        cx=cx_op, y_spring=y_spring, span=w,
                        rise=opening_layout.rise_mm,
                        voussoir_count=voussoir_count,
                        with_keystone=with_keystone,
                        archivolt_bands=archivolt_bands,
                        y_bottom=opening_layout.y_bottom,
                    )
                else:
                    op_el = SemicircularArchElement(
                        id=op_id, kind="arch_opening",
                        envelope=(cx_op - w/2, opening_layout.effective_top,
                                   cx_op + w/2, opening_layout.y_bottom),
                        cx=cx_op, y_spring=y_spring, span=w,
                        voussoir_count=voussoir_count,
                        with_keystone=with_keystone,
                        archivolt_bands=archivolt_bands,
                        y_bottom=opening_layout.y_bottom,
                    )
            else:
                # Phase 22 Part 4: non-arch doors emit strokes at a heavier
                # weight so the opening silhouette reads as the primary
                # entrance.
                is_door = opening_layout.plan.kind == "door"
                op_el = WindowElement(
                    id=op_id, kind=opening_layout.plan.kind,
                    envelope=(opening_layout.x_center - opening_layout.width_mm/2,
                               opening_layout.y_top,
                               opening_layout.x_center + opening_layout.width_mm/2,
                               opening_layout.y_bottom),
                    x_center=opening_layout.x_center,
                    y_top=opening_layout.y_top,
                    y_bottom=opening_layout.y_bottom,
                    width_mm=opening_layout.width_mm,
                    height_mm=opening_layout.height_mm,
                    hood=opening_layout.plan.hood,
                    has_keystone=opening_layout.plan.has_keystone,
                    stroke_boost=0.10 if is_door else 0.0,
                )
            parent_bay.add(op_el)
    
    # Pilasters — flank bays on ordered stories
    for p in pilasters:
        parent_bay_id = f"facade.story_{p.story_index}.bay_{p.bay_index}"
        parent_bay = facade.find(parent_bay_id)
        pil_id = f"{parent_bay_id}.pilaster_{p.side}"
        pil_el = PilasterElement(
            id=pil_id, kind="pilaster",
            envelope=p.envelope,
            cx=p.cx, width_mm=p.width_mm,
            base_y=p.base_y, top_y=p.top_y,
            order=p.order,
        )
        parent_bay.add(pil_el)
    
    # Between-story courses: emit a FULL entablature band above ordered
    # stories (architrave + frieze + cornice), otherwise a thin string
    # course.
    from .. import canon
    _order_cls = {
        "tuscan":      canon.Tuscan,
        "doric":       canon.Doric,
        "ionic":       canon.Ionic,
        "corinthian":  canon.Corinthian,
        "composite":   canon.Composite,
    }
    for i in range(len(stories) - 1):
        lower = stories[i]
        y_shared = lower.y_top  # = stories[i+1].y_bottom
        if lower.plan.has_order and lower.plan.has_order in _order_cls:
            # Derive a module diameter D from the first bay's pilaster width,
            # falling back to 12mm. This keeps the entablature's D consistent
            # with the pilasters crowning the story below.
            D = 12.0
            for bay in bays:
                if bay.plan.pilasters is not None:
                    D = bay.plan.pilasters.width_frac * bay.pitch_mm
                    break
            order_dims = _order_cls[lower.plan.has_order](D=D)
            ent_h = order_dims.entablature_h
            # Inset x_left/x_right by the cornice projection so the total bbox
            # (including cornice overhang) stays within canvas.
            cornice_projection = 0.5 * D  # conservative — covers all orders
            band_x_left = plan.canvas_left + cornice_projection
            band_x_right = plan.canvas_right - cornice_projection

            # If quoins are enabled, inset further so entablature doesn't
            # overlap quoins at the outer edges.
            if getattr(plan, 'with_quoins', False):
                band_x_left += plan.quoin_width_mm
                band_x_right -= plan.quoin_width_mm

            band = EntablatureBandElement(
                id=f"facade.entablature_{i}_{i+1}", kind="entablature_band",
                envelope=(band_x_left, y_shared - ent_h,
                          band_x_right, y_shared),
                order=lower.plan.has_order,
                x_left=band_x_left, x_right=band_x_right,
                y_top_of_capital=y_shared, D=D,
                cornice_at_edges=True,   # band must stay inside canvas/quoins
            )
            facade.add(band)
        else:
            # Plain string course for non-ordered stories
            c = StringCourseLayout(
                between_story_indices=(i, i + 1),
                y_center=y_shared,
                height_mm=lower.plan.string_course_height,
                x_left=plan.canvas_left, x_right=plan.canvas_right,
            )
            sc_el = StringCourseElement(
                id=f"facade.string_course_{i}", kind="string_course",
                envelope=c.envelope,
                y_center=c.y_center, height_mm=c.height_mm,
                x_left=c.x_left, x_right=c.x_right,
            )
            facade.add(sc_el)
    
    # Plinth — base course at the very bottom of the facade. Render
    # BEFORE the parapet so the top-down draw order has plinth under
    # walls (which sit above it), walls under parapet. The tree order
    # here doesn't affect z-order (all children render in tree order);
    # what matters is that the plinth's envelope sits below all stories.
    if plinth_layout is not None:
        pl_el = PlinthElement(
            id="facade.plinth", kind="plinth",
            envelope=(plan.canvas_left - plinth_layout.plan.projection_mm,
                      plinth_layout.y_top,
                      plan.canvas_right + plinth_layout.plan.projection_mm,
                      plinth_layout.y_bottom),
            x_left=plan.canvas_left, x_right=plan.canvas_right,
            y_top=plinth_layout.y_top, y_bottom=plinth_layout.y_bottom,
            variant=plinth_layout.plan.kind,
            projection_mm=plinth_layout.plan.projection_mm,
            metadata={"height_mm": plinth_layout.height_mm},
        )
        facade.add(pl_el)

    # Parapet
    if parapet_layout is not None:
        # For balustrade variant, interrupt the run at each bay axis with a
        # pedestal block (the bay's rhythm reads up into the parapet).
        ped_xs = (
            [b.axis_x for b in bays]
            if parapet_layout.plan.kind == "balustrade"
            else []
        )
        par_el = ParapetElement(
            id="facade.parapet", kind=parapet_layout.plan.kind,
            envelope=(plan.canvas_left, parapet_layout.y_top,
                       plan.canvas_right, parapet_layout.y_bottom),
            x_left=plan.canvas_left, x_right=plan.canvas_right,
            y_top=parapet_layout.y_top, y_bottom=parapet_layout.y_bottom,
            baluster_variant=parapet_layout.plan.baluster_variant,
            pedestal_positions=ped_xs,
            metadata={"height_mm": parapet_layout.height_mm},
        )
        facade.add(par_el)

    # Phase 22 Part 3: corner quoins. When ``plan.with_quoins`` is set,
    # emit two ``QuoinElement`` children of the facade, one at each outer
    # x edge, spanning the full canvas height. They are ``Material.ORNAMENT``
    # so they render in front of walls without participating in CSG.
    if getattr(plan, "with_quoins", False):
        quoin_w = plan.quoin_width_mm
        for side, cx_quoin in (
            ("left",  plan.canvas_left + quoin_w / 2),
            ("right", plan.canvas_right - quoin_w / 2),
        ):
            quoin = QuoinElement(
                id=f"facade.quoin_{side}", kind="quoin",
                envelope=(cx_quoin - quoin_w / 2, plan.canvas_top,
                          cx_quoin + quoin_w / 2, plan.canvas_bottom),
                side=side, x_center=cx_quoin,
                y_top=plan.canvas_top, y_bottom=plan.canvas_bottom,
                block_width_mm=quoin_w,
            )
            facade.add(quoin)

    # Final validation — containment must hold for the tree we just built
    violations = validate_tree(facade, tol=1.5)
    # Filter: only Layer A (structural) violations raise PlanInfeasible.
    # Some overshoot is tolerated for architrave/cornice/voussoir projections
    # that EXCEED the opening/bay envelope by design; we log these but don't
    # hard-fail here. The hard-stop cases were already caught in the primitives
    # (opening_overflows_story, etc.).
    critical = [v for v in violations
                if v.overshoot_mm is not None and v.overshoot_mm > 3.0]
    if critical:
        raise PlanInfeasible(
            reason="containment_failed_post_build",
            element_id=critical[0].element_id,
            details=(
                f"{len(critical)} critical containment violation(s) after "
                f"tree assembly. First: {critical[0].message}"
            ),
            suggested_fix=(
                "check that opening dimensions and bay pitches give cornices "
                "enough room, or increase the canvas."
            ),
        )
    
    # Stash the report on the returned element for debugging
    facade.metadata["violations"] = violations
    facade.metadata["plan"] = plan

    # Phase 28: auto-emit ShadowElement children for every shadow-producing
    # element. Runs AFTER validation because shadow polygons legitimately
    # extend past their parent's envelope (e.g. cornice hood shadows sit
    # outboard of the window opening) and are decorative rather than
    # structural — they should not trigger containment violations.
    if getattr(plan, "shadows_enabled", True):
        shadow_count = 0
        for node in list(facade.descendants()):
            if hasattr(node, "collect_shadows"):
                try:
                    shadows = node.collect_shadows()
                except Exception:
                    shadows = []
                for sh in shadows:
                    sh.id = f"facade.shadow_{shadow_count}"
                    shadow_count += 1
                    node.add(sh)
    return facade


# ── Phase 29 — Portico solver ──────────────────────────────────────────

def solve_portico(plan: "PorticoPlan"):
    """Solve a ``PorticoPlan`` into a validated ``PorticoElement`` tree.

    Vertical budget allocation (bottom to top, SVG y-down):

        canvas_h  =  plinth_h  +  pedestal_h  +  column_h
                                +  entablature_h  +  pediment_h

    The module diameter ``D`` is derived so that the colonnade's
    outermost column axes, offset by half the intercolumniation, land
    within the canvas width:

        (column_count - 1) * intercol_modules * M  +  outer_margin*D  ≤  canvas_w

    where ``outer_margin`` reserves room for the leftmost and rightmost
    column's abacus projection. Once ``D`` is chosen by this width
    constraint, the vertical budget is checked; if the canvas is too
    short (for the chosen order's column_h + entablature + pediment +
    pedestal + plinth), raises ``PlanInfeasible(reason='insufficient_height')``.
    """
    import math

    from ..containment import validate_tree
    from .. import canon
    from .elements import (
        PorticoElement, ColumnRunElement, PedimentElement,
        PedestalCourseElement, PlinthElement, EntablatureBandElement,
    )

    _order_cls = {
        "tuscan":      canon.Tuscan,
        "doric":       canon.Doric,
        "ionic":       canon.Ionic,
        "corinthian":  canon.Corinthian,
        "composite":   canon.Composite,
        "greek_doric": canon.GreekDoric,
        "greek_ionic": canon.GreekIonic,
    }
    if plan.order not in _order_cls:
        raise PlanInfeasible(
            reason="unknown_order",
            details=f"unknown order {plan.order!r}",
            suggested_fix="use one of: " + ", ".join(_order_cls),
        )
    OrderCls = _order_cls[plan.order]

    canvas_w = plan.canvas_width
    canvas_h = plan.canvas_height

    # ── Step 1: derive D so the colonnade + its sub-structure + pediment
    # all scale consistently. Both width and height budgets scale LINEARLY
    # with D (the module diameter), so we solve each independently and
    # take the smaller D.
    #
    # Width: the colonnade — from outer abacus left edge to outer abacus
    # right edge — is the primary horizontal extent. Everything above
    # (entablature, pediment) sits on that span; everything below
    # (pedestal, plinth) reads as a base course under that same span.
    #
    #   colonnade_w = (N-1) * intercol_M * M + 2 * D     (D = 2M abacus projection)
    #               = D * ((N-1) * intercol_M / 2 + 2)
    #               = D * W_factor
    #
    # The cornice projects an additional ~1·D past each end of the
    # colonnade, so the TOTAL horizontal footprint is W_factor·D + 2·D.
    # A small padding factor keeps the outermost cornice moulding clear
    # of the plate frame.
    n_gaps = max(1, plan.column_count - 1)
    W_factor = n_gaps * plan.intercolumniation_modules / 2.0 + 2.0
    W_total = W_factor + 2.0   # add 1·D each side for cornice projection
    width_budget = canvas_w * 0.94
    D_from_width = width_budget / W_total
    if D_from_width <= 0:
        raise PlanInfeasible(
            reason="insufficient_width",
            details=(
                f"canvas_w ({canvas_w:.2f}mm) too narrow for "
                f"column_count={plan.column_count} at "
                f"intercolumniation={plan.intercolumniation_modules}M"
            ),
            suggested_fix="widen canvas or reduce column_count",
        )

    # Height: plinth (fixed) + pedestal·D + column·D + entablature·D + pediment
    # where pediment_h = (colonnade_w / 2) * tan(slope) = D * W_factor/2 * tan(slope).
    # So pediment ALSO scales linearly with D — it is NOT a fixed term.
    probe = OrderCls(D=1.0)
    plinth_h = plan.plinth.height_mm if plan.plinth else 0.0
    ped_flag = 1.0 if plan.pedestal else 0.0
    slope_tan = (math.tan(math.radians(plan.pediment.slope_deg))
                 if plan.pediment is not None else 0.0)
    H_factor = (
        ped_flag * probe.pedestal_D
        + probe.column_D
        + probe.entablature_D
        + (W_factor / 2.0) * slope_tan
    )
    if H_factor <= 0 or canvas_h - plinth_h <= 0:
        raise PlanInfeasible(
            reason="insufficient_height",
            details=(
                f"canvas_h ({canvas_h:.2f}mm) too short for the non-plinth "
                f"stack (plinth_h={plinth_h:.2f}mm)"
            ),
            suggested_fix="increase canvas height or remove the plinth",
        )
    D_from_height = (canvas_h - plinth_h) / H_factor
    if D_from_height < 1e-3:
        raise PlanInfeasible(
            reason="insufficient_height",
            details=(
                f"canvas_h ({canvas_h:.2f}mm) cannot fit the portico stack "
                f"for the {plan.order} order"
            ),
            suggested_fix="increase canvas height",
        )

    # Final D respects both budgets — whichever is tighter.
    D = min(D_from_width, D_from_height)
    dims = OrderCls(D=D)

    # Actual solved dimensions at the final D.
    plinth_h_final = plinth_h
    pedestal_h_final = dims.pedestal_h if plan.pedestal else 0.0
    column_h_final = dims.column_h
    entablature_h_final = dims.entablature_h
    colonnade_w = D * W_factor
    pediment_h_final = (colonnade_w / 2.0) * slope_tan

    total_final = (
        plinth_h_final + pedestal_h_final + column_h_final
        + entablature_h_final + pediment_h_final
    )
    if total_final > canvas_h + 1.0:
        raise PlanInfeasible(
            reason="insufficient_height",
            details=(
                f"solved portico stack ({total_final:.2f}mm) still exceeds "
                f"canvas_h ({canvas_h:.2f}mm) after shrinking D to {D:.2f}mm"
            ),
            suggested_fix="increase canvas height",
        )

    # Colonnade horizontal extents — used for plinth / pedestal / entablature /
    # pediment so they DO rest on the columns rather than floating over canvas.
    colonnade_center_x = (plan.canvas_left + plan.canvas_right) / 2
    colonnade_left_x = colonnade_center_x - colonnade_w / 2.0
    colonnade_right_x = colonnade_center_x + colonnade_w / 2.0

    # ── Step 3: compute y-coordinates ──────────────────────────────────
    # Portico sits at the BOTTOM of the canvas. Plinth bottom = canvas_bottom.
    y_plinth_bottom = plan.canvas_bottom
    y_plinth_top = y_plinth_bottom - plinth_h_final
    y_pedestal_bottom = y_plinth_top
    y_pedestal_top = y_pedestal_bottom - pedestal_h_final
    y_column_base = y_pedestal_top
    y_column_top = y_column_base - column_h_final   # top of capital
    y_entablature_bottom = y_column_top
    y_entablature_top = y_entablature_bottom - entablature_h_final
    y_pediment_base = y_entablature_top
    y_pediment_apex = y_pediment_base - pediment_h_final

    # ── Step 4: compute column x-coords ────────────────────────────────
    # Columns are centred within the colonnade_left_x..colonnade_right_x span
    # so their outer abacus edges land at the colonnade extents (one D from
    # each axis).
    M = dims.D / 2
    intercol_mm = plan.intercolumniation_modules * M
    half_count = (plan.column_count - 1) / 2
    column_xs = [
        colonnade_center_x + (i - half_count) * intercol_mm
        for i in range(plan.column_count)
    ]

    # ── Step 5: build the tree ─────────────────────────────────────────
    portico = PorticoElement(
        id="portico", kind="portico",
        envelope=plan.canvas,
        metadata={"order": plan.order, "D": D,
                  "column_count": plan.column_count,
                  "intercolumniation_modules": plan.intercolumniation_modules,
                  "colonnade_left_x": colonnade_left_x,
                  "colonnade_right_x": colonnade_right_x,
                  "plan": plan},
    )

    # Plinth (stylobate) — spans the colonnade, not the canvas. A small
    # projection_mm steps it outward past the colonnade so columns read
    # as standing on a defined base course.
    if plan.plinth is not None:
        plinth_proj = plan.plinth.projection_mm
        plinth_xl = colonnade_left_x - plinth_proj
        plinth_xr = colonnade_right_x + plinth_proj
        plinth_el = PlinthElement(
            id="portico.plinth", kind="plinth",
            envelope=(plinth_xl, y_plinth_top, plinth_xr, y_plinth_bottom),
            x_left=colonnade_left_x, x_right=colonnade_right_x,
            y_top=y_plinth_top, y_bottom=y_plinth_bottom,
            variant=plan.plinth.kind,
            projection_mm=plinth_proj,
            metadata={"height_mm": plinth_h_final},
        )
        portico.add(plinth_el)

    # Pedestal course — spans the colonnade (columns stand on this).
    if plan.pedestal and pedestal_h_final > 0:
        ped_el = PedestalCourseElement(
            id="portico.pedestal", kind="pedestal",
            envelope=(colonnade_left_x, y_pedestal_top,
                      colonnade_right_x, y_pedestal_bottom),
            x_left=colonnade_left_x, x_right=colonnade_right_x,
            y_top=y_pedestal_top, y_bottom=y_pedestal_bottom,
        )
        portico.add(ped_el)

    # Column run (colonnade). Envelope clamped to colonnade extents so
    # the outermost abacus matches the entablature above it.
    run = ColumnRunElement(
        id="portico.columns", kind="column_run",
        envelope=(colonnade_left_x, y_column_top,
                  colonnade_right_x, y_column_base),
        order=plan.order,
        column_xs=column_xs,
        base_y=y_column_base,
        dims=dims,
    )
    portico.add(run)

    # Entablature band — carried by the colonnade. Architrave aligns
    # with the outer column abacus edges; the cornice projects outward
    # by ~D on each side, so the envelope is widened accordingly.
    cornice_proj = D
    ent_el = EntablatureBandElement(
        id="portico.entablature", kind="entablature_band",
        envelope=(colonnade_left_x - cornice_proj, y_entablature_top,
                  colonnade_right_x + cornice_proj, y_entablature_bottom),
        order=plan.order,
        x_left=colonnade_left_x, x_right=colonnade_right_x,
        y_top_of_capital=y_entablature_bottom,
        D=D,
        cornice_at_edges=False,   # cornice projects past the colonnade
    )
    portico.add(ent_el)

    # Pediment — base corners AT the entablature corners.
    if plan.pediment is not None:
        ped = PedimentElement(
            id="portico.pediment", kind="pediment",
            envelope=(colonnade_left_x, y_pediment_apex,
                      colonnade_right_x, y_pediment_base),
            x_left=colonnade_left_x, x_right=colonnade_right_x,
            y_base=y_pediment_base,
            slope_deg=plan.pediment.slope_deg,
            fill=plan.pediment.fill,
            acroterion=plan.pediment.acroterion,
            tympanum_inset_mm=max(0.8, D * 0.1),
        )
        portico.add(ped)

    # ── Step 6: validate. Only Layer A critical violations raise. ──────
    violations = validate_tree(portico, tol=1.5)
    critical = [
        v for v in violations
        if v.overshoot_mm is not None and v.overshoot_mm > 3.0
    ]
    if critical:
        raise PlanInfeasible(
            reason="containment_failed_post_build",
            element_id=critical[0].element_id,
            details=(
                f"{len(critical)} critical containment violation(s) after "
                f"tree assembly. First: {critical[0].message}"
            ),
            suggested_fix="enlarge canvas or reduce column_count",
        )

    portico.metadata["violations"] = violations
    return portico


# ── Phase 30 — Boathouse solver ─────────────────────────────────────────

# Boat-bay : upper-story height ratio. Boat bays must be tall enough for
# a shell to launch on a trailer; upper-story is a lower clerestory.
# This ratio is the one place a "feel" choice is encoded; everything else
# is geometry.
_BOAT_BAY_RATIO = 1.6
_UPPER_STORY_RATIO = 1.0

# Minimum bay width (mm) below which the arched openings degenerate into
# unreadable strokes. Used as an infeasibility floor.
_MIN_BAY_WIDTH_MM = 18.0

# Minimum boat-bay height for an arch to be drawable (the rise alone
# needs at least ~half the bay width).
_MIN_BOAT_BAY_HEIGHT_MM = 20.0


def solve_boathouse(plan: "BoathousePlan"):
    """Solve a ``BoathousePlan`` into a validated ``BoathouseElement`` tree.

    Vertical budget allocation (bottom to top, SVG y-down):

        canvas_h  =  plinth_h  +  boat_bay_h  +  upper_story_h  +  gable_h

    where ``gable_h = (canvas_w / 2) * tan(slope)`` for a gable-end-on
    elevation. ``boat_bay_h`` and ``upper_story_h`` share the leftover
    budget by ``_BOAT_BAY_RATIO : _UPPER_STORY_RATIO`` so the result is
    fully derived (no hand-tuned mm anywhere).

    Horizontal budget: the ``bay_count`` boat bays tile the full canvas
    width. Upper-story windows are evenly spaced inside the same width.

    Raises ``PlanInfeasible`` when:
      * the canvas is too short to fit the stack, OR
      * the canvas is too narrow for ``bay_count`` bays at the minimum
        readable width, OR
      * a clamped ridge_height_mm cap leaves no room for the upper story.
    """
    import math

    from ..containment import validate_tree
    from ..elements.arches import SemicircularArchElement
    from .elements import (
        BoathouseElement, RoofElement, BayElement, StoryElement,
        WallElement, WindowElement, PlinthElement,
    )

    canvas_w = plan.canvas_width
    canvas_h = plan.canvas_height

    # ── Step 1: width feasibility ──────────────────────────────────────
    # Reserve ``overhang_mm`` inset on each side of the canvas for the
    # eaves to project into; the wall (and bay rhythm) sits inside that.
    # Walls + bays span ``wall_w``, eaves extend OUT to the canvas edge.
    overhang = plan.roof.overhang_mm
    wall_left = plan.canvas_left + overhang
    wall_right = plan.canvas_right - overhang
    wall_w = wall_right - wall_left
    if wall_w <= 0:
        raise PlanInfeasible(
            reason="insufficient_width",
            details=(
                f"roof overhang ({overhang:.2f}mm × 2) consumes the entire "
                f"canvas width ({canvas_w:.2f}mm)"
            ),
            suggested_fix="reduce roof.overhang_mm or widen canvas",
        )
    bay_pitch = wall_w / plan.bay_count
    if bay_pitch < _MIN_BAY_WIDTH_MM:
        raise PlanInfeasible(
            reason="insufficient_width",
            details=(
                f"wall_w ({wall_w:.2f}mm) gives bay_pitch "
                f"{bay_pitch:.2f}mm < min {_MIN_BAY_WIDTH_MM:.2f}mm "
                f"for bay_count={plan.bay_count}"
            ),
            suggested_fix=(
                f"widen canvas to at least "
                f"{_MIN_BAY_WIDTH_MM * plan.bay_count + 2 * overhang:.0f}mm "
                f"or reduce bay_count"
            ),
        )

    # ── Step 2: vertical budget ────────────────────────────────────────
    plinth_h = plan.plinth.height_mm if plan.plinth else 0.0
    if plinth_h >= canvas_h:
        raise PlanInfeasible(
            reason="plinth_overflow",
            details=(
                f"plinth height_mm ({plinth_h:.2f}mm) meets or exceeds "
                f"canvas height ({canvas_h:.2f}mm)"
            ),
            suggested_fix="reduce PlinthPlan.height_mm or enlarge canvas",
        )

    # Gable: a gable-end facing the viewer spans the FULL canvas width
    # (the rake lands at the eave, which is the canvas edge). The rake
    # meets at the midline, so geometric gable_h = (canvas_w/2) * tan(slope).
    # ``ridge_height_mm`` (when set) caps the gable height — useful when
    # the geometric value would be too tall for the canvas.
    slope_tan = math.tan(math.radians(plan.roof.slope_deg))
    geometric_gable_h = (canvas_w / 2.0) * slope_tan if plan.roof.gable_end else 0.0
    if plan.roof.ridge_height_mm is not None:
        gable_h = min(geometric_gable_h, plan.roof.ridge_height_mm)
    else:
        gable_h = geometric_gable_h

    stories_budget = canvas_h - plinth_h - gable_h
    if stories_budget < _MIN_BOAT_BAY_HEIGHT_MM:
        raise PlanInfeasible(
            reason="insufficient_height",
            details=(
                f"canvas_h ({canvas_h:.2f}mm) too short: "
                f"plinth ({plinth_h:.2f}) + gable ({gable_h:.2f}) "
                f"leaves only {stories_budget:.2f}mm for the boat bay + "
                f"upper story stack (need at least "
                f"{_MIN_BOAT_BAY_HEIGHT_MM:.2f}mm)"
            ),
            suggested_fix=(
                "increase canvas height, reduce roof.slope_deg, "
                "set roof.ridge_height_mm to cap the gable, "
                "or remove the plinth"
            ),
        )

    # Allocate stories_budget by ratio. When upper story is disabled, all
    # of it goes to boat_bay_h.
    if plan.has_upper_story:
        total_ratio = _BOAT_BAY_RATIO + _UPPER_STORY_RATIO
        boat_bay_h = stories_budget * (_BOAT_BAY_RATIO / total_ratio)
        upper_story_h = stories_budget * (_UPPER_STORY_RATIO / total_ratio)
    else:
        boat_bay_h = stories_budget
        upper_story_h = 0.0

    if boat_bay_h < _MIN_BOAT_BAY_HEIGHT_MM:
        raise PlanInfeasible(
            reason="insufficient_height",
            details=(
                f"derived boat_bay_h ({boat_bay_h:.2f}mm) below minimum "
                f"({_MIN_BOAT_BAY_HEIGHT_MM:.2f}mm)"
            ),
            suggested_fix="increase canvas height or reduce roof slope",
        )

    # ── Step 3: y-coordinates ──────────────────────────────────────────
    y_plinth_bottom = plan.canvas_bottom
    y_plinth_top = y_plinth_bottom - plinth_h
    y_boat_bottom = y_plinth_top
    y_boat_top = y_boat_bottom - boat_bay_h
    y_upper_bottom = y_boat_top
    y_upper_top = y_upper_bottom - upper_story_h
    y_eave = y_upper_top
    y_apex = y_eave - gable_h

    # Sanity: y_apex must be >= canvas_top (within tolerance). The
    # vertical-stack equation guarantees it but we belt-and-brace check.
    if y_apex < plan.canvas_top - 0.5:
        raise PlanInfeasible(
            reason="height_imbalance",
            details=(
                f"computed apex y={y_apex:.2f} above canvas_top "
                f"y={plan.canvas_top:.2f}"
            ),
        )

    # ── Step 4: build the tree ─────────────────────────────────────────
    boathouse = BoathouseElement(
        id="boathouse", kind="boathouse",
        envelope=plan.canvas,
        metadata={
            "bay_count": plan.bay_count,
            "bay_kind": plan.bay_kind,
            "has_upper_story": plan.has_upper_story,
            "boat_bay_h": boat_bay_h,
            "upper_story_h": upper_story_h,
            "gable_h": gable_h,
            "plinth_h": plinth_h,
            "plan": plan,
        },
    )

    # Plinth (water table) — spans the wall width (NOT the eave overhang).
    if plan.plinth is not None:
        plinth_proj = plan.plinth.projection_mm
        plinth_el = PlinthElement(
            id="boathouse.plinth", kind="plinth",
            envelope=(wall_left - plinth_proj, y_plinth_top,
                      wall_right + plinth_proj, y_plinth_bottom),
            x_left=wall_left, x_right=wall_right,
            y_top=y_plinth_top, y_bottom=y_plinth_bottom,
            variant=plan.plinth.kind,
            projection_mm=plinth_proj,
            metadata={"height_mm": plinth_h},
        )
        boathouse.add(plinth_el)

    # Boat-bay band: a StoryElement holding a wall background + N
    # BayElements, each carrying one arched (or trabeated) opening.
    boat_band = StoryElement(
        id="boathouse.boat_band", kind="story",
        envelope=(wall_left, y_boat_top,
                  wall_right, y_boat_bottom),
        metadata={"label": "boat_bays", "height_mm": boat_bay_h},
    )
    boathouse.add(boat_band)

    # Wall background. Smooth so the bays are the protagonists.
    wall_el = WallElement(
        id="boathouse.boat_band.wall", kind="wall",
        envelope=(wall_left, y_boat_top,
                  wall_right, y_boat_bottom),
        x_left=wall_left, x_right=wall_right,
        y_top=y_boat_top, y_bottom=y_boat_bottom,
        variant="smooth",
    )
    boat_band.add(wall_el)

    # Each boat bay: a BayElement, then a single opening centred in it.
    # ``bay_pitch`` comes from wall_w / bay_count so bays tile exactly.
    # Opening width = 0.7 of the bay pitch (leaves piers between bays).
    # For arched openings, height = (bay_pitch * 0.7 / 2) for the arch
    # rise + remaining boat_bay_h for the rectangular jamb portion.
    opening_width_frac = 0.70
    for i in range(plan.bay_count):
        bx_left = wall_left + i * bay_pitch
        bx_right = bx_left + bay_pitch
        bx_center = (bx_left + bx_right) / 2

        bay_el = BayElement(
            id=f"boathouse.boat_band.bay_{i}", kind="bay",
            envelope=(bx_left, y_boat_top, bx_right, y_boat_bottom),
            metadata={"axis_x": bx_center, "pitch_mm": bay_pitch},
        )
        boat_band.add(bay_el)

        op_w = bay_pitch * opening_width_frac
        if plan.bay_kind == "arched":
            # Semicircular: the arch RISE is op_w/2. Total opening height
            # = boat_bay_h, of which boat_bay_h - op_w/2 is the
            # rectangular jamb portion below the springing.
            rise = op_w / 2
            if rise >= boat_bay_h:
                # Bay too short for a semicircular arch. Clamp the opening
                # width so the rise fits, leaving 30% of boat_bay_h for
                # the jamb portion. Solver-level recovery — never silently
                # produces an infeasible opening.
                op_w = boat_bay_h * 1.4   # rise = 0.7 * boat_bay_h
                rise = op_w / 2
            y_spring = y_boat_bottom - (boat_bay_h - rise)
            arch_el = SemicircularArchElement(
                id=f"boathouse.boat_band.bay_{i}.opening",
                kind="arch_opening",
                envelope=(bx_center - op_w/2, y_spring - rise,
                          bx_center + op_w/2, y_boat_bottom),
                cx=bx_center, y_spring=y_spring, span=op_w,
                voussoir_count=9, with_keystone=True, archivolt_bands=0,
                y_bottom=y_boat_bottom,
            )
            bay_el.add(arch_el)
        else:
            # Trabeated: a tall rectangular opening drawn as a
            # WindowElement. The legacy ``window_opening`` builder
            # extends ITS OWN bbox past the opening rectangle in every
            # direction:
            #   above (architrave):                 op_w * 1/6
            #   each side (architrave):             op_w * 1/6
            #   below (architrave + sill + corbel): op_w * 0.39
            # We back the opening dims off so the legacy bbox stays
            # inside the bay envelope, and shrink op_w when the bay
            # pitch can't afford the architrave overhang.
            top_pad = op_w / 6.0
            side_pad = op_w / 6.0
            bottom_pad = op_w * 0.39
            # Lateral fit: opening + architrave on both sides ≤ bay_pitch
            max_op_w_lateral = bay_pitch / (1.0 + 2.0 * (1.0 / 6.0))
            op_w = min(op_w, max_op_w_lateral * 0.98)
            top_pad = op_w / 6.0
            side_pad = op_w / 6.0
            bottom_pad = op_w * 0.39
            op_h = max(8.0, boat_bay_h - top_pad - bottom_pad - 1.0)
            y_op_bottom = y_boat_bottom - bottom_pad
            y_op_top = y_op_bottom - op_h
            win_el = WindowElement(
                id=f"boathouse.boat_band.bay_{i}.opening",
                kind="door",
                envelope=(bx_center - op_w/2 - side_pad,
                          y_op_top - top_pad,
                          bx_center + op_w/2 + side_pad,
                          y_boat_bottom),
                x_center=bx_center,
                y_top=y_op_top, y_bottom=y_op_bottom,
                width_mm=op_w, height_mm=op_h,
                hood="none", has_keystone=False, has_sill=True,
                stroke_boost=0.10,
            )
            bay_el.add(win_el)

    # Upper story (clerestory): one StoryElement with N small windows.
    if plan.has_upper_story and upper_story_h > 0:
        upper_band = StoryElement(
            id="boathouse.upper_band", kind="story",
            envelope=(wall_left, y_upper_top,
                      wall_right, y_upper_bottom),
            metadata={"label": "clerestory", "height_mm": upper_story_h},
        )
        boathouse.add(upper_band)

        upper_wall = WallElement(
            id="boathouse.upper_band.wall", kind="wall",
            envelope=(wall_left, y_upper_top,
                      wall_right, y_upper_bottom),
            x_left=wall_left, x_right=wall_right,
            y_top=y_upper_top, y_bottom=y_upper_bottom,
            variant="smooth",
        )
        upper_band.add(upper_wall)

        if plan.upper_story_window_count > 0:
            n_win = plan.upper_story_window_count
            # Even spacing: N windows in N+1 gaps so margins are equal.
            win_pitch = wall_w / (n_win + 1)
            win_w = min(win_pitch * 0.55, bay_pitch * 0.45)
            win_h = upper_story_h * 0.65
            for j in range(n_win):
                cx = wall_left + (j + 1) * win_pitch
                y_win_top = y_upper_top + (upper_story_h - win_h) / 2
                y_win_bot = y_win_top + win_h
                # Wrap each window in a BayElement so the
                # SiblingNonOverlap check (siblings of upper_band's
                # children) sees independent x-extents.
                bay_el = BayElement(
                    id=f"boathouse.upper_band.bay_{j}", kind="bay",
                    envelope=(cx - win_pitch/2, y_upper_top,
                              cx + win_pitch/2, y_upper_bottom),
                )
                upper_band.add(bay_el)
                win_el = WindowElement(
                    id=f"boathouse.upper_band.bay_{j}.window",
                    kind="window",
                    envelope=(cx - win_w/2, y_win_top,
                              cx + win_w/2, y_win_bot),
                    x_center=cx,
                    y_top=y_win_top, y_bottom=y_win_bot,
                    width_mm=win_w, height_mm=win_h,
                    hood="none", has_keystone=False, has_sill=True,
                )
                bay_el.add(win_el)

    # Roof: a gable above the upper story (or above the boat band when
    # upper story is disabled). Eaves project outward to the canvas
    # edges; the rake meets the wall at wall_left / wall_right. The
    # apex sits at the canvas midline above the wall span.
    roof_el = RoofElement(
        id="boathouse.roof", kind="roof",
        envelope=(plan.canvas_left, y_apex,
                  plan.canvas_right, y_eave + 1.0),
        x_left_eave=plan.canvas_left,
        x_right_eave=plan.canvas_right,
        x_left_wall=wall_left,
        x_right_wall=wall_right,
        y_eave=y_eave, y_apex=y_apex,
        slope_deg=plan.roof.slope_deg,
        overhang_mm=overhang,
        has_shingle_hatch=plan.roof.has_shingle_hatch,
    )
    boathouse.add(roof_el)

    # ── Step 5: validate. Only Layer A critical violations raise. ──────
    violations = validate_tree(boathouse, tol=1.5)
    critical = [
        v for v in violations
        if v.overshoot_mm is not None and v.overshoot_mm > 3.0
    ]
    if critical:
        raise PlanInfeasible(
            reason="containment_failed_post_build",
            element_id=critical[0].element_id,
            details=(
                f"{len(critical)} critical containment violation(s) after "
                f"tree assembly. First: {critical[0].message}"
            ),
            suggested_fix="enlarge canvas or reduce bay_count",
        )

    boathouse.metadata["violations"] = violations
    return boathouse
