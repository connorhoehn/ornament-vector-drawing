# Phase 21 — CSG-based Solid/Void abstraction

## The problem

Current plan-based rendering still shows wall/opening overlap in
`out/plate_palazzo_plan.png` — the ground floor's rusticated joint lines
run through the arch openings. The current system renders walls and
openings as two independent layers and layers them on top of each other.

The user's insight, correctly stated: *"It has to be defined with an
abstraction that cannot fail and is comprehensive."*

Retrospective validation (the validators + scene graph) catches overlap
after it's drawn. The right abstraction prevents it at construction time:
**walls are solid material; openings are holes cut from them**. You
boolean-subtract the holes. The overlap becomes structurally impossible.

## The abstraction

Every Element is tagged with a **material role**:

```python
class Material(str, Enum):
    SOLID    = "solid"      # walls, piers, stringcourses — subtractable material
    VOID     = "void"       # openings — cuts into enclosing solids
    ORNAMENT = "ornament"   # columns, pilasters, cornices, balusters — 
                             # 3D-projecting objects that sit IN FRONT OF walls
    FRAME    = "frame"      # architraves, hoods — decorate voids; render normally
```

### Render rules

1. **SOLID** elements compute their outline geometry, then **subtract the
   union of all VOID footprints in their scope** before emitting strokes.
2. **VOID** elements emit no strokes themselves — they register a
   footprint polygon that solids will subtract from.
3. **ORNAMENT** and **FRAME** render normally on top of solids.
4. Scope = siblings + descendants of siblings in the same parent.

### Implementation

```python
from shapely.geometry import Polygon
from shapely.ops import unary_union

class Element:
    material: Material = Material.ORNAMENT
    
    def void_footprint(self) -> Polygon | None:
        """Return the void polygon this element cuts from solids.
        Non-None only for Material.VOID."""
        return None
    
    def render_strokes(self) -> Iterator[StrokedPolyline]:
        # default implementation handles CSG for SOLID elements
        if self.material == Material.SOLID:
            yield from self._render_with_voids_subtracted()
        else:
            yield from self._render_native()
    
    def _render_with_voids_subtracted(self):
        # walk scope, gather voids, subtract from own outline
        voids = [e.void_footprint() for e in self._scope()
                 if e.material == Material.VOID and e.void_footprint()]
        if not voids:
            yield from self._render_native()
            return
        void_union = unary_union(voids)
        # Subclasses provide their own _solid_polygons(); we clip each
        for poly in self._solid_polygons():
            clipped = poly.difference(void_union)
            if clipped.is_empty:
                continue
            for sub in _iter_polygons(clipped):
                yield list(sub.exterior.coords), self._stroke_weight
                for hole in sub.interiors:
                    yield list(hole.coords), self._stroke_weight
```

### Specific element classifications

| Element | Material | Notes |
|---|---|---|
| `WallElement` | SOLID | all rustication blocks are subtractable |
| `WindowElement` | VOID | footprint = opening rect; hood + architrave are FRAME children |
| `ArchElement` | VOID | footprint = the arch's total opening shape (rect + semicircle) |
| `PilasterElement` | ORNAMENT | projects from wall plane |
| `ColumnElement` | ORNAMENT | same |
| `StringCourseElement` | SOLID | a continuous band; doesn't get cut by openings within a story (it's between stories) |
| `ParapetElement` | ORNAMENT | on top of building |
| `EntablatureElement` | ORNAMENT | above capitals |

### What this prevents structurally

- **Brick pattern running through an opening** — impossible; the wall's block polygons literally have the opening subtracted
- **Pediment hood rendering behind a wall** — the hood is FRAME material, renders on top
- **Column standing INSIDE a window opening** — the column is ORNAMENT; if it happens to be positioned inside a VOID footprint, the SOLID containing both still subtracts the void, and the column just renders in front of the hole — architecturally unusual but not a rendering bug
- **Story above overlapping story below** — already enforced by containment

### What this adds to the validation layer

```python
# Layer A (structural):
class VoidEntirelyInsideSolid(Constraint):
    """Every VOID element's footprint must be fully inside at least one
    SOLID element's outline. Otherwise the void is cutting into air."""

class NoVoidVoidOverlap(Constraint):
    """Two VOID elements shouldn't overlap unless explicitly declared
    (e.g. nested arched window in an arcuated wall)."""
```

## Migration plan

**Part 1 — Minimum viable fix (today, before Phase 21 proper)**

Just teach `WallElement` to subtract opening footprints from its block grid.
No enum, no full CSG framework. Solver passes `void_polygons` to WallElement
at construction. This fixes the visible palazzo_plan bug without the broader
abstraction.

**Part 2 — Full Phase 21 (2-3 sessions)**

1. Add `Material` enum to `engraving/element.py`
2. Add `void_footprint()` method and scope-walker
3. Refactor `WindowElement` + `ArchElement` to return void footprints
4. Refactor `WallElement` + `StringCourseElement` to subtract
5. Write `VoidEntirelyInsideSolid` + `NoVoidVoidOverlap` constraints
6. Apply to all existing plates; visual regression check

**Part 3 — Extensions (later)**

- Layered solids: rusticated BASE course + smooth wall above, both solid but
  at different heights
- "Boss" elements (projecting quoins, rustic keystones) that add to the SOLID
  rather than cutting from it
- Shadow rendering that uses the SOLID/VOID boundary to know where to cast
  (soffits, recessed openings)

## Budget

Part 1: ~2 hours  
Part 2: ~8 hours across 2 sessions  
Part 3: ~8 hours (optional extensions)

## Acceptance test

```python
def test_wall_subtracts_arch_void():
    """The palazzo_plan render should have ZERO joint lines crossing any
    arch opening. Mathematical property checked by walking the rendered
    strokes and intersecting them with arch polygons."""
    from plates.plate_palazzo_plan import build_validated
    svg, _ = build_validated()
    # Parse rendered SVG, get all polylines, get all arch openings
    # For each joint-line polyline, shapely-intersect with each arch polygon
    # Assert intersection is empty for every pair
```

When Part 2 is complete, this test passes deterministically.
