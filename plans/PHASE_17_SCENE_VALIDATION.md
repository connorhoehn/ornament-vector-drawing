# Phase 17 — Scene-graph constraint validation system

## Why the current validation isn't enough

Current validators are **tactical** — single predicates that check one ratio or one builder's metadata at a time. The user's critique:

> "There is probably a very comprehensive system that can be added… geometric, can use cartesian and 3D points to verify positions of hierarchical elements across different levels and for example in a different level of the building both vertical and horizontal."

A real classical building has structural logic that **spans across stories and across facades**. Examples that current validators don't catch:

- A column on the upper story should sit directly above a column on the lower story (vertical axis)
- A pilaster on the piano nobile should sit directly above a pier in the arcade below
- Window axes should align vertically across all stories
- A pediment apex should align with the central door's centerline (vertical)
- Corner columns should match cardinal positions in plan AND elevation
- Symmetric pairs about the building centerline should mirror in both x and z
- Roman superposition: heaviest order on bottom, lighter above (Tuscan→Doric→Ionic→Corinthian)
- Rusticated joints in adjacent bays should align horizontally to read as one continuous course

These are all **multi-element relational constraints**, not per-element predicates. They require a **scene graph** with positions and a **constraint engine**.

---

## The system

### 1. SceneNode — the unit of structural geometry

```python
@dataclass
class SceneNode:
    """A node in the architectural scene graph."""
    id: str                                    # unique identifier path: "story_1.bay_2.column"
    kind: str                                   # "column", "window", "pilaster", "arch", "pier", "pediment", "balustrade", "story", "bay", "facade"
    pos: tuple[float, float, float]            # 3D Cartesian position in mm (x, y, z)
                                                # x = horizontal across facade, y = vertical (down=larger), z = depth (front=0)
    bbox_local: BBox                           # bounding box in element's local frame
    anchors: dict[str, Anchor]                 # named points in local frame
    parent: SceneNode | None                   # hierarchical parent
    children: list[SceneNode]                  # hierarchical children
    metadata: dict                              # element-specific data (order_kind, etc.)

    def world_pos(self, anchor_name: str = None) -> tuple[float, float, float]:
        """Resolve an anchor's world position by walking up the parent chain."""
```

Every existing builder's `ElementResult` becomes a `SceneNode` with `pos = (cx, ground_y, 0)` for elevation, anchors transformed to local frame.

### 2. Scene — the container

```python
class Scene:
    """A hierarchical scene of architectural elements with constraints."""
    nodes: dict[str, SceneNode]                # flat lookup by id
    root: SceneNode                            # root (typically a Building or Facade)
    constraints: list[Constraint]              # constraints to verify

    def add(self, node: SceneNode, parent_id: str = None) -> None: ...
    def find(self, query: str) -> list[SceneNode]: ...
        # query syntax: "story_*.column" finds all columns across stories
        # "bay_2.*" finds everything in bay 2
    def constrain(self, c: Constraint) -> None: ...
    def validate(self, strict: bool = False) -> ValidationReport: ...
```

### 3. Constraint base + concrete classes

```python
class Constraint(Protocol):
    """A geometric relationship between scene nodes that must hold."""
    nodes: list[str]                            # node ids participating
    label: str
    
    def check(self, scene: Scene) -> list[str]:
        """Return list of error messages; empty if satisfied."""
```

### Concrete constraints

#### Alignment

- `VerticallyAligned(node_ids, axis: "x"|"z", tol)` — all nodes share the named axis coordinate
- `HorizontallyAligned(node_ids, axis: "y"|"z", tol)` — all nodes share the named axis coordinate
- `OnCommonAxis(node_ids, axis_node_id)` — all nodes' axis anchors intersect a reference axis

#### Adjacency

- `StandsOn(upper, lower, anchor_pair=("bottom_center", "top_center"), tol)` — upper's bottom anchor coincides with lower's top anchor
- `MeetsAt(a, b, anchor_a, anchor_b, tol)` — two specific anchors coincide
- `Touches(a, b, tol)` — bbox edges within tol of touching

#### Centering

- `CenteredOn(child, parent, tol)` — child's axis is parent's axis
- `CenteredBetween(child, left, right, tol)` — child centered between two reference nodes

#### Symmetry

- `MirrorPair(left, right, axis_x, tol)` — two nodes' positions mirror each other about a vertical axis
- `SymmetricChildren(parent_id, axis: "x"|"z", tol)` — parent's children form a mirror set
- `BilateralFacade(facade_id, tol)` — entire facade is bilaterally symmetric about its centerline

#### Hierarchical

- `ContainedIn(child, parent, margin)` — child's bbox fits inside parent's
- `ChildrenSpanParent(parent, axis: "x"|"y", margin)` — children together cover parent's extent

#### Architectural-specific

- `CorrespondingBays(story_a, story_b, tol)` — bay axes line up vertically across two stories
- `SuperpositionOrder(stories, expected_order)` — expected_order = ["doric", "ionic", "corinthian"] enforces Vignola's superposition rule
- `GroundLine(nodes, ground_y, tol)` — listed nodes share a common ground y
- `EvenPitch(nodes, axis: "x"|"y", expected_pitch, tol)` — listed nodes have constant on-center spacing
- `KeystoneOverDoor(door_node, keystone_node, tol)` — keystone centered on door
- `ColumnsUnderPediment(column_ids, pediment_id, tol)` — outermost columns flank pediment base

#### Detail-at-scale

- `MinFeatureVisible(node, plate_dpi, min_pixels=2)` — node's smallest dimension is visible at print resolution
- `StrokeReadable(layer, plate_size_mm, min_stroke_mm)` — stroke weight readable at plate scale

---

## How elements get into the scene

### Auto-build from existing plate code

Each plate's `build_validated()` populates a Scene:

```python
def build_validated():
    scene = Scene()
    
    facade_node = SceneNode(id="facade", kind="facade", pos=(0, 0, 0), ...)
    scene.add(facade_node)
    
    for s_idx, story in enumerate(stories):
        story_node = SceneNode(id=f"story_{s_idx}", kind="story", pos=(0, story_y, 0),
                               parent=facade_node, ...)
        scene.add(story_node, parent_id="facade")
        
        for b_idx, bay in enumerate(bays):
            bay_node = SceneNode(id=f"story_{s_idx}.bay_{b_idx}", kind="bay",
                                 pos=(bay.axis_x, story_y, 0), parent=story_node, ...)
            scene.add(bay_node, ...)
            
            opening = bay.openings[s_idx]
            opening_node = SceneNode(id=f"story_{s_idx}.bay_{b_idx}.opening",
                                     kind=opening.kind,
                                     pos=(bay.axis_x, opening_y, 0), ...)
            scene.add(opening_node, ...)
    
    # Add constraints
    scene.constrain(BilateralFacade("facade"))
    for b_idx in range(len(bays)):
        scene.constrain(CorrespondingBays(f"story_0.bay_{b_idx}", f"story_1.bay_{b_idx}"))
        scene.constrain(CorrespondingBays(f"story_1.bay_{b_idx}", f"story_2.bay_{b_idx}"))
    
    # Validate
    report = scene.validate()
    return svg_path, report
```

### Auto-build from ElementResult

A helper that converts ElementResult to SceneNode automatically:

```python
def from_element_result(result: ElementResult, id: str, parent: SceneNode = None) -> SceneNode:
    """Convert any ElementResult to a SceneNode rooted at its anchor."""
```

---

## Z-axis / 3D — what it means for elevation drawings

Even though plates show elevations (front view), classical buildings have logic that connects:

- **Front facade columns** at `z = 0` (front face)
- **Side facade columns** at `z = building_depth`
- **Corner columns** at `z = 0` AND `z = building_depth` — they're the SAME column visible from two angles
- **Plan view** (a different drawing convention) shows `(x, z)` — looking down

For now, all drawings are at `z = 0`. The system **supports** z but doesn't require it. Future plates could include side elevations that constrain to match the front via shared corner columns.

---

## Scene query language

Find nodes by pattern:

- `"story_1.*"` — everything inside story_1
- `"*.column"` — every column at any depth
- `"story_*.bay_2.*"` — everything in bay 2 across all stories
- `"facade.story_0.bay_2.opening"` — exactly one node

Used by constraints:

```python
scene.constrain(VerticallyAligned(scene.find("story_*.bay_2.*"), axis="x"))
# Every element in bay 2 across all stories must share an x coordinate
```

---

## Interactive debugging

When validation fails, the scene-graph system produces actionable reports:

```
ConstraintError: VerticallyAligned[axis=x] failed
  story_0.bay_2.column.axis  → x = 100.5
  story_1.bay_2.pilaster.axis → x = 102.0
  diff = 1.5 mm, tol = 0.5 mm
Suggested fix: piano-nobile bay axes should reference arcade pier midpoints
```

Plus a **visual debug overlay** mode: render the scene with axis lines drawn red where constraints fail.

```python
scene.render_debug(output_path="out/schematic_debug.svg")
# Renders the plate + dashed red axis lines at every failed constraint
```

---

## Implementation in 4 waves

### Wave 1 — Foundation (~3 hours)

- `engraving/scene.py` — `SceneNode`, `Scene`, query language
- `engraving/scene_constraints.py` — `Constraint` protocol + 8 core constraints (VerticallyAligned, StandsOn, CenteredOn, MirrorPair, CorrespondingBays, GroundLine, EvenPitch, ContainedIn)
- `from_element_result()` helper

### Wave 2 — Wire existing plates (~2 hours)

- Convert `plate_schematic.build_validated()` to populate a Scene
- Add CorrespondingBays, BilateralFacade, GroundLine constraints
- Run — find which constraints fire as bugs (these are real misalignments the validator now detects)

### Wave 3 — Architectural constraint library (~3 hours)

- Add: `SuperpositionOrder`, `KeystoneOverDoor`, `ColumnsUnderPediment`, `RusticationCoursesAlign`, `WindowAxesAlignAcrossStories`
- Apply to plate_palazzo_v2 + plate_portico
- Build deliberately-bad-scene tests

### Wave 4 — Visual debug overlay (~2 hours)

- `scene.render_debug(svg_path)` — draws red dashed axis lines at every failed constraint
- Each failure annotated with text labels
- Integrate with the CLI: `ornament debug <plate>` produces `out/<plate>_debug.svg`

---

## Cross-comparison: what existing predicates handle vs. what scene constraints add

| Question | Predicate (current) | Scene constraint (new) |
|---|---|---|
| Is column 7D tall? | ✅ `column_h ≈ 7×D` | (not needed at scene level) |
| Do upper-story windows line up with arches? | ❌ no | ✅ `CorrespondingBays` |
| Is the facade bilaterally symmetric? | ❌ no | ✅ `BilateralFacade` |
| Does central door have keystone above? | ❌ no | ✅ `KeystoneOverDoor` |
| Are columns in superposition order? | ❌ no | ✅ `SuperpositionOrder` |
| Do triglyphs sit over column axes? | ✅ `triglyph_over_every_column` | ✅ same, but at scene level — generalizes to "modillions over column axes," "balusters over piers," etc. |
| Is the leaf silhouette closed? | ✅ `is_closed` | (not needed at scene level — this is per-element) |

Scene constraints don't replace per-element predicates; they layer **above** them.

---

## Acceptance test for Phase 17 completion

```python
def test_scene_graph_catches_misaligned_facade():
    # Build a facade where the central door is NOT centered
    facade = make_palazzo_facade(
        bay_count=5,
        central_door_offset_x=10.0,  # deliberately misaligned
    )
    scene = facade.to_scene()
    report = scene.validate()
    
    # The bilateral-symmetry constraint should fire
    assert any("BilateralFacade" in e for e in report)
    assert any("central" in e.lower() and "door" in e.lower() for e in report)
```

---

## Effort estimate

Total: ~10 hours of agent work across 4 waves. Each wave delivers a usable layer; the system is incremental.

---

## When this is done

- Plates build with their structural relationships explicitly declared
- Misalignments are caught at build time with actionable error messages
- New plates compose the constraint library declaratively
- A debug overlay shows WHERE failures are
- The validation library is no longer a list of disconnected predicates but a **structural model checker** for classical architecture
