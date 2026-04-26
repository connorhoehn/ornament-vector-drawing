"""Phase 32 — Tests for the DimensionElement + factory helpers."""
from __future__ import annotations

import pytest

from engraving.element import Element
from engraving.planner.elements import (
    DimensionElement,
    horizontal_dimension,
    vertical_dimension,
    render_dimensions,
)


class TestDimensionElementBasics:
    def test_emits_extension_lines_dim_line_and_ticks(self):
        """A horizontal DimensionElement should emit at least:
        two extension lines, one dimension line, and two tick markers
        (= 5 polylines)."""
        d = DimensionElement(
            id="d", kind="dimension",
            p1=(0.0, 10.0), p2=(20.0, 10.0),
            label="20 mm", offset_mm=5.0,
        )
        polylines = list(d.render_strokes())
        assert len(polylines) >= 5
        # All dimension strokes render at hairline weight.
        for pl, w in polylines:
            assert w == pytest.approx(0.12)

    def test_label_is_emitted_via_text_labels(self):
        d = DimensionElement(
            id="d", kind="dimension",
            p1=(0.0, 10.0), p2=(20.0, 10.0),
            label="7 D", offset_mm=5.0,
        )
        labels = d.text_labels()
        assert len(labels) == 1
        text, x, y, size, anchor = labels[0]
        assert text == "7 D"
        assert anchor == "middle"
        # Label sits roughly at the midpoint of the dim line (x=10).
        assert x == pytest.approx(10.0, abs=0.1)

    def test_empty_label_yields_no_text(self):
        d = DimensionElement(
            id="d", kind="dimension",
            p1=(0.0, 10.0), p2=(20.0, 10.0),
            label="", offset_mm=5.0,
        )
        assert d.text_labels() == []


class TestHorizontalDimension:
    def test_horizontal_dim_line_sits_at_y_line(self):
        """horizontal_dimension places the dim line at the requested
        y_line. In SVG y-down, y_line above the measured points means
        y_line < p_left.y."""
        d = horizontal_dimension(
            p_left=(10.0, 50.0), p_right=(60.0, 50.0),
            y_line=40.0, label="50 mm",
        )
        # Find the dim line: the segment whose endpoints share y ≈ 40.
        polylines = list(d.render_strokes())
        dim_lines = [pl for pl, _ in polylines
                     if len(pl) == 2
                     and pl[0][1] == pytest.approx(40.0, abs=0.01)
                     and pl[1][1] == pytest.approx(40.0, abs=0.01)]
        assert len(dim_lines) >= 1, (
            f"Expected a dim line at y=40; got {polylines}"
        )
        # Endpoints should span from x=10 to x=60.
        dim_line = dim_lines[0]
        xs = sorted(p[0] for p in dim_line)
        assert xs[0] == pytest.approx(10.0)
        assert xs[-1] == pytest.approx(60.0)


class TestVerticalDimension:
    def test_vertical_dim_line_sits_at_x_line(self):
        """vertical_dimension places the dim line at the requested
        x_line, to the right of the measured points when x_line > p_top.x."""
        d = vertical_dimension(
            p_top=(50.0, 30.0), p_bottom=(50.0, 80.0),
            x_line=70.0, label="column",
        )
        polylines = list(d.render_strokes())
        dim_lines = [pl for pl, _ in polylines
                     if len(pl) == 2
                     and pl[0][0] == pytest.approx(70.0, abs=0.01)
                     and pl[1][0] == pytest.approx(70.0, abs=0.01)]
        assert len(dim_lines) >= 1
        ys = sorted(p[1] for p in dim_lines[0])
        assert ys[0] == pytest.approx(30.0)
        assert ys[-1] == pytest.approx(80.0)


class TestNegativeOffsetFlipsSide:
    def test_negative_offset_flips_to_opposite_side(self):
        """Negative offset_mm places the dim line on the other side of
        the measured line."""
        pos = DimensionElement(
            id="p", kind="dimension",
            p1=(0.0, 10.0), p2=(20.0, 10.0),
            label="pos", offset_mm=5.0,
        )
        neg = DimensionElement(
            id="n", kind="dimension",
            p1=(0.0, 10.0), p2=(20.0, 10.0),
            label="neg", offset_mm=-5.0,
        )
        # Find dim lines: horizontal segments not touching the measured y=10.
        def find_dim_y(elem):
            for pl, _ in elem.render_strokes():
                if len(pl) == 2 and pl[0][1] == pytest.approx(pl[1][1]):
                    if pl[0][1] != pytest.approx(10.0):
                        return pl[0][1]
            return None
        y_pos = find_dim_y(pos)
        y_neg = find_dim_y(neg)
        assert y_pos is not None and y_neg is not None
        # Flip: one is above (smaller y) the other below (larger y).
        assert (y_pos < 10.0 and y_neg > 10.0) or (y_pos > 10.0 and y_neg < 10.0)
        # Symmetry: the two are mirror images across the measured line.
        assert (y_pos - 10.0) == pytest.approx(-(y_neg - 10.0), abs=0.01)


class TestZeroLengthDimension:
    def test_zero_length_emits_no_strokes(self):
        """When p1 == p2, the dim is degenerate. Must not crash, must
        emit zero strokes, must report an empty label list."""
        d = DimensionElement(
            id="z", kind="dimension",
            p1=(5.0, 5.0), p2=(5.0, 5.0),
            label="zero", offset_mm=5.0,
        )
        assert list(d.render_strokes()) == []
        assert d.text_labels() == []

    def test_zero_length_bbox_is_degenerate_point(self):
        d = DimensionElement(
            id="z", kind="dimension",
            p1=(5.0, 5.0), p2=(5.0, 5.0),
            label="zero",
        )
        assert d.effective_bbox() == (5.0, 5.0, 5.0, 5.0)


class TestPorticoPlateIntegration:
    def test_portico_plate_renders_at_least_three_dimensions(self):
        """End-to-end: the portico plate now emits at least 3
        DimensionElements in its rendered output. We verify by running the
        plate's build_validated and then searching the produced SVG for the
        three expected dimension labels."""
        from pathlib import Path
        from plates import plate_portico_plan

        svg_path, report = plate_portico_plan.build_validated()
        assert svg_path.endswith(".svg")
        svg_text = Path(svg_path).read_text()
        # The plate emits three dimension callouts: column_h,
        # entablature_h, and colonnade_w.
        assert "column" in svg_text
        assert "entab" in svg_text
        assert "colonnade" in svg_text

    def test_dimension_tree_walk_counts_three_dimensions(self):
        """A programmatic check: mirror the plate's dimension
        construction and assert we get at least 3 DimensionElement nodes
        in the walked tree."""
        from engraving.planner.elements import (
            ColumnRunElement, EntablatureBandElement,
        )
        from plates import plate_portico_plan

        plan = plate_portico_plan.make_plan()
        portico = plan.solve()
        D = portico.metadata["D"]
        col_left = portico.metadata["colonnade_left_x"]
        col_right = portico.metadata["colonnade_right_x"]
        column_run = next(c for c in portico.children
                          if isinstance(c, ColumnRunElement))
        ent_band = next(c for c in portico.children
                        if isinstance(c, EntablatureBandElement))
        column_top_y = column_run.top_of_capital_y
        column_base_y = column_run.base_y
        ent_top_y = ent_band.envelope[1]
        ent_bot_y = ent_band.envelope[3]

        dim_root = Element(id="dims", kind="dim_group",
                           envelope=(0, 0, 300, 300))
        x_col_dim = col_right + D * 0.8
        dim_root.add(vertical_dimension(
            p_top=(col_right, column_top_y),
            p_bottom=(col_right, column_base_y),
            x_line=x_col_dim, label="col",
        ))
        dim_root.add(vertical_dimension(
            p_top=(col_right, ent_top_y),
            p_bottom=(col_right, ent_bot_y),
            x_line=x_col_dim + D * 1.4, label="ent",
        ))
        dim_root.add(horizontal_dimension(
            p_left=(col_left, column_base_y),
            p_right=(col_right, column_base_y),
            y_line=column_base_y + D * 0.9, label="col_w",
        ))
        dims = [n for n in dim_root.walk()
                if isinstance(n, DimensionElement)]
        assert len(dims) >= 3
