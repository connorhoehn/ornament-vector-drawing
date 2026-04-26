"""Entablature elements wrapping the 4 order-specific entablature builders.

Entablature envelope = (left_x, top_y, right_x, top_of_capital_y) — meaning
the space above the capital up to entablature_h. The rendered geometry
(architrave, frieze, cornice, dentils, modillions, mutules) must fit within
this envelope. Containment catches oversized cornices projecting past the
envelope or metadata counts that don't match the geometry.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Iterator

from ..element import Element, StrokedPolyline
from ..schema import BBox, Polyline
from .. import canon
from .. import entablature_doric as _doric_mod
from .. import entablature_ionic as _ionic_mod
from .. import entablature_corinthian as _corinth_mod
from .. import elements as _tuscan_elements_mod


_LAYER_WEIGHTS = {
    "fasciae": 0.25,
    "polylines": 0.25,  # legacy Tuscan key
    "rules": 0.25,
    "triglyphs": 0.25,
    "metopes": 0.18,
    "guttae": 0.18,
    "mutules": 0.25,
    "dentils": 0.18,
    "modillions": 0.25,
    "caissons": 0.18,
    "rosettes": 0.18,
    "voussoirs": 0.25,
}


@dataclass
class EntablatureElement(Element):
    """Base for entablatures. Subclasses set their builder."""
    dims: object = None
    left_x: float = 0.0
    right_x: float = 0.0
    top_of_capital_y: float = 0.0
    column_axes_x: list = field(default_factory=list)
    _result: object = field(default=None, repr=False, init=False)

    def _build(self):
        raise NotImplementedError

    def _ensure_built(self):
        if self._result is None:
            self._result = self._build()
        return self._result

    def render_strokes(self) -> Iterator[StrokedPolyline]:
        r = self._ensure_built()
        # ElementResult path: iterate polylines dict
        if hasattr(r, "polylines"):
            for layer_name, polylines in r.polylines.items():
                weight = _LAYER_WEIGHTS.get(layer_name, 0.25)
                for pl in polylines:
                    yield pl, weight
        else:
            # Legacy dict return (Tuscan via elements.entablature)
            for pl in r.get("polylines", []):
                yield pl, 0.25

    def effective_bbox(self) -> BBox:
        r = self._ensure_built()
        if hasattr(r, "bbox"):
            return r.bbox
        # Legacy: scan polylines for bbox
        xs, ys = [], []
        for pl in r.get("polylines", []):
            for x, y in pl:
                xs.append(x); ys.append(y)
        if not xs:
            return self.envelope
        return (min(xs), min(ys), max(xs), max(ys))


@dataclass
class TuscanEntablature(EntablatureElement):
    """Tuscan via legacy elements.entablature — returns dict not ElementResult."""
    with_dentils: bool = False

    def _build(self):
        return _tuscan_elements_mod.entablature(
            self.left_x, self.right_x, self.top_of_capital_y, self.dims,
            with_dentils=self.with_dentils,
        )


@dataclass
class DoricEntablature(EntablatureElement):
    def _build(self):
        return _doric_mod.doric_entablature(
            self.left_x, self.right_x, self.top_of_capital_y, self.dims,
            self.column_axes_x, return_result=True,
        )


@dataclass
class IonicEntablature(EntablatureElement):
    def _build(self):
        return _ionic_mod.ionic_entablature(
            self.left_x, self.right_x, self.top_of_capital_y, self.dims,
            return_result=True,
        )


@dataclass
class CorinthianEntablature(EntablatureElement):
    dentil_width_D: float | None = None
    dentil_height_D: float | None = None
    dentil_oc_D: float | None = None

    def _build(self):
        return _corinth_mod.corinthian_entablature(
            self.left_x, self.right_x, self.top_of_capital_y, self.dims,
            self.column_axes_x, return_result=True,
            dentil_width_D=self.dentil_width_D,
            dentil_height_D=self.dentil_height_D,
            dentil_oc_D=self.dentil_oc_D,
        )


@dataclass
class CompositeEntablature(EntablatureElement):
    def _build(self):
        return _corinth_mod.composite_entablature(
            self.left_x, self.right_x, self.top_of_capital_y, self.dims,
            self.column_axes_x, return_result=True,
        )


ENTABLATURE_ELEMENT = {
    "tuscan":     TuscanEntablature,
    "doric":      DoricEntablature,
    "ionic":      IonicEntablature,
    "corinthian": CorinthianEntablature,
    "composite":  CompositeEntablature,
}


def entablature_for(order_name: str, **kw) -> EntablatureElement:
    cls = ENTABLATURE_ELEMENT[order_name.lower()]
    return cls(**kw)


if __name__ == "__main__":
    col_xs = [60, 120, 180, 240]
    dims = canon.Doric(D=20)
    ent = DoricEntablature(
        id="demo_doric_ent", kind="doric_entablature",
        envelope=(40, 100, 260, 200),
        dims=dims, left_x=40, right_x=260,
        top_of_capital_y=200, column_axes_x=col_xs,
    )
    print(f"Doric entablature bbox: {ent.effective_bbox()}")
    print(f"  strokes: {sum(1 for _ in ent.render_strokes())}")

    for cls_name, Cls, Dims in [
        ("Ionic", IonicEntablature, canon.Ionic),
        ("Corinthian", CorinthianEntablature, canon.Corinthian),
        ("Composite", CompositeEntablature, canon.Composite),
    ]:
        e = Cls(id=f"d_{cls_name.lower()}", kind=f"{cls_name.lower()}_entab",
                envelope=(40, 100, 260, 200), dims=Dims(D=20),
                left_x=40, right_x=260, top_of_capital_y=200, column_axes_x=col_xs)
        print(f"{cls_name}: bbox={e.effective_bbox()}, strokes={sum(1 for _ in e.render_strokes())}")
