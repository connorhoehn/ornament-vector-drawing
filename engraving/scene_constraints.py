"""Concrete constraints over a Scene. See PHASE_17_SCENE_VALIDATION.md."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Literal

from .scene import Scene, SceneNode, Vec3


# ── Debug overlay helpers ──────────────────────────────────────────────

def _dashed_vline(x: float, ymin: float, ymax: float) -> str:
    return (f'<line x1="{x:.3f}" y1="{ymin:.3f}" x2="{x:.3f}" '
            f'y2="{ymax:.3f}" stroke="red" stroke-width="0.2" '
            f'stroke-dasharray="2,1" />')


def _dashed_hline(y: float, xmin: float, xmax: float) -> str:
    return (f'<line x1="{xmin:.3f}" y1="{y:.3f}" x2="{xmax:.3f}" '
            f'y2="{y:.3f}" stroke="red" stroke-width="0.2" '
            f'stroke-dasharray="2,1" />')


def _highlight_bbox(bbox) -> str:
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0, y1 - y0
    return (f'<rect x="{x0:.3f}" y="{y0:.3f}" width="{w:.3f}" '
            f'height="{h:.3f}" fill="red" fill-opacity="0.08" '
            f'stroke="red" stroke-width="0.2" stroke-dasharray="1,1" />')


def _dot(x: float, y: float, r: float = 0.6) -> str:
    return (f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{r:.3f}" '
            f'fill="red" stroke="none" />')


@dataclass
class Constraint:
    """Base — subclasses implement check(scene) -> list[str]."""
    label: str = ""

    def check(self, scene: Scene) -> list[str]:
        return []

    def debug_geometry(self, scene: Scene) -> list[str]:
        """Return a list of SVG element strings that visualize this
        constraint's failure. Default: no geometry.
        """
        return []


# ── Alignment ──────────────────────────────────────────────────────────

@dataclass
class VerticallyAligned(Constraint):
    """All listed nodes share x-coordinate (using node origin or named anchor)."""
    node_ids: list[str] = field(default_factory=list)
    anchor: str | None = None         # use node anchor if specified
    tol: float = 0.5                   # mm

    def check(self, scene: Scene) -> list[str]:
        if len(self.node_ids) < 2:
            return []
        xs = []
        for nid in self.node_ids:
            n = scene.get(nid)
            wp = n.world_pos(self.anchor)
            xs.append((nid, wp[0]))
        ref_x = xs[0][1]
        errs = []
        for nid, x in xs[1:]:
            if abs(x - ref_x) > self.tol:
                errs.append(
                    f"VerticallyAligned[{self.label}]: {nid} x={x:.3f} "
                    f"differs from {xs[0][0]} x={ref_x:.3f} (tol={self.tol})"
                )
        return errs

    def debug_geometry(self, scene: Scene) -> list[str]:
        if not self.check(scene):
            return []
        xs: list[float] = []
        ys: list[float] = []
        for nid in self.node_ids:
            if nid not in scene.nodes:
                continue
            wp = scene.get(nid).world_pos(self.anchor)
            xs.append(wp[0])
            ys.append(wp[1])
        if not xs:
            return []
        ymin, ymax = min(ys) - 5.0, max(ys) + 5.0
        out = [_dashed_vline(x, ymin, ymax) for x in xs]
        for nid in self.node_ids:
            n = scene.nodes.get(nid)
            if n is not None:
                out.append(_highlight_bbox(n.world_bbox()))
        return out


@dataclass
class HorizontallyAligned(Constraint):
    node_ids: list[str] = field(default_factory=list)
    anchor: str | None = None
    tol: float = 0.5

    def check(self, scene: Scene) -> list[str]:
        if len(self.node_ids) < 2:
            return []
        ys = [(nid, scene.get(nid).world_pos(self.anchor)[1]) for nid in self.node_ids]
        ref_y = ys[0][1]
        errs = []
        for nid, y in ys[1:]:
            if abs(y - ref_y) > self.tol:
                errs.append(
                    f"HorizontallyAligned[{self.label}]: {nid} y={y:.3f} "
                    f"differs from {ys[0][0]} y={ref_y:.3f} (tol={self.tol})"
                )
        return errs

    def debug_geometry(self, scene: Scene) -> list[str]:
        if not self.check(scene):
            return []
        xs: list[float] = []
        ys: list[float] = []
        for nid in self.node_ids:
            if nid not in scene.nodes:
                continue
            wp = scene.get(nid).world_pos(self.anchor)
            xs.append(wp[0])
            ys.append(wp[1])
        if not ys:
            return []
        xmin, xmax = min(xs) - 5.0, max(xs) + 5.0
        out = [_dashed_hline(y, xmin, xmax) for y in ys]
        for nid in self.node_ids:
            n = scene.nodes.get(nid)
            if n is not None:
                out.append(_highlight_bbox(n.world_bbox()))
        return out


# ── Adjacency ──────────────────────────────────────────────────────────

@dataclass
class StandsOn(Constraint):
    """Upper node's bottom anchor coincides with lower node's top anchor."""
    upper_id: str = ""
    lower_id: str = ""
    upper_anchor: str = "bottom_center"
    lower_anchor: str = "top_center"
    tol: float = 0.3

    def check(self, scene: Scene) -> list[str]:
        try:
            up = scene.get(self.upper_id).world_pos(self.upper_anchor)
            lo = scene.get(self.lower_id).world_pos(self.lower_anchor)
        except KeyError as e:
            return [f"StandsOn[{self.label}]: missing anchor: {e}"]
        dx = abs(up[0] - lo[0])
        dy = abs(up[1] - lo[1])
        if dx > self.tol or dy > self.tol:
            return [f"StandsOn[{self.label}]: {self.upper_id}.{self.upper_anchor}={up[:2]} "
                    f"!= {self.lower_id}.{self.lower_anchor}={lo[:2]} (tol={self.tol})"]
        return []

    def debug_geometry(self, scene: Scene) -> list[str]:
        if not self.check(scene):
            return []
        out: list[str] = []
        try:
            up = scene.get(self.upper_id).world_pos(self.upper_anchor)
            lo = scene.get(self.lower_id).world_pos(self.lower_anchor)
        except KeyError:
            return out
        # Dots at the two anchor points.
        out.append(_dot(up[0], up[1], r=0.8))
        out.append(_dot(lo[0], lo[1], r=0.8))
        # Vertical dashed lines at both anchor x's so mis-centering is visible.
        ymin = min(up[1], lo[1]) - 5.0
        ymax = max(up[1], lo[1]) + 5.0
        out.append(_dashed_vline(up[0], ymin, ymax))
        if abs(up[0] - lo[0]) > 1e-9:
            out.append(_dashed_vline(lo[0], ymin, ymax))
        # Horizontal dashed lines at both anchor y's.
        xmin = min(up[0], lo[0]) - 5.0
        xmax = max(up[0], lo[0]) + 5.0
        out.append(_dashed_hline(up[1], xmin, xmax))
        if abs(up[1] - lo[1]) > 1e-9:
            out.append(_dashed_hline(lo[1], xmin, xmax))
        # Highlight both node bboxes.
        for nid in (self.upper_id, self.lower_id):
            n = scene.nodes.get(nid)
            if n is not None:
                out.append(_highlight_bbox(n.world_bbox()))
        return out


# ── Centering ──────────────────────────────────────────────────────────

@dataclass
class CenteredOn(Constraint):
    """Child node's axis equals parent's axis."""
    child_id: str = ""
    parent_id: str = ""
    anchor: str = "axis"
    tol: float = 0.5

    def check(self, scene: Scene) -> list[str]:
        try:
            cx = scene.get(self.child_id).world_pos(self.anchor)[0]
            px = scene.get(self.parent_id).world_pos(self.anchor)[0]
        except KeyError as e:
            return [f"CenteredOn[{self.label}]: {e}"]
        if abs(cx - px) > self.tol:
            return [f"CenteredOn[{self.label}]: {self.child_id} x={cx:.3f} "
                    f"not centered on {self.parent_id} x={px:.3f}"]
        return []

    def debug_geometry(self, scene: Scene) -> list[str]:
        if not self.check(scene):
            return []
        try:
            c = scene.get(self.child_id)
            p = scene.get(self.parent_id)
        except KeyError:
            return []
        cb = c.world_bbox()
        pb = p.world_bbox()
        ymin = min(cb[1], pb[1]) - 5.0
        ymax = max(cb[3], pb[3]) + 5.0
        out = [
            _dashed_vline(c.world_pos(self.anchor)[0], ymin, ymax),
            _dashed_vline(p.world_pos(self.anchor)[0], ymin, ymax),
            _highlight_bbox(cb),
        ]
        return out


# ── Symmetry ──────────────────────────────────────────────────────────

@dataclass
class MirrorPair(Constraint):
    """Two nodes symmetric about a vertical axis."""
    left_id: str = ""
    right_id: str = ""
    axis_x: float = 0.0
    tol: float = 0.5

    def check(self, scene: Scene) -> list[str]:
        try:
            lx = scene.get(self.left_id).world_pos()[0]
            rx = scene.get(self.right_id).world_pos()[0]
        except KeyError as e:
            return [f"MirrorPair[{self.label}]: {e}"]
        ldx = self.axis_x - lx     # how far left of axis
        rdx = rx - self.axis_x     # how far right of axis
        if abs(ldx - rdx) > self.tol:
            return [f"MirrorPair[{self.label}]: {self.left_id} dist-from-axis={ldx:.3f}, "
                    f"{self.right_id} dist={rdx:.3f}"]
        return []

    def debug_geometry(self, scene: Scene) -> list[str]:
        if not self.check(scene):
            return []
        out: list[str] = []
        try:
            l = scene.get(self.left_id)
            r = scene.get(self.right_id)
        except KeyError:
            return out
        ly = l.world_pos()[1]
        ry = r.world_pos()[1]
        ymin = min(ly, ry) - 10.0
        ymax = max(ly, ry) + 10.0
        # Mirror axis.
        out.append(_dashed_vline(self.axis_x, ymin, ymax))
        # Each node's vertical axis.
        out.append(_dashed_vline(l.world_pos()[0], ymin, ymax))
        out.append(_dashed_vline(r.world_pos()[0], ymin, ymax))
        # Highlight both bboxes.
        out.append(_highlight_bbox(l.world_bbox()))
        out.append(_highlight_bbox(r.world_bbox()))
        return out


@dataclass
class BilateralFacade(Constraint):
    """Entire facade's children form a mirror set about its centerline."""
    facade_id: str = ""
    tol: float = 0.5

    def check(self, scene: Scene) -> list[str]:
        try:
            facade = scene.get(self.facade_id)
        except KeyError as e:
            return [f"BilateralFacade: {e}"]
        # Find the centerline x
        cx = (facade.world_bbox()[0] + facade.world_bbox()[2]) / 2
        # Group children by their x distance from cx; pair them up
        kids_x = [(c.id, c.world_pos()[0]) for c in facade.children]
        kids_x.sort(key=lambda t: t[1])
        errs = []
        n = len(kids_x)
        for i in range(n // 2):
            l_id, l_x = kids_x[i]
            r_id, r_x = kids_x[n - 1 - i]
            ldx = cx - l_x
            rdx = r_x - cx
            if abs(ldx - rdx) > self.tol:
                errs.append(
                    f"BilateralFacade[{self.label}]: pair ({l_id} x={l_x:.3f}, "
                    f"{r_id} x={r_x:.3f}) not symmetric about cx={cx:.3f}"
                )
        # Middle child if odd count must be on the centerline
        if n % 2:
            mid = kids_x[n // 2]
            if abs(mid[1] - cx) > self.tol:
                errs.append(
                    f"BilateralFacade[{self.label}]: middle child {mid[0]} "
                    f"x={mid[1]:.3f} != centerline cx={cx:.3f}"
                )
        return errs

    def debug_geometry(self, scene: Scene) -> list[str]:
        if not self.check(scene):
            return []
        out: list[str] = []
        try:
            facade = scene.get(self.facade_id)
        except KeyError:
            return out
        fb = facade.world_bbox()
        cx = (fb[0] + fb[2]) / 2
        ymin, ymax = fb[1] - 5.0, fb[3] + 5.0
        # Centerline.
        out.append(_dashed_vline(cx, ymin, ymax))
        # Axis line for each child.
        for child in facade.children:
            cwx = child.world_pos()[0]
            out.append(_dashed_vline(cwx, ymin, ymax))
        # Highlight the offending (non-mirrored) children. We mark every
        # child whose mirror distance doesn't match its pair.
        kids_x = [(c.id, c.world_pos()[0]) for c in facade.children]
        kids_x.sort(key=lambda t: t[1])
        n = len(kids_x)
        for i in range(n // 2):
            l_id, l_x = kids_x[i]
            r_id, r_x = kids_x[n - 1 - i]
            ldx = cx - l_x
            rdx = r_x - cx
            if abs(ldx - rdx) > self.tol:
                for nid in (l_id, r_id):
                    node = scene.nodes.get(nid)
                    if node is not None:
                        out.append(_highlight_bbox(node.world_bbox()))
        if n % 2:
            mid_id, mid_x = kids_x[n // 2]
            if abs(mid_x - cx) > self.tol:
                node = scene.nodes.get(mid_id)
                if node is not None:
                    out.append(_highlight_bbox(node.world_bbox()))
        return out


# ── Hierarchical ──────────────────────────────────────────────────────

@dataclass
class ContainedIn(Constraint):
    """Child bbox fits inside parent bbox + margin."""
    child_id: str = ""
    parent_id: str = ""
    margin: float = 0.0

    def check(self, scene: Scene) -> list[str]:
        try:
            cb = scene.get(self.child_id).world_bbox()
            pb = scene.get(self.parent_id).world_bbox()
        except KeyError as e:
            return [f"ContainedIn: {e}"]
        if not (cb[0] >= pb[0] - self.margin and cb[1] >= pb[1] - self.margin
                and cb[2] <= pb[2] + self.margin and cb[3] <= pb[3] + self.margin):
            return [f"ContainedIn[{self.label}]: {self.child_id} {cb} not in "
                    f"{self.parent_id} {pb} (margin={self.margin})"]
        return []

    def debug_geometry(self, scene: Scene) -> list[str]:
        if not self.check(scene):
            return []
        try:
            cb = scene.get(self.child_id).world_bbox()
            pb = scene.get(self.parent_id).world_bbox()
        except KeyError:
            return []
        return [_highlight_bbox(cb), _highlight_bbox(pb)]


# ── Architectural-specific ────────────────────────────────────────────

@dataclass
class CorrespondingBays(Constraint):
    """Two stories' bays must align vertically (same x for matching bay index)."""
    story_a_id: str = ""
    story_b_id: str = ""
    tol: float = 0.5

    def check(self, scene: Scene) -> list[str]:
        try:
            a = scene.get(self.story_a_id)
            b = scene.get(self.story_b_id)
        except KeyError as e:
            return [f"CorrespondingBays: {e}"]
        a_bays = [c for c in a.children if c.kind == "bay"]
        b_bays = [c for c in b.children if c.kind == "bay"]
        if len(a_bays) != len(b_bays):
            return [f"CorrespondingBays[{self.label}]: bay counts differ "
                    f"({self.story_a_id}={len(a_bays)} vs {self.story_b_id}={len(b_bays)})"]
        errs = []
        for ai, bi in zip(a_bays, b_bays):
            ax = ai.world_pos()[0]
            bx = bi.world_pos()[0]
            if abs(ax - bx) > self.tol:
                errs.append(
                    f"CorrespondingBays[{self.label}]: {ai.id} x={ax:.3f} "
                    f"vs {bi.id} x={bx:.3f}"
                )
        return errs

    def debug_geometry(self, scene: Scene) -> list[str]:
        if not self.check(scene):
            return []
        out: list[str] = []
        try:
            a = scene.get(self.story_a_id)
            b = scene.get(self.story_b_id)
        except KeyError:
            return out
        a_bays = [c for c in a.children if c.kind == "bay"]
        b_bays = [c for c in b.children if c.kind == "bay"]
        # Span covering both stories' y range.
        ys = []
        for n in (a, b):
            bb = n.world_bbox()
            ys.extend([bb[1], bb[3]])
        if not ys:
            return out
        ymin, ymax = min(ys) - 5.0, max(ys) + 5.0
        for ai, bi in zip(a_bays, b_bays):
            ax = ai.world_pos()[0]
            bx = bi.world_pos()[0]
            if abs(ax - bx) > self.tol:
                out.append(_dashed_vline(ax, ymin, ymax))
                out.append(_dashed_vline(bx, ymin, ymax))
                out.append(_highlight_bbox(ai.world_bbox()))
                out.append(_highlight_bbox(bi.world_bbox()))
        return out


@dataclass
class GroundLine(Constraint):
    """Listed nodes share a common ground y."""
    node_ids: list[str] = field(default_factory=list)
    ground_y: float = 0.0
    tol: float = 0.5

    def check(self, scene: Scene) -> list[str]:
        errs = []
        for nid in self.node_ids:
            try:
                ny = scene.get(nid).world_pos()[1]
            except KeyError as e:
                errs.append(f"GroundLine: {e}")
                continue
            if abs(ny - self.ground_y) > self.tol:
                errs.append(f"GroundLine[{self.label}]: {nid} y={ny:.3f} "
                            f"!= ground={self.ground_y}")
        return errs

    def debug_geometry(self, scene: Scene) -> list[str]:
        if not self.check(scene):
            return []
        xs: list[float] = []
        ys: list[float] = []
        for nid in self.node_ids:
            n = scene.nodes.get(nid)
            if n is None:
                continue
            wp = n.world_pos()
            xs.append(wp[0])
            ys.append(wp[1])
        if not xs:
            return []
        xmin, xmax = min(xs) - 5.0, max(xs) + 5.0
        out = [_dashed_hline(self.ground_y, xmin, xmax)]
        for nid in self.node_ids:
            n = scene.nodes.get(nid)
            if n is not None:
                out.append(_highlight_bbox(n.world_bbox()))
        return out


@dataclass
class EvenPitch(Constraint):
    """Listed nodes have constant on-center spacing along an axis."""
    node_ids: list[str] = field(default_factory=list)
    axis: Literal["x", "y"] = "x"
    tol: float = 0.5

    def check(self, scene: Scene) -> list[str]:
        if len(self.node_ids) < 3:
            return []
        idx = 0 if self.axis == "x" else 1
        coords = sorted(scene.get(nid).world_pos()[idx] for nid in self.node_ids)
        pitches = [coords[i+1] - coords[i] for i in range(len(coords)-1)]
        ref = pitches[0]
        errs = []
        for i, p in enumerate(pitches[1:], 1):
            if abs(p - ref) > self.tol:
                errs.append(f"EvenPitch[{self.label}]: pitch[{i}]={p:.3f} "
                            f"differs from pitch[0]={ref:.3f}")
        return errs

    def debug_geometry(self, scene: Scene) -> list[str]:
        if not self.check(scene):
            return []
        xs: list[float] = []
        ys: list[float] = []
        for nid in self.node_ids:
            n = scene.nodes.get(nid)
            if n is None:
                continue
            wp = n.world_pos()
            xs.append(wp[0])
            ys.append(wp[1])
        if not xs:
            return []
        out: list[str] = []
        if self.axis == "x":
            ymin, ymax = min(ys) - 5.0, max(ys) + 5.0
            for x in xs:
                out.append(_dashed_vline(x, ymin, ymax))
        else:
            xmin, xmax = min(xs) - 5.0, max(xs) + 5.0
            for y in ys:
                out.append(_dashed_hline(y, xmin, xmax))
        for nid in self.node_ids:
            n = scene.nodes.get(nid)
            if n is not None:
                out.append(_highlight_bbox(n.world_bbox()))
        return out


# ── Wave-3 specialized architectural constraints ──────────────────────
# Classical references cited per Vignola (Regola delli cinque ordini,
# 1562; English edition Ware 1902).


@dataclass
class SuperpositionOrder(Constraint):
    """Roman superposition rule: heavier orders below, lighter above.

    Standard sequence (Vignola, Regola, plates I–V; Ware p. 4): Tuscan /
    Doric / Ionic / Corinthian / Composite, any subset in this order
    from bottom to top. The canonical example is the Colosseum
    (Doric–Ionic–Corinthian).

    Each story node must carry ``metadata["has_order"]`` naming its
    order; stories without that metadata are ignored. The check walks
    ``story_ids`` bottom-to-top and verifies the collected order names
    form a (non-strict) sub-sequence of ``expected_sequence``.
    """
    story_ids: list[str] = field(default_factory=list)    # bottom to top
    expected_sequence: list[str] = field(default_factory=lambda: [
        "tuscan", "doric", "ionic", "corinthian", "composite"
    ])

    def check(self, scene: Scene) -> list[str]:
        if len(self.story_ids) < 2:
            return []
        actual: list[tuple[str, str]] = []  # (story_id, order_name)
        errs: list[str] = []
        for sid in self.story_ids:
            try:
                n = scene.get(sid)
            except KeyError as e:
                errs.append(f"SuperpositionOrder[{self.label}]: {e}")
                continue
            o = n.metadata.get("has_order")
            if o is None:
                continue
            actual.append((sid, str(o).lower()))
        # Walk actual story-orders against expected_sequence, requiring
        # monotonic non-decreasing index in expected_sequence.
        exp = [e.lower() for e in self.expected_sequence]
        last_idx = -1
        last_story = None
        for sid, name in actual:
            if name not in exp:
                errs.append(
                    f"SuperpositionOrder[{self.label}]: story {sid!r} "
                    f"carries unknown order {name!r} (expected one of "
                    f"{self.expected_sequence})"
                )
                continue
            idx = exp.index(name)
            if idx < last_idx:
                errs.append(
                    f"SuperpositionOrder[{self.label}]: story {sid!r} "
                    f"({name}) is lighter than story {last_story!r} below "
                    f"it — violates sequence {self.expected_sequence}"
                )
            else:
                last_idx = idx
                last_story = sid
        return errs


@dataclass
class KeystoneOverDoor(Constraint):
    """A keystone node must be horizontally centered over a door node.

    Vignola, Regola, plate XXXII (arched openings); Ware p. 92: the
    keystone's axis coincides with the arch's (and the door's) axis of
    symmetry. Only the x-coordinate is checked; y is free so the
    keystone can sit anywhere on the arch head.
    """
    door_id: str = ""
    keystone_id: str = ""
    tol: float = 0.5

    def check(self, scene: Scene) -> list[str]:
        try:
            dx = scene.get(self.door_id).world_pos()[0]
            kx = scene.get(self.keystone_id).world_pos()[0]
        except KeyError as e:
            return [f"KeystoneOverDoor[{self.label}]: {e}"]
        if abs(dx - kx) > self.tol:
            return [
                f"KeystoneOverDoor[{self.label}]: keystone {self.keystone_id} "
                f"x={kx:.3f} not centered over door {self.door_id} "
                f"x={dx:.3f} (tol={self.tol})"
            ]
        return []


@dataclass
class ColumnsUnderPediment(Constraint):
    """Outermost columns flank pediment base; apex centered on span.

    Vignola, Regola, plates VI–X (full orders with pediments); Ware
    pp. 142–144: a classical pediment spans the outer columns of the
    portico — its left and right tails align with the outer column
    axes, and its apex sits on the midpoint of that span.

    The pediment is expected to expose either ``pos`` (apex) plus an
    ``apex`` / ``left`` / ``right`` anchor, or fall back to its world
    bounding box: bbox[0] = left edge x, bbox[2] = right edge x,
    mid-x = apex.
    """
    column_ids: list[str] = field(default_factory=list)   # left-to-right
    pediment_id: str = ""
    tol: float = 1.0

    def check(self, scene: Scene) -> list[str]:
        if len(self.column_ids) < 2:
            return [f"ColumnsUnderPediment[{self.label}]: need ≥2 columns"]
        try:
            ped = scene.get(self.pediment_id)
            cols = [scene.get(c) for c in self.column_ids]
        except KeyError as e:
            return [f"ColumnsUnderPediment[{self.label}]: {e}"]

        col_xs = [c.world_pos()[0] for c in cols]
        left_col = min(col_xs)
        right_col = max(col_xs)
        mid_col = 0.5 * (left_col + right_col)

        # Prefer named anchors on the pediment if present.
        def _try_anchor(name: str):
            try:
                return ped.world_pos(name)
            except KeyError:
                return None

        ped_left = _try_anchor("left")
        ped_right = _try_anchor("right")
        ped_apex = _try_anchor("apex")

        if ped_left is not None:
            left_x = ped_left[0]
        else:
            left_x = ped.world_bbox()[0]
        if ped_right is not None:
            right_x = ped_right[0]
        else:
            right_x = ped.world_bbox()[2]
        if ped_apex is not None:
            apex_x = ped_apex[0]
        else:
            apex_x = 0.5 * (left_x + right_x)

        errs: list[str] = []
        if abs(left_x - left_col) > self.tol:
            errs.append(
                f"ColumnsUnderPediment[{self.label}]: pediment left edge "
                f"x={left_x:.3f} ≠ leftmost column x={left_col:.3f} "
                f"(tol={self.tol})"
            )
        if abs(right_x - right_col) > self.tol:
            errs.append(
                f"ColumnsUnderPediment[{self.label}]: pediment right edge "
                f"x={right_x:.3f} ≠ rightmost column x={right_col:.3f} "
                f"(tol={self.tol})"
            )
        if abs(apex_x - mid_col) > self.tol:
            errs.append(
                f"ColumnsUnderPediment[{self.label}]: pediment apex "
                f"x={apex_x:.3f} ≠ column-span midpoint x={mid_col:.3f} "
                f"(tol={self.tol})"
            )
        return errs


@dataclass
class WindowAxesAlignAcrossStories(Constraint):
    """Windows in the same bay across stories share an x-axis.

    Ware p. 223 (on astylar palazzi): windows of each bay are stacked
    on a common vertical axis from story to story. The check looks up
    ``<story_id>.bay_<bay_index>.opening`` (or ``.window``) for every
    story in ``story_ids`` and compares their world-x.
    """
    bay_index: int = 0
    story_ids: list[str] = field(default_factory=list)
    tol: float = 0.5

    def check(self, scene: Scene) -> list[str]:
        if len(self.story_ids) < 2:
            return []
        xs: list[tuple[str, float]] = []
        errs: list[str] = []
        for sid in self.story_ids:
            # Try opening first, then window, then bay itself.
            candidates = [
                f"{sid}.bay_{self.bay_index}.opening",
                f"{sid}.bay_{self.bay_index}.window",
                f"{sid}.bay_{self.bay_index}",
            ]
            found = None
            for cid in candidates:
                if cid in scene.nodes:
                    found = cid
                    break
            if found is None:
                errs.append(
                    f"WindowAxesAlignAcrossStories[{self.label}]: no "
                    f"opening/window/bay node for story {sid!r} "
                    f"bay {self.bay_index}"
                )
                continue
            xs.append((found, scene.get(found).world_pos()[0]))
        if len(xs) < 2:
            return errs
        ref_id, ref_x = xs[0]
        for nid, x in xs[1:]:
            if abs(x - ref_x) > self.tol:
                errs.append(
                    f"WindowAxesAlignAcrossStories[{self.label}]: "
                    f"{nid} x={x:.3f} differs from {ref_id} x={ref_x:.3f} "
                    f"(tol={self.tol})"
                )
        return errs


@dataclass
class RusticationCoursesAlign(Constraint):
    """Horizontal joint lines in adjacent rusticated bays share y values.

    Vignola, Regola, plate XXVIII (rustication); Ware pp. 47–49: in a
    single rusticated course, the horizontal joints of one bay must
    continue across the adjacent bay at the same heights. Each bay
    node in the story is expected to carry ``metadata["joint_ys"]`` —
    a sorted list of world-y values at which horizontal joints cut
    the bay face.
    """
    story_id: str = ""
    tol: float = 0.5

    def check(self, scene: Scene) -> list[str]:
        try:
            story = scene.get(self.story_id)
        except KeyError as e:
            return [f"RusticationCoursesAlign[{self.label}]: {e}"]
        bays = [c for c in story.children if c.kind == "bay"]
        if len(bays) < 2:
            return []
        ref_bay = None
        ref_ys: list[float] | None = None
        errs: list[str] = []
        for b in bays:
            jys = b.metadata.get("joint_ys")
            if jys is None:
                continue
            jys_sorted = sorted(float(y) for y in jys)
            if ref_ys is None:
                ref_ys = jys_sorted
                ref_bay = b.id
                continue
            if len(jys_sorted) != len(ref_ys):
                errs.append(
                    f"RusticationCoursesAlign[{self.label}]: bay {b.id} has "
                    f"{len(jys_sorted)} joints vs {ref_bay} has {len(ref_ys)}"
                )
                continue
            for i, (y, ry) in enumerate(zip(jys_sorted, ref_ys)):
                if abs(y - ry) > self.tol:
                    errs.append(
                        f"RusticationCoursesAlign[{self.label}]: bay {b.id} "
                        f"joint[{i}] y={y:.3f} differs from {ref_bay} "
                        f"y={ry:.3f} (tol={self.tol})"
                    )
        return errs


@dataclass
class TriglyphOverEachColumn(Constraint):
    """For Doric entablatures: triglyph centered over every column axis.

    Vitruvius IV.3; Vignola, Regola, plate XIII; Ware p. 68: in a
    canonical Doric frieze, a triglyph sits directly above each column
    axis (with intermediate triglyphs over each intercolumniation).
    """
    column_ids: list[str] = field(default_factory=list)
    triglyph_ids: list[str] = field(default_factory=list)
    tol: float = 0.3

    def check(self, scene: Scene) -> list[str]:
        try:
            col_xs = [scene.get(c).world_pos()[0] for c in self.column_ids]
            tri_xs = [scene.get(t).world_pos()[0] for t in self.triglyph_ids]
        except KeyError as e:
            return [f"TriglyphOverEachColumn[{self.label}]: {e}"]
        errs: list[str] = []
        for cid, cx in zip(self.column_ids, col_xs):
            if not any(abs(tx - cx) <= self.tol for tx in tri_xs):
                errs.append(
                    f"TriglyphOverEachColumn[{self.label}]: no triglyph "
                    f"within {self.tol} of column {cid} (x={cx:.3f}); "
                    f"triglyph xs = {[round(t, 3) for t in tri_xs]}"
                )
        return errs


@dataclass
class StylobateUnderColumns(Constraint):
    """All listed columns share a common base_y (stylobate).

    Vignola, Regola, plate V; Ware p. 27: the stylobate is the
    continuous horizontal plinth on which the columns of a colonnade
    stand — every column's base sits at the same y.
    """
    column_ids: list[str] = field(default_factory=list)
    tol: float = 0.5

    def check(self, scene: Scene) -> list[str]:
        if len(self.column_ids) < 2:
            return []
        ys: list[tuple[str, float]] = []
        errs: list[str] = []
        for cid in self.column_ids:
            try:
                ys.append((cid, scene.get(cid).world_pos()[1]))
            except KeyError as e:
                errs.append(f"StylobateUnderColumns[{self.label}]: {e}")
        if len(ys) < 2:
            return errs
        ref_id, ref_y = ys[0]
        for cid, y in ys[1:]:
            if abs(y - ref_y) > self.tol:
                errs.append(
                    f"StylobateUnderColumns[{self.label}]: column {cid} "
                    f"y={y:.3f} differs from {ref_id} y={ref_y:.3f} "
                    f"(tol={self.tol})"
                )
        return errs


@dataclass
class IntercolumniationConsistent(Constraint):
    """Column on-centers are consistent (eustyle, systyle, etc.).

    Vitruvius III.3 and Ware pp. 31–33 codify the classical
    intercolumniations (pycnostyle 1½D, systyle 2D, eustyle 2¼D,
    diastyle 3D, araeostyle 4D). If ``expected_pitch`` is given, every
    gap is compared to it; otherwise all gaps must equal each other.
    Columns are sorted by x before pitches are computed.
    """
    column_ids: list[str] = field(default_factory=list)
    expected_pitch: float | None = None
    tol: float = 0.5

    def check(self, scene: Scene) -> list[str]:
        if len(self.column_ids) < 2:
            return []
        try:
            xs = sorted(scene.get(c).world_pos()[0] for c in self.column_ids)
        except KeyError as e:
            return [f"IntercolumniationConsistent[{self.label}]: {e}"]
        if len(xs) < 2:
            return []
        pitches = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
        errs: list[str] = []
        if self.expected_pitch is not None:
            for i, p in enumerate(pitches):
                if abs(p - self.expected_pitch) > self.tol:
                    errs.append(
                        f"IntercolumniationConsistent[{self.label}]: "
                        f"pitch[{i}]={p:.3f} ≠ expected "
                        f"{self.expected_pitch:.3f} (tol={self.tol})"
                    )
        else:
            if len(pitches) < 2:
                return []
            ref = pitches[0]
            for i, p in enumerate(pitches[1:], 1):
                if abs(p - ref) > self.tol:
                    errs.append(
                        f"IntercolumniationConsistent[{self.label}]: "
                        f"pitch[{i}]={p:.3f} differs from pitch[0]={ref:.3f} "
                        f"(tol={self.tol})"
                    )
        return errs


# ── Phase 18 — Opening hierarchy + assembly bounds ────────────────────

@dataclass
class OpeningWidthHierarchy(Constraint):
    """Openings narrow as you go up the facade. Ground arches widest,
    piano nobile narrower, upper story smallest. After Vignola/Palladio.
    """
    opening_ids: list[str] = field(default_factory=list)  # bottom to top
    strictness: Literal["strict", "monotonic", "classical"] = "monotonic"
    tol: float = 0.5  # mm slop for monotonic

    def check(self, scene: Scene) -> list[str]:
        widths = []
        for oid in self.opening_ids:
            try:
                n = scene.get(oid)
            except KeyError as e:
                return [f"OpeningWidthHierarchy[{self.label}]: {e}"]
            bx0, _, bx1, _ = n.bbox_local
            widths.append((oid, bx1 - bx0))
        errs = []
        for i in range(1, len(widths)):
            prev_w = widths[i - 1][1]
            cur_w = widths[i][1]
            if self.strictness == "strict":
                if cur_w >= prev_w:
                    errs.append(
                        f"OpeningWidthHierarchy[{self.label}]: "
                        f"{widths[i][0]} (w={cur_w:.2f}) not strictly narrower "
                        f"than {widths[i-1][0]} (w={prev_w:.2f})"
                    )
            elif self.strictness == "monotonic":
                if cur_w > prev_w + self.tol:
                    errs.append(
                        f"OpeningWidthHierarchy[{self.label}]: "
                        f"{widths[i][0]} (w={cur_w:.2f}) wider than "
                        f"{widths[i-1][0]} (w={prev_w:.2f})"
                    )
        return errs


@dataclass
class OpeningHeightHierarchy(Constraint):
    """Piano nobile is the tallest opening (most important room); ground
    and upper stories shorter. piano_nobile_index=1 by default (second
    from bottom).
    """
    opening_ids: list[str] = field(default_factory=list)  # bottom to top
    piano_nobile_index: int = 1
    tol: float = 0.5

    def check(self, scene: Scene) -> list[str]:
        heights = []
        for oid in self.opening_ids:
            try:
                n = scene.get(oid)
            except KeyError as e:
                return [f"OpeningHeightHierarchy[{self.label}]: {e}"]
            _, by0, _, by1 = n.bbox_local
            heights.append((oid, by1 - by0))
        if self.piano_nobile_index >= len(heights):
            return []
        pn_id, pn_h = heights[self.piano_nobile_index]
        errs = []
        for oid, h in heights:
            if oid != pn_id and h > pn_h + self.tol:
                errs.append(
                    f"OpeningHeightHierarchy[{self.label}]: "
                    f"{oid} (h={h:.2f}) taller than piano nobile "
                    f"{pn_id} (h={pn_h:.2f})"
                )
        return errs


@dataclass
class BayContentFits(Constraint):
    """An opening's assembly bbox must not exceed the bay pitch by more
    than max_overlap_frac. Catches ballooning architraves that crowd
    adjacent bays.
    """
    opening_id: str = ""
    bay_pitch: float = 0.0
    max_overlap_frac: float = 0.85

    def check(self, scene: Scene) -> list[str]:
        try:
            n = scene.get(self.opening_id)
        except KeyError as e:
            return [f"BayContentFits[{self.label}]: {e}"]
        bx0, _, bx1, _ = n.bbox_local
        w = bx1 - bx0
        allowed = self.bay_pitch * self.max_overlap_frac
        if w > allowed:
            return [
                f"BayContentFits[{self.label}]: {self.opening_id} "
                f"bbox_w={w:.2f} exceeds {self.max_overlap_frac:.0%} of "
                f"bay_pitch={self.bay_pitch:.2f}"
            ]
        return []


@dataclass
class ElementConfinedToStory(Constraint):
    """A pilaster, column, or window assembly MUST NOT extend past its
    containing story's y range. User-observed on 2026-04-19: pilasters on
    the piano nobile were extending up into the upper story's wall and
    down into the ground story, crossing the string-course floor lines.
    In a well-formed facade, an element's vertical extent stays within
    (story.y_top, story.y_bottom).

    Applies to columns, pilasters, windows, and their architraves.
    """
    element_id: str = ""
    story_y_top: float = 0.0       # y at the TOP of the story (smaller y in SVG)
    story_y_bottom: float = 0.0    # y at the BOTTOM (larger y)
    tol: float = 0.5

    def check(self, scene: Scene) -> list[str]:
        try:
            n = scene.get(self.element_id)
        except KeyError as e:
            return [f"ElementConfinedToStory[{self.label}]: {e}"]
        _, ey0, _, ey1 = n.world_bbox()
        # ey0 < ey1 in SVG where y grows downward
        errs = []
        if ey0 < self.story_y_top - self.tol:
            errs.append(
                f"ElementConfinedToStory[{self.label}]: {self.element_id} "
                f"top y={ey0:.2f} extends above story_y_top={self.story_y_top:.2f} "
                f"(overshoot {self.story_y_top - ey0:.2f}mm)"
            )
        if ey1 > self.story_y_bottom + self.tol:
            errs.append(
                f"ElementConfinedToStory[{self.label}]: {self.element_id} "
                f"bottom y={ey1:.2f} extends below story_y_bottom={self.story_y_bottom:.2f} "
                f"(overshoot {ey1 - self.story_y_bottom:.2f}mm)"
            )
        return errs

    def debug_geometry(self, scene: Scene) -> list[str]:
        if not self.check(scene):
            return []
        try:
            bbox = scene.get(self.element_id).world_bbox()
            return [_highlight_bbox(bbox)]
        except KeyError:
            return []


if __name__ == "__main__":
    from .scene import Scene, SceneNode

    scene = Scene()
    # Stack 3 boxes correctly
    scene.add(SceneNode(id="a", kind="box", pos=(100, 0, 0)))
    scene.add(SceneNode(id="b", kind="box", pos=(100, -50, 0)))
    scene.add(SceneNode(id="c", kind="box", pos=(100, -100, 0)))

    scene.constrain(VerticallyAligned(node_ids=["a", "b", "c"], label="stack"))
    report = scene.validate()
    print(f"aligned stack: {len(report)} errors (expect 0)")

    # Misalign one
    scene2 = Scene()
    scene2.add(SceneNode(id="a", kind="box", pos=(100, 0, 0)))
    scene2.add(SceneNode(id="b", kind="box", pos=(105, -50, 0)))  # off by 5
    scene2.constrain(VerticallyAligned(node_ids=["a", "b"], label="stack", tol=0.5))
    report = scene2.validate()
    print(f"misaligned stack: {len(report)} errors (expect 1)")
    for e in report: print(f"  - {e}")
