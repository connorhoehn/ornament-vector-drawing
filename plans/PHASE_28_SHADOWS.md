# Phase 28 — CSG-native shadows

## Problem

Period engravings derive much of their visual richness from SHADOWS — parallel-hatch fills on the lit-from-upper-left convention that give depth to recessed openings, cornice soffits, and pilaster faces.

Current state:
- Legacy builders return `shadows: list[Shadow]` in their dicts (shapely Polygons + hatch angle + density)
- Wrapper elements (`WindowElement`, `ArchElement`, etc.) currently DROP these shadows — they don't render them
- The old plate files hatched shadows manually using `hatching.parallel_hatch(polygon)`
- New plan-based plates have NO shadow rendering at all

Result: the generated palazzo looks flat compared to legacy renders that included shadow hatching.

## Goal

Shadows become first-class Elements in the tree. Every recessed zone (opening intrados, cornice soffit, pilaster right-face, balcony underside) is a `ShadowElement` that renders parallel-hatch fills automatically.

## Plan — 4 days

### Day 1 — `ShadowElement` base

```python
# engraving/planner/elements.py (additions)
from dataclasses import dataclass, field
from shapely.geometry import Polygon
from ..element import Element, Material, StrokedPolyline

@dataclass
class ShadowElement(Element):
    """A CSG-native shadow region. Renders parallel-hatch polyline fills
    on its polygon. Light is assumed from upper-left (315° from horizontal).
    """
    polygon: Polygon = None
    angle_deg: float = 45.0          # hatch direction
    density: Literal["light", "medium", "dark"] = "medium"
    material: Material = field(default=Material.ORNAMENT)  # layer on top of everything
    
    _SPACING = {"light": 0.55, "medium": 0.40, "dark": 0.28}
    
    def render_strokes(self):
        if self.polygon is None or self.polygon.is_empty:
            return
        from engraving.hatching import parallel_hatch
        spacing = self._SPACING[self.density]
        for line_polyline in parallel_hatch(
            self.polygon, angle_deg=self.angle_deg, spacing=spacing):
            yield line_polyline, 0.12   # hatch always hairline
    
    def effective_bbox(self):
        if self.polygon is None or self.polygon.is_empty:
            return self.envelope
        return self.polygon.bounds
```

### Day 2 — Wire shadows into WindowElement / ArchElement / PilasterElement

Each of these has legacy shadow polygons available in their `_build()` output. Expose via a new method:

```python
class WindowElement(Element):
    def collect_shadows(self) -> list[ShadowElement]:
        """Extract legacy shadow polygons and wrap as ShadowElements."""
        built = self._ensure_built()
        shadows = []
        for s in built.get("shadows", []):
            if s.polygon is None or s.polygon.is_empty:
                continue
            shadows.append(ShadowElement(
                id=f"{self.id}.shadow_{len(shadows)}",
                kind="shadow",
                envelope=s.polygon.bounds,
                polygon=s.polygon,
                angle_deg=s.angle_deg,
                density=s.density,
            ))
        return shadows
```

Apply similarly to ArchElement (voussoir soffit shadows), PilasterElement (right-face shadow), WallElement (soffit under cornice), BalustradeElement (shadow under rail), QuoinElement (joint shadows).

### Day 3 — Solver emits shadow elements

In `solve()`:

```python
# After building the tree, walk and add shadows as children
shadow_count = 0
for node in list(facade.descendants()):  # list() because we're mutating
    if hasattr(node, "collect_shadows"):
        for shadow in node.collect_shadows():
            shadow.id = f"facade.shadow_{shadow_count}"
            shadow_count += 1
            node.add(shadow)
```

Test: a rendered palazzo should have 20-100 shadow elements (per plate).

### Day 4 — Aesthetic rule + configuration

Add a `ShadowPlan` top-level configuration:

```python
@dataclass
class FacadePlan:
    ...
    shadows_enabled: bool = True
    shadow_density_default: str = "medium"   # override per-element if needed
```

When `shadows_enabled=False`, `collect_shadows()` returns `[]`. Useful for construction drawings vs presentation drawings.

Aesthetic rule (Layer C): `ShadowConsistency` — every facade shadow should use a consistent `angle_deg` (unless the element specifies otherwise). Currently shadows are drawn at various angles depending on element kind — consistency would improve the final look.

Tests:

```python
class TestShadowElement:
    def test_shadow_element_renders_hatch(self):
        from shapely.geometry import Polygon
        from engraving.planner.elements import ShadowElement
        poly = Polygon([(0,0), (20,0), (20,10), (0,10)])
        s = ShadowElement(id="s", kind="shadow",
                          envelope=poly.bounds, polygon=poly,
                          angle_deg=45, density="medium")
        strokes = list(s.render_strokes())
        assert len(strokes) > 5  # several hatch lines
    
    def test_palazzo_has_shadows(self):
        from plates.plate_palazzo_plan import make_plan
        from engraving.planner.elements import ShadowElement
        plan = make_plan()
        plan.shadows_enabled = True
        facade = plan.solve()
        shadows = [n for n in facade.descendants() if isinstance(n, ShadowElement)]
        assert len(shadows) > 10
```

### Re-render palazzo and compare

Before/after side-by-side: should see shadow hatch fills inside:
- Each arch intrados (dark soffit under springing line)
- Each cornice soffit (horizontal dark band under every cornice)
- Right face of each pilaster (narrow vertical hatch)
- Right face of each baluster (catches afternoon light)

## Acceptance criteria

- Every Element subclass exposing shadow-producing geometry has `collect_shadows()`
- `FacadePlan.solve()` automatically adds ShadowElements to the tree
- `shadows_enabled=False` disables them (useful for construction drawings)
- Rendered palazzo has visible shadow hatching on cornice soffits and arch intrados
- All tests pass (300+ after this phase)

## Effort

~4 days. Day 1 (ShadowElement itself) is trivial. Days 2-3 (wiring into every element type) is the bulk. Day 4 is polish + tests.

## Forward work

- Angle selection per story (upper stories use lighter shadows since they receive less obstruction)
- Season / time of day parameters on FacadePlan — change shadow angle programmatically
- Soft shadows (fade-out gradient at edge of hatch region)
- Cast shadows (a moulding casts a shadow on the wall BELOW it; would require ray-casting)
