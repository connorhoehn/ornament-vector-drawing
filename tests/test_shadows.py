"""Tests for ShadowElement + auto-emission (Phase 28)."""
import pytest
from shapely.geometry import Polygon

from engraving.planner.elements import ShadowElement, WindowElement


class TestShadowElement:
    def test_renders_parallel_hatch(self):
        poly = Polygon([(0, 0), (20, 0), (20, 10), (0, 10)])
        s = ShadowElement(
            id="s", kind="shadow", envelope=tuple(poly.bounds),
            polygon=poly, angle_deg=45, density="medium",
        )
        strokes = list(s.render_strokes())
        # A 20x10 polygon at 0.4mm spacing (rotated diagonal hatch)
        # yields ~50 hatch lines; some tolerance for geometry drift.
        assert 20 <= len(strokes) <= 100
        for polyline, weight in strokes:
            assert weight == 0.12  # all hairline

    def test_empty_polygon_no_strokes(self):
        s = ShadowElement(id="s", kind="shadow", envelope=(0, 0, 0, 0),
                          polygon=None)
        assert list(s.render_strokes()) == []

    def test_density_affects_spacing(self):
        poly = Polygon([(0, 0), (40, 0), (40, 40), (0, 40)])
        s_light = ShadowElement(id="a", kind="shadow",
                                envelope=tuple(poly.bounds),
                                polygon=poly, density="light")
        s_dark = ShadowElement(id="b", kind="shadow",
                               envelope=tuple(poly.bounds),
                               polygon=poly, density="dark")
        n_light = sum(1 for _ in s_light.render_strokes())
        n_dark = sum(1 for _ in s_dark.render_strokes())
        assert n_dark > n_light  # denser hatch, more lines

    def test_effective_bbox_uses_polygon(self):
        poly = Polygon([(5, 10), (25, 10), (25, 30), (5, 30)])
        s = ShadowElement(id="s", kind="shadow", envelope=(0, 0, 100, 100),
                          polygon=poly)
        bb = s.effective_bbox()
        assert bb == (5.0, 10.0, 25.0, 30.0)

    def test_effective_bbox_falls_back_to_envelope(self):
        s = ShadowElement(id="s", kind="shadow", envelope=(1, 2, 3, 4),
                          polygon=None)
        assert s.effective_bbox() == (1, 2, 3, 4)


class TestShadowAutoEmit:
    def test_window_collect_shadows_method_exists(self):
        w = WindowElement(
            id="w", kind="window",
            envelope=(0, 0, 60, 100),
            x_center=30, y_top=20, y_bottom=80,
            width_mm=30, height_mm=60,
            hood="triangular", has_keystone=True,
        )
        assert hasattr(w, "collect_shadows")
        shadows = w.collect_shadows()
        # A window with triangular hood has multiple shadow regions
        # (sill underside, hood soffit, architrave undersides, pediment)
        assert isinstance(shadows, list)
        assert all(isinstance(s, ShadowElement) for s in shadows)

    def test_window_with_hood_emits_multiple_shadows(self):
        w = WindowElement(
            id="w", kind="window",
            envelope=(0, 0, 60, 100),
            x_center=30, y_top=20, y_bottom=80,
            width_mm=30, height_mm=60,
            hood="triangular", has_keystone=True,
        )
        shadows = w.collect_shadows()
        # triangular hood = architrave(3) + sill(1) + cornice(1) + pediment(1)
        # + brackets(1) = ~7 shadows
        assert len(shadows) >= 3

    def test_palazzo_plan_has_shadow_elements(self):
        from engraving.planner import (FacadePlan, StoryPlan, BayPlan,
                                        OpeningPlan, ParapetPlan, PilasterPlan)
        plan = FacadePlan(
            canvas=(0, 0, 200, 200),
            stories=[
                StoryPlan(height_ratio=1.0, wall="arcuated", min_height_mm=40),
                StoryPlan(height_ratio=1.2, wall="smooth", has_order="ionic"),
                StoryPlan(height_ratio=0.8, wall="smooth"),
            ],
            bays=[BayPlan(openings=[
                OpeningPlan(kind="arch_window", width_frac=0.5,
                            height_frac=0.25, has_keystone=True),
                OpeningPlan(kind="window", width_frac=0.4, height_frac=0.55,
                            hood="triangular", has_keystone=True),
                OpeningPlan(kind="window", width_frac=0.3, height_frac=0.5,
                            hood="cornice"),
            ], pilasters=PilasterPlan(order="ionic", width_frac=0.08))
                for _ in range(5)],
            parapet=ParapetPlan(kind="balustrade", height_ratio=0.22),
        )
        facade = plan.solve()
        shadow_nodes = [n for n in facade.descendants()
                        if isinstance(n, ShadowElement)]
        # 15 openings (5 bays x 3 stories) plus arcuated wall joint shadows
        # should produce many shadow nodes.
        assert len(shadow_nodes) >= 5

    def test_shadows_disabled_emits_none(self):
        from engraving.planner import (FacadePlan, StoryPlan, BayPlan,
                                        OpeningPlan)
        plan = FacadePlan(
            canvas=(0, 0, 200, 200),
            stories=[StoryPlan(height_ratio=1.0, wall="smooth")],
            bays=[BayPlan(openings=[
                OpeningPlan(kind="window", width_frac=0.4, height_frac=0.5,
                            hood="cornice"),
            ]) for _ in range(3)],
            shadows_enabled=False,
        )
        facade = plan.solve()
        shadow_nodes = [n for n in facade.descendants()
                        if isinstance(n, ShadowElement)]
        assert shadow_nodes == []
