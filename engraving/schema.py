"""Foundation types for the validation library.

Every builder (column silhouette, entablature, arch, window, ...) returns an
`ElementResult`. The result carries its polylines categorized by stroke layer,
its named anchor points (the validation interface), its bounding box, and any
child elements. The composition layer asserts relationships between anchors.

See `plans/HANDOFF.md` for the full rationale.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

Point = tuple[float, float]
Polyline = list[Point]
BBox = tuple[float, float, float, float]  # (x_min, y_min, x_max, y_max)


@dataclass(frozen=True)
class Anchor:
    """A named semantic point in a drawing.

    The name identifies a role (``"bottom_center"``, ``"abacus_top"``,
    ``"volute_eye_left"``) that validators can reason about. Compositional
    rules express alignments and meetings as predicates over anchors.
    """
    name: str
    x: float
    y: float
    role: str = ""  # "attach", "spring", "axis", "corner", "center"

    def as_tuple(self) -> Point:
        return (self.x, self.y)


@dataclass
class ElementResult:
    """Standardized return value for every builder.

    Fields
    ------
    kind :
        Machine-readable element identifier (``"tuscan_column"``,
        ``"ionic_entablature"``, ``"semicircular_arch"``).
    dims_ref :
        The canonical dataclass that parameterized this element
        (e.g. a ``canon.Tuscan`` instance). May be None for primitives
        that don't reference canon directly (arches, windows).
    polylines :
        Categorized by stroke layer. Common keys: ``"silhouette"``,
        ``"rules"``, ``"ornament"``, ``"dentils"``, ``"voussoirs"``,
        ``"architrave"``, ``"cornice"``. The validation layer does not
        prescribe the category names — builders define them.
    anchors :
        The public validation interface. Keys are anchor names.
    bbox :
        Axis-aligned bounding box covering all polylines.
    shadows :
        List of ``elements.Shadow`` instances (shapely polygon + hatch
        angle + density label) — separate from polylines because they
        are regions, not strokes.
    children :
        Nested ``ElementResult`` objects for composite elements
        (portico contains columns; facade contains stories).
    metadata :
        Free-form dict for counts and flags that validators read:
        ``num_triglyphs``, ``num_dentils``, ``num_leaves``,
        ``num_voussoirs``, etc.
    """
    kind: str
    dims_ref: Any = None
    polylines: dict[str, list[Polyline]] = field(default_factory=dict)
    anchors: dict[str, Anchor] = field(default_factory=dict)
    bbox: BBox = (0.0, 0.0, 0.0, 0.0)
    shadows: list = field(default_factory=list)
    children: list["ElementResult"] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def all_polylines(self) -> list[Polyline]:
        """Flatten every layer into a single list — useful for overlap checks
        and overall bbox computation."""
        out: list[Polyline] = []
        for lines in self.polylines.values():
            out.extend(lines)
        return out

    def add_anchor(self, name: str, x: float, y: float, role: str = "") -> None:
        self.anchors[name] = Anchor(name=name, x=x, y=y, role=role)

    def add_polylines(self, layer: str, lines: list[Polyline]) -> None:
        self.polylines.setdefault(layer, []).extend(lines)

    def compute_bbox(self) -> BBox:
        """Recompute bbox from all polylines. Call after building."""
        pts = [p for pl in self.all_polylines() for p in pl]
        if not pts:
            self.bbox = (0.0, 0.0, 0.0, 0.0)
            return self.bbox
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        self.bbox = (min(xs), min(ys), max(xs), max(ys))
        return self.bbox


def bbox_union(bboxes: list[BBox]) -> BBox:
    """Union of axis-aligned bboxes."""
    if not bboxes:
        return (0.0, 0.0, 0.0, 0.0)
    xs0, ys0, xs1, ys1 = zip(*bboxes)
    return (min(xs0), min(ys0), max(xs1), max(ys1))


def bbox_contains(outer: BBox, inner: BBox, margin: float = 0.0) -> bool:
    """Is `inner` fully inside `outer` (with optional margin)?"""
    return (inner[0] >= outer[0] - margin and
            inner[1] >= outer[1] - margin and
            inner[2] <= outer[2] + margin and
            inner[3] <= outer[3] + margin)


def bbox_intersects(a: BBox, b: BBox) -> bool:
    return not (a[2] < b[0] or b[2] < a[0] or a[3] < b[1] or b[3] < a[1])
