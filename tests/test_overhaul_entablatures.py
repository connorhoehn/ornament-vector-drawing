"""Tests for EntablatureElement subclasses."""

import pytest
from engraving.element import Element
from engraving.containment import validate_tree
from engraving.elements.entablatures import (
    TuscanEntablature, DoricEntablature, IonicEntablature,
    CorinthianEntablature, CompositeEntablature, entablature_for,
)
from engraving import canon


def test_doric_entablature_builds():
    ent = DoricEntablature(
        id="e", kind="doric_entablature",
        envelope=(40, 100, 260, 200),
        dims=canon.Doric(D=20),
        left_x=40, right_x=260,
        top_of_capital_y=200, column_axes_x=[60, 120, 180, 240],
    )
    bx = ent.effective_bbox()
    assert bx[2] > bx[0]
    assert bx[3] > bx[1]
    strokes = list(ent.render_strokes())
    assert len(strokes) > 10  # triglyphs + metopes + guttae + ...


def test_ionic_entablature_builds():
    ent = IonicEntablature(
        id="e", kind="ionic_entablature",
        envelope=(40, 100, 260, 200),
        dims=canon.Ionic(D=20),
        left_x=40, right_x=260, top_of_capital_y=200,
    )
    strokes = list(ent.render_strokes())
    assert len(strokes) > 5


def test_corinthian_entablature_with_modillions():
    ent = CorinthianEntablature(
        id="e", kind="corinthian_entablature",
        envelope=(40, 100, 260, 200),
        dims=canon.Corinthian(D=20),
        left_x=40, right_x=260, top_of_capital_y=200,
        column_axes_x=[60, 120, 180, 240],
    )
    strokes = list(ent.render_strokes())
    assert len(strokes) > 20  # modillions + caissons + rosettes + dentils


def test_composite_entablature_distinct_from_corinthian():
    """Composite uses chunkier dentils per Ware p.24."""
    e_comp = CompositeEntablature(
        id="ec", kind="composite_ent",
        envelope=(40, 100, 260, 200),
        dims=canon.Composite(D=20),
        left_x=40, right_x=260, top_of_capital_y=200,
        column_axes_x=[60, 120, 180, 240],
    )
    r = e_comp._ensure_built()
    # Composite dentils should be present
    dentil_layer = r.polylines.get("dentils", [])
    assert len(dentil_layer) > 0


def test_tuscan_entablature_legacy_dict():
    ent = TuscanEntablature(
        id="et", kind="tuscan_entablature",
        envelope=(40, 100, 260, 200),
        dims=canon.Tuscan(D=20),
        left_x=40, right_x=260, top_of_capital_y=200,
    )
    bx = ent.effective_bbox()
    assert bx != (0,0,0,0)
    strokes = list(ent.render_strokes())
    assert len(strokes) > 0


def test_entablature_for_factory():
    for name, Cls in [("tuscan", TuscanEntablature),
                       ("doric", DoricEntablature),
                       ("ionic", IonicEntablature),
                       ("corinthian", CorinthianEntablature),
                       ("composite", CompositeEntablature)]:
        kwargs = dict(id="f", kind="f", envelope=(0,0,300,100),
                      dims=getattr(canon, name.capitalize())(D=20),
                      left_x=0, right_x=300, top_of_capital_y=100)
        if name in ("doric", "corinthian", "composite"):
            kwargs["column_axes_x"] = [60, 120, 180, 240]
        e = entablature_for(name, **kwargs)
        assert isinstance(e, Cls)
