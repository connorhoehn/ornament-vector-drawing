import pytest
from engraving.planner import (FacadePlan, StoryPlan, BayPlan, OpeningPlan,
                                ParapetPlan, PlanInfeasible)
from engraving.planner.solver import (solve_story_heights, solve_bay_layout,
                                       solve_openings)


class TestStoryHeights:
    def test_equal_ratios_divide_evenly(self):
        plan = FacadePlan(
            canvas=(0, 0, 200, 300),
            stories=[StoryPlan(height_ratio=1.0), StoryPlan(height_ratio=1.0),
                     StoryPlan(height_ratio=1.0)],
            bays=[BayPlan(openings=[OpeningPlan() for _ in range(3)])],
        )
        layouts, _, _ = solve_story_heights(plan)
        assert len(layouts) == 3
        assert all(abs(l.height_mm - 100.0) < 0.5 for l in layouts)

    def test_story_order_bottom_to_top(self):
        plan = FacadePlan(
            canvas=(0, 0, 200, 300),
            stories=[StoryPlan(height_ratio=1.0, label="ground"),
                     StoryPlan(height_ratio=1.5, label="piano"),
                     StoryPlan(height_ratio=0.5, label="attic")],
            bays=[BayPlan(openings=[OpeningPlan() for _ in range(3)])],
        )
        layouts, _, _ = solve_story_heights(plan)
        # Bottom story (index 0) has the largest y_bottom (closer to canvas_bottom)
        assert layouts[0].y_bottom == 300
        assert layouts[0].y_top < layouts[0].y_bottom
        # Successive stories stack upward
        assert layouts[1].y_bottom == layouts[0].y_top
        assert layouts[2].y_bottom == layouts[1].y_top

    def test_min_height_respected(self):
        plan = FacadePlan(
            canvas=(0, 0, 200, 300),
            stories=[StoryPlan(height_ratio=0.1, min_height_mm=80),
                     StoryPlan(height_ratio=2.0)],
            bays=[BayPlan(openings=[OpeningPlan(), OpeningPlan()])],
        )
        layouts, _, _ = solve_story_heights(plan)
        # Story 0 naive would be 300 * 0.1/2.1 ≈ 14mm < 80; pinned at 80
        assert layouts[0].height_mm >= 79.5
        # Story 1 gets the remainder
        assert layouts[1].height_mm >= 219.5

    def test_infeasible_min_heights_raise(self):
        plan = FacadePlan(
            canvas=(0, 0, 200, 100),
            stories=[StoryPlan(height_ratio=1.0, min_height_mm=60),
                     StoryPlan(height_ratio=1.0, min_height_mm=60)],
            bays=[BayPlan(openings=[OpeningPlan(), OpeningPlan()])],
        )
        with pytest.raises(PlanInfeasible) as exc:
            solve_story_heights(plan)
        assert exc.value.reason == "insufficient_height"

    def test_parapet_allocated(self):
        plan = FacadePlan(
            canvas=(0, 0, 200, 400),
            stories=[StoryPlan(height_ratio=1.0)],
            bays=[BayPlan(openings=[OpeningPlan()])],
            parapet=ParapetPlan(kind="balustrade", height_ratio=0.25),
        )
        layouts, parapet, _ = solve_story_heights(plan)
        assert parapet is not None
        # Parapet gets 0.25 / 1.25 = 20% of canvas_h = 80
        assert abs(parapet.height_mm - 80) < 0.5

    def test_story_heights_respect_ratios_when_unpinned(self):
        """Phase 24 Day 1: when no ``min_height_mm`` floor is active, the
        constraint solver should honor the declared height_ratios. With
        ratios 1 and 2 the upper story should be ~2× the lower."""
        plan = FacadePlan(
            canvas=(0, 0, 200, 300),
            stories=[StoryPlan(height_ratio=1.0),
                     StoryPlan(height_ratio=2.0)],
            bays=[BayPlan(openings=[OpeningPlan(), OpeningPlan()])],
        )
        layouts, _, _ = solve_story_heights(plan)
        # Story 1 should be ~2x story 0 within 20% tolerance
        assert 1.6 <= layouts[1].height_mm / layouts[0].height_mm <= 2.4


class TestBayLayout:
    def test_equal_bays_equal_pitch(self):
        plan = FacadePlan(
            canvas=(0, 0, 300, 200),
            stories=[StoryPlan()],
            bays=[BayPlan(openings=[OpeningPlan()]) for _ in range(5)],
        )
        bays = solve_bay_layout(plan)
        assert len(bays) == 5
        expected_pitch = 300 / 5
        assert all(abs(b.pitch_mm - expected_pitch) < 0.01 for b in bays)
        # First bay centered at 30, last at 270
        assert abs(bays[0].axis_x - 30) < 0.01
        assert abs(bays[-1].axis_x - 270) < 0.01

    def test_weighted_bays(self):
        plan = FacadePlan(
            canvas=(0, 0, 300, 200),
            stories=[StoryPlan()],
            bays=[BayPlan(openings=[OpeningPlan()], width_weight=1.0),
                   BayPlan(openings=[OpeningPlan()], width_weight=2.0),  # central double
                   BayPlan(openings=[OpeningPlan()], width_weight=1.0)],
        )
        bays = solve_bay_layout(plan)
        # Total weight 4; pitches 75, 150, 75
        assert abs(bays[0].pitch_mm - 75) < 0.1
        assert abs(bays[1].pitch_mm - 150) < 0.1
        assert abs(bays[2].pitch_mm - 75) < 0.1


class TestOpenings:
    def test_opening_width_is_frac_of_pitch(self):
        # Narrow opening + tall story keeps the Phase-31 sill reservation
        # (0.40·w below the rect) well inside story.height_mm so the test
        # isolates the width_frac × pitch identity rather than tripping
        # the overflow check.
        plan = FacadePlan(
            canvas=(0, 0, 500, 1000),
            stories=[StoryPlan(height_ratio=1.0)],
            bays=[BayPlan(openings=[OpeningPlan(width_frac=0.2, height_frac=0.6)])],
        )
        stories, _, _ = solve_story_heights(plan)
        bays = solve_bay_layout(plan)
        # pitch = 500; opening width = 100
        opening_layout = solve_openings(plan, stories, bays)
        assert abs(opening_layout[0][0].width_mm - 100) < 0.1
        assert abs(opening_layout[0][0].height_mm - 600) < 0.1   # 0.6 * 1000

    def test_arch_rise_semicircular(self):
        plan = FacadePlan(
            canvas=(0, 0, 100, 200),
            stories=[StoryPlan(height_ratio=1.0)],
            bays=[BayPlan(openings=[OpeningPlan(kind="arch_window",
                                                 width_frac=0.5,
                                                 height_frac=0.3)])],
        )
        stories, _, _ = solve_story_heights(plan)
        bays = solve_bay_layout(plan)
        # width = 50, rise = 25, height = 60
        opening_layout = solve_openings(plan, stories, bays)
        o = opening_layout[0][0]
        assert abs(o.width_mm - 50) < 0.1
        assert abs(o.rise_mm - 25) < 0.1
        assert abs(o.height_mm - 60) < 0.1
        # effective_top should be story top + rise above y_top
        assert o.effective_top == o.y_top - o.rise_mm

    def test_arch_overflow_caught(self):
        """THE USER-FLAGGED BUG. Arch whose rise exceeds story height
        should be refused."""
        plan = FacadePlan(
            canvas=(0, 0, 200, 100),
            stories=[StoryPlan(height_ratio=1.0)],  # 100mm tall
            bays=[BayPlan(openings=[OpeningPlan(kind="arch_window",
                                                 width_frac=0.9,     # 180mm wide → rise 90
                                                 height_frac=0.5)])],  # h=50
        )
        stories, _, _ = solve_story_heights(plan)
        bays = solve_bay_layout(plan)
        # total = 50 + 90 = 140mm; story is 100mm → infeasible
        with pytest.raises(PlanInfeasible) as exc:
            solve_openings(plan, stories, bays)
        assert exc.value.reason == "opening_overflows_story"

    def test_hierarchy_violation_caught(self):
        """Upper opening wider than lower should be rejected. Uses tall
        stories and narrow heights so the sill-reservation overflow check
        (Phase 31) doesn't fire first — this test specifically targets
        the opening-hierarchy rule."""
        plan = FacadePlan(
            canvas=(0, 0, 400, 1000),
            stories=[StoryPlan(height_ratio=1.0), StoryPlan(height_ratio=1.0)],
            bays=[BayPlan(openings=[
                OpeningPlan(width_frac=0.2, height_frac=0.3),  # ground: small
                OpeningPlan(width_frac=0.5, height_frac=0.3),  # upper: WIDER — wrong
            ])],
        )
        stories, _, _ = solve_story_heights(plan)
        bays = solve_bay_layout(plan)
        with pytest.raises(PlanInfeasible) as exc:
            solve_openings(plan, stories, bays)
        assert exc.value.reason == "opening_hierarchy_violated"


# ── Day 9 — Pilaster + string-course tests ─────────────────────────────

from engraving.planner import PilasterPlan
from engraving.planner.solver import (solve_pilasters, solve_string_courses,
                                       PilasterLayout, StringCourseLayout)


class TestPilasterLayout:
    def test_pilaster_only_on_ordered_stories(self):
        plan = FacadePlan(
            canvas=(0, 0, 200, 300),
            stories=[
                StoryPlan(height_ratio=1.0, wall="smooth"),   # no order
                StoryPlan(height_ratio=1.0, has_order="ionic"),
                StoryPlan(height_ratio=1.0, wall="smooth"),
            ],
            bays=[BayPlan(
                openings=[OpeningPlan() for _ in range(3)],
                pilasters=PilasterPlan(order="ionic", width_frac=0.08),
            )],
        )
        stories, _, _ = solve_story_heights(plan)
        bays = solve_bay_layout(plan)
        pilasters = solve_pilasters(plan, stories, bays)
        # Only the Ionic story (index 1) has pilasters; 2 per bay × 1 bay = 2
        assert len(pilasters) == 2
        assert all(p.story_index == 1 for p in pilasters)
        sides = {p.side for p in pilasters}
        assert sides == {"left", "right"}

    def test_pilasters_flank_bay(self):
        plan = FacadePlan(
            canvas=(0, 0, 400, 200),
            stories=[StoryPlan(height_ratio=1.0, has_order="ionic")],
            bays=[BayPlan(
                openings=[OpeningPlan()],
                pilasters=PilasterPlan(order="ionic", width_frac=0.1),
            )],
        )
        stories, _, _ = solve_story_heights(plan)
        bays = solve_bay_layout(plan)
        pilasters = solve_pilasters(plan, stories, bays)
        # Single bay at axis_x=200; pilasters should be on either side
        left = next(p for p in pilasters if p.side == "left")
        right = next(p for p in pilasters if p.side == "right")
        assert left.cx < 200
        assert right.cx > 200
        # Symmetric about bay axis
        assert abs((200 - left.cx) - (right.cx - 200)) < 0.5


class TestStringCourses:
    def test_string_course_between_adjacent_stories(self):
        plan = FacadePlan(
            canvas=(0, 0, 200, 300),
            stories=[StoryPlan(height_ratio=1.0), StoryPlan(height_ratio=1.0),
                     StoryPlan(height_ratio=1.0)],
            bays=[BayPlan(openings=[OpeningPlan() for _ in range(3)])],
        )
        stories, _, _ = solve_story_heights(plan)
        courses = solve_string_courses(plan, stories)
        # 3 stories → 2 courses
        assert len(courses) == 2
        # First course at shared edge between story 0 and 1
        assert abs(courses[0].y_center - stories[0].y_top) < 0.01
        # Course spans full canvas width
        assert courses[0].x_left == 0
        assert courses[0].x_right == 200

    def test_no_course_for_single_story(self):
        plan = FacadePlan(
            canvas=(0, 0, 200, 100),
            stories=[StoryPlan(height_ratio=1.0)],
            bays=[BayPlan(openings=[OpeningPlan()])],
        )
        stories, _, _ = solve_story_heights(plan)
        courses = solve_string_courses(plan, stories)
        assert courses == []


class TestEntablatureBand:
    def test_entablature_band_over_ordered_story(self):
        from engraving.planner import (FacadePlan, StoryPlan, BayPlan,
                                        OpeningPlan, PilasterPlan)
        plan = FacadePlan(
            canvas=(0, 0, 300, 250),
            stories=[
                StoryPlan(height_ratio=1.0),
                StoryPlan(height_ratio=1.4, has_order="ionic"),
                StoryPlan(height_ratio=0.85),
            ],
            bays=[BayPlan(openings=[
                OpeningPlan(width_frac=0.4, height_frac=0.5),
                OpeningPlan(width_frac=0.35, height_frac=0.55),
                OpeningPlan(width_frac=0.30, height_frac=0.45),
            ], pilasters=PilasterPlan(order="ionic", width_frac=0.08))
                for _ in range(5)],
        )
        facade = plan.solve()
        # There should be at least one EntablatureBandElement
        from engraving.planner.elements import EntablatureBandElement
        bands = [n for n in facade.descendants()
                 if isinstance(n, EntablatureBandElement)]
        assert len(bands) >= 1

    def test_entablature_band_replaces_string_course_only_for_ordered(self):
        """Stories WITHOUT has_order should still get plain string
        courses above them; only ordered stories get the full band."""
        from engraving.planner import (FacadePlan, StoryPlan, BayPlan,
                                        OpeningPlan, PilasterPlan)
        from engraving.planner.elements import (EntablatureBandElement,
                                                 StringCourseElement)
        plan = FacadePlan(
            canvas=(0, 0, 300, 300),
            stories=[
                StoryPlan(height_ratio=1.0),                         # plain
                StoryPlan(height_ratio=1.4, has_order="ionic"),     # ordered
                StoryPlan(height_ratio=0.85),                        # plain
            ],
            bays=[BayPlan(openings=[
                OpeningPlan(width_frac=0.4, height_frac=0.5),
                OpeningPlan(width_frac=0.35, height_frac=0.55),
                OpeningPlan(width_frac=0.30, height_frac=0.45),
            ], pilasters=PilasterPlan(order="ionic", width_frac=0.08))
                for _ in range(3)],
        )
        facade = plan.solve()
        bands = [n for n in facade.descendants()
                 if isinstance(n, EntablatureBandElement)]
        courses = [n for n in facade.descendants()
                   if isinstance(n, StringCourseElement)]
        # Story 0 (plain) → string course between it and story 1 (ordered)
        # Story 1 (ordered) → entablature band between it and story 2 (plain)
        assert len(bands) == 1
        assert len(courses) == 1

    def test_entablature_band_spans_full_canvas(self):
        from engraving.planner import (FacadePlan, StoryPlan, BayPlan,
                                        OpeningPlan, PilasterPlan)
        from engraving.planner.elements import EntablatureBandElement
        plan = FacadePlan(
            canvas=(10, 0, 310, 250),
            stories=[
                StoryPlan(height_ratio=1.0, has_order="ionic"),
                StoryPlan(height_ratio=1.0),
            ],
            bays=[BayPlan(openings=[
                OpeningPlan(width_frac=0.4, height_frac=0.5),
                OpeningPlan(width_frac=0.35, height_frac=0.45),
            ], pilasters=PilasterPlan(order="ionic", width_frac=0.08))
                for _ in range(3)],
        )
        facade = plan.solve()
        bands = [n for n in facade.descendants()
                 if isinstance(n, EntablatureBandElement)]
        assert len(bands) == 1
        band = bands[0]
        # Phase 24 Day 2: the entablature's x_left/x_right are inset from
        # canvas edges by the cornice projection so the cornice overhang
        # stays within the canvas (containment_failed_post_build fix).
        # Inset = 0.5 * D; D is derived from pilaster width.
        # For this plan: bay pitch = 300/3 = 100, pilaster width_frac=0.08
        # → D = 8.0, so cornice_projection = 4.0.
        assert band.x_left >= 10 - 0.01
        assert band.x_right <= 310 + 0.01
        # Confirm the band + cornice overhang lies within the canvas
        bx = band.effective_bbox()
        assert bx[0] >= 10 - 0.5
        assert bx[2] <= 310 + 0.5


def test_plan_to_elements_smoke():
    """End-to-end sanity: a simple plan produces layout objects that can
    be used to construct Elements. (Full Element tree assembly is Day 10.)"""
    from engraving.element import Element
    from engraving.elements.columns import column_for
    from engraving import canon

    plan = FacadePlan(
        canvas=(0, 0, 300, 200),
        stories=[StoryPlan(height_ratio=1.0, has_order="ionic")],
        bays=[BayPlan(
            openings=[OpeningPlan(width_frac=0.4, height_frac=0.6)],
            pilasters=PilasterPlan(order="ionic", width_frac=0.08),
        )],
    )
    stories, _, _ = solve_story_heights(plan)
    bays = solve_bay_layout(plan)
    openings = solve_openings(plan, stories, bays)
    pilasters = solve_pilasters(plan, stories, bays)

    # All layouts produced
    assert len(stories) == 1
    assert len(bays) == 1
    assert len(openings) == 1 and len(openings[0]) == 1
    assert len(pilasters) == 2   # left + right ionic pilaster


class TestWindowRichness:
    def test_window_with_triangular_pediment_renders(self):
        from engraving.planner.elements import WindowElement
        w = WindowElement(
            id="w", kind="window",
            envelope=(0, 0, 50, 100),
            x_center=25, y_top=30, y_bottom=70,
            width_mm=30, height_mm=40,
            hood="triangular", has_keystone=True,
        )
        strokes = list(w.render_strokes())
        assert len(strokes) > 5  # opening + architrave + sill + hood + keystone + ...

    def test_window_without_hood_simpler(self):
        from engraving.planner.elements import WindowElement
        w = WindowElement(
            id="w", kind="window",
            envelope=(0, 0, 50, 100),
            x_center=25, y_top=30, y_bottom=70,
            width_mm=30, height_mm=40,
            hood="none", has_keystone=False, has_sill=True,
        )
        strokes_no_hood = list(w.render_strokes())
        w2 = WindowElement(
            id="w2", kind="window",
            envelope=(0, 0, 50, 100),
            x_center=25, y_top=30, y_bottom=70,
            width_mm=30, height_mm=40,
            hood="triangular", has_keystone=True, has_sill=True,
        )
        strokes_with_hood = list(w2.render_strokes())
        assert len(strokes_with_hood) > len(strokes_no_hood)


class TestParapet:
    """ParapetElement should emit real balustrade geometry (rails, balusters,
    optional pedestals) rather than a silent empty band."""

    def test_balustrade_parapet_renders_balusters(self):
        from engraving.planner.elements import ParapetElement
        p = ParapetElement(
            id="par", kind="balustrade",
            envelope=(0, 0, 200, 20),
            x_left=0, x_right=200, y_top=0, y_bottom=20,
        )
        strokes = list(p.render_strokes())
        # Expect multiple rail segments + many baluster polylines — well
        # above any trivial fixed count.
        assert len(strokes) > 5

    def test_balustrade_parapet_with_pedestals(self):
        from engraving.planner.elements import ParapetElement
        p = ParapetElement(
            id="par", kind="balustrade",
            envelope=(0, 0, 200, 20),
            x_left=0, x_right=200, y_top=0, y_bottom=20,
            pedestal_positions=[50.0, 100.0, 150.0],
        )
        strokes = list(p.render_strokes())
        # Pedestals add their own outlines on top of the rails + balusters.
        assert len(strokes) > 10

    def test_attic_parapet_solid_rectangle(self):
        from engraving.planner.elements import ParapetElement
        p = ParapetElement(
            id="par", kind="attic",
            envelope=(0, 0, 200, 20),
            x_left=0, x_right=200, y_top=0, y_bottom=20,
        )
        strokes = list(p.render_strokes())
        # Rectangle = four sides.
        assert len(strokes) == 4

    def test_cornice_parapet_single_rule(self):
        from engraving.planner.elements import ParapetElement
        p = ParapetElement(
            id="par", kind="cornice",
            envelope=(0, 0, 200, 20),
            x_left=0, x_right=200, y_top=0, y_bottom=20,
        )
        strokes = list(p.render_strokes())
        assert len(strokes) == 1

    def test_none_parapet_no_strokes(self):
        from engraving.planner.elements import ParapetElement
        p = ParapetElement(
            id="par", kind="none",
            envelope=(0, 0, 200, 20),
            x_left=0, x_right=200, y_top=0, y_bottom=20,
        )
        strokes = list(p.render_strokes())
        assert len(strokes) == 0

    def test_parapet_effective_bbox(self):
        from engraving.planner.elements import ParapetElement
        p = ParapetElement(
            id="par", kind="balustrade",
            envelope=(0, 0, 200, 20),
            x_left=0, x_right=200, y_top=0, y_bottom=20,
        )
        assert p.effective_bbox() == (0, 0, 200, 20)

    def test_solver_populates_parapet_with_pedestals_at_bay_axes(self):
        """The solver should hand ParapetElement the bay axes as pedestal
        positions for balustrade parapets, so the bay rhythm reads up into
        the parapet."""
        from engraving.planner.solver import solve
        from engraving.planner.elements import ParapetElement
        plan = FacadePlan(
            canvas=(0, 0, 500, 400),
            stories=[StoryPlan(height_ratio=1.0)],
            bays=[BayPlan(openings=[OpeningPlan(width_frac=0.4, height_frac=0.6)])
                  for _ in range(3)],
            parapet=ParapetPlan(kind="balustrade", height_ratio=0.25),
        )
        facade = solve(plan)
        par = facade.find("facade.parapet")
        assert isinstance(par, ParapetElement)
        assert par.kind == "balustrade"
        # Three bays → three pedestal positions
        assert len(par.pedestal_positions) == 3
        # Render should emit real geometry (not an empty band)
        strokes = list(par.render_strokes())
        assert len(strokes) > 5


class TestWallElement:
    def test_smooth_wall_outline_only(self):
        from engraving.planner.elements import WallElement
        w = WallElement(
            id="w", kind="wall",
            envelope=(0, 0, 100, 50),
            x_left=0, x_right=100, y_top=0, y_bottom=50,
            variant="smooth",
        )
        strokes = list(w.render_strokes())
        # Smooth: just the outline rectangle
        assert len(strokes) == 1

    def test_banded_wall_has_blocks(self):
        from engraving.planner.elements import WallElement
        w = WallElement(
            id="w", kind="wall",
            envelope=(0, 0, 100, 50),
            x_left=0, x_right=100, y_top=0, y_bottom=50,
            variant="banded", course_h=15, block_w=30,
        )
        strokes = list(w.render_strokes())
        # Banded: outline + blocks + joints
        assert len(strokes) > 3


class TestWallNative:
    """Phase 23 Day 2: WallElement emits geometry natively via
    ``_emit_geometry()`` instead of wrapping the legacy
    ``rustication.wall()`` dict."""

    def test_smooth_wall_outline_only(self):
        from engraving.planner.elements import WallElement
        w = WallElement(
            id="w", kind="wall", envelope=(0, 0, 100, 50),
            x_left=0, x_right=100, y_top=0, y_bottom=50, variant="smooth",
        )
        geometry = list(w._emit_geometry())
        outlines = [g for g, tag in geometry if tag == "outline"]
        assert len(outlines) == 1
        # Closed rectangle = 5 points
        assert len(outlines[0]) == 5

    def test_banded_wall_has_blocks_and_joints(self):
        from engraving.planner.elements import WallElement
        w = WallElement(
            id="w", kind="wall", envelope=(0, 0, 100, 50),
            x_left=0, x_right=100, y_top=0, y_bottom=50,
            variant="banded", course_h=15, block_w=30,
        )
        geometry = list(w._emit_geometry())
        n_outline = sum(1 for _, tag in geometry if tag == "outline")
        n_blocks = sum(1 for _, tag in geometry if tag == "blocks")
        n_joints = sum(1 for _, tag in geometry if tag == "joints")
        assert n_outline == 1
        assert n_blocks > 3   # multiple blocks across the wall
        assert n_joints > 0   # horizontal course lines


class TestPilasterRichness:
    def test_pilaster_has_multiple_strokes(self):
        from engraving.planner.elements import PilasterElement
        p = PilasterElement(
            id="p", kind="pilaster",
            envelope=(95, 0, 105, 100),
            cx=100, width_mm=10,
            base_y=100, top_y=0,
            order="tuscan",
        )
        strokes = list(p.render_strokes())
        # A proper pilaster has many more than 3 strokes (base + shaft + capital moldings)
        assert len(strokes) > 5


class TestMaterialCSG:
    def test_window_reports_void_footprint(self):
        from engraving.planner.elements import WindowElement
        from engraving.element import Material
        w = WindowElement(
            id="w", kind="window", envelope=(0, 0, 100, 100),
            x_center=50, y_top=20, y_bottom=80,
            width_mm=30, height_mm=60,
        )
        assert w.material == Material.VOID
        fp = w.void_footprint()
        assert fp is not None
        assert not fp.is_empty

    def test_wall_auto_discovers_voids(self):
        from engraving.planner.elements import WallElement, WindowElement
        from engraving.element import Element

        story = Element(id="story", kind="story", envelope=(0, 0, 100, 100))
        wall = WallElement(
            id="story.wall", kind="wall", envelope=(0, 0, 100, 100),
            x_left=0, x_right=100, y_top=0, y_bottom=100,
            variant="banded", course_h=20, block_w=40,
        )
        story.add(wall)
        # Add a window as a sibling of the wall
        win = WindowElement(
            id="story.window", kind="window",
            envelope=(40, 30, 60, 70),
            x_center=50, y_top=30, y_bottom=70,
            width_mm=20, height_mm=40,
        )
        story.add(win)

        void_union = wall._void_union()
        assert void_union is not None
        assert not void_union.is_empty

    def test_wall_discovers_grandchild_voids(self):
        """VOID elements added as grandchildren of the wall's parent should
        still be discovered — the scope walk is recursive."""
        from engraving.planner.elements import (
            WallElement, WindowElement, BayElement,
        )
        from engraving.element import Element

        story = Element(id="story", kind="story", envelope=(0, 0, 100, 100))
        wall = WallElement(
            id="story.wall", kind="wall", envelope=(0, 0, 100, 100),
            x_left=0, x_right=100, y_top=0, y_bottom=100,
            variant="banded", course_h=20, block_w=40,
        )
        story.add(wall)
        bay = BayElement(
            id="story.bay_0", kind="bay",
            envelope=(0, 0, 100, 100),
        )
        story.add(bay)
        win = WindowElement(
            id="story.bay_0.window", kind="window",
            envelope=(40, 30, 60, 70),
            x_center=50, y_top=30, y_bottom=70,
            width_mm=20, height_mm=40,
        )
        bay.add(win)

        footprints = wall._collect_void_footprints()
        assert len(footprints) == 1

    def test_semicircular_arch_reports_void(self):
        from engraving.elements.arches import SemicircularArchElement
        from engraving.element import Material
        arch = SemicircularArchElement(
            id="a", kind="arch", envelope=(40, 0, 160, 200),
            cx=100, y_spring=150, span=60,
            voussoir_count=9, with_keystone=True,
        )
        assert arch.material == Material.VOID
        fp = arch.void_footprint()
        assert fp is not None
        assert not fp.is_empty

    def test_wall_voidbboxes_escape_hatch_still_works(self):
        """A caller may still manually inject void_bboxes even when no
        sibling VOID elements exist."""
        from engraving.planner.elements import WallElement
        w = WallElement(
            id="w", kind="wall",
            envelope=(0, 0, 100, 100),
            x_left=0, x_right=100, y_top=0, y_bottom=100,
            variant="banded", course_h=20, block_w=40,
            void_bboxes=[(40, 40, 60, 60)],
        )
        union = w._void_union()
        assert union is not None
        assert not union.is_empty

    def test_default_material_is_ornament(self):
        from engraving.element import Element, Material
        e = Element(id="x", kind="x", envelope=(0, 0, 1, 1))
        assert e.material == Material.ORNAMENT
        assert e.void_footprint() is None


class TestAestheticLayer:
    def test_stroke_weight_hierarchy_catches_monotone(self):
        from engraving.element import Element
        from engraving.validate.aesthetic import StrokeWeightHierarchy
        from typing import Iterator

        class AllSameWeight(Element):
            def render_strokes(self):
                for i in range(10):
                    yield [(0, i), (10, i)], 0.25   # all at FINE

        e = AllSameWeight(id="mono", kind="test", envelope=(0, 0, 10, 10))
        vs = StrokeWeightHierarchy().check(e)
        assert len(vs) > 0

    def test_min_feature_caught(self):
        from engraving.element import Element
        from engraving.validate.aesthetic import MinimumFeatureAtScale
        # Tiny leaf element
        e = Element(id="tiny", kind="leaf", envelope=(0, 0, 0.1, 0.1))
        vs = MinimumFeatureAtScale(min_mm=0.5).check(e)
        assert len(vs) > 0

    def test_check_aesthetic_runs_all_rules(self):
        from engraving.planner import FacadePlan, StoryPlan, BayPlan, OpeningPlan, ParapetPlan, PilasterPlan
        from engraving.validate.aesthetic import check_aesthetic

        plan = FacadePlan(
            canvas=(0, 0, 200, 120),
            stories=[StoryPlan(height_ratio=1.0, wall="smooth")],
            bays=[BayPlan(openings=[OpeningPlan(width_frac=0.4, height_frac=0.5)])],
        )
        facade = plan.solve()
        violations = check_aesthetic(facade)
        # Some violations expected (small test plan)
        assert isinstance(violations, list)


class TestPlanDebugOverlay:
    """Day 17 — Element-tree debug overlay & Plan.explain()."""

    def test_explain_produces_output(self):
        from engraving.planner import (FacadePlan, StoryPlan, BayPlan,
                                        OpeningPlan)
        p = FacadePlan(
            canvas=(0, 0, 200, 100),
            stories=[StoryPlan(height_ratio=1.0, label="g"),
                     StoryPlan(height_ratio=1.0, label="p")],
            bays=[BayPlan(
                openings=[OpeningPlan(width_frac=0.4, height_frac=0.5),
                          OpeningPlan(width_frac=0.3, height_frac=0.5)])
                  for _ in range(3)],
        )
        text = p.explain()
        assert "FacadePlan" in text
        assert "stories" in text.lower()
        assert "bays" in text.lower()

    def test_explain_mentions_parapet_when_present(self):
        from engraving.planner import (FacadePlan, StoryPlan, BayPlan,
                                        OpeningPlan, ParapetPlan)
        p = FacadePlan(
            canvas=(0, 0, 200, 200),
            stories=[StoryPlan(height_ratio=1.0)],
            bays=[BayPlan(openings=[OpeningPlan(width_frac=0.4,
                                                 height_frac=0.5)])],
            parapet=ParapetPlan(kind="balustrade", height_ratio=0.25),
        )
        text = p.explain()
        assert "parapet" in text.lower()
        assert "balustrade" in text.lower()

    def test_explain_reports_solve_feasibility(self):
        from engraving.planner import (FacadePlan, StoryPlan, BayPlan,
                                        OpeningPlan)
        p = FacadePlan(
            canvas=(0, 0, 300, 200),
            stories=[StoryPlan(height_ratio=1.0)],
            bays=[BayPlan(openings=[OpeningPlan(width_frac=0.4,
                                                 height_frac=0.5)])],
        )
        text = p.explain()
        # Feasible plans should indicate success (check marker + count)
        assert ("feasible" in text.lower()) or ("elements" in text.lower())

    def test_debug_render_produces_overlay(self, tmp_path):
        from engraving.planner import (FacadePlan, StoryPlan, BayPlan,
                                        OpeningPlan)
        from engraving.planner.debug import render_debug

        # Build a minimal source SVG ourselves (avoid touching the out/ dir)
        src = tmp_path / "src.svg"
        src.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'width="300mm" height="200mm" viewBox="0 0 300 200">'
            '<rect x="0" y="0" width="300" height="200" fill="white"/>'
            '</svg>'
        )

        p = FacadePlan(
            canvas=(0, 0, 300, 200),
            stories=[StoryPlan(height_ratio=1.0)],
            bays=[BayPlan(openings=[OpeningPlan(width_frac=0.4,
                                                 height_frac=0.5)])],
        )
        facade = p.solve()
        out = tmp_path / "debug.svg"
        render_debug(facade, src, out)
        assert out.exists()
        # File should at least contain the source content
        body = out.read_text()
        assert "<svg" in body

    def test_debug_render_includes_violation_overlays(self, tmp_path):
        """Feed a synthetic violation via extra_violations and verify it
        shows up as a coloured rect + label in the overlay."""
        from engraving.element import Element, Violation
        from engraving.planner.debug import (render_debug, LAYER_COLORS)

        # Minimal element tree
        root = Element(id="root", kind="facade", envelope=(0, 0, 100, 100))
        child = Element(id="child", kind="bay", envelope=(10, 10, 40, 40))
        # Give the child a concrete effective bbox via a render_strokes impl
        child.render_strokes = lambda: iter([
            ([(10, 10), (40, 10), (40, 40), (10, 40), (10, 10)], 0.25)
        ])
        root.add(child)

        src = tmp_path / "src.svg"
        src.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'width="100mm" height="100mm" viewBox="0 0 100 100"></svg>'
        )
        out = tmp_path / "debug.svg"

        extras = [
            Violation(layer="B", rule="SuperpositionOrder",
                       element_id="child", message="demo B"),
            Violation(layer="C", rule="StrokeWeightHierarchy",
                       element_id="child", message="demo C"),
        ]
        render_debug(root, src, out, extra_violations=extras)

        body = out.read_text()
        assert "DEBUG OVERLAY" in body
        # Layer B → orange, Layer C → blue
        assert LAYER_COLORS["B"] in body
        assert LAYER_COLORS["C"] in body
        assert "SuperpositionOrder" in body
        assert "StrokeWeightHierarchy" in body

    def test_debug_render_layer_filtering(self, tmp_path):
        """include_layers should suppress violations for unlisted layers."""
        from engraving.element import Element, Violation
        from engraving.planner.debug import render_debug, LAYER_COLORS

        root = Element(id="root", kind="facade", envelope=(0, 0, 100, 100))
        child = Element(id="child", kind="bay", envelope=(10, 10, 40, 40))
        child.render_strokes = lambda: iter([
            ([(10, 10), (40, 10), (40, 40), (10, 40), (10, 10)], 0.25)
        ])
        root.add(child)

        src = tmp_path / "src.svg"
        src.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" '
            'width="100mm" height="100mm" viewBox="0 0 100 100"></svg>'
        )
        out = tmp_path / "debug.svg"

        extras = [
            Violation(layer="B", rule="RuleB", element_id="child",
                       message="b"),
            Violation(layer="C", rule="RuleC", element_id="child",
                       message="c"),
        ]
        render_debug(root, src, out, include_layers=("A", "B"),
                     extra_violations=extras)
        body = out.read_text()
        assert "RuleB" in body
        assert "RuleC" not in body


class TestQuoins:
    def test_quoins_emitted_when_requested(self):
        from engraving.planner import (FacadePlan, StoryPlan, BayPlan,
                                        OpeningPlan)
        from engraving.planner.elements import QuoinElement
        plan = FacadePlan(
            canvas=(0, 0, 300, 200),
            stories=[StoryPlan(height_ratio=1.0)],
            bays=[BayPlan(openings=[OpeningPlan(width_frac=0.4,
                                                  height_frac=0.5)])
                  for _ in range(3)],
            with_quoins=True, quoin_width_mm=8.0,
        )
        facade = plan.solve()
        quoins = [n for n in facade.descendants()
                  if isinstance(n, QuoinElement)]
        assert len(quoins) == 2
        assert {q.side for q in quoins} == {"left", "right"}

    def test_no_quoins_when_disabled(self):
        from engraving.planner import (FacadePlan, StoryPlan, BayPlan,
                                        OpeningPlan)
        from engraving.planner.elements import QuoinElement
        plan = FacadePlan(
            canvas=(0, 0, 300, 200),
            stories=[StoryPlan(height_ratio=1.0)],
            bays=[BayPlan(openings=[OpeningPlan(width_frac=0.4,
                                                  height_frac=0.5)])
                  for _ in range(3)],
            with_quoins=False,
        )
        facade = plan.solve()
        quoins = [n for n in facade.descendants()
                  if isinstance(n, QuoinElement)]
        assert len(quoins) == 0


class TestDoorDifferentiation:
    """Phase 22 Part 4: doors read as visibly heavier than windows."""

    def test_arch_door_gets_more_voussoirs(self):
        from engraving.planner import (FacadePlan, StoryPlan, BayPlan,
                                        OpeningPlan)
        from engraving.elements.arches import SemicircularArchElement
        # Build a 3-bay plan with central arch_door flanked by arch_windows.
        plan = FacadePlan(
            canvas=(0, 0, 300, 200),
            stories=[StoryPlan(height_ratio=1.0)],
            bays=[
                BayPlan(openings=[OpeningPlan(kind="arch_window",
                                               width_frac=0.4,
                                               height_frac=0.35)]),
                BayPlan(openings=[OpeningPlan(kind="arch_door",
                                               width_frac=0.55,
                                               height_frac=0.50)],
                        width_weight=1.2),
                BayPlan(openings=[OpeningPlan(kind="arch_window",
                                               width_frac=0.4,
                                               height_frac=0.35)]),
            ],
        )
        facade = plan.solve()
        arches = [n for n in facade.descendants()
                  if isinstance(n, SemicircularArchElement)]
        door = next(a for a in arches if a.id.endswith("bay_1.opening"))
        window = next(a for a in arches if a.id.endswith("bay_0.opening"))
        assert door.voussoir_count > window.voussoir_count

    def test_arch_door_forces_keystone_and_archivolt(self):
        from engraving.planner import (FacadePlan, StoryPlan, BayPlan,
                                        OpeningPlan)
        from engraving.elements.arches import SemicircularArchElement
        plan = FacadePlan(
            canvas=(0, 0, 300, 200),
            stories=[StoryPlan(height_ratio=1.0)],
            bays=[
                BayPlan(openings=[OpeningPlan(kind="arch_door",
                                               width_frac=0.5,
                                               height_frac=0.5,
                                               has_keystone=False)],
                        width_weight=1.0),
            ],
        )
        facade = plan.solve()
        arch = next(n for n in facade.descendants()
                    if isinstance(n, SemicircularArchElement))
        # Door forces the keystone on, even when the plan didn't ask for it,
        # and gets an extra outer archivolt band.
        assert arch.with_keystone is True
        assert arch.archivolt_bands >= 1

    def test_plain_door_gets_stroke_boost(self):
        from engraving.planner import (FacadePlan, StoryPlan, BayPlan,
                                        OpeningPlan)
        from engraving.planner.elements import WindowElement
        plan = FacadePlan(
            canvas=(0, 0, 300, 200),
            stories=[StoryPlan(height_ratio=1.0)],
            bays=[
                BayPlan(openings=[OpeningPlan(kind="window",
                                               width_frac=0.4,
                                               height_frac=0.5)]),
                BayPlan(openings=[OpeningPlan(kind="door",
                                               width_frac=0.4,
                                               height_frac=0.5)]),
            ],
        )
        facade = plan.solve()
        wins = [n for n in facade.descendants()
                if isinstance(n, WindowElement)]
        door = next(w for w in wins if w.kind == "door")
        window = next(w for w in wins if w.kind == "window")
        assert door.stroke_boost > window.stroke_boost
        # The rendered opening stroke weight should also be heavier.
        door_weights = [weight for _, weight in door.render_strokes()]
        win_weights = [weight for _, weight in window.render_strokes()]
        assert max(door_weights) > max(win_weights)


class TestBossedSmoothWall:
    """Phase 22 Part 5: bossed_smooth wall variant."""

    def test_bossed_smooth_has_horizontal_rules(self):
        from engraving.planner.elements import WallElement
        w = WallElement(
            id="w", kind="wall",
            envelope=(0, 0, 200, 60),
            x_left=0, x_right=200, y_top=0, y_bottom=60,
            variant="bossed_smooth",
        )
        strokes = list(w.render_strokes())
        # Outline + several horizontal rules (60mm / 15mm ≈ 4 intervals → 3
        # interior rules, plus the outline rect = 4 strokes).
        assert len(strokes) > 3

    def test_bossed_smooth_rules_are_horizontal(self):
        from engraving.planner.elements import WallElement
        w = WallElement(
            id="w", kind="wall",
            envelope=(0, 0, 200, 60),
            x_left=0, x_right=200, y_top=0, y_bottom=60,
            variant="bossed_smooth",
        )
        strokes = list(w.render_strokes())
        # The first stroke is the outline (closed rect, 5 points). All
        # subsequent strokes are 2-point horizontal lines spanning x0→x1.
        for pl, _weight in strokes[1:]:
            assert len(pl) == 2
            (x0, y0), (x1, y1) = pl
            assert y0 == y1          # horizontal
            assert (x0, x1) == (0, 200)

    def test_bossed_smooth_has_no_vertical_joints(self):
        """The variant must not emit any vertical joint lines — that's what
        distinguishes it from 'banded' / 'arcuated' rustication."""
        from engraving.planner.elements import WallElement
        w = WallElement(
            id="w", kind="wall",
            envelope=(0, 0, 200, 60),
            x_left=0, x_right=200, y_top=0, y_bottom=60,
            variant="bossed_smooth",
        )
        strokes = list(w.render_strokes())
        for pl, _weight in strokes[1:]:
            (x0, y0), (x1, y1) = pl
            # No stroke should be vertical (x0==x1).
            assert x0 != x1

    def test_bossed_smooth_accepted_in_story_plan(self):
        from engraving.planner import StoryPlan
        # Should not raise
        sp = StoryPlan(wall="bossed_smooth")
        assert sp.wall == "bossed_smooth"

    def test_invalid_wall_variant_still_rejected(self):
        from engraving.planner import StoryPlan
        with pytest.raises(ValueError):
            StoryPlan(wall="totally_bogus")
