"""Tests for FacadePlan YAML roundtrip + SVG embedding."""
import pytest
from engraving.planner import (FacadePlan, StoryPlan, BayPlan, OpeningPlan,
                                ParapetPlan, PilasterPlan)
from engraving.planner.io import (plan_to_yaml, plan_from_yaml,
                                    embed_plan_in_svg, extract_plan_from_svg)


def _make_sample_plan():
    return FacadePlan(
        canvas=(0.0, 0.0, 200.0, 150.0),
        stories=[
            StoryPlan(height_ratio=1.3, wall="arcuated", label="ground"),
            StoryPlan(height_ratio=1.4, wall="smooth", has_order="ionic",
                      label="piano_nobile"),
            StoryPlan(height_ratio=0.85, wall="smooth", label="attic"),
        ],
        bays=[
            BayPlan(openings=[
                OpeningPlan(kind="arch_window", width_frac=0.5, height_frac=0.3),
                OpeningPlan(kind="window", width_frac=0.42, height_frac=0.6),
                OpeningPlan(kind="window", width_frac=0.32, height_frac=0.5),
            ], pilasters=PilasterPlan(order="ionic", width_frac=0.08))
            for _ in range(3)
        ],
        parapet=ParapetPlan(kind="balustrade", height_ratio=0.25),
    )


class TestYAMLRoundtrip:
    def test_roundtrip_preserves_plan(self):
        p1 = _make_sample_plan()
        text = plan_to_yaml(p1)
        p2 = plan_from_yaml(text)
        assert p1.canvas == p2.canvas
        assert len(p1.stories) == len(p2.stories)
        assert len(p1.bays) == len(p2.bays)
        for s1, s2 in zip(p1.stories, p2.stories):
            assert s1.height_ratio == s2.height_ratio
            assert s1.wall == s2.wall
            assert s1.has_order == s2.has_order
        assert p1.parapet.kind == p2.parapet.kind

    def test_yaml_is_human_readable(self):
        plan = _make_sample_plan()
        text = plan_to_yaml(plan)
        assert "canvas:" in text
        assert "stories:" in text
        assert "height_ratio:" in text
        assert "ionic" in text  # order name visible

    def test_yaml_deterministic(self):
        plan = _make_sample_plan()
        t1 = plan_to_yaml(plan)
        t2 = plan_to_yaml(plan)
        assert t1 == t2


class TestSVGEmbed:
    def test_embed_and_extract(self, tmp_path):
        plan = _make_sample_plan()
        svg_text = (
            '<?xml version="1.0"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" width="200mm" height="150mm">\n'
            '  <rect x="0" y="0" width="200" height="150" fill="white"/>\n'
            '</svg>\n'
        )
        embedded = embed_plan_in_svg(svg_text, plan)
        assert "<metadata id=\"facade-plan\">" in embedded
        assert "stories:" in embedded

        # Write + read round-trip
        svg_path = tmp_path / "test.svg"
        svg_path.write_text(embedded)
        extracted = extract_plan_from_svg(svg_path)
        assert extracted is not None
        assert extracted.canvas == plan.canvas
        assert len(extracted.stories) == len(plan.stories)

    def test_extract_returns_none_when_no_metadata(self, tmp_path):
        svg_path = tmp_path / "plain.svg"
        svg_path.write_text('<svg><rect/></svg>')
        assert extract_plan_from_svg(svg_path) is None

    def test_embedding_replaces_existing(self):
        plan = _make_sample_plan()
        svg_text = '<svg>\n<metadata id="facade-plan"><![CDATA[OLD]]></metadata>\n</svg>'
        embedded = embed_plan_in_svg(svg_text, plan)
        assert "OLD" not in embedded
        assert "stories:" in embedded


class TestOptionalFields:
    def test_plan_without_parapet(self):
        p1 = FacadePlan(
            canvas=(0, 0, 100, 100),
            stories=[StoryPlan(height_ratio=1.0)],
            bays=[BayPlan(openings=[OpeningPlan()])],
        )
        p2 = plan_from_yaml(plan_to_yaml(p1))
        assert p2.parapet is None

    def test_plan_without_pilasters(self):
        p1 = FacadePlan(
            canvas=(0, 0, 100, 100),
            stories=[StoryPlan(height_ratio=1.0)],
            bays=[BayPlan(openings=[OpeningPlan()], pilasters=None)],
        )
        p2 = plan_from_yaml(plan_to_yaml(p1))
        assert p2.bays[0].pilasters is None


class TestPageSaveWithPlan:
    def test_save_embeds_plan(self, tmp_path):
        import config
        from engraving.render import Page, frame
        from engraving.planner.io import extract_plan_from_svg

        page = Page()
        frame(page)
        plan = _make_sample_plan()

        # Patch OUT_DIR for this test
        original_out = config.OUT_DIR
        config.OUT_DIR = tmp_path
        try:
            svg_path = page.save_svg_with_plan("test_embed", plan)
            extracted = extract_plan_from_svg(svg_path)
            assert extracted is not None
            assert extracted.canvas == plan.canvas
        finally:
            config.OUT_DIR = original_out


class TestCLIReload:
    def test_reload_changes_order(self, tmp_path):
        # Generate a plate, then reload with a different order
        from engraving.cli import main
        from engraving.planner.io import extract_plan_from_svg

        # Use CLI to generate baseline
        baseline = tmp_path / "baseline.svg"
        main(["generate", "palazzo",
              "--bays", "5",
              "--piano-nobile-order", "ionic",
              "-o", str(baseline)])

        baseline_plan = extract_plan_from_svg(baseline)
        assert baseline_plan is not None
        # piano nobile should be ionic
        pn = next(s for s in baseline_plan.stories if s.has_order)
        assert pn.has_order == "ionic"

        # Reload with corinthian
        reloaded = tmp_path / "reloaded.svg"
        rc = main(["reload", str(baseline),
                    "--piano-nobile-order", "corinthian",
                    "-o", str(reloaded)])
        assert rc == 0

        # Verify override took effect
        reloaded_plan = extract_plan_from_svg(reloaded)
        pn2 = next(s for s in reloaded_plan.stories if s.has_order)
        assert pn2.has_order == "corinthian"
