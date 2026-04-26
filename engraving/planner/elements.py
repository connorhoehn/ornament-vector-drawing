"""Lightweight Element subclasses specific to the planner's structural
hierarchy (facade, story, bay, pilaster, string course, parapet).

Column/arch/entablature Elements live in ``engraving.elements``; this
module just provides the structural containers the planner populates.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator

from ..element import Element, Material, StrokedPolyline
from ..schema import BBox, Polyline


# ── Phase 28 — CSG-native shadows ──────────────────────────────────────


@dataclass
class ShadowElement(Element):
    """A shadow region rendered as parallel-hatch line fills.

    Classical engraving convention: light from upper-left, hatch at 45
    degrees from horizontal (override per-element when needed). Density
    controls hatch spacing; all strokes render at a uniform hairline
    weight so the hatch reads as tone rather than line.
    """
    polygon: object = None          # shapely Polygon/MultiPolygon; world coords
    angle_deg: float = 45.0         # hatch direction, CCW from horizontal
    density: str = "medium"         # "light" | "medium" | "dark"
    material: Material = field(default=Material.ORNAMENT)

    _SPACING_BY_DENSITY = {"light": 0.55, "medium": 0.40, "dark": 0.28}

    def render_strokes(self) -> Iterator[StrokedPolyline]:
        if self.polygon is None:
            return
        try:
            is_empty = self.polygon.is_empty
        except Exception:
            return
        if is_empty:
            return
        from ..hatching import parallel_hatch
        spacing = self._SPACING_BY_DENSITY.get(self.density, 0.40)
        for line_polyline in parallel_hatch(
                self.polygon, angle_deg=self.angle_deg, spacing=spacing):
            if len(line_polyline) >= 2:
                yield line_polyline, 0.12   # hatch is always hairline

    def effective_bbox(self) -> BBox:
        if self.polygon is None:
            return self.envelope
        try:
            if self.polygon.is_empty:
                return self.envelope
            return tuple(self.polygon.bounds)
        except Exception:
            return self.envelope


@dataclass
class FacadeElement(Element):
    """Root of a facade. Renders nothing itself — children do all the work."""
    pass


@dataclass
class StoryElement(Element):
    """One horizontal story. Its envelope is the rectangle (canvas_left,
    y_top, canvas_right, y_bottom). Wall rendering and openings are
    children."""
    pass


@dataclass
class BayElement(Element):
    """A vertical bay column within a story. Envelope = (left_x, y_top,
    right_x, y_bottom) for that story. Contains the opening + any
    per-bay elements (pilasters are children of the story above this)."""
    pass


@dataclass
class WindowElement(Element):
    """A rectangular window opening rendered as a full classical
    composition: opening + architrave + optional sill + optional pediment
    hood (cornice/triangular/segmental) + optional keystone + flanking
    brackets (ancones) when a hood is present.

    Delegates geometry to ``engraving.windows.window_opening``.
    """
    x_center: float = 0.0
    y_top: float = 0.0        # top of opening rectangle (smaller y)
    y_bottom: float = 0.0     # bottom of opening rectangle (larger y)
    width_mm: float = 0.0
    height_mm: float = 0.0
    hood: str = "none"        # "none" | "cornice" | "triangular" | "segmental"
    has_keystone: bool = False
    has_sill: bool = True
    # Phase 22 Part 4: door openings get a heavier silhouette. The solver
    # sets ``stroke_boost`` to a positive value when ``kind`` is door-like so
    # the opening rectangle, architrave, and keystone all render at a bumped
    # weight. Non-door kinds leave this at 0.0.
    stroke_boost: float = 0.0
    material: Material = field(default=Material.VOID)

    _built: dict | None = field(default=None, repr=False, init=False)

    def void_footprint(self):
        """The glazed opening rectangle (world coords). The architrave
        frame, sill, and hood are FRAME decoration rendered on top and do
        NOT subtract from the enclosing solid wall."""
        from shapely.geometry import box
        xl = self.x_center - self.width_mm / 2
        xr = self.x_center + self.width_mm / 2
        y0 = min(self.y_top, self.y_bottom)
        y1 = max(self.y_top, self.y_bottom)
        if xr <= xl or y1 <= y0:
            return None
        return box(xl, y0, xr, y1)

    def _build(self) -> dict:
        from .. import windows as _windows_mod
        xl = self.x_center - self.width_mm / 2
        return _windows_mod.window_opening(
            x=xl, y_top=self.y_top,
            w=self.width_mm, h=self.height_mm,
            hood=self.hood, keystone=self.has_keystone,
        )

    def _ensure_built(self) -> dict:
        if self._built is None:
            self._built = self._build()
        return self._built

    def render_strokes(self) -> Iterator[StrokedPolyline]:
        built = self._ensure_built()
        # Phase 22 Part 4: door openings get a heavier silhouette. Either
        # rely on ``stroke_boost`` passed in by the solver OR detect by the
        # element's own ``kind``.
        is_door = self.kind in ("door", "arch_door") or self.stroke_boost > 0
        boost = self.stroke_boost if self.stroke_boost > 0 else (
            0.10 if is_door else 0.0
        )
        # Stroke weights by classical layer importance.
        weights = {
            "opening": 0.25 + boost,
            "architrave": 0.25 + boost,
            "sill": 0.25,
            "hood": 0.25 + (boost * 0.5),
            "brackets": 0.25,
            "keystone": 0.35 + boost,
        }
        # Layers to skip entirely.
        skip = {"shadows", "overall_bbox"}
        for layer_name, value in built.items():
            if layer_name in skip:
                continue
            # Sill is optional — honor has_sill.
            if layer_name == "sill" and not self.has_sill:
                continue
            if value is None:
                continue
            weight = weights.get(layer_name, 0.25)
            if isinstance(value, list):
                # Either list-of-polylines (e.g. architrave, sill, hood,
                # brackets) or a single polyline (e.g. opening is a list
                # of (x,y) tuples).
                if value and isinstance(value[0], tuple):
                    # Single polyline as a list of points.
                    yield list(value), weight
                else:
                    for pl in value:
                        if isinstance(pl, list) and pl and isinstance(pl[0], tuple):
                            yield pl, weight
            elif isinstance(value, tuple):
                # Typed tuples like overall_bbox are filtered above. Skip here.
                continue
        yield from super().render_strokes()

    def effective_bbox(self) -> BBox:
        built = self._ensure_built()
        bbox = built.get("overall_bbox")
        if bbox:
            return bbox
        return super().effective_bbox()

    def collect_shadows(self) -> list["ShadowElement"]:
        """Phase 28: extract legacy Shadow objects from the built geometry
        and wrap each as a ShadowElement child. Called by the solver after
        the main tree is assembled."""
        built = self._ensure_built()
        out: list[ShadowElement] = []
        for i, s in enumerate(built.get("shadows", []) or []):
            poly = getattr(s, "polygon", None)
            if poly is None:
                continue
            try:
                if poly.is_empty:
                    continue
            except Exception:
                continue
            out.append(ShadowElement(
                id=f"{self.id}.shadow_{i}",
                kind="shadow",
                envelope=tuple(poly.bounds),
                polygon=poly,
                angle_deg=getattr(s, "angle_deg", 45.0),
                density=getattr(s, "density", "medium"),
            ))
        return out


@dataclass
class PilasterElement(Element):
    """A classical pilaster: rectangular shaft with plinth + base moldings,
    neck, and capital bands, delegated to the legacy ``engraving.pilasters``
    builder so each of Tuscan/Doric/Ionic/Corinthian/Composite/Greek
    variants shows its characteristic subdivision stack."""
    cx: float = 0.0
    width_mm: float = 0.0
    base_y: float = 0.0      # SVG: bottom of pilaster (larger y)
    top_y: float = 0.0       # SVG: top of pilaster (smaller y)
    order: str = "ionic"
    material: Material = field(default=Material.ORNAMENT)
    _built: list = field(default=None, repr=False, init=False)

    def _build(self) -> list:
        from .. import pilasters as _pil
        from .. import canon

        order_cls = {
            "tuscan":      canon.Tuscan,
            "doric":       canon.Doric,
            "ionic":       canon.Ionic,
            "corinthian":  canon.Corinthian,
            "composite":   canon.Composite,
            "greek_doric": canon.GreekDoric,
            "greek_ionic": canon.GreekIonic,
        }[self.order]

        # Choose D so the legacy pilaster's column_h matches the available
        # story height (base_y - top_y). The legacy builder grows upward
        # from base_y by column_h = D * column_D, so to fit the envelope
        # we solve D = available_height / column_D. Fall back to width_mm
        # if column_D is 0 (e.g. degenerate orders).
        available_h = max(1e-3, self.base_y - self.top_y)
        probe = order_cls(D=1.0)
        if probe.column_D > 0:
            D = available_h / probe.column_D
        else:
            D = self.width_mm
        dims = order_cls(D=D)

        return _pil.pilaster(
            dims, cx=self.cx, base_y=self.base_y, width=self.width_mm,
        )

    def _ensure_built(self) -> list:
        if self._built is None:
            self._built = self._build()
        return self._built

    def render_strokes(self) -> Iterator[StrokedPolyline]:
        polys = self._ensure_built()
        # Classical hierarchy: the shaft edges (first two polylines from
        # ``engraving.pilasters.pilaster`` — the two verticals that define
        # the column silhouette) carry the HEAVIEST weight so the order
        # reads as primary structure, not wall decoration. Base / capital
        # mouldings render at a medium weight.
        for idx, pl in enumerate(polys):
            if idx < 2:
                yield pl, 0.50   # shaft edges — heavy column silhouette
            else:
                yield pl, 0.30   # base / cap mouldings — medium
        yield from super().render_strokes()

    def effective_bbox(self) -> BBox:
        polys = self._ensure_built()
        xs = [p[0] for pl in polys for p in pl]
        ys = [p[1] for pl in polys for p in pl]
        if not xs:
            return self.envelope
        return (min(xs), min(ys), max(xs), max(ys))


@dataclass
class WallElement(Element):
    """A wall panel rendered either as a smooth outline or, for rusticated
    variants, a full ashlar grid with optional vermiculation/rock-face/
    arcuation — delegated to the legacy ``engraving.rustication.wall``
    builder. Coordinates follow the SVG y-down convention, with
    ``(x_left, y_top)`` as the top-left corner."""
    x_left: float = 0.0
    x_right: float = 0.0
    y_top: float = 0.0
    y_bottom: float = 0.0
    variant: str = "smooth"    # "smooth" | "banded" | "arcuated" | "chamfered" | "rock_faced" | "vermiculated" | "bossed_smooth"
    course_h: float = 0.0      # for rusticated variants; auto-fills if 0
    block_w: float = 0.0
    arch_springings_y: list = field(default_factory=list)
    arch_spans: list = field(default_factory=list)
    # Phase 21 Part 2: walls auto-discover voids from sibling elements
    # that carry ``material == Material.VOID``. ``void_bboxes`` remains as
    # an optional escape hatch — callers may inject (x0, y0, x1, y1) rects
    # explicitly and they will be unioned with the auto-discovered set.
    void_bboxes: list = field(default_factory=list)
    material: Material = field(default=Material.SOLID)
    _built: dict = field(default=None, repr=False, init=False)

    def _build(self) -> dict:
        from .. import rustication as _rust
        x0 = self.x_left
        y0 = self.y_top
        width = self.x_right - self.x_left
        height = self.y_bottom - self.y_top
        if self.variant == "smooth":
            # Just return an outline — no rustication detail.
            return {
                "outline": [
                    (x0, y0), (x0 + width, y0),
                    (x0 + width, y0 + height), (x0, y0 + height), (x0, y0),
                ],
                "block_rects": [], "joints": [], "joint_shadows": [],
                "arch_voussoirs": [], "face_carving": [], "face_stipples": [],
            }
        if self.variant == "bossed_smooth":
            # Phase 22 Part 5: smooth wall outline + evenly-spaced horizontal
            # hairline rules, no vertical joints. Reads as subtle banding
            # across an otherwise plain wall.
            outline = [
                (x0, y0), (x0 + width, y0),
                (x0 + width, y0 + height), (x0, y0 + height), (x0, y0),
            ]
            joints: list = []
            # One rule every ~15mm; guarantee at least 1 interior rule.
            n_rules = max(2, int(height / 15))
            for k in range(1, n_rules):
                y = y0 + height * k / n_rules
                joints.append([(x0, y), (x0 + width, y)])
            return {
                "outline": outline,
                "block_rects": [], "joints": joints,
                "joint_shadows": [], "arch_voussoirs": [],
                "face_carving": [], "face_stipples": [],
            }
        course_h = self.course_h or max(12, height / 5)
        block_w = self.block_w or max(24, course_h * 2)
        return _rust.wall(
            x0=x0, y0=y0, width=width, height=height,
            course_h=course_h, block_w=block_w,
            variant=self.variant,
            arch_springings_y=self.arch_springings_y or None,
            arch_spans=self.arch_spans or None,
        )

    def _ensure_built(self) -> dict:
        if self._built is None:
            self._built = self._build()
        return self._built

    # ── Phase 23 Day 2: native polyline emission ──────────────────────
    #
    # The methods below emit ``(polyline, layer_tag)`` pairs directly,
    # without going through the legacy ``rustication.wall()`` dict.
    # ``render_strokes()`` consumes this stream and maps each layer tag
    # to a stroke weight. The legacy ``_build()`` path is kept in place
    # for any tests or callers that still introspect the dict shape.

    def _emit_geometry(self):
        """Yield ``(polyline, layer_tag)`` pairs. Native implementation.

        Layer tags: ``'outline'``, ``'blocks'``, ``'joints'``,
        ``'voussoirs'``, ``'carving'``, ``'banding'``.
        """
        if self.variant == "smooth":
            yield from self._emit_smooth()
        elif self.variant == "bossed_smooth":
            yield from self._emit_bossed_smooth()
        elif self.variant in ("banded", "chamfered", "rock_faced",
                              "vermiculated", "arcuated"):
            yield from self._emit_rusticated()
        else:
            yield from self._emit_smooth()

    def _emit_smooth(self):
        outline = [
            (self.x_left, self.y_top), (self.x_right, self.y_top),
            (self.x_right, self.y_bottom), (self.x_left, self.y_bottom),
            (self.x_left, self.y_top),
        ]
        yield outline, "outline"

    def _emit_bossed_smooth(self):
        yield from self._emit_smooth()
        height = self.y_bottom - self.y_top
        # One rule every ~15mm; guarantee at least 1 interior rule
        # (matches the legacy ``_build`` bossed_smooth branch).
        n_rules = max(2, int(height / 15))
        for k in range(1, n_rules):
            y = self.y_top + height * k / n_rules
            yield [(self.x_left, y), (self.x_right, y)], "banding"

    def _emit_rusticated(self):
        """Port of the banded / chamfered / rock_faced / vermiculated /
        arcuated rustication logic to a native polyline stream.

        Yields block rects as ``'blocks'`` and joint centerlines as
        ``'joints'``. Variant-specific face carving falls through to
        dedicated helpers. Arcuated voussoirs are intentionally out of
        scope here — arcuated walls get them from ``ArchElement``
        children.
        """
        import math

        width = self.x_right - self.x_left
        height = self.y_bottom - self.y_top
        course_h = self.course_h or max(12, height / 5)
        block_w = self.block_w or max(24, course_h * 2)

        # Outline
        yield [
            (self.x_left, self.y_top), (self.x_right, self.y_top),
            (self.x_right, self.y_bottom), (self.x_left, self.y_bottom),
            (self.x_left, self.y_top),
        ], "outline"

        # Courses: running bond — alternate rows offset by block_w / 2
        n_courses = max(1, int(math.ceil(height / course_h)))
        actual_course_h = height / n_courses

        for row in range(n_courses):
            y0 = self.y_top + row * actual_course_h
            y1 = y0 + actual_course_h

            # Horizontal joint above this row (not at the very top edge)
            if row > 0:
                yield [(self.x_left, y0), (self.x_right, y0)], "joints"

            # Running-bond offset
            offset = (block_w / 2) if (row % 2 == 1) else 0.0
            x_cursor = self.x_left - offset
            while x_cursor < self.x_right:
                x0 = max(x_cursor, self.x_left)
                x1 = min(x_cursor + block_w, self.x_right)
                if x1 > x0:
                    # Block rect (closed polygon)
                    yield [
                        (x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0),
                    ], "blocks"
                    # Vertical joint on the RIGHT of this block for
                    # variants that carve verticals too.
                    if self.variant in ("chamfered",) and x1 < self.x_right - 0.1:
                        yield [(x1, y0), (x1, y1)], "joints"
                x_cursor += block_w

        # Variant-specific face carving
        if self.variant == "vermiculated":
            yield from self._emit_vermiculated_carving()
        elif self.variant == "rock_faced":
            yield from self._emit_rock_faced_stipple()
        elif self.variant == "arcuated":
            # Voussoirs + radiation are contributed by ArchElement
            # children rather than by the wall itself.
            pass

    def _emit_vermiculated_carving(self):
        """Sinusoidal worm-track grooves across the wall face."""
        import math
        width = self.x_right - self.x_left
        height = self.y_bottom - self.y_top
        n_rows = max(2, int(height / 15))
        for k in range(n_rows):
            y0 = self.y_top + (k + 0.5) * height / n_rows
            pts = []
            for i in range(50):
                x = self.x_left + i * width / 49
                y = y0 + 2 * math.sin(i * math.pi / 4)
                pts.append((x, y))
            yield pts, "carving"

    def _emit_rock_faced_stipple(self):
        """Stipple face with short dot-segments."""
        import random
        r = random.Random(42)
        width = self.x_right - self.x_left
        height = self.y_bottom - self.y_top
        # ~1 dot per 8 mm² across the wall
        n_dots = int(width * height / 8)
        for _ in range(n_dots):
            x = self.x_left + r.random() * width
            y = self.y_top + r.random() * height
            yield [(x, y), (x + 0.3, y)], "carving"

    def _collect_void_footprints(self):
        """Walk descendants of this wall's parent (i.e. siblings + their
        descendants) and collect each VOID element's ``void_footprint()``.
        Returns the list of shapely polygons (possibly empty)."""
        if self.parent is None:
            return []
        footprints = []
        for node in self.parent.descendants():
            if node is self:
                continue
            if getattr(node, "material", None) == Material.VOID:
                fp = node.void_footprint()
                if fp is not None and not fp.is_empty:
                    footprints.append(fp)
        return footprints

    def _void_union(self):
        """shapely geometry of all voids to subtract from this wall's
        geometry. Returns None when there are no voids.

        Combines auto-discovered ``Material.VOID`` siblings (and their
        descendants) with any ``void_bboxes`` that were passed in
        explicitly as a backward-compat / manual-injection escape hatch.
        """
        footprints = self._collect_void_footprints()
        if self.void_bboxes:
            from shapely.geometry import box
            footprints.extend(box(*b) for b in self.void_bboxes)
        if not footprints:
            return None
        from shapely.ops import unary_union
        return unary_union(footprints)

    @staticmethod
    def _geom_to_polylines(geom) -> list:
        """Convert a shapely Polygon/MultiPolygon/LineString to a list of
        polylines suitable for our render pipeline."""
        if geom.is_empty:
            return []
        out = []
        geom_type = geom.geom_type
        if geom_type == "Polygon":
            out.append(list(geom.exterior.coords))
            for hole in geom.interiors:
                out.append(list(hole.coords))
        elif geom_type in ("MultiPolygon", "GeometryCollection"):
            for g in geom.geoms:
                out.extend(WallElement._geom_to_polylines(g))
        elif geom_type == "LineString":
            out.append(list(geom.coords))
        elif geom_type == "MultiLineString":
            for g in geom.geoms:
                out.append(list(g.coords))
        return out

    def render_strokes(self) -> Iterator[StrokedPolyline]:
        # Phase 23 Day 2: consume native ``_emit_geometry()`` stream and
        # map layer tags to stroke weights directly, rather than reverse-
        # engineering the legacy dict shape.
        voids = self._void_union()

        weights = {
            "outline":   0.35,
            "blocks":    0.18,
            "joints":    0.25,
            "banding":   0.18,
            "voussoirs": 0.25,
            "carving":   0.18,
        }

        for polyline, layer in self._emit_geometry():
            weight = weights.get(layer, 0.25)
            # Outline always renders as-is — it's the wall's silhouette.
            if voids is None or layer == "outline":
                yield polyline, weight
                continue
            if layer == "blocks":
                # Closed polygon — CSG-subtract voids.
                try:
                    from shapely.geometry import Polygon
                    poly = Polygon(polyline)
                    if poly.is_valid:
                        clipped = poly.difference(voids)
                        for pl in self._geom_to_polylines(clipped):
                            yield pl, weight
                        continue
                except Exception:
                    pass
                yield polyline, weight
            elif layer in ("joints", "banding"):
                # Line — CSG-clip against voids so joints and bossed-smooth
                # banding rules don't cut across window / arch openings.
                try:
                    from shapely.geometry import LineString
                    line = LineString(polyline)
                    clipped = line.difference(voids)
                    for pl in self._geom_to_polylines(clipped):
                        if len(pl) >= 2:
                            yield pl, weight
                    continue
                except Exception:
                    pass
                yield polyline, weight
            else:
                # carving, voussoirs — thin decoration, no clip
                yield polyline, weight

        yield from super().render_strokes()

    def effective_bbox(self) -> BBox:
        return (self.x_left, self.y_top, self.x_right, self.y_bottom)

    def collect_shadows(self) -> list["ShadowElement"]:
        """Phase 28: walls (rusticated variants) emit thin joint shadow
        bands along the bottom edge of every course. Smooth walls have
        no joint shadows."""
        built = self._ensure_built()
        voids = self._void_union()
        out: list[ShadowElement] = []
        for i, s in enumerate(built.get("joint_shadows", []) or []):
            poly = getattr(s, "polygon", None)
            if poly is None:
                continue
            try:
                if poly.is_empty:
                    continue
            except Exception:
                continue
            # Clip shadow against any void openings in the wall so hatch
            # doesn't run through windows/arches.
            if voids is not None:
                try:
                    poly = poly.difference(voids)
                except Exception:
                    pass
                try:
                    if poly.is_empty:
                        continue
                except Exception:
                    continue
            out.append(ShadowElement(
                id=f"{self.id}.shadow_{i}",
                kind="shadow",
                envelope=tuple(poly.bounds),
                polygon=poly,
                angle_deg=getattr(s, "angle_deg", 45.0),
                density=getattr(s, "density", "medium"),
            ))
        return out


@dataclass
class StringCourseElement(Element):
    """Thin horizontal molding between stories."""
    y_center: float = 0.0
    height_mm: float = 0.0
    x_left: float = 0.0
    x_right: float = 0.0
    material: Material = field(default=Material.SOLID)

    def render_strokes(self) -> Iterator[StrokedPolyline]:
        h = self.height_mm / 2
        # Double-line course
        yield [(self.x_left, self.y_center - h),
               (self.x_right, self.y_center - h)], 0.25
        yield [(self.x_left, self.y_center + h),
               (self.x_right, self.y_center + h)], 0.25
        yield from super().render_strokes()

    def effective_bbox(self) -> BBox:
        h = self.height_mm / 2
        return (self.x_left, self.y_center - h, self.x_right, self.y_center + h)


@dataclass
class EntablatureBandElement(Element):
    """A full-width entablature band that separates two stories. Uses the
    canonical architrave/frieze/cornice proportions of a specific classical
    order — delegates geometry to ``engraving.elements.entablatures``.

    ``x_left`` / ``x_right`` specify the ARCHITRAVE span. The cornice
    naturally projects outward past those edges by roughly 1·D. Two modes:

      * ``cornice_at_edges=False`` (default, e.g. portico where the band
        rests on a colonnade): architrave matches x_left/x_right and the
        cornice overhangs past them — the caller is responsible for
        leaving ~D of room in the enclosing envelope on each side.

      * ``cornice_at_edges=True`` (e.g. palazzo between-story band that
        spans the full canvas width): the architrave is inset by ~D
        inside the builder so the projecting cornice lands AT
        x_left/x_right. Useful when the band must stay within a
        rectangular frame (quoin, canvas edge) that can't be crossed.
    """
    order: str = "ionic"
    x_left: float = 0.0
    x_right: float = 0.0
    y_top_of_capital: float = 0.0  # top of the story below (where entablature sits)
    D: float = 12.0                # module diameter for entablature sizing
    cornice_at_edges: bool = False
    material: Material = field(default=Material.ORNAMENT)
    _inner: object = field(default=None, repr=False, init=False)

    def _get_inner(self):
        if self._inner is None:
            from ..elements.entablatures import entablature_for
            from .. import canon
            order_cls = {
                "tuscan":     canon.Tuscan,
                "doric":      canon.Doric,
                "ionic":      canon.Ionic,
                "corinthian": canon.Corinthian,
                "composite":  canon.Composite,
            }[self.order]
            dims = order_cls(D=self.D)
            if self.cornice_at_edges:
                # Palazzo-style: x_left / x_right mark where the cornice
                # must land (canvas edge, quoin edge). Inset the architrave
                # inward by one D so the projecting cornice lands at the
                # requested edges.
                inset = self.D
                build_left = self.x_left + inset
                build_right = self.x_right - inset
                if build_right <= build_left:
                    build_left, build_right = self.x_left, self.x_right
            else:
                # Portico-style: x_left / x_right mark the ARCHITRAVE span
                # (i.e. the outer column abacus edges). Cornice projects
                # outward past those — caller leaves ~D room in envelope.
                build_left = self.x_left
                build_right = self.x_right
            # column_axes_x: two imaginary columns at the extremes so
            # triglyphs (if any) bracket the band
            col_axes = [build_left + 20, build_right - 20]
            self._inner = entablature_for(
                self.order, id=f"{self.id}.inner",
                kind=f"{self.order}_entablature_inner",
                envelope=self.envelope,
                dims=dims, left_x=build_left, right_x=build_right,
                top_of_capital_y=self.y_top_of_capital,
                column_axes_x=col_axes,
            )
        return self._inner

    def _collect_void_footprints(self):
        """Collect ``Material.VOID`` descendants of this band's siblings.
        Same shape as ``WallElement._collect_void_footprints`` — an
        entablature band spans the full facade width and must not cut
        horizontal rules through window or arch openings in neighbouring
        stories."""
        if self.parent is None:
            return []
        footprints = []
        for node in self.parent.descendants():
            if node is self:
                continue
            if getattr(node, "material", None) == Material.VOID:
                fp = node.void_footprint()
                if fp is not None and not fp.is_empty:
                    footprints.append(fp)
        return footprints

    def _void_union(self):
        footprints = self._collect_void_footprints()
        if not footprints:
            return None
        from shapely.ops import unary_union
        return unary_union(footprints)

    def render_strokes(self) -> Iterator[StrokedPolyline]:
        inner = self._get_inner()
        voids = self._void_union()
        if voids is None:
            yield from inner.render_strokes()
            yield from super().render_strokes()
            return
        # CSG-clip every stroke against the union of void openings so
        # architrave / frieze / cornice rules stop at the edge of any
        # window or arch they would otherwise cut through.
        from shapely.geometry import LineString, Polygon
        for polyline, weight in inner.render_strokes():
            if len(polyline) < 2:
                yield polyline, weight
                continue
            try:
                # Closed polygons (cornice blocks, dentils) → subtract voids.
                if polyline[0] == polyline[-1] and len(polyline) >= 4:
                    poly = Polygon(polyline)
                    if poly.is_valid:
                        clipped = poly.difference(voids)
                        for pl in WallElement._geom_to_polylines(clipped):
                            yield pl, weight
                        continue
                # Open polylines → difference the LineString.
                line = LineString(polyline)
                clipped = line.difference(voids)
                for pl in WallElement._geom_to_polylines(clipped):
                    if len(pl) >= 2:
                        yield pl, weight
            except Exception:
                yield polyline, weight
        yield from super().render_strokes()

    def effective_bbox(self) -> BBox:
        inner = self._get_inner()
        return inner.effective_bbox()


@dataclass
class QuoinElement(Element):
    """A vertical run of rusticated corner blocks at one outer edge of
    the facade. Alternating block heights (double-height → single-height)
    with V-grooved joints, per classical palazzo convention.

    ``side``: 'left' or 'right' — which outer corner.
    ``x_center``: centerline x of this column of quoins.
    ``block_width_mm``: how far the quoin stones project / extend inward.
    """
    side: str = "left"          # "left" or "right"
    x_center: float = 0.0
    y_top: float = 0.0
    y_bottom: float = 0.0
    block_width_mm: float = 10.0
    block_heights: tuple = (12.0, 6.0)  # alternating tall, short
    material: Material = field(default=Material.ORNAMENT)

    def render_strokes(self) -> Iterator[StrokedPolyline]:
        import itertools
        xl = self.x_center - self.block_width_mm / 2
        xr = self.x_center + self.block_width_mm / 2
        # Outline
        yield [(xl, self.y_top), (xr, self.y_top),
               (xr, self.y_bottom), (xl, self.y_bottom),
               (xl, self.y_top)], 0.35

        # Alternating block rectangles with horizontal joint lines
        y_cursor = self.y_top
        heights_cycle = itertools.cycle(self.block_heights)
        while y_cursor < self.y_bottom - 0.5:
            h = next(heights_cycle)
            y_next = min(y_cursor + h, self.y_bottom)
            # Horizontal joint line above this block (except at very top)
            if y_cursor > self.y_top + 0.1:
                yield [(xl, y_cursor), (xr, y_cursor)], 0.25
            y_cursor = y_next
        yield from super().render_strokes()

    def effective_bbox(self) -> BBox:
        return (self.x_center - self.block_width_mm / 2, self.y_top,
                self.x_center + self.block_width_mm / 2, self.y_bottom)


@dataclass
class ParapetElement(Element):
    """Balustrade / attic / cornice top treatment.

    For ``kind="balustrade"``, delegates geometry to
    ``engraving.balustrades.balustrade_run`` producing rails, balusters,
    and optional pedestal blocks at ``pedestal_positions`` (typically bay
    axes). For ``kind="attic"``, emits a plain rectangular block. For
    ``kind="cornice"``, emits a single horizontal rule at mid-height.
    For ``kind="none"``, emits nothing.
    """
    x_left: float = 0.0
    x_right: float = 0.0
    y_top: float = 0.0       # top of parapet (smaller y in SVG)
    y_bottom: float = 0.0    # bottom (larger y — where parapet sits on story below)
    baluster_variant: str = "tuscan"
    # list of x-positions where pedestal blocks interrupt the balustrade
    pedestal_positions: list = field(default_factory=list)
    material: Material = field(default=Material.ORNAMENT)

    _built: dict | None = field(default=None, repr=False, init=False)

    def _build(self) -> dict:
        # The Element base class keeps ``kind`` as a free-form string. We
        # inspect it directly so the same field drives both the tree's kind
        # metadata and the rendering branch.
        if self.kind == "none":
            return {"balusters": [], "top_rail": [], "bottom_rail": [],
                    "pedestals": [], "shadows": []}
        if self.kind == "attic":
            # A blank rectangular attic block
            return {
                "top_rail": [
                    [(self.x_left, self.y_top), (self.x_right, self.y_top)],
                    [(self.x_right, self.y_top), (self.x_right, self.y_bottom)],
                    [(self.x_right, self.y_bottom), (self.x_left, self.y_bottom)],
                    [(self.x_left, self.y_bottom), (self.x_left, self.y_top)],
                ],
                "balusters": [], "bottom_rail": [], "pedestals": [], "shadows": [],
            }
        if self.kind == "cornice":
            y_mid = (self.y_top + self.y_bottom) / 2
            return {
                "top_rail": [[(self.x_left, y_mid), (self.x_right, y_mid)]],
                "balusters": [], "bottom_rail": [], "pedestals": [], "shadows": [],
            }
        # kind == "balustrade" (default)
        from .. import balustrades as _bal
        return _bal.balustrade_run(
            x0=self.x_left, x1=self.x_right,
            y_top_of_rail=self.y_top,
            height=self.y_bottom - self.y_top,
            baluster_variant=self.baluster_variant,
            include_pedestals_at=self.pedestal_positions or None,
        )

    def _ensure_built(self) -> dict:
        if self._built is None:
            self._built = self._build()
        return self._built

    def render_strokes(self) -> Iterator[StrokedPolyline]:
        built = self._ensure_built()
        # Top rail, bottom rail — heavy rails
        for pl in built.get("top_rail", []) or []:
            yield pl, 0.35
        for pl in built.get("bottom_rail", []) or []:
            yield pl, 0.35
        # Balusters — each is a list of polylines (right, left, plinth, cap)
        for baluster in built.get("balusters", []) or []:
            if isinstance(baluster, list):
                for pl in baluster:
                    if isinstance(pl, list) and pl and isinstance(pl[0], tuple):
                        yield pl, 0.25
        # Pedestals — heavy outlines
        for pd in built.get("pedestals", []) or []:
            if isinstance(pd, list) and pd and isinstance(pd[0], tuple):
                yield pd, 0.35
        yield from super().render_strokes()

    def effective_bbox(self) -> BBox:
        return (self.x_left, self.y_top, self.x_right, self.y_bottom)


@dataclass
class PlinthElement(Element):
    """Base course at the very bottom of the facade — stylobate / water
    table / plinth. Solid horizontal band with top and bottom rules,
    optionally projecting outward past the wall line on both sides.
    Material is ``SOLID`` so it reads as wall mass under the ground story.
    """
    x_left: float = 0.0
    x_right: float = 0.0
    y_top: float = 0.0       # where the story above meets the plinth (smaller y)
    y_bottom: float = 0.0    # bottom of canvas (larger y)
    variant: str = "smooth"  # "smooth" | "banded" | "chamfered"
    projection_mm: float = 0.0
    material: Material = field(default=Material.SOLID)

    def render_strokes(self) -> Iterator[StrokedPolyline]:
        xl = self.x_left - self.projection_mm
        xr = self.x_right + self.projection_mm
        # Top rule (water-table shadow line) and bottom rule (ground line)
        # carry the visual weight; vertical sides are lighter.
        yield [(xl, self.y_top), (xr, self.y_top)], 0.45
        yield [(xl, self.y_bottom), (xr, self.y_bottom)], 0.45
        yield [(xl, self.y_top), (xl, self.y_bottom)], 0.35
        yield [(xr, self.y_top), (xr, self.y_bottom)], 0.35
        if self.variant == "banded":
            y_mid = (self.y_top + self.y_bottom) / 2
            yield [(xl, y_mid), (xr, y_mid)], 0.25
        elif self.variant == "chamfered":
            y_bevel = self.y_top + min(1.2, (self.y_bottom - self.y_top) * 0.25)
            yield [(xl, y_bevel), (xr, y_bevel)], 0.18
        yield from super().render_strokes()

    def void_footprint(self):
        return None

    def effective_bbox(self) -> BBox:
        return (self.x_left - self.projection_mm, self.y_top,
                self.x_right + self.projection_mm, self.y_bottom)


# ── Phase 29 — Portico elements ────────────────────────────────────────


@dataclass
class PorticoElement(Element):
    """Root of a portico subtree. Renders nothing itself — children
    (plinth, pedestal course, column run, entablature band, pediment)
    do the work. Parallel to ``FacadeElement``.
    """
    pass


@dataclass
class PedestalCourseElement(Element):
    """A continuous pedestal course running beneath a column colonnade.
    Rendered as a plain banded block — the portico-scale analogue of
    ``ParapetElement(kind='attic')``. Exists as its own element so the
    tree records the column base line distinct from the stylobate.
    """
    x_left: float = 0.0
    x_right: float = 0.0
    y_top: float = 0.0       # top of pedestal (column base sits here) — smaller y
    y_bottom: float = 0.0    # bottom (larger y)
    material: Material = field(default=Material.SOLID)

    def render_strokes(self) -> Iterator[StrokedPolyline]:
        # Outline
        yield [(self.x_left, self.y_top), (self.x_right, self.y_top),
               (self.x_right, self.y_bottom), (self.x_left, self.y_bottom),
               (self.x_left, self.y_top)], 0.35
        # Cap rule just below the top
        h = self.y_bottom - self.y_top
        cap_y = self.y_top + max(0.6, h * 0.12)
        yield [(self.x_left, cap_y), (self.x_right, cap_y)], 0.25
        # Base rule just above the bottom
        base_y = self.y_bottom - max(0.6, h * 0.12)
        yield [(self.x_left, base_y), (self.x_right, base_y)], 0.25
        yield from super().render_strokes()

    def effective_bbox(self) -> BBox:
        return (self.x_left, self.y_top, self.x_right, self.y_bottom)


@dataclass
class ColumnRunElement(Element):
    """A row of N free-standing columns spaced by the intercolumniation.

    Unlike ``PilasterElement`` (which is attached to a wall), a
    ColumnRun is a free-standing colonnade. It owns its ``ColumnElement``
    children directly and delegates rendering to them. The envelope is
    the bbox of the full run (outermost column's outermost abacus edge
    on both sides, base_y at the bottom, top_y of the capital at the
    top).

    Fields:
      order       — one of tuscan/doric/ionic/corinthian/composite/
                    greek_doric/greek_ionic
      column_xs   — world x-coord of each column's axis (centerline),
                    left-to-right
      base_y      — y of the column base (where it sits on its
                    pedestal/plinth) — SVG larger y
      dims        — canon.Order instance; supplies column_h, abacus, etc.
    """
    order: str = "tuscan"
    column_xs: list = field(default_factory=list)
    base_y: float = 0.0
    dims: object = None
    material: Material = field(default=Material.ORNAMENT)

    def __post_init__(self):
        # Instantiate concrete ColumnElement children when we have dims.
        if self.dims is None or not self.column_xs:
            return
        from ..elements.columns import column_for
        col_h = self.dims.column_h
        # Envelope width per column: compute from the intercolumniation so
        # adjacent columns don't overlap. Each column gets at most half the
        # gap to each neighbour, minus a hair so SiblingNonOverlap has
        # breathing room. Fall back to ~D when there's only one column.
        if len(self.column_xs) >= 2:
            xs_sorted = sorted(self.column_xs)
            min_gap = min(b - a for a, b in zip(xs_sorted, xs_sorted[1:]))
            half_w = max(self.dims.D * 0.45, (min_gap / 2) - 0.75)
        else:
            half_w = self.dims.D * 0.6
        for i, cx in enumerate(self.column_xs):
            col = column_for(
                self.order,
                id=f"{self.id}.col_{i}",
                kind=f"{self.order}_column",
                envelope=(cx - half_w, self.base_y - col_h,
                          cx + half_w, self.base_y),
                dims=self.dims, cx=cx, base_y=self.base_y,
            )
            self.add(col)

    @property
    def top_of_capital_y(self) -> float:
        """y where the columns' capitals meet the entablature above."""
        if self.dims is None:
            return self.base_y
        return self.base_y - self.dims.column_h

    def render_strokes(self) -> Iterator[StrokedPolyline]:
        # Columns are children; default super() recursion renders them.
        yield from super().render_strokes()

    def effective_bbox(self) -> BBox:
        if not self.column_xs or self.dims is None:
            return self.envelope
        half_w = self.dims.D * 1.1
        x_min = min(self.column_xs) - half_w
        x_max = max(self.column_xs) + half_w
        y_top = self.base_y - self.dims.column_h
        return (x_min, y_top, x_max, self.base_y)


@dataclass
class PedimentElement(Element):
    """A triangular pediment gable: two raking cornices rising from the
    base corners to an apex, plus the horizontal base line (top of the
    entablature below) and an optional inner raking-cornice rule inset
    by the cornice moulding thickness.

    Geometry (SVG y-down; apex is the smallest y):
        base left = (x_left, y_base)
        base right = (x_right, y_base)
        apex = ((x_left + x_right) / 2, y_base - height)

    where height = (x_right - x_left) / 2 * tan(slope_deg).

    ``tympanum_inset_mm`` controls the inner raking-cornice rule (the
    face of the cornice moulding — an engraver would show this as a
    parallel line inside the outer rake). ``acroterion`` is accepted but
    unused in Phase 29 (future apex ornament hook).
    """
    x_left: float = 0.0
    x_right: float = 0.0
    y_base: float = 0.0        # SVG y of the horizontal base edge (larger y)
    slope_deg: float = 15.0
    fill: bool = False
    acroterion: bool = False
    tympanum_inset_mm: float = 2.0
    material: Material = field(default=Material.ORNAMENT)

    @property
    def apex_xy(self) -> tuple[float, float]:
        import math
        cx = (self.x_left + self.x_right) / 2
        half_span = (self.x_right - self.x_left) / 2
        height = half_span * math.tan(math.radians(self.slope_deg))
        return (cx, self.y_base - height)

    @property
    def height_mm(self) -> float:
        import math
        half_span = (self.x_right - self.x_left) / 2
        return half_span * math.tan(math.radians(self.slope_deg))

    def render_strokes(self) -> Iterator[StrokedPolyline]:
        import math
        apex_x, apex_y = self.apex_xy
        # Base line (top of entablature below)
        yield [(self.x_left, self.y_base),
               (self.x_right, self.y_base)], 0.35
        # Outer raking cornices (left + right to apex)
        yield [(self.x_left, self.y_base),
               (apex_x, apex_y)], 0.35
        yield [(apex_x, apex_y),
               (self.x_right, self.y_base)], 0.35
        # Inner raking-cornice rule: offset the two rakes downward by
        # ``tympanum_inset_mm`` (measured perpendicular-to-rake, then
        # approximated as a vertical shift — good enough at 12-22°).
        inset = max(0.0, self.tympanum_inset_mm)
        if inset > 0:
            # Shrink the triangle by ``inset`` vertical distance — the
            # inner apex sits ``inset`` below the outer apex and the
            # inner base corners move inboard so the slope is preserved.
            dx = inset / math.tan(math.radians(self.slope_deg))
            inner_left = (self.x_left + dx, self.y_base)
            inner_right = (self.x_right - dx, self.y_base)
            inner_apex = (apex_x, apex_y + inset)
            if inner_right[0] > inner_left[0] and inner_apex[1] < self.y_base:
                yield [inner_left, inner_apex], 0.25
                yield [inner_apex, inner_right], 0.25
        yield from super().render_strokes()

    def effective_bbox(self) -> BBox:
        apex_x, apex_y = self.apex_xy
        return (self.x_left, apex_y, self.x_right, self.y_base)


# ── Phase 30 — Boathouse elements ──────────────────────────────────────


@dataclass
class BoathouseElement(Element):
    """Root of a boathouse subtree. Renders nothing itself — children
    (plinth, boat bay band, upper story, roof) do the work. Parallel to
    ``FacadeElement`` and ``PorticoElement``.
    """
    pass


@dataclass
class RoofElement(Element):
    """A gabled roof rendered as two rake lines + an eave line + optional
    shingle hatch + rafter-tail ticks.

    Geometry (SVG y-down; apex is smallest y):
        eave left   = (x_left_eave,  y_eave)
        eave right  = (x_right_eave, y_eave)
        apex        = (x_apex, y_apex)   with y_apex = y_eave - gable_height

    ``x_left_eave`` / ``x_right_eave`` extend past the wall line by
    ``overhang_mm`` on each side (the deep McKim eave). ``x_left_wall`` /
    ``x_right_wall`` are where the rake "lands" on the wall (i.e. the
    wall extents) — used so the rafter-tail ticks sit over the wall's
    top edge.

    ``has_shingle_hatch`` toggles parallel stripes across the two rake
    faces. Stripes run near-vertical (85° from horizontal) so they read
    as courses of shingles sloping with the roof.
    """
    x_left_eave: float = 0.0
    x_right_eave: float = 0.0
    x_left_wall: float = 0.0
    x_right_wall: float = 0.0
    y_eave: float = 0.0         # horizontal line along the top of the upper story
    y_apex: float = 0.0         # apex of the gable (smaller y)
    slope_deg: float = 22.0
    overhang_mm: float = 6.0
    has_shingle_hatch: bool = True
    material: Material = field(default=Material.ORNAMENT)

    @property
    def apex_x(self) -> float:
        return (self.x_left_wall + self.x_right_wall) / 2

    @property
    def gable_height(self) -> float:
        return self.y_eave - self.y_apex

    def render_strokes(self) -> Iterator[StrokedPolyline]:
        apex_x = self.apex_x
        # Eave line — the horizontal "cornice" across the top of the
        # upper story, extended past the wall line by ``overhang_mm``.
        yield [(self.x_left_eave, self.y_eave),
               (self.x_right_eave, self.y_eave)], 0.35
        # Two rake lines from each eave corner up to the apex. Heavy
        # silhouette weight so the roof reads as primary structure.
        yield [(self.x_left_eave, self.y_eave),
               (apex_x, self.y_apex)], 0.35
        yield [(apex_x, self.y_apex),
               (self.x_right_eave, self.y_eave)], 0.35

        # Optional shingle hatch inside the gable triangle (over the
        # wall-supported zone — not the overhang lip). Uses the project's
        # ``parallel_hatch`` at 85° from horizontal so courses read as
        # shingle bands sloping with the roof.
        if self.has_shingle_hatch:
            from shapely.geometry import Polygon
            from ..hatching import parallel_hatch
            gable_poly = Polygon([
                (self.x_left_wall, self.y_eave),
                (apex_x, self.y_apex),
                (self.x_right_wall, self.y_eave),
                (self.x_left_wall, self.y_eave),
            ])
            if gable_poly.is_valid and not gable_poly.is_empty:
                for pl in parallel_hatch(gable_poly, angle_deg=85.0,
                                           spacing=2.2):
                    if len(pl) >= 2:
                        yield pl, 0.12

        # Rafter-tail ticks: short vertical downticks at the eave,
        # stepping across the full eave extent (over both wall AND
        # overhang) so they read as the cut ends of exposed rafters.
        # Spacing = one tick per ~6mm of eave.
        eave_span = self.x_right_eave - self.x_left_eave
        if eave_span > 1.0:
            n_ticks = max(3, int(eave_span / 6.0))
            for i in range(n_ticks + 1):
                x = self.x_left_eave + (i / n_ticks) * eave_span
                yield [(x, self.y_eave),
                       (x, self.y_eave + 1.0)], 0.18

        yield from super().render_strokes()

    def effective_bbox(self) -> BBox:
        return (self.x_left_eave, self.y_apex,
                self.x_right_eave, self.y_eave + 1.0)


# ── Phase 32 — Dimension annotations ───────────────────────────────────


@dataclass
class DimensionElement(Element):
    """A measurement callout: two extension lines, a parallel dimension
    line, two end ticks, and an offset text label.

    Renders ONLY hairline strokes so dimensions read as reference, not
    structure. Text is NOT emitted by ``render_strokes()`` (the stream is
    polyline-only by project convention) — the plate must call
    ``text_labels()`` and feed each tuple to ``page.text(...)``. See the
    ``render_dimensions`` helper below for the one-shot tree walker.

    Geometry conventions (SVG y-down):
      - ``p1`` and ``p2`` are the two world points being measured.
      - ``offset_mm`` is the perpendicular distance from the measured
        line to the dimension line. A positive offset places the
        dimension line on the "left-hand side" of the p1→p2 vector (i.e.
        90° counter-clockwise rotation of the unit vector). Negative
        offset flips to the other side.
      - ``extension_mm`` is the extra length each extension line projects
        past the dimension line.
      - ``tick_style``: "tick" (perpendicular ±1mm slash), "arrow"
        (V-arrowhead pointing inward), or "slash" (45° architectural
        slash). All drawn as hairline.
      - ``text_size_mm`` controls the label font size.

    Zero-length dimensions (p1 == p2) render nothing and report an
    empty bbox — gracefully handled.
    """
    p1: tuple[float, float] = (0.0, 0.0)
    p2: tuple[float, float] = (0.0, 0.0)
    label: str = ""
    offset_mm: float = 6.0
    tick_style: str = "tick"           # "tick" | "arrow" | "slash"
    extension_mm: float = 2.0
    text_size_mm: float = 2.4
    stroke_mm: float = 0.12            # hairline by default (reference layer)
    material: Material = field(default=Material.ORNAMENT)

    def _axes(self):
        """Return (ux, uy, nx, ny, length) where (ux, uy) is the unit
        vector p1→p2, (nx, ny) is the perpendicular (rotated +90° CCW in
        standard math; i.e. rotated CCW seen on a y-up diagram), and
        length is |p2 - p1|. Returns None when the dimension is
        zero-length."""
        import math
        dx = self.p2[0] - self.p1[0]
        dy = self.p2[1] - self.p1[1]
        L = math.hypot(dx, dy)
        if L < 1e-6:
            return None
        ux, uy = dx / L, dy / L
        # Perpendicular convention (in SVG y-down):
        # For a horizontal p1→p2 (ux=+1, uy=0), we want positive offset
        # to place the dim line ABOVE the measured line, i.e. at smaller
        # y. That corresponds to n = (0, -1) = (uy, -ux).
        # For a vertical TOP-to-BOTTOM p1→p2 (ux=0, uy=+1), we want
        # positive offset to place the dim line to the LEFT, i.e. at
        # smaller x. That is n = (-1, 0) = (uy, -ux). Consistent.
        nx, ny = uy, -ux
        return ux, uy, nx, ny, L

    def _dim_line_endpoints(self):
        """Compute the two endpoints of the dimension (offset) line."""
        axes = self._axes()
        if axes is None:
            return None
        ux, uy, nx, ny, _ = axes
        d1 = (self.p1[0] + nx * self.offset_mm,
              self.p1[1] + ny * self.offset_mm)
        d2 = (self.p2[0] + nx * self.offset_mm,
              self.p2[1] + ny * self.offset_mm)
        return d1, d2

    def _extension_line(self, p, dp):
        """Extension line from measured point p out to (and slightly past)
        the offset dimension line endpoint dp. The extension extends
        ``extension_mm`` past dp along the offset direction."""
        axes = self._axes()
        if axes is None:
            return None
        ux, uy, nx, ny, _ = axes
        # Sign of the perpendicular travel: positive offset → +n direction.
        sign = 1.0 if self.offset_mm >= 0 else -1.0
        extra = self.extension_mm * sign
        end = (dp[0] + nx * extra, dp[1] + ny * extra)
        return [p, end]

    def _tick_at(self, dp):
        """Generate the tick-mark polyline(s) at one end of the dimension
        line. Returns a list of polylines (usually 1, sometimes 2 for
        arrows)."""
        axes = self._axes()
        if axes is None:
            return []
        ux, uy, nx, ny, _ = axes
        style = self.tick_style
        if style == "tick":
            # Short perpendicular slash, 1mm each side.
            half = 1.0
            return [[
                (dp[0] - nx * half, dp[1] - ny * half),
                (dp[0] + nx * half, dp[1] + ny * half),
            ]]
        if style == "slash":
            # 45° architectural slash: diagonal across the dimension line.
            import math
            s = 1.2
            cos45 = math.cos(math.radians(45))
            sin45 = math.sin(math.radians(45))
            # Rotate the extension-axis direction by 45°.
            rx = ux * cos45 - nx * sin45
            ry = uy * cos45 - ny * sin45
            return [[
                (dp[0] - rx * s, dp[1] - ry * s),
                (dp[0] + rx * s, dp[1] + ry * s),
            ]]
        if style == "arrow":
            # V-arrowhead pointing INWARD along the dimension line.
            # Each arm is 1.5mm and splays ~20° from the dim-line axis.
            import math
            arm = 1.5
            splay = math.radians(20.0)
            # Determine whether this endpoint is p1's dp or p2's dp by
            # asking the caller (we can't tell from dp alone). We infer
            # direction by which endpoint is closer: arrow points toward
            # the OTHER endpoint. For that we need the dim line endpoints.
            endpoints = self._dim_line_endpoints()
            if endpoints is None:
                return []
            d1, d2 = endpoints
            # Is dp == d1 or d2? Point the arrow TOWARD the other one.
            if abs(dp[0] - d1[0]) < 1e-6 and abs(dp[1] - d1[1]) < 1e-6:
                inward = (ux, uy)          # toward d2
            else:
                inward = (-ux, -uy)        # toward d1
            ix, iy = inward
            # Two arms: rotate inward vector by ±splay and go arm mm.
            c, s = math.cos(splay), math.sin(splay)
            a1 = (ix * c - iy * s, ix * s + iy * c)
            a2 = (ix * c + iy * s, -ix * s + iy * c)
            return [
                [dp, (dp[0] + a1[0] * arm, dp[1] + a1[1] * arm)],
                [dp, (dp[0] + a2[0] * arm, dp[1] + a2[1] * arm)],
            ]
        return []

    def _label_xy(self):
        """Position for the text label: midpoint of the dim line, nudged
        a further ~1mm in the offset direction so the text doesn't sit
        on top of the line."""
        endpoints = self._dim_line_endpoints()
        if endpoints is None:
            return None
        d1, d2 = endpoints
        axes = self._axes()
        if axes is None:
            return None
        ux, uy, nx, ny, _ = axes
        mid = ((d1[0] + d2[0]) / 2, (d1[1] + d2[1]) / 2)
        sign = 1.0 if self.offset_mm >= 0 else -1.0
        nudge = (self.text_size_mm * 0.55) * sign
        # Text baseline sits "above" the line for positive offset;
        # compensate with a y-adjustment toward n so it reads OUTSIDE the
        # structure (away from p1/p2).
        lx = mid[0] + nx * nudge
        ly = mid[1] + ny * nudge
        return lx, ly

    # ── Element API ──────────────────────────────────────────────────

    def render_strokes(self) -> Iterator[StrokedPolyline]:
        axes = self._axes()
        if axes is None:
            # Zero-length: emit nothing.
            return
        endpoints = self._dim_line_endpoints()
        if endpoints is None:
            return
        d1, d2 = endpoints
        w = self.stroke_mm

        # Two extension lines.
        ext1 = self._extension_line(self.p1, d1)
        ext2 = self._extension_line(self.p2, d2)
        if ext1 is not None:
            yield ext1, w
        if ext2 is not None:
            yield ext2, w

        # Dimension line.
        yield [d1, d2], w

        # Ticks at each end.
        for pl in self._tick_at(d1):
            yield pl, w
        for pl in self._tick_at(d2):
            yield pl, w

        yield from super().render_strokes()

    def effective_bbox(self) -> BBox:
        axes = self._axes()
        if axes is None:
            # Zero-length: degenerate point.
            return (self.p1[0], self.p1[1], self.p1[0], self.p1[1])
        endpoints = self._dim_line_endpoints()
        if endpoints is None:
            return self.envelope
        d1, d2 = endpoints
        xs = [self.p1[0], self.p2[0], d1[0], d2[0]]
        ys = [self.p1[1], self.p2[1], d1[1], d2[1]]
        return (min(xs), min(ys), max(xs), max(ys))

    def text_labels(self) -> list[tuple[str, float, float, float, str]]:
        """Yield (text, x, y, font_size, anchor) tuples for the SVG text
        layer. Plates should iterate this and call ``page.text(...)`` for
        each — ``render_strokes()`` is polyline-only and cannot emit text.

        Returns an empty list for zero-length dimensions or empty label.
        """
        if not self.label:
            return []
        xy = self._label_xy()
        if xy is None:
            return []
        return [(self.label, xy[0], xy[1], self.text_size_mm, "middle")]


def horizontal_dimension(p_left: tuple[float, float],
                         p_right: tuple[float, float],
                         y_line: float,
                         label: str,
                         id: str = "dim_h",
                         tick_style: str = "tick",
                         extension_mm: float = 2.0,
                         text_size_mm: float = 2.4,
                         stroke_mm: float = 0.12) -> DimensionElement:
    """Convenience: build a horizontal DimensionElement where the dim line
    sits at ``y_line``. ``p_left`` and ``p_right`` are the measured points
    (any y); the dim line runs horizontally at ``y_line``. The offset is
    derived so the dim line lands at ``y_line``.

    Sign convention: in SVG y-down, positive offset from a horizontal
    left-to-right p1→p2 vector is upward (smaller y). Therefore
    ``offset_mm = p_left.y - y_line``.
    """
    # Snap both measured points to the SAME y (that of p_left) so the
    # dimension is truly horizontal. The caller is responsible for
    # supplying co-linear points; we assert light-heartedly by using
    # p_left's y as the reference.
    y_ref = p_left[1]
    offset = y_ref - y_line
    return DimensionElement(
        id=id, kind="dimension",
        p1=(p_left[0], y_ref),
        p2=(p_right[0], y_ref),
        label=label,
        offset_mm=offset,
        tick_style=tick_style,
        extension_mm=extension_mm,
        text_size_mm=text_size_mm,
        stroke_mm=stroke_mm,
    )


def vertical_dimension(p_top: tuple[float, float],
                       p_bottom: tuple[float, float],
                       x_line: float,
                       label: str,
                       id: str = "dim_v",
                       tick_style: str = "tick",
                       extension_mm: float = 2.0,
                       text_size_mm: float = 2.4,
                       stroke_mm: float = 0.12) -> DimensionElement:
    """Convenience: build a vertical DimensionElement where the dim line
    sits at ``x_line``. ``p_top`` / ``p_bottom`` are the measured points
    (in SVG y-down, p_top has the smaller y).

    Perpendicular convention (see DimensionElement._axes): for a vertical
    top-to-bottom p1→p2 (uy=+1), n=(uy, -ux)=(+1, 0) — i.e. positive
    offset moves the dim line to the RIGHT (larger x). So the offset
    that puts the dim line at x_line is ``x_line - p_top.x``.
    """
    x_ref = p_top[0]
    offset = x_line - x_ref
    return DimensionElement(
        id=id, kind="dimension",
        p1=(x_ref, p_top[1]),
        p2=(x_ref, p_bottom[1]),
        label=label,
        offset_mm=offset,
        tick_style=tick_style,
        extension_mm=extension_mm,
        text_size_mm=text_size_mm,
        stroke_mm=stroke_mm,
    )


def render_dimensions(page, root: Element,
                      frame_bbox: tuple[float, float, float, float] | None = None,
                      label_margin_mm: float = 2.0) -> int:
    """Walk ``root``'s subtree and emit every ``DimensionElement``.

    When ``frame_bbox`` is provided, dimension polylines are clipped to
    stay inside the rectangle and labels whose positions fall outside
    the rectangle (plus ``label_margin_mm``) are dropped. This prevents
    extension lines from exiting the plate frame — a defect noticed on
    palazzo-plan / boathouse / corinthian-capital-detail plates in the
    Phase 46 audit.

    Returns the number of DimensionElements rendered (labels suppressed
    by clipping don't alter the count — the element still exists).
    """
    count = 0
    for node in root.walk():
        if not isinstance(node, DimensionElement):
            continue
        count += 1
        for pl, weight in node.render_strokes():
            if frame_bbox is not None:
                clipped = _clip_polyline_to_bbox(pl, frame_bbox)
                for sub in clipped:
                    if len(sub) >= 2:
                        page.polyline(sub, stroke_width=weight)
            else:
                page.polyline(pl, stroke_width=weight)
        for text, x, y, size, anchor in node.text_labels():
            if frame_bbox is not None:
                x0, y0, x1, y1 = frame_bbox
                if not (x0 + label_margin_mm <= x <= x1 - label_margin_mm
                        and y0 + label_margin_mm <= y <= y1 - label_margin_mm):
                    continue
            page.text(text, x=x, y=y, font_size=size, anchor=anchor)
    return count


def _clip_polyline_to_bbox(
    poly: list[tuple[float, float]],
    bbox: tuple[float, float, float, float],
) -> list[list[tuple[float, float]]]:
    """Clip a polyline against an axis-aligned rectangle. Returns a list
    of sub-polylines (a single polyline may produce multiple pieces if
    it exits and re-enters the rectangle).

    Liang–Barsky per segment, stitched into contiguous runs so the
    caller emits the minimum number of drawsvg paths.
    """
    x_min, y_min, x_max, y_max = bbox
    out: list[list[tuple[float, float]]] = []
    cur: list[tuple[float, float]] = []
    for i in range(len(poly) - 1):
        seg = _clip_segment_lb(poly[i], poly[i + 1],
                               x_min, y_min, x_max, y_max)
        if seg is None:
            if cur:
                out.append(cur)
                cur = []
            continue
        a, b = seg
        if not cur:
            cur.append(a)
            cur.append(b)
        elif cur[-1] == a:
            cur.append(b)
        else:
            out.append(cur)
            cur = [a, b]
    if cur:
        out.append(cur)
    return out


def _clip_segment_lb(
    p0: tuple[float, float], p1: tuple[float, float],
    x_min: float, y_min: float, x_max: float, y_max: float,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Liang–Barsky segment clip. Returns (a, b) — the segment clipped
    to the rectangle — or None if the segment is entirely outside."""
    x0, y0 = p0
    x1, y1 = p1
    dx = x1 - x0
    dy = y1 - y0
    p = (-dx, dx, -dy, dy)
    q = (x0 - x_min, x_max - x0, y0 - y_min, y_max - y0)
    u1 = 0.0
    u2 = 1.0
    for pi, qi in zip(p, q):
        if abs(pi) < 1e-12:
            if qi < 0:
                return None
            continue
        t = qi / pi
        if pi < 0:
            if t > u2:
                return None
            if t > u1:
                u1 = t
        else:
            if t < u1:
                return None
            if t < u2:
                u2 = t
    a = (x0 + u1 * dx, y0 + u1 * dy)
    b = (x0 + u2 * dx, y0 + u2 * dy)
    return a, b
