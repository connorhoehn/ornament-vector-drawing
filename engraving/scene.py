"""Scene-graph for hierarchical architectural validation.

Every element in a plate becomes a SceneNode. SceneNodes form a tree (via
parent/children). Each node carries a 3D Cartesian position (x, y, z) and
named anchors in its local frame. The Scene container indexes nodes by id
and supports glob-style queries for constraints.

See plans/PHASE_17_SCENE_VALIDATION.md for the full design.
"""
from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from typing import Iterator

from .schema import Anchor, BBox, ElementResult


Vec3 = tuple[float, float, float]


@dataclass
class SceneNode:
    id: str                                       # path-style id e.g. "facade.story_1.bay_2.column"
    kind: str                                      # "column", "window", "pilaster", "arch", "story", "bay", "facade"
    pos: Vec3 = (0.0, 0.0, 0.0)                   # 3D position of node origin in WORLD coords (mm)
    bbox_local: BBox = (0.0, 0.0, 0.0, 0.0)       # bounding box in LOCAL frame (relative to pos)
    anchors: dict[str, Anchor] = field(default_factory=dict)   # in LOCAL frame
    parent: "SceneNode | None" = None
    children: list["SceneNode"] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def world_pos(self, anchor_name: str = None) -> Vec3:
        """Resolve anchor's world position (or node origin's if no anchor named)."""
        if anchor_name is None:
            return self.pos
        if anchor_name not in self.anchors:
            raise KeyError(f"node {self.id!r} has no anchor {anchor_name!r}")
        a = self.anchors[anchor_name]
        return (self.pos[0] + a.x, self.pos[1] + a.y, self.pos[2])

    def world_bbox(self) -> BBox:
        x0, y0, x1, y1 = self.bbox_local
        return (self.pos[0] + x0, self.pos[1] + y0,
                self.pos[0] + x1, self.pos[1] + y1)

    def descendants(self) -> Iterator["SceneNode"]:
        for c in self.children:
            yield c
            yield from c.descendants()


class Scene:
    """A hierarchical scene with constraints."""

    def __init__(self):
        self.nodes: dict[str, SceneNode] = {}
        self.root: SceneNode | None = None
        self.constraints: list = []

    def add(self, node: SceneNode, parent_id: str | None = None) -> None:
        if node.id in self.nodes:
            raise ValueError(f"duplicate node id: {node.id}")
        self.nodes[node.id] = node
        if parent_id:
            parent = self.nodes[parent_id]
            parent.children.append(node)
            node.parent = parent
        elif self.root is None:
            self.root = node

    def get(self, node_id: str) -> SceneNode:
        return self.nodes[node_id]

    def find(self, pattern: str) -> list[SceneNode]:
        """Glob-style query. Examples:
            "story_*.bay_2.*"       — everything in bay 2 across stories
            "*.column"              — every column at any depth
            "facade.story_0.bay_*"  — every bay in story 0
        Pattern uses fnmatch on the node's id.
        """
        return [n for n in self.nodes.values() if fnmatch.fnmatch(n.id, pattern)]

    def constrain(self, c) -> None:
        self.constraints.append(c)

    def validate(self) -> "ValidationReport":
        from .validate import ValidationReport
        report = ValidationReport()
        for c in self.constraints:
            errs = c.check(self)
            report.errors.extend(errs)
        return report

    def render_debug(self, source_svg, output_svg):
        """Re-render the source SVG with overlay annotations for every failed
        constraint.

        For each failed constraint, draw:
          - Red dashed axis lines at the relevant nodes' positions
          - Red text label at the constraint's anchor point
          - A faded red highlight box around offending node bboxes

        The output SVG is a copy of source_svg with an ``<!-- DEBUG OVERLAY -->``
        block injected just before ``</svg>``. Plate SVGs use 1:1 mm units so
        world coordinates map directly to SVG user units (no transform needed).

        Returns the Path to output_svg.
        """
        from pathlib import Path as _Path

        source_svg = _Path(source_svg)
        output_svg = _Path(output_svg)

        src_text = source_svg.read_text()
        overlay_lines: list[str] = []

        for c in self.constraints:
            errs = c.check(self)
            if not errs:
                continue
            # Geometry (axis lines + highlight boxes) for this constraint.
            geometry = c.debug_geometry(self) if hasattr(c, "debug_geometry") else []
            overlay_lines.extend(geometry)
            # Text labels per error.
            label_pos = self._error_label_pos(c)
            if label_pos is not None:
                x, y = label_pos
                for i, err in enumerate(errs):
                    # Stack labels vertically if multiple errors on the same
                    # constraint, so they don't overlap.
                    ly = y + i * 3.5
                    text = _svg_escape(err[:80])
                    overlay_lines.append(
                        f'<text x="{x:.3f}" y="{ly:.3f}" font-size="2.4" '
                        f'fill="red" font-family="serif">{text}</text>'
                    )

        if overlay_lines:
            overlay = "\n".join(overlay_lines)
            closing = "</svg>"
            if closing in src_text:
                out_text = src_text.replace(
                    closing,
                    f"<!-- DEBUG OVERLAY -->\n"
                    f'<g id="scene-debug-overlay" fill="none" stroke="red">\n'
                    f"{overlay}\n"
                    f"</g>\n{closing}",
                )
            else:
                out_text = src_text
        else:
            out_text = src_text

        output_svg.write_text(out_text)
        return output_svg

    def _error_label_pos(self, constraint) -> tuple[float, float] | None:
        """Pick an anchor point on the plate near which to draw a label for
        the given constraint. Returns (x, y) in world mm, or None if the
        constraint references no resolvable nodes.
        """
        # Collect every node id this constraint references, if any.
        ids: list[str] = []
        for attr in ("node_ids",):
            v = getattr(constraint, attr, None)
            if isinstance(v, list):
                ids.extend(v)
        for attr in ("upper_id", "lower_id", "left_id", "right_id",
                     "child_id", "parent_id", "facade_id",
                     "story_a_id", "story_b_id"):
            v = getattr(constraint, attr, None)
            if isinstance(v, str) and v:
                ids.append(v)

        xs: list[float] = []
        ys: list[float] = []
        for nid in ids:
            n = self.nodes.get(nid)
            if n is None:
                continue
            wp = n.world_pos()
            xs.append(wp[0])
            ys.append(wp[1])
        if not xs:
            return None
        x = sum(xs) / len(xs)
        # Place the label slightly above the mean y (smaller y = up in SVG).
        y = min(ys) - 4.0
        return (x, y)


def _svg_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace('"', "&quot;")
         .replace("'", "&#39;")
    )


def from_element_result(result: ElementResult, id: str,
                         pos: Vec3 = (0.0, 0.0, 0.0),
                         metadata: dict = None) -> SceneNode:
    """Convert an ElementResult to a SceneNode rooted at the given position.

    The ElementResult's anchors become the SceneNode's local anchors;
    the bbox is inherited; metadata is copied + merged with provided dict.
    """
    md = dict(result.metadata)
    if metadata:
        md.update(metadata)
    # Anchors in ElementResult are already in absolute coords (x, y in mm).
    # For SceneNode, we want them in LOCAL frame relative to pos.
    local_anchors = {
        name: Anchor(name=a.name, x=a.x - pos[0], y=a.y - pos[1], role=a.role)
        for name, a in result.anchors.items()
    }
    bx0, by0, bx1, by1 = result.bbox
    local_bbox = (bx0 - pos[0], by0 - pos[1], bx1 - pos[0], by1 - pos[1])
    return SceneNode(
        id=id, kind=result.kind, pos=pos,
        bbox_local=local_bbox, anchors=local_anchors,
        metadata=md,
    )


if __name__ == "__main__":
    # Smoke test — scene construction, query, anchor resolution.
    scene = Scene()
    scene.add(SceneNode(id="facade", kind="facade", pos=(0.0, 0.0, 0.0),
                        bbox_local=(0.0, -400.0, 600.0, 0.0)))
    scene.add(SceneNode(id="facade.story_0", kind="story",
                        pos=(0.0, 0.0, 0.0)),
              parent_id="facade")
    scene.add(SceneNode(id="facade.story_0.bay_0", kind="bay",
                        pos=(100.0, 0.0, 0.0)),
              parent_id="facade.story_0")
    scene.add(SceneNode(id="facade.story_0.bay_1", kind="bay",
                        pos=(300.0, 0.0, 0.0)),
              parent_id="facade.story_0")
    bays = scene.find("facade.story_0.bay_*")
    print(f"scene: {len(scene.nodes)} nodes, {len(bays)} bays found (expect 2)")
    # Anchor resolution.
    col = SceneNode(id="col", kind="column", pos=(100.0, -50.0, 0.0),
                    anchors={"top": Anchor("top", 0.0, -200.0)})
    print(f"col.world_pos('top') = {col.world_pos('top')} (expect (100.0, -250.0, 0.0))")
