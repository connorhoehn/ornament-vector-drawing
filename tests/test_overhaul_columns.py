"""Tests for ColumnElement subclasses."""

import pytest
from engraving.element import Element
from engraving.containment import validate_tree
from engraving.elements.columns import (
    TuscanColumn, DoricColumn, IonicColumn, CorinthianColumn,
    CompositeColumn, GreekDoricColumn, GreekIonicColumn, column_for,
)
from engraving import canon


@pytest.mark.parametrize("cls,Dims,kind", [
    (TuscanColumn, canon.Tuscan, "tuscan_column"),
    (DoricColumn, canon.Doric, "doric_column"),
    (IonicColumn, canon.Ionic, "ionic_column"),
    (CorinthianColumn, canon.Corinthian, "corinthian_column"),
    (CompositeColumn, canon.Composite, "composite_column"),
    (GreekDoricColumn, canon.GreekDoric, "greek_doric_column"),
    (GreekIonicColumn, canon.GreekIonic, "greek_ionic_column"),
])
def test_each_order_renders(cls, Dims, kind):
    D = 20.0
    col = cls(id=f"c_{kind}", kind=kind, envelope=(0, 0, 200, 250),
              dims=Dims(D=D), cx=100, base_y=200)
    strokes = list(col.render_strokes())
    assert len(strokes) > 0
    bx = col.effective_bbox()
    # All columns should have positive width + height
    assert bx[2] > bx[0]
    assert bx[3] > bx[1]


def test_column_in_envelope_passes():
    D = 20.0
    dims = canon.Tuscan(D=D)
    # Column needs about D+margin wide × column_h tall
    expected_h = dims.column_D * D  # 7 × 20 = 140
    story = Element(id="story", kind="story",
                    envelope=(70, 200 - expected_h - 5, 130, 200 + 5))
    col = TuscanColumn(id="story.col", kind="tuscan_column",
                        envelope=(80, 200 - expected_h, 120, 200),
                        dims=dims, cx=100, base_y=200)
    story.add(col)
    vs = validate_tree(story, tol=5.0)  # loose tol for this test
    # The col's effective_bbox may exceed its own envelope a touch due to abacus
    # Report any containment violations — allow up to 2 for abacus projection
    containment_vs = [v for v in vs if v.rule == "HierarchicalContainment"]
    assert len(containment_vs) <= 2


def test_column_for_factory():
    c = column_for("tuscan", id="f", kind="tuscan_column",
                   envelope=(0, 0, 50, 200),
                   dims=canon.Tuscan(D=10), cx=25, base_y=150)
    assert isinstance(c, TuscanColumn)
    c2 = column_for("CORINTHIAN", id="f2", kind="corinthian_column",
                     envelope=(0, 0, 50, 250),
                     dims=canon.Corinthian(D=10), cx=25, base_y=150)
    assert isinstance(c2, CorinthianColumn)


def test_unknown_order_raises():
    with pytest.raises(KeyError):
        column_for("barbaric", id="x", kind="x",
                   envelope=(0,0,1,1), dims=None, cx=0, base_y=0)
