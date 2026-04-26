"""Containment and adjacency constraints — the mathematical backbone.

Every check operates on an Element tree and returns a list of Violation
objects (structured, not strings). These are the Layer A rules: if any
fail, the geometry is structurally invalid and rendering should refuse.
"""
from __future__ import annotations

from typing import Iterable

from .element import Element, Violation
from .schema import BBox


# ── The backbone ──────────────────────────────────────────────────────

def hierarchical_containment(root: Element, tol: float = 0.5) -> list[Violation]:
    """THE backbone rule: every child's effective_bbox fits its parent's
    envelope (within tol mm). Walks the entire subtree rooted at ``root``.
    """
    return root.check_containment(tol=tol)


# ── Sibling non-overlap ────────────────────────────────────────────────

def sibling_non_overlap(parent: Element, axis: str = "x", tol: float = 0.5,
                        exceptions: Iterable[tuple[str, str]] = ()) -> list[Violation]:
    """Siblings of ``parent`` do not overlap each other along ``axis``.

    ``exceptions`` is an iterable of (id_a, id_b) pairs whose overlap is
    explicitly allowed (e.g. an arch voussoir ring overlapping its keystone).
    """
    ex = {(a, b) for a, b in exceptions} | {(b, a) for a, b in exceptions}
    violations: list[Violation] = []
    children = parent.children
    for i in range(len(children)):
        for j in range(i + 1, len(children)):
            a, b = children[i], children[j]
            if (a.id, b.id) in ex:
                continue
            # Exempt specific kinds that legitimately overlap siblings by
            # design: walls (SOLID background), shadows, and narrow ornament
            # elements that straddle walls or bay edges (quoins, parapets,
            # string courses, entablature bands).
            try:
                skip_kinds = {
                    "wall", "shadow", "quoin", "parapet", "plinth",
                    "string_course", "entablature_band", "facade",
                    "roof", "pediment",
                }
                if a.kind in skip_kinds or b.kind in skip_kinds:
                    continue
            except Exception:
                pass
            # Use declared ENVELOPE (not effective_bbox) for sibling check.
            # effective_bbox includes projecting ornament + shadows, which
            # legitimately extend past envelope but shouldn't count as overlap.
            ax = a.envelope
            bx = b.envelope
            if _overlap_axis(ax, bx, axis, tol):
                overlap_mm = _overlap_mm(ax, bx, axis)
                violations.append(Violation(
                    layer="A",
                    rule="SiblingNonOverlap",
                    element_id=a.id,
                    parent_id=parent.id,
                    axis=axis,
                    overshoot_mm=overlap_mm,
                    message=(
                        f"{a.id} and {b.id} overlap along {axis} axis "
                        f"by {overlap_mm:.3f} mm (parent={parent.id})"
                    ),
                ))
    return violations


# ── Shared edges (story meets story, etc.) ─────────────────────────────

def shared_edge(a: Element, b: Element, edge: str, tol: float = 0.5) -> list[Violation]:
    """Two elements share a common edge.

    ``edge`` is one of "top" (a's top y == b's bottom y), "bottom", "left",
    "right". This is how we ensure stories stack without gaps or overlap:
    story[1].bottom == story[0].top.
    """
    a_bb = a.effective_bbox()
    b_bb = b.effective_bbox()
    pairs = {
        "top":    (a_bb[1], b_bb[3]),   # a's top y (smaller) == b's bottom y (larger)
        "bottom": (a_bb[3], b_bb[1]),
        "left":   (a_bb[0], b_bb[2]),
        "right":  (a_bb[2], b_bb[0]),
    }
    if edge not in pairs:
        raise ValueError(f"edge must be one of {list(pairs)}")
    pa, pb = pairs[edge]
    if abs(pa - pb) > tol:
        return [Violation(
            layer="A", rule="SharedEdge", element_id=a.id, parent_id="",
            axis=edge, overshoot_mm=abs(pa - pb),
            message=(
                f"{a.id}.{edge}={pa:.3f} does not meet {b.id}'s "
                f"corresponding edge={pb:.3f} (gap {abs(pa - pb):.3f}mm)"
            ),
        )]
    return []


# ── Positivity: no inside-out bboxes ───────────────────────────────────

def positivity_of_dims(root: Element) -> list[Violation]:
    """Every element's envelope has positive width and height."""
    violations: list[Violation] = []
    for n in root.walk():
        x0, y0, x1, y1 = n.envelope
        if x1 < x0 or y1 < y0:
            violations.append(Violation(
                layer="A", rule="PositivityOfDims",
                element_id=n.id, parent_id=n.parent.id if n.parent else "",
                message=(
                    f"{n.id} envelope inverted: "
                    f"({x0:.3f},{y0:.3f})-({x1:.3f},{y1:.3f})"
                ),
            ))
    return violations


# ── Top-level: validate_tree ───────────────────────────────────────────

def validate_tree(root: Element, *, tol: float = 0.5) -> list[Violation]:
    """Run all Layer A checks against a tree. Returns all violations.
    If the list is empty, the tree is structurally valid."""
    out: list[Violation] = []
    out.extend(positivity_of_dims(root))
    out.extend(hierarchical_containment(root, tol=tol))
    # Sibling non-overlap at EVERY node: walk the tree and check each parent.
    # Using axis="both" so only TRUE overlaps (both axes) fire — siblings that
    # stack vertically (same x-range, different y) or tile horizontally
    # (same y-range, different x) are fine.
    for n in root.walk():
        if n.children:
            out.extend(sibling_non_overlap(n, axis="both", tol=tol))
    return out


# ── Helpers ────────────────────────────────────────────────────────────

def _overlap_axis(a: BBox, b: BBox, axis: str, tol: float) -> bool:
    if axis == "x":
        return a[2] > b[0] + tol and b[2] > a[0] + tol
    if axis == "y":
        return a[3] > b[1] + tol and b[3] > a[1] + tol
    if axis == "both":
        return (a[2] > b[0] + tol and b[2] > a[0] + tol and
                a[3] > b[1] + tol and b[3] > a[1] + tol)
    raise ValueError(f"axis must be 'x', 'y', or 'both', got {axis!r}")


def _overlap_mm(a: BBox, b: BBox, axis: str) -> float:
    if axis == "x":
        return max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    if axis == "y":
        return max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    return 0.0


# ── Self-test ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    from .element import Element

    # Parent envelope 100×100 at origin, child at (10,10)-(50,50) — fits.
    root = Element(id="root", kind="facade", envelope=(0, 0, 100, 100))

    class FixedBBoxElement(Element):
        def __init__(self, id, envelope, actual_bbox):
            super().__init__(id=id, kind="test", envelope=envelope)
            self._actual = actual_bbox
        def effective_bbox(self):
            return self._actual
        def render_strokes(self):
            return iter([])

    # Good child — inside envelope
    root.add(FixedBBoxElement("good", (10, 10, 50, 50), (10, 10, 50, 50)))
    vs = validate_tree(root)
    print(f"good child: {len(vs)} violations (expect 0)")

    # Bad child — extends past parent
    root.add(FixedBBoxElement("bad", (60, 60, 90, 90), (60, 60, 120, 90)))
    vs = validate_tree(root)
    print(f"+bad child: {len(vs)} violations (expect ≥1)")
    for v in vs:
        print(f"  {v}")
