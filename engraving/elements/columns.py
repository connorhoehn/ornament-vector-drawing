"""Column elements wrapping the 7 order silhouette builders.

Each ColumnElement knows its canonical envelope: the rectangular volume
the column occupies (plinth at bottom to abacus at top, max width =
abacus_half_width × 2). If the drawn silhouette exceeds this (e.g.
Corinthian abacus with diagonal wider than the envelope width), containment
catches it.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterator

from ..element import Element, StrokedPolyline
from ..schema import BBox, Polyline
from .. import canon
from .. import orders as _tuscan_mod
from .. import order_doric as _doric_mod
from .. import order_ionic as _ionic_mod
from .. import order_corinthian as _corinthian_mod
from .. import order_composite as _composite_mod
from .. import order_greek_doric as _greek_doric_mod
from .. import order_greek_ionic as _greek_ionic_mod


# Layer stroke weights — classical hierarchy
_LAYER_WEIGHTS = {
    "silhouette": 0.35,
    "rules": 0.25,
    "acanthus": 0.18,
    "helices": 0.18,
    "caulicoli": 0.18,
    "volutes": 0.25,
    "echinus": 0.25,
    "abacus": 0.25,
    "fleuron": 0.18,
    "bell_guides": 0.18,
    "annulets": 0.25,
}


@dataclass
class ColumnElement(Element):
    """Base for classical column elements. Subclasses set the builder_fn
    and dims class."""
    dims: object = None            # canon.Order subclass instance
    cx: float = 0.0
    base_y: float = 0.0            # y of column bottom (top of pedestal)
    _result: object = field(default=None, repr=False, init=False)
    _builder: callable = field(default=None, repr=False)

    def _ensure_built(self):
        if self._result is None:
            self._result = self._builder(self.dims, self.cx, self.base_y,
                                          return_result=True)
        return self._result

    def render_strokes(self) -> Iterator[StrokedPolyline]:
        r = self._ensure_built()
        for layer_name, polylines in r.polylines.items():
            weight = _LAYER_WEIGHTS.get(layer_name, 0.25)
            for pl in polylines:
                yield pl, weight

    def effective_bbox(self) -> BBox:
        r = self._ensure_built()
        return r.bbox


@dataclass
class TuscanColumn(ColumnElement):
    def __post_init__(self):
        self._builder = _tuscan_mod.tuscan_column_silhouette


@dataclass
class DoricColumn(ColumnElement):
    def __post_init__(self):
        self._builder = _doric_mod.doric_column_silhouette


@dataclass
class IonicColumn(ColumnElement):
    def __post_init__(self):
        self._builder = _ionic_mod.ionic_column_silhouette


@dataclass
class CorinthianColumn(ColumnElement):
    def __post_init__(self):
        self._builder = _corinthian_mod.corinthian_column_silhouette


@dataclass
class CompositeColumn(ColumnElement):
    def __post_init__(self):
        self._builder = _composite_mod.composite_column_silhouette


@dataclass
class GreekDoricColumn(ColumnElement):
    def __post_init__(self):
        self._builder = _greek_doric_mod.greek_doric_column_silhouette


@dataclass
class GreekIonicColumn(ColumnElement):
    def __post_init__(self):
        self._builder = _greek_ionic_mod.greek_ionic_column_silhouette


# Registry for programmatic lookup
ORDER_ELEMENT = {
    "tuscan":     TuscanColumn,
    "doric":      DoricColumn,
    "ionic":      IonicColumn,
    "corinthian": CorinthianColumn,
    "composite":  CompositeColumn,
    "greek_doric": GreekDoricColumn,
    "greek_ionic": GreekIonicColumn,
}


def column_for(order_name: str, **kw) -> ColumnElement:
    """Factory: column_for('tuscan', dims=canon.Tuscan(D=20), cx=100, base_y=200)."""
    cls = ORDER_ELEMENT[order_name.lower()]
    return cls(**kw)


if __name__ == "__main__":
    dims = canon.Tuscan(D=20)
    col = TuscanColumn(
        id="demo_tuscan", kind="tuscan_column",
        envelope=(85, 60, 115, 200),
        dims=dims, cx=100, base_y=200,
    )
    print(f"Tuscan column effective_bbox: {col.effective_bbox()}")
    for cls_name in ("Doric", "Ionic", "Corinthian", "Composite", "GreekDoric", "GreekIonic"):
        order_map = {"Doric": (DoricColumn, canon.Doric),
                     "Ionic": (IonicColumn, canon.Ionic),
                     "Corinthian": (CorinthianColumn, canon.Corinthian),
                     "Composite": (CompositeColumn, canon.Composite),
                     "GreekDoric": (GreekDoricColumn, canon.GreekDoric),
                     "GreekIonic": (GreekIonicColumn, canon.GreekIonic)}
        Cls, Dims = order_map[cls_name]
        c = Cls(id=f"demo_{cls_name.lower()}", kind=f"{cls_name.lower()}_column",
                envelope=(0, 0, 200, 250),
                dims=Dims(D=20), cx=100, base_y=200)
        print(f"{cls_name}: bbox={c.effective_bbox()}, strokes={sum(1 for _ in c.render_strokes())}")
