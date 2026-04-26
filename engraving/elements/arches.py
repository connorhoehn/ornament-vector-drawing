"""Arch elements wrapping the legacy arch builders.

The critical correctness property: ``effective_bbox()`` must include the
voussoir ring's outermost extent, the keystone's projection ABOVE the
extrados, and the imposts' flanking blocks — NOT just the intrados span.
This is the fix for 'arches extending into the piano nobile' that the
user flagged: the legacy wall() passed the arch height as a story-fraction
but the actual drawn arch (with keystone + voussoirs) exceeded that.
"""
from __future__ import annotations
from typing import Iterator, Literal
from dataclasses import dataclass, field

from ..element import Element, Material, StrokedPolyline
from ..schema import Anchor, BBox, Polyline
from .. import arches as _arches


@dataclass
class ArchElement(Element):
    """Base for arch elements. Subclasses implement _build().

    ``y_bottom`` is the floor / sill level of the opening. If > y_spring
    the arch element renders two vertical jambs going down from the
    springing to the floor, and its void_footprint includes the full
    rectangular "door" portion below the springing. If == y_spring
    (default) the arch is just the arc above the springing with no
    rectangular jamb zone.
    """

    # Inputs
    cx: float = 0.0
    y_spring: float = 0.0
    span: float = 0.0
    voussoir_count: int = 0
    with_keystone: bool = False
    keystone_width: float | None = None
    archivolt_bands: int = 0
    y_bottom: float = 0.0  # floor level (SVG: larger y than y_spring). 0 means
                           # "no below-springing jamb zone" (use if arch IS the
                           # whole opening, as in a vault or a decorative motif).
    material: Material = field(default=Material.VOID)

    # Cached result
    _built: dict | None = field(default=None, repr=False, init=False)

    def _build(self) -> dict:
        raise NotImplementedError

    def void_footprint(self):
        """Return the TIGHT arch opening footprint as a shapely polygon —
        the actual arch shape, not the bounding rectangle. Phase 22 Part 1
        fix: previous version used box(effective_bbox) which left a visible
        rectangular edge above the arch apex in rusticated walls.

        Shape = rectangular portion from ``y_bottom`` up to the springing
        line (the "door" portion below the arch) + the half-disk above
        the springing (semicircular or segmental, as determined by the
        subclass's _arc_points()).
        """
        import math
        from shapely.geometry import Polygon
        from shapely.ops import unary_union
        r = self.span / 2
        xl = self.cx - r
        xr = self.cx + r
        # Use the declared y_bottom when set; otherwise fall back to the
        # effective_bbox's bottom (backward compat for callers that don't
        # specify y_bottom).
        y_bot = self.y_bottom if self.y_bottom > self.y_spring + 0.01 \
            else self.effective_bbox()[3]
        parts = []
        if y_bot > self.y_spring + 0.1:
            rect = Polygon([
                (xl, self.y_spring),
                (xr, self.y_spring),
                (xr, y_bot),
                (xl, y_bot),
                (xl, self.y_spring),
            ])
            parts.append(rect)
        # Arc portion (subclass supplies arc points)
        arc_pts = list(self._arc_points(n=48))
        if arc_pts:
            poly_pts = list(arc_pts) + [(xr, self.y_spring),
                                         (xl, self.y_spring),
                                         arc_pts[0]]
            try:
                arc_poly = Polygon(poly_pts).buffer(0)
                if not arc_poly.is_empty:
                    parts.append(arc_poly)
            except Exception:
                pass
        if not parts:
            return None
        return unary_union(parts)

    def _arc_points(self, n: int = 48):
        """Yield (x, y) points along the intrados arc (sub-spring → apex →
        sub-spring, in SVG y-down coords). Subclasses override."""
        return ()

    def _ensure_built(self) -> dict:
        if self._built is None:
            self._built = self._build()
        return self._built

    def render_strokes(self) -> Iterator[StrokedPolyline]:
        built = self._ensure_built()
        # Stroke weights by classical layer importance
        for pl in built.get("intrados", []):
            yield pl, 0.35
        for pl in built.get("extrados", []):
            yield pl, 0.35
        for pl in built.get("voussoirs", []):
            yield pl, 0.25
        if built.get("keystone"):
            yield built["keystone"], 0.35
        for pl in built.get("archivolts", []):
            yield pl, 0.25
        for pl in built.get("imposts", []):
            yield pl, 0.25
        # Jambs: when y_bottom sits below springing, draw vertical lines
        # from springing down to the floor on both sides. Without these
        # the bottom-level openings (doors) read as floating arcs.
        if self.y_bottom > self.y_spring + 0.1:
            r = self.span / 2
            yield [(self.cx - r, self.y_spring),
                   (self.cx - r, self.y_bottom)], 0.35
            yield [(self.cx + r, self.y_spring),
                   (self.cx + r, self.y_bottom)], 0.35

    def effective_bbox(self) -> BBox:
        built = self._ensure_built()
        xs, ys = [], []
        for layer_key in ("intrados", "extrados", "voussoirs", "archivolts", "imposts"):
            for pl in built.get(layer_key, []):
                for x, y in pl:
                    xs.append(x); ys.append(y)
        if built.get("keystone"):
            for x, y in built["keystone"]:
                xs.append(x); ys.append(y)
        if not xs:
            return self.envelope
        x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
        # Extend downward to include the jamb zone when present.
        if self.y_bottom > self.y_spring + 0.1:
            y1 = max(y1, self.y_bottom)
            r = self.span / 2
            x0 = min(x0, self.cx - r)
            x1 = max(x1, self.cx + r)
        return (x0, y0, x1, y1)

    def collect_shadows(self):
        """Phase 28: extract legacy Shadow objects from the built arch
        (intrados soffit, keystone flank, impost undersides) and wrap
        each as a ShadowElement."""
        from ..planner.elements import ShadowElement
        built = self._ensure_built()
        out = []
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
class SemicircularArchElement(ArchElement):
    """Semicircular arch: rise = span/2.

    The FULL rendered height above the springing line is span/2 (the apex)
    plus voussoir depth (the extrados ring) plus any keystone projection.
    """

    def _arc_points(self, n: int = 48):
        """Semicircle from (cx - r, y_spring) over apex (cx, y_spring - r)
        back to (cx + r, y_spring)."""
        import math
        r = self.span / 2
        for i in range(n + 1):
            t = math.pi + math.pi * (i / n)
            yield (self.cx + r * math.cos(t),
                   self.y_spring + r * math.sin(t))

    def _build(self) -> dict:
        return _arches.semicircular_arch(
            cx=self.cx, y_spring=self.y_spring, span=self.span,
            voussoir_count=self.voussoir_count,
            with_keystone=self.with_keystone,
            keystone_width=self.keystone_width,
            archivolt_bands=self.archivolt_bands,
        )


@dataclass
class SegmentalArchElement(ArchElement):
    """Segmental arch with explicit rise < span/2."""
    rise: float = 0.0

    def _arc_points(self, n: int = 48):
        """Circular segment from (cx - r_chord, y_spring) to
        (cx + r_chord, y_spring) with apex at (cx, y_spring - rise)."""
        import math
        half_span = self.span / 2
        if self.rise <= 0 or self.rise >= half_span:
            # Degenerate: fall back to semicircle
            r = half_span
            for i in range(n + 1):
                t = math.pi + math.pi * (i / n)
                yield (self.cx + r * math.cos(t),
                       self.y_spring + r * math.sin(t))
            return
        # Radius of full circle: R = (span^2 + 4*rise^2) / (8*rise)
        R = (self.span ** 2 + 4 * self.rise ** 2) / (8 * self.rise)
        # Circle center is BELOW springing by (R - rise)
        cy = self.y_spring + (R - self.rise)
        # Angle from center to springing endpoints (in SVG coords)
        # The endpoints are at (cx ± half_span, y_spring). Angle from
        # center (cx, cy) = atan2(y_spring - cy, ±half_span - 0)
        theta_end = math.atan2(self.y_spring - cy, half_span)   # slight negative
        # Sweep from left endpoint (angle π - theta_end, which is near π)
        # through apex (angle = -π/2 in SVG = straight up) to right (theta_end)
        theta_left = math.pi - theta_end
        theta_right = theta_end
        for i in range(n + 1):
            t = theta_left + (theta_right - theta_left) * (i / n)
            yield (self.cx + R * math.cos(t), cy + R * math.sin(t))

    def _build(self) -> dict:
        return _arches.segmental_arch(
            cx=self.cx, y_spring=self.y_spring, span=self.span, rise=self.rise,
            voussoir_count=self.voussoir_count,
            with_keystone=self.with_keystone,
            keystone_width=self.keystone_width,
            archivolt_bands=self.archivolt_bands,
        )


if __name__ == "__main__":
    arch = SemicircularArchElement(
        id="demo", kind="semicircular_arch",
        envelope=(40, 20, 160, 100),
        cx=100, y_spring=100, span=80,
        voussoir_count=11, with_keystone=True, archivolt_bands=2,
    )
    print(f"effective_bbox: {arch.effective_bbox()}")
    print(f"stroke count: {sum(1 for _ in arch.render_strokes())}")
