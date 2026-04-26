"""Facade composition — assemble Stories, Bays, and Openings into elevations.

After Ware, *The American Vignola* p. 45 ("Superposition"). A classical facade
is a stack of stories (bottom-up), with a consistent rhythm of bays (vertical
axes). This module composes the primitives from ``rustication``, ``arches``,
``windows``, ``pilasters`` and ``balustrades`` into a single facade result
dict. No SVG is emitted here — the output is a layered dict of polylines and
shadow regions, which a plate file consumes.

Coordinate convention matches the rest of the package: mm, y increases
downward (SVG). ``base_y`` is the y-coordinate of the ground line; stories
stack upward from there with ever-decreasing y.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from . import arches as arches_mod
from . import balustrades as bal
from . import canon
from . import pilasters as pil_mod
from . import rustication
from . import windows as win_mod
from .elements import Shadow
from .geometry import Polyline


# Stroke-weight hints used to categorize polylines for plate rendering.
# Plates read ``result["layers"]`` and look up each sublist's weight to
# stroke them at differentiated line thicknesses.
STROKE_HAIRLINE = 0.18
STROKE_FINE = 0.25
STROKE_MEDIUM = 0.35
STROKE_HEAVY = 0.50


OpeningKind = Literal["window", "door", "arch_window", "arch_door",
                      "niche", "blank"]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Opening:
    """A window, door, or arched opening in a bay."""
    kind: OpeningKind
    width: float          # mm
    height: float         # mm
    hood: str = "none"    # passed to windows.window_opening
    has_keystone: bool = False
    # For arches
    rise: float | None = None


@dataclass
class Bay:
    """A vertical column of openings aligned on one x-axis.

    ``openings`` is bottom-up, one entry per story. Use ``Opening(kind="blank",
    …)`` for a story that should show no opening on this bay.
    ``pilaster_order``, if set, produces flanking pilasters of that order on
    stories whose ``has_order`` matches. ``pilaster_width`` controls the face
    width of those pilasters (0 → derive from the order's D).
    """
    openings: list[Opening]
    pilaster_order: str | None = None  # "doric", "ionic", etc.
    pilaster_width: float = 0.0
    axis_x: float = 0.0  # populated by Facade.layout()


@dataclass
class Story:
    """One horizontal story of the facade.

    ``height`` is the vertical extent of this story (in mm). Sum of story
    heights is the facade height.
    ``wall`` is either a string naming a rustication variant, or a dict
    specifying the variant (key ``"variant"``) plus extra kwargs passed to
    ``rustication.wall`` (e.g. ``course_h``, ``block_w``, ``bond``).
    ``has_order`` is the order name to use for flanking pilasters on this
    story ("tuscan", "doric", "ionic", "corinthian", "composite"), or None.
    ``string_course_height`` is the thickness of the projecting molding at
    the bottom of this story (0 suppresses the course).
    """
    height: float
    wall: str | dict = "smooth"
    has_order: str | None = None
    string_course_height: float = 2.0


@dataclass
class Facade:
    """Full facade composition."""
    width: float
    stories: list[Story]              # bottom-to-top
    bays: list[Bay]                   # left-to-right
    base_y: float                     # y of the ground line
    margin_frac: float = 0.10         # horizontal margin as a fraction of width
    parapet: dict | None = None       # e.g. {"type": "balustrade", "height": 18}

    # ---- Layout ------------------------------------------------------------
    def layout(self) -> None:
        """Compute ``bay.axis_x`` evenly across the facade minus margins."""
        n = len(self.bays)
        if n == 0:
            return
        margin = self.width * self.margin_frac
        usable = self.width - 2.0 * margin
        step = usable / n
        for i, bay in enumerate(self.bays):
            bay.axis_x = margin + (i + 0.5) * step

    # ---- Render ------------------------------------------------------------
    def render(self) -> dict:
        """Compose every layer of the facade and return a layered dict.

        The returned ``layers`` dict maps a category name to a dict of the
        form ``{"polylines": [...], "weight": <float>}`` (plus optional
        per-entry detail lists under ``"entries"``). Plates should iterate
        ``layers.values()`` and stroke each layer at its recommended weight.
        The flat ``polylines`` list is preserved for backward compatibility.
        """
        self.layout()

        # Layered output: each layer is a bucket of polylines with a weight.
        layers: dict[str, dict[str, Any]] = {
            "wall_outlines":   {"polylines": [], "weight": STROKE_MEDIUM,
                                "entries": []},
            "wall_blocks":     {"polylines": [], "weight": STROKE_HAIRLINE},
            "wall_joints":     {"polylines": [], "weight": STROKE_HAIRLINE},
            "wall_voussoirs":  {"polylines": [], "weight": STROKE_FINE},
            "string_courses":  {"polylines": [], "weight": STROKE_MEDIUM,
                                "entries": []},
            "pilasters":       {"polylines": [], "weight": STROKE_MEDIUM,
                                "entries": []},
            "windows":         {"polylines": [], "weight": STROKE_MEDIUM,
                                "entries": []},
            "arches":          {"polylines": [], "weight": STROKE_MEDIUM,
                                "entries": []},
            "parapet":         {"polylines": [], "weight": STROKE_MEDIUM,
                                "entries": []},
        }
        all_polylines: list[Polyline] = []
        all_shadows: list[Shadow] = []

        # Pre-compute y bounds for each story (bottom-up).
        # The facade grows upward (smaller y) from base_y.
        story_bounds: list[tuple[float, float]] = []  # (y_bot, y_top) per story
        y_cursor = self.base_y
        for story in self.stories:
            y_bot = y_cursor
            y_top = y_cursor - story.height
            story_bounds.append((y_bot, y_top))
            y_cursor = y_top

        facade_top_y = y_cursor  # after stacking all stories

        # ---- Openings first: we need their footprints to clip the walls --
        # Render each opening, record its polylines, AND compute a shapely
        # polygon footprint per story (union of all opening bounding shapes
        # plus a small architrave halo). Walls are then rendered with those
        # footprints subtracted from their block grid and joint lines.
        per_story_openings: list[list[Polygon]] = [[] for _ in self.stories]
        opening_renders: list[tuple[int, str, dict]] = []  # (story_i, kind, dict)

        for i, story in enumerate(self.stories):
            y_bot, y_top = story_bounds[i]
            story_h = y_bot - y_top
            for bay in self.bays:
                if i >= len(bay.openings):
                    continue
                opening = bay.openings[i]
                if opening.kind == "blank":
                    continue
                rendered = _render_opening(opening, bay.axis_x, y_bot, y_top,
                                           story_h)
                if rendered is None:
                    continue
                kind, result = rendered
                opening_renders.append((i, kind, result))
                footprint = _opening_footprint(opening, bay.axis_x, y_bot,
                                               story_h)
                if footprint is not None and not footprint.is_empty:
                    per_story_openings[i].append(footprint)

        story_unions: list[Any] = []
        for polys in per_story_openings:
            if not polys:
                story_unions.append(None)
            else:
                story_unions.append(unary_union(polys))

        # ---- Walls (per story), with opening clipping ---------------------
        for i, story in enumerate(self.stories):
            wall_dict = _render_wall(self, story, story_bounds[i], i,
                                     openings_union=story_unions[i])
            layers["wall_outlines"]["entries"].append(wall_dict)
            # Wall outline: always drawn.
            if "outline" in wall_dict:
                layers["wall_outlines"]["polylines"].append(wall_dict["outline"])
                all_polylines.append(wall_dict["outline"])
            layers["wall_blocks"]["polylines"].extend(
                wall_dict.get("block_rects", []))
            layers["wall_joints"]["polylines"].extend(
                wall_dict.get("joints", []))
            layers["wall_voussoirs"]["polylines"].extend(
                wall_dict.get("arch_voussoirs", []))
            layers["wall_blocks"]["polylines"].extend(
                wall_dict.get("face_carving", []))
            all_polylines.extend(wall_dict.get("joints", []))
            all_polylines.extend(wall_dict.get("block_rects", []))
            all_polylines.extend(wall_dict.get("face_carving", []))
            all_polylines.extend(wall_dict.get("arch_voussoirs", []))
            all_shadows.extend(wall_dict.get("joint_shadows", []))

        # ---- String courses (at the bottom of each story except the ground)
        for i, story in enumerate(self.stories):
            if i == 0:
                continue  # no course at ground line
            if story.string_course_height <= 0:
                continue
            y_bot, _ = story_bounds[i]
            course = _string_course(0.0, self.width, y_bot,
                                    story.string_course_height)
            layers["string_courses"]["entries"].append(course)
            layers["string_courses"]["polylines"].extend(course["polylines"])
            all_polylines.extend(course["polylines"])
            all_shadows.extend(course["shadows"])

        # ---- Openings: emit the previously-rendered polylines -------------
        for (i, kind, result) in opening_renders:
            if kind == "window":
                layers["windows"]["entries"].append(result)
                _collect_window_polylines(result, layers["windows"]["polylines"])
                _collect_window_polylines(result, all_polylines)
                all_shadows.extend(result.get("shadows", []))
            else:  # "arch"
                layers["arches"]["entries"].append(result)
                _collect_arch_polylines(result, layers["arches"]["polylines"])
                _collect_arch_polylines(result, all_polylines)
                all_shadows.extend(result.get("shadows", []))

        # ---- Pilasters (per story that declares an order) -----------------
        for i, story in enumerate(self.stories):
            if story.has_order is None:
                continue
            y_bot, y_top = story_bounds[i]
            story_h = y_bot - y_top
            for bay in self.bays:
                pil_result = _render_pilasters_for_bay(
                    bay, story, i, y_bot, story_h)
                if pil_result is None:
                    continue
                layers["pilasters"]["entries"].append(pil_result)
                layers["pilasters"]["polylines"].extend(pil_result["polylines"])
                all_polylines.extend(pil_result["polylines"])

        # ---- Parapet ------------------------------------------------------
        if self.parapet is not None:
            parapet_result = _render_parapet(self, facade_top_y)
            if parapet_result is not None:
                layers["parapet"]["entries"].append(parapet_result)
                layers["parapet"]["polylines"].extend(parapet_result["polylines"])
                all_polylines.extend(parapet_result["polylines"])
                all_shadows.extend(parapet_result.get("shadows", []))

        # ---- BBox ---------------------------------------------------------
        bbox = _bbox_of_polylines(all_polylines,
                                  fallback=(0.0, facade_top_y,
                                            self.width, self.base_y))

        return {
            "polylines": all_polylines,
            "shadows": all_shadows,
            "layers": layers,
            "bbox": bbox,
        }

    # ---- Scene export ------------------------------------------------------
    def to_scene(self, render_result: dict):
        """Convert a rendered Facade into a Scene populated with hierarchical nodes.

        Hierarchy:
            facade
            ├── story_0
            │   ├── bay_0
            │   │   └── opening      (window / arch / door)
            │   ├── bay_1 ...
            │   └── pier_0, pier_1   (only on arcuated stories)
            ├── story_1 ...
            └── parapet              (if present)

        Each node carries world position, bbox, and key anchors. The Scene's
        constraint list is populated with the architectural rules that should
        hold for any well-formed facade:
          - BilateralFacade
          - CorrespondingBays for each adjacent pair of stories
          - StandsOn for each story-on-story junction
          - EvenPitch for bays within a story
        """
        from .scene import Scene, SceneNode
        from .scene_constraints import (
            BilateralFacade, CorrespondingBays, StandsOn, EvenPitch,
        )
        from .schema import Anchor

        scene = Scene()

        # Root facade node
        bbox = render_result.get("bbox", (0.0, 0.0, self.width, 100.0))
        fcx = (bbox[0] + bbox[2]) / 2.0
        facade_node = SceneNode(
            id="facade", kind="facade",
            pos=(fcx, self.base_y, 0.0),
            bbox_local=(bbox[0] - fcx, bbox[1] - self.base_y,
                        bbox[2] - fcx, bbox[3] - self.base_y),
            anchors={"axis": Anchor("axis", 0.0, 0.0, "axis")},
        )
        scene.add(facade_node)

        # Stories (bottom-up build order; story y shrinks as we go up).
        story_y = self.base_y
        story_ids: list[str] = []
        for s_idx, story in enumerate(self.stories):
            story_y_top = story_y - story.height
            sid = f"facade.story_{s_idx}"
            story_ids.append(sid)
            story_node = SceneNode(
                id=sid, kind="story",
                pos=(fcx, story_y, 0.0),
                bbox_local=(bbox[0] - fcx, story_y_top - story_y,
                            bbox[2] - fcx, 0.0),
                anchors={
                    "bottom_center": Anchor("bottom_center", 0.0, 0.0,
                                            "attach"),
                    "top_center":    Anchor("top_center", 0.0,
                                            story_y_top - story_y, "attach"),
                },
                metadata={"story_index": s_idx, "wall": str(story.wall),
                          "has_order": story.has_order},
            )
            scene.add(story_node, parent_id="facade")

            # Bays
            for b_idx, bay in enumerate(self.bays):
                bid = f"facade.story_{s_idx}.bay_{b_idx}"
                opening = bay.openings[s_idx] if s_idx < len(bay.openings) else None
                opening_height = opening.height if opening else 30.0
                opening_width = opening.width if opening else 20.0
                opening_y_top = (story_y + story_y_top) / 2.0 + opening_height / 2.0
                bay_node = SceneNode(
                    id=bid, kind="bay",
                    pos=(bay.axis_x, story_y, 0.0),
                    bbox_local=(-opening_width / 2.0, story_y_top - story_y,
                                 opening_width / 2.0, 0.0),
                    anchors={"axis": Anchor("axis", 0.0,
                                            (story_y_top - story_y) / 2.0,
                                            "axis")},
                    metadata={"bay_index": b_idx,
                              "opening_kind": opening.kind if opening else None},
                )
                scene.add(bay_node, parent_id=sid)

                # Opening as a child of bay
                if opening is not None and opening.kind != "blank":
                    oid = f"{bid}.opening"
                    op_node = SceneNode(
                        id=oid, kind=opening.kind,
                        pos=(bay.axis_x, opening_y_top, 0.0),
                        bbox_local=(-opening.width / 2.0, 0.0,
                                     opening.width / 2.0, opening.height),
                        anchors={
                            "axis": Anchor("axis", 0.0, opening.height / 2.0,
                                           "axis"),
                            "top_center": Anchor("top_center", 0.0, 0.0,
                                                 "attach"),
                            "bottom_center": Anchor("bottom_center", 0.0,
                                                    opening.height, "attach"),
                        },
                        metadata={"hood": opening.hood,
                                  "has_keystone": opening.has_keystone},
                    )
                    scene.add(op_node, parent_id=bid)

            story_y = story_y_top  # next story sits above

        # ── Constraints ──
        # Bilateral facade symmetry
        scene.constrain(BilateralFacade(facade_id="facade", tol=1.0,
                                        label="facade-symmetry"))

        # Corresponding bays across adjacent stories
        for i in range(len(story_ids) - 1):
            scene.constrain(CorrespondingBays(
                story_a_id=story_ids[i], story_b_id=story_ids[i + 1], tol=1.0,
                label=f"bays-{i}-to-{i+1}"))

        # Even pitch of bays within a story (only when 3+ bays)
        for sid in story_ids:
            bay_ids = [n.id for n in scene.get(sid).children if n.kind == "bay"]
            if len(bay_ids) >= 3:
                scene.constrain(EvenPitch(node_ids=bay_ids, axis="x", tol=1.0,
                                          label=f"{sid}-bay-pitch"))

        # Story-on-story stacking (upper.bottom_center == lower.top_center)
        for i in range(len(story_ids) - 1):
            scene.constrain(StandsOn(
                upper_id=story_ids[i + 1],
                lower_id=story_ids[i],
                upper_anchor="bottom_center",
                lower_anchor="top_center",
                tol=1.0,
                label=f"story-{i+1}-on-{i}",
            ))

        return scene


# ---------------------------------------------------------------------------
# Wall rendering
# ---------------------------------------------------------------------------

def _normalize_wall_spec(spec: str | dict) -> tuple[str, dict]:
    """Return (variant, kwargs) from a Story.wall spec."""
    if isinstance(spec, str):
        return spec, {}
    kwargs = dict(spec)
    variant = kwargs.pop("variant", "smooth")
    return variant, kwargs


def _collect_arch_openings(facade: Facade, story_index: int,
                           y_bot: float) -> tuple[list[float], list[tuple[float, float]]]:
    """For arcuated walls: collect (springing_y, (cx, span)) per arch opening.

    The springing y MUST match the value used by ``_opening_footprint`` and
    ``_render_opening`` for the same opening kind, otherwise the voussoirs
    rendered by rustication will drift relative to the actual arch drawn
    by ``arches_mod`` — producing radial "fan" wedges that extend below the
    visible intrados of the arch opening.
    """
    springings: list[float] = []
    spans: list[tuple[float, float]] = []
    story = facade.stories[story_index]
    story_h = story.height
    for bay in facade.bays:
        if story_index >= len(bay.openings):
            continue
        op = bay.openings[story_index]
        if op.kind not in ("arch_window", "arch_door"):
            continue
        # Use the SAME sill margin and springing formula as
        # _opening_footprint / _render_opening so rustication's voussoirs
        # sit exactly on the visible arch's springing line.
        sill_margin = story_h * 0.04 if op.kind == "arch_door" else story_h * 0.10
        y_opening_bot = y_bot - sill_margin
        y_spring = y_opening_bot - op.height
        springings.append(y_spring)
        spans.append((bay.axis_x, op.width))
    return springings, spans


def _render_wall(facade: Facade, story: Story,
                 bounds: tuple[float, float], story_index: int,
                 openings_union: Any = None) -> dict:
    """Render one story's wall using rustication.wall.

    If ``openings_union`` is given (a shapely Polygon/MultiPolygon of all
    opening footprints for this story), the wall's block_rects and joints
    are clipped to exclude the opening interiors so the wall reads as
    perforated by the openings rather than drawn underneath them.

    Wall treatments are restricted by story: only the ground floor (or a
    story whose variant explicitly calls for rustication) gets full ashlar
    blocks. Smooth stories emit just the outer rectangle — no blocks, no
    vertical joints. Banded upper stories emit horizontal string-coursing
    only (via rustication's ``emit_blocks=False``).
    """
    y_bot, y_top = bounds
    height = y_bot - y_top
    variant, kwargs = _normalize_wall_spec(story.wall)

    # ------------------------------------------------------------------
    # Smooth stories: bypass rustication entirely. Emit only the outer
    # rectangle outline so plates still have a wall boundary to stroke.
    # ------------------------------------------------------------------
    if variant == "smooth":
        outline: Polyline = [
            (0.0, y_top),
            (facade.width, y_top),
            (facade.width, y_bot),
            (0.0, y_bot),
            (0.0, y_top),
        ]
        return {
            "outline": outline,
            "joints": [],
            "joint_shadows": [],
            "block_rects": [],
            "face_carving": [],
            "face_stipples": [],
            "arch_voussoirs": [],
        }

    kwargs.setdefault("course_h", max(6.0, height / 6.0))
    kwargs.setdefault("block_w", max(12.0, height / 3.0))
    kwargs.setdefault("bond", "running")

    # Banded upper stories: only horizontal string-coursing, no block grid.
    # Callers opt in by setting ``emit_blocks=False`` in the wall dict.
    if variant == "banded" and kwargs.get("emit_blocks", True) is False:
        pass  # kwargs already carry emit_blocks=False to rustication.wall

    if variant == "arcuated":
        springings, spans = _collect_arch_openings(
            facade, story_index, y_bot)
        if springings:
            kwargs.setdefault("arch_springings_y", springings)
            kwargs.setdefault("arch_spans", spans)
        else:
            # No arches here — degrade to banded so the wall still renders.
            variant = "banded"

    wall_dict = rustication.wall(
        x0=0.0, y0=y_top, width=facade.width, height=height,
        variant=variant, **kwargs)

    # Clip blocks and joints against the union of opening footprints so
    # the wall reads as perforated by the openings rather than drawn
    # underneath them.
    if openings_union is not None and not openings_union.is_empty:
        wall_dict = dict(wall_dict)
        wall_dict["block_rects"] = _clip_blocks(
            wall_dict.get("block_rects", []), openings_union)
        wall_dict["joints"] = _clip_joints(
            wall_dict.get("joints", []), openings_union)

    return wall_dict


# ---------------------------------------------------------------------------
# Opening footprints + wall clipping
# ---------------------------------------------------------------------------

def _opening_footprint(op: Opening, axis_x: float, y_bot: float,
                       story_h: float) -> Polygon | None:
    """Shapely polygon covering the area the wall should NOT draw through.

    This is the opening's bounding shape plus a small architrave halo so the
    wall also doesn't bleed through the frame. Returned in facade
    coordinates (y increases downward).
    """
    # Halo padding so block outlines don't kiss the architrave edge.
    # Tie padding to opening width so it scales with plate size.
    pad = max(0.8, op.width * 0.06)

    if op.kind == "blank":
        return None

    if op.kind in ("window", "door", "niche"):
        sill_margin = story_h * 0.08
        y_opening_bot = y_bot - sill_margin
        y_opening_top = y_opening_bot - op.height
        x0 = axis_x - op.width / 2.0 - pad
        x1 = axis_x + op.width / 2.0 + pad
        # Extend a bit above to catch hood/pediment overlap.
        hood_ext = op.width * 0.45 if op.hood != "none" else op.width * 0.10
        y_top_pad = y_opening_top - hood_ext
        return box(x0, y_top_pad, x1, y_opening_bot + pad * 0.5)

    if op.kind in ("arch_window", "arch_door"):
        sill_margin = story_h * 0.04 if op.kind == "arch_door" else story_h * 0.10
        y_opening_bot = y_bot - sill_margin
        y_spring = y_opening_bot - op.height
        half_span = op.width / 2.0
        # Semicircular apex rises by half_span above the springing.
        y_apex = y_spring - half_span
        x0 = axis_x - half_span - pad
        x1 = axis_x + half_span + pad
        # Include the voussoir ring thickness (a course_h-scaled band) in
        # the halo above the apex.
        y_top_pad = y_apex - pad * 2.0
        return box(x0, y_top_pad, x1, y_opening_bot + pad * 0.5)

    return None


def _clip_blocks(block_rects: list[Polyline],
                 openings_union: Any) -> list[Polyline]:
    """Subtract opening footprints from each block-rect polyline.

    Blocks mostly inside the opening are dropped. Blocks that straddle the
    opening edge are clipped to the exterior remainder.
    """
    clipped: list[Polyline] = []
    for rect_polyline in block_rects:
        if len(rect_polyline) < 4:
            continue
        try:
            rect_poly = Polygon(rect_polyline)
        except Exception:
            continue
        if not rect_poly.is_valid or rect_poly.area <= 0:
            continue
        if not rect_poly.intersects(openings_union):
            clipped.append(rect_polyline)
            continue
        remainder = rect_poly.difference(openings_union)
        if remainder.is_empty:
            continue
        # Drop tiny slivers left over when a block is mostly inside an opening.
        if remainder.area < 0.05 * rect_poly.area:
            continue
        geoms = [remainder] if isinstance(remainder, Polygon) else list(
            getattr(remainder, "geoms", []))
        for geom in geoms:
            if geom.is_empty or geom.area <= 0:
                continue
            clipped.append(list(geom.exterior.coords))
    return clipped


def _clip_joints(joint_polylines: list[Polyline],
                 openings_union: Any) -> list[Polyline]:
    """Clip joint line-segments to the exterior of the opening footprints."""
    clipped: list[Polyline] = []
    for line_polyline in joint_polylines:
        if len(line_polyline) < 2:
            continue
        try:
            line = LineString(line_polyline)
        except Exception:
            continue
        if not line.intersects(openings_union):
            clipped.append(line_polyline)
            continue
        remainder = line.difference(openings_union)
        if remainder.is_empty:
            continue
        gt = remainder.geom_type
        if gt == "LineString":
            coords = list(remainder.coords)
            if len(coords) >= 2:
                clipped.append(coords)
        elif gt == "MultiLineString":
            for g in remainder.geoms:
                coords = list(g.coords)
                if len(coords) >= 2:
                    clipped.append(coords)
    return clipped


def _collect_wall_polylines(wall_dict: dict, out: list[Polyline]) -> None:
    if "outline" in wall_dict:
        out.append(wall_dict["outline"])
    out.extend(wall_dict.get("joints", []))
    out.extend(wall_dict.get("block_rects", []))
    out.extend(wall_dict.get("face_carving", []))
    out.extend(wall_dict.get("arch_voussoirs", []))


# ---------------------------------------------------------------------------
# String course (thin molded band at story boundaries)
# ---------------------------------------------------------------------------

def _string_course(x0: float, width: float, y_top: float, h: float) -> dict:
    """A thin molded horizontal band at y_top, thickness h."""
    from shapely.geometry import Polygon
    x1 = x0 + width
    y_bot = y_top + h
    outline: Polyline = [
        (x0, y_top),
        (x1, y_top),
        (x1, y_bot),
        (x0, y_bot),
        (x0, y_top),
    ]
    # A faint interior rule for the cyma/fillet edge.
    rule = [(x0, y_top + h * 0.55), (x1, y_top + h * 0.55)]
    # Soffit shadow under the course.
    shadow = Shadow(
        Polygon([(x0, y_bot),
                 (x1, y_bot),
                 (x1, y_bot + h * 0.25),
                 (x0, y_bot + h * 0.25)]),
        angle_deg=10.0, density="medium")
    return {
        "polylines": [outline, rule],
        "shadows": [shadow],
    }


# ---------------------------------------------------------------------------
# Opening rendering (windows + arches)
# ---------------------------------------------------------------------------

def _render_opening(op: Opening, axis_x: float,
                    y_bot: float, y_top: float,
                    story_h: float) -> tuple[str, dict] | None:
    """Return (kind, rendered_dict). kind in {"window", "arch"}."""
    if op.kind == "blank" or op.kind == "niche":
        # niche: treat as a plain window without hood for v1
        if op.kind == "blank":
            return None
    if op.kind in ("window", "door", "niche"):
        # Position opening vertically: centered in upper ~70% of story,
        # with the sill sitting a bit above y_bot.
        sill_margin = story_h * 0.08
        y_opening_bot = y_bot - sill_margin
        y_opening_top = y_opening_bot - op.height
        # x: axis_x is the centerline.
        x0 = axis_x - op.width / 2.0
        hood = op.hood if op.kind != "niche" else "none"
        result = win_mod.window_opening(
            x=x0, y_top=y_opening_top,
            w=op.width, h=op.height,
            hood=hood, keystone=op.has_keystone)
        return ("window", result)

    if op.kind in ("arch_window", "arch_door"):
        # Arched opening: axis_x is the arch's horizontal center. Springing
        # line sits at the top of the rectangular part. Use the same vertical
        # layout as windows so the arch feels integrated.
        sill_margin = story_h * 0.04 if op.kind == "arch_door" else story_h * 0.10
        y_opening_bot = y_bot - sill_margin
        y_spring = y_opening_bot - op.height
        # Semicircular by default; segmental only if op.rise set below half-span.
        half_span = op.width / 2.0
        if op.rise is None or op.rise >= half_span - 0.01:
            arch_result = arches_mod.semicircular_arch(
                cx=axis_x, y_spring=y_spring, span=op.width,
                voussoir_count=9,
                with_keystone=op.has_keystone or True,
                archivolt_bands=1)
        else:
            arch_result = arches_mod.segmental_arch(
                cx=axis_x, y_spring=y_spring, span=op.width, rise=op.rise,
                voussoir_count=9,
                with_keystone=op.has_keystone or True,
                archivolt_bands=1)
        # Augment with the jamb rectangle (the vertical sides from sill to
        # springing line) so the opening reads as a full doorway/window.
        jamb_left = [(axis_x - half_span, y_spring),
                     (axis_x - half_span, y_opening_bot)]
        jamb_right = [(axis_x + half_span, y_spring),
                      (axis_x + half_span, y_opening_bot)]
        sill = [(axis_x - half_span, y_opening_bot),
                (axis_x + half_span, y_opening_bot)]
        arch_result = dict(arch_result)  # copy
        jambs = arch_result.setdefault("jambs", [])
        jambs.extend([jamb_left, jamb_right, sill])
        return ("arch", arch_result)

    return None


def _collect_window_polylines(win: dict, out: list[Polyline]) -> None:
    if win.get("opening"):
        out.append(win["opening"])
    out.extend(win.get("architrave", []))
    out.extend(win.get("sill", []))
    out.extend(win.get("hood", []))
    out.extend(win.get("brackets", []))
    if win.get("keystone"):
        out.append(win["keystone"])


def _collect_arch_polylines(arch: dict, out: list[Polyline]) -> None:
    out.extend(arch.get("intrados", []))
    out.extend(arch.get("extrados", []))
    out.extend(arch.get("voussoirs", []))
    out.extend(arch.get("archivolts", []))
    out.extend(arch.get("imposts", []))
    if arch.get("keystone"):
        out.append(arch["keystone"])
    out.extend(arch.get("jambs", []))


# ---------------------------------------------------------------------------
# Pilaster rendering
# ---------------------------------------------------------------------------

def _render_pilasters_for_bay(bay: Bay, story: Story, story_index: int,
                              base_y: float, story_h: float) -> dict | None:
    """Flanking pilasters for one bay in one ordered story.

    Pilasters sit OUTBOARD of the bay's opening, so the architrave is
    visually framed by them rather than overlapping. The flank offset is
    derived from the opening width when available, with a small gap.
    """
    order_name = story.has_order
    if order_name is None:
        return None
    # Size the order so the column height fits the story height (with small
    # allowance for entablature margin). column_h = column_D * D => D set
    # so that column_D * D ~ story_h * 0.92.
    proto = canon.make(order_name, D=1.0)
    target_col_h = story_h * 0.90
    D = target_col_h / proto.column_D
    order = canon.make(order_name, D=D)

    pw = bay.pilaster_width if bay.pilaster_width > 0 else order.D
    # Derive flank offset from the opening width of THIS story's opening so
    # the pilaster inner edges sit just outside the window architrave.
    half_span = 0.0
    architrave_halo = 0.0
    if story_index < len(bay.openings):
        op = bay.openings[story_index]
        if op.kind != "blank":
            half_span = op.width / 2.0
            # Windows grow an architrave of ~w/6 on each side.
            if op.kind in ("window", "door", "niche"):
                architrave_halo = op.width / 6.0
    gap = pw * 0.25
    # Inner edge of pilaster should sit at half_span + architrave_halo + gap.
    # Pilaster center is inner_edge + pw/2.
    inner_edge = half_span + architrave_halo + gap
    offset = max(pw * 2.0, inner_edge + pw / 2.0)
    cx_left = bay.axis_x - offset
    cx_right = bay.axis_x + offset

    polys: list[Polyline] = []
    polys.extend(pil_mod.pilaster(order, cx=cx_left, base_y=base_y,
                                  width=pw, projection=0.15))
    polys.extend(pil_mod.pilaster(order, cx=cx_right, base_y=base_y,
                                  width=pw, projection=0.15))
    return {
        "order": order_name,
        "axis_x": bay.axis_x,
        "polylines": polys,
    }


# ---------------------------------------------------------------------------
# Parapet
# ---------------------------------------------------------------------------

def _render_parapet(facade: Facade, facade_top_y: float) -> dict | None:
    spec = facade.parapet or {}
    kind = spec.get("type", "balustrade")
    height = spec.get("height", 18.0)

    if kind == "balustrade":
        # Pedestal posts at each bay axis (also at the corners).
        ped_positions = spec.get("pedestals_at")
        if ped_positions is None:
            margin = facade.width * facade.margin_frac
            ped_positions = [margin]
            ped_positions.extend(bay.axis_x for bay in facade.bays)
            ped_positions.append(facade.width - margin)
        # y_top_of_rail is the topmost y of the balustrade's top rail.
        # The balustrade's bottom-of-bottom-rail should land on facade_top_y.
        y_top_of_rail = facade_top_y - height
        run = bal.balustrade_run(
            x0=facade.width * facade.margin_frac,
            x1=facade.width * (1.0 - facade.margin_frac),
            y_top_of_rail=y_top_of_rail,
            height=height,
            baluster_variant=spec.get("variant", "tuscan"),
            include_pedestals_at=ped_positions,
        )
        polys: list[Polyline] = []
        polys.extend(run.get("top_rail", []))
        polys.extend(run.get("bottom_rail", []))
        polys.extend(run.get("pedestals", []))
        for bpolys in run.get("balusters", []):
            polys.extend(bpolys)
        shadows = list(run.get("shadows", []))
        # bal.Shadow is a local dataclass — wrap to elements.Shadow if needed.
        shadows = [_coerce_shadow(s) for s in shadows]
        return {
            "type": "balustrade",
            "polylines": polys,
            "shadows": shadows,
        }

    if kind == "attic":
        # Simple attic story: a plain rectangular parapet with a top rule.
        from shapely.geometry import Polygon
        y_top = facade_top_y - height
        x0 = 0.0
        x1 = facade.width
        polys = [
            [(x0, facade_top_y), (x1, facade_top_y),
             (x1, y_top), (x0, y_top), (x0, facade_top_y)],
            [(x0, y_top + height * 0.2),
             (x1, y_top + height * 0.2)],
        ]
        shadow = Shadow(
            Polygon([(x0, facade_top_y),
                     (x1, facade_top_y),
                     (x1, facade_top_y + height * 0.08),
                     (x0, facade_top_y + height * 0.08)]),
            angle_deg=10.0, density="medium")
        return {
            "type": "attic",
            "polylines": polys,
            "shadows": [shadow],
        }

    return None


def _coerce_shadow(s: Any) -> Shadow:
    """Wrap balustrades.Shadow (local dataclass) as elements.Shadow."""
    if isinstance(s, Shadow):
        return s
    # Duck-type — both dataclasses have .polygon / .angle_deg / .density
    return Shadow(getattr(s, "polygon"),
                  angle_deg=getattr(s, "angle_deg", 45.0),
                  density=getattr(s, "density", "medium"))


# ---------------------------------------------------------------------------
# BBox helper
# ---------------------------------------------------------------------------

def _bbox_of_polylines(polys: list[Polyline],
                       fallback: tuple[float, float, float, float]
                       ) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for pl in polys:
        for (px, py) in pl:
            xs.append(px)
            ys.append(py)
    if not xs or not ys:
        return fallback
    return (min(xs), min(ys), max(xs), max(ys))


# ---------------------------------------------------------------------------
# Smoke test — Dury-Carondelet-inspired 3-story, 5-bay facade
# ---------------------------------------------------------------------------

def _smoke() -> None:
    """Build a 3-story, 5-bay palazzo facade and print summary metrics."""
    # Story heights: piano nobile tallest, ground a little shorter, attic
    # the shortest. Units mm.
    ground_h = 90.0
    piano_h = 120.0
    upper_h = 75.0

    # Five bays: middle bay is the main door on the ground floor.
    ground_arch_win = Opening(kind="arch_window", width=44.0, height=40.0,
                              has_keystone=True)
    ground_arch_door = Opening(kind="arch_door", width=52.0, height=56.0,
                               has_keystone=True)

    piano_win = Opening(kind="window", width=40.0, height=70.0,
                        hood="triangular", has_keystone=True)
    piano_win_seg = Opening(kind="window", width=40.0, height=70.0,
                            hood="segmental", has_keystone=True)

    upper_win = Opening(kind="window", width=34.0, height=44.0,
                        hood="cornice", has_keystone=False)

    # Alternate triangular/segmental pediments on the piano nobile.
    piano_for_bay = [piano_win, piano_win_seg, piano_win,
                     piano_win_seg, piano_win]

    bays: list[Bay] = []
    for i in range(5):
        if i == 2:
            ground_op = ground_arch_door
        else:
            ground_op = ground_arch_win
        bay = Bay(
            openings=[ground_op, piano_for_bay[i], upper_win],
            pilaster_order="ionic",
            pilaster_width=6.0,
        )
        bays.append(bay)

    facade = Facade(
        width=480.0,
        base_y=400.0,
        stories=[
            Story(height=ground_h,
                  wall={"variant": "arcuated",
                        "course_h": 12.0, "block_w": 28.0},
                  string_course_height=0.0),
            Story(height=piano_h,
                  wall={"variant": "smooth",
                        "course_h": 20.0, "block_w": 40.0},
                  has_order="ionic",
                  string_course_height=3.0),
            Story(height=upper_h,
                  wall={"variant": "banded",
                        "course_h": 15.0, "block_w": 40.0},
                  string_course_height=2.5),
        ],
        bays=bays,
        parapet={"type": "balustrade", "height": 22.0,
                 "variant": "tuscan"},
    )

    out = facade.render()

    # --- Metrics --------------------------------------------------------
    bbox = out["bbox"]
    layers = out["layers"]
    n_poly = len(out["polylines"])
    n_shadow = len(out["shadows"])
    layer_counts = {k: len(v.get("polylines", [])) for k, v in layers.items()}

    print(f"bbox = ({bbox[0]:.2f}, {bbox[1]:.2f}, "
          f"{bbox[2]:.2f}, {bbox[3]:.2f})")
    print(f"total polylines: {n_poly}")
    print(f"total shadows:   {n_shadow}")
    print("layer counts:")
    for k, v in layer_counts.items():
        print(f"  {k}: {v}")

    # --- Assertions ------------------------------------------------------
    # bbox x-extent should span roughly the facade width.
    assert bbox[0] <= 20.0 and bbox[2] >= 460.0, \
        f"bbox x-range should span the facade; got {bbox}"
    # The top of the drawn content should rise above the facade_top (base_y -
    # sum of story heights). Accept a generous tolerance for parapet height.
    facade_top_y = facade.base_y - (ground_h + piano_h + upper_h)
    assert bbox[1] < facade_top_y + 5.0, \
        f"drawn content should extend to or above facade top {facade_top_y}"
    # Every layer should have at least one entry.
    for key, count in layer_counts.items():
        assert count > 0, f"layer {key!r} is empty"
    # A rich facade should have hundreds of polylines.
    assert n_poly > 200, f"expected > 200 polylines, got {n_poly}"
    print("smoke test OK")


if __name__ == "__main__":
    _smoke()
