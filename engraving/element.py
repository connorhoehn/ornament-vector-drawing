"""The unified Element base class.

Every architectural thing — column, arch, window, pilaster, story, bay,
facade, balustrade — is an Element. Elements form a tree (parent / children),
have a declared ``envelope`` (the world-coordinate bbox they MUST fit inside),
expose named ``anchors`` (connection points), and know how to render
themselves as stroked polylines.

Mathematical rule: ``self.effective_bbox() ⊆ self.envelope`` always.
Violations are caught by ``check_containment()`` before rendering.

See ``plans/OVERHAUL.md`` for the full design.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator

from .schema import Anchor, BBox, ElementResult, Polyline


# (polyline, stroke_width_mm) pairs
StrokedPolyline = tuple[Polyline, float]


class Material(str, Enum):
    """Material classification for CSG-style solid/void composition.

    - SOLID: subtractable mass (walls, piers). Voids in scope are cut out.
    - VOID: opening/hole. Reports a footprint polygon that solids subtract.
    - ORNAMENT: projecting object (columns, pilasters). Renders on top.
    - FRAME: decorates voids (architraves, hoods). Renders on top.

    Inherits from ``str`` so JSON/metadata round-trips remain trivial.
    """
    SOLID    = "solid"
    VOID     = "void"
    ORNAMENT = "ornament"
    FRAME    = "frame"


@dataclass
class Element:
    """Base class for all architectural elements.

    Every subclass must:
      - declare ``envelope`` (the bbox it must fit in; set at construction)
      - implement ``render_strokes()`` yielding (polyline, stroke_mm) pairs
      - implement ``effective_bbox()`` returning its actual bbox

    Hierarchy: ``parent`` is the containing element, ``children`` are nested
    elements. Anchors are in WORLD coordinates (unlike the local-frame
    anchors in ``schema.Anchor`` for ElementResult).
    """

    id: str                                           # unique within scene
    kind: str                                          # "column", "arch", ...
    envelope: BBox = (0.0, 0.0, 0.0, 0.0)              # world-coord bbox this element must fit inside
    anchors: dict[str, Anchor] = field(default_factory=dict)
    children: list["Element"] = field(default_factory=list)
    parent: "Element | None" = field(default=None, repr=False)
    metadata: dict = field(default_factory=dict)
    material: Material = field(default=Material.ORNAMENT)

    # ── CSG / void-cutting support ─────────────────────────────────────
    def void_footprint(self):
        """Return a shapely polygon (world coordinates) describing the
        hole this element cuts from enclosing solids, or ``None`` if this
        element is not a void. Only ``Material.VOID`` elements should
        override this with a non-None return.
        """
        return None

    # ── Subclass responsibilities ─────────────────────────────────────

    def render_strokes(self) -> Iterator[StrokedPolyline]:
        """Yield (polyline, stroke_width_mm) pairs for this element.
        Default: recursively yield from children. Subclasses emit their own
        polylines first, then super().render_strokes() for children."""
        for child in self.children:
            yield from child.render_strokes()

    def effective_bbox(self) -> BBox:
        """Return the tightest axis-aligned bbox covering this element's
        rendered geometry (including children).

        Default: compute from render_strokes(). Subclasses can override
        for efficiency when they know their bbox without sampling.
        """
        xs: list[float] = []
        ys: list[float] = []
        for polyline, _ in self.render_strokes():
            for x, y in polyline:
                xs.append(x)
                ys.append(y)
        if not xs:
            return self.envelope  # empty element — use its envelope
        return (min(xs), min(ys), max(xs), max(ys))

    # ── Hierarchy operations ───────────────────────────────────────────

    def add(self, child: "Element") -> "Element":
        """Attach a child element. Sets child.parent."""
        child.parent = self
        self.children.append(child)
        return child

    def descendants(self) -> Iterator["Element"]:
        """Walk the full subtree (depth-first, not including self)."""
        for c in self.children:
            yield c
            yield from c.descendants()

    def walk(self) -> Iterator["Element"]:
        """Walk including self."""
        yield self
        yield from self.descendants()

    def find(self, element_id: str) -> "Element | None":
        for n in self.walk():
            if n.id == element_id:
                return n
        return None

    # ── Containment ────────────────────────────────────────────────────

    def check_containment(self, tol: float = 0.5) -> list["Violation"]:
        """Return a list of containment violations for this subtree.

        For every (parent, child) pair, checks ``child.effective_bbox``
        fits inside ``parent.envelope`` within ``tol``. Returns empty if
        all contained.
        """
        violations: list[Violation] = []
        for child in self.descendants():
            if child.parent is None:
                continue
            parent_env = child.parent.envelope
            child_bb = child.effective_bbox()
            for side, pv, cv, sign, name in [
                (0, parent_env[0], child_bb[0], -1, "left"),
                (1, parent_env[1], child_bb[1], -1, "top"),
                (2, parent_env[2], child_bb[2], +1, "right"),
                (3, parent_env[3], child_bb[3], +1, "bottom"),
            ]:
                overshoot = sign * (cv - pv)
                if overshoot > tol:
                    violations.append(Violation(
                        layer="A",
                        rule="HierarchicalContainment",
                        element_id=child.id,
                        parent_id=child.parent.id,
                        axis=name,
                        overshoot_mm=overshoot,
                        message=(
                            f"{child.id} {name}={cv:.3f} extends past "
                            f"{child.parent.id} {name}={pv:.3f} "
                            f"(overshoot {overshoot:.3f}mm)"
                        ),
                    ))
        return violations

    # ── Compatibility bridge with the old ElementResult ────────────────

    @classmethod
    def from_element_result(cls, result: ElementResult, id: str,
                            envelope: BBox | None = None) -> "LegacyElement":
        """Wrap a legacy ElementResult as an Element. Used during migration
        so new Element-based tools can consume old builders."""
        env = envelope if envelope is not None else result.bbox
        return LegacyElement(
            id=id,
            kind=result.kind,
            envelope=env,
            legacy_polylines=list(result.polylines.items()),
            anchors=dict(result.anchors),
            metadata=dict(result.metadata),
        )


@dataclass
class Violation:
    """A structured constraint failure. More useful than string messages
    for debugging and programmatic filtering."""
    layer: str                     # "A" mathematical, "B" canonical, "C" aesthetic
    rule: str                      # "HierarchicalContainment", "SuperpositionOrder"
    element_id: str
    message: str
    parent_id: str = ""
    axis: str = ""                 # "left" / "right" / "top" / "bottom" / "x" / "y"
    overshoot_mm: float = 0.0

    def __str__(self) -> str:
        return f"[{self.layer}] {self.rule}: {self.message}"


@dataclass
class LegacyElement(Element):
    """Wraps a legacy ElementResult's polylines as an Element. Transitional
    — used only while migrating builders to native Element subclasses.

    ``legacy_polylines`` is a list of ``(layer_name, [polyline, ...])``
    tuples with stroke weights assigned per layer via a lookup table.
    """
    legacy_polylines: list[tuple[str, list[Polyline]]] = field(default_factory=list)

    _DEFAULT_WEIGHTS = {
        "silhouette": 0.35,
        "rules": 0.25,
        "ornament": 0.18,
        "dentils": 0.18,
        "voussoirs": 0.25,
        "shadow": 0.12,
    }

    def render_strokes(self) -> Iterator[StrokedPolyline]:
        for layer_name, polylines in self.legacy_polylines:
            weight = self._DEFAULT_WEIGHTS.get(layer_name, 0.25)
            for pl in polylines:
                yield pl, weight
        yield from super().render_strokes()
