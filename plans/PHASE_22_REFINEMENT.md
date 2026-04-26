# Phase 22 — Geometric Refinement

**Goal:** close the gap between "structurally correct palazzo" and "looks like a period engraving." Every issue here is visible in `out/plate_palazzo_plan.png` and has a concrete geometric fix.

## Part 1 — Tight void footprints

**Problem:** `ArchElement.void_footprint()` returns `box(effective_bbox)` — the axis-aligned bounding rectangle around the arch. The wall subtracts a rectangle, leaving a visible rectangular edge above the arch apex.

**Fix:** Each arch subclass builds a shapely Polygon that traces the ACTUAL opening:
- Rectangular below springing (from springing down to opening bottom)
- Semi-circular (or segmental) arc above springing sampled at 40+ points
- Union the two

```python
def void_footprint(self):
    from shapely.geometry import Polygon, box
    from shapely.ops import unary_union
    import math
    r = self.span / 2
    xl, xr = self.cx - r, self.cx + r
    # Rect below springing (only if the arch has content below y_spring)
    # Arch element's effective_bbox bottom = largest y. But arches rendered
    # on their own have no below-springing portion; when used as openings,
    # the Opening's y_bottom is further below y_spring.
    # ArchElement.cx/y_spring/span only. Caller supplies y_bottom separately.
    # Simpler: draw the arc polygon + extend rect down to effective_bbox.bottom.
    bbox = self.effective_bbox()
    rect = box(xl, self.y_spring, xr, bbox[3])
    # Arc polygon
    n = 48
    arc_pts = []
    for i in range(n + 1):
        t = math.pi + math.pi * (i / n)
        arc_pts.append((self.cx + r * math.cos(t),
                        self.y_spring + r * math.sin(t)))
    arc_pts.append((xr, self.y_spring))
    arc_pts.append((xl, self.y_spring))
    arc_pts.append(arc_pts[0])
    arc_poly = Polygon(arc_pts).buffer(0)
    return unary_union([rect, arc_poly])
```

Same for `SegmentalArchElement` using the rise instead of `r`.

**Test:** render a wall with an arch void; assert the wall polyline intersection with a point ABOVE the apex on the arch centerline is empty but a point at the same y OUTSIDE the arch returns intersects the wall.

## Part 2 — Real entablature between piano nobile and upper story

**Problem:** stories are separated only by thin `StringCourseElement` double lines. A proper Ionic piano nobile should have a complete entablature on top: architrave + frieze + cornice, projecting forward.

**Fix:** Add `EntablaturePlan` as part of `StoryPlan`:
```python
@dataclass
class StoryPlan:
    ...
    with_entablature: bool = False   # cap this story with a full entablature
```

When True, solver allocates ~0.25D (where D = piano nobile diameter equivalent derived from pilaster width) for an entablature band above the story, using the order's canonical architrave/frieze/cornice subdivisions.

`EntablatureBandElement` wraps the existing `EntablatureElement` wrappers and replaces the StringCourseElement between that story and the next.

## Part 3 — Quoins (corner rustication)

**Problem:** Real palazzi have rusticated corner blocks (quoins) — alternating large/small stones at the outer corners that read as a strong vertical masonry pier at each end.

**Fix:** Add `with_quoins: bool = True` to `FacadePlan`. When set, the solver emits two `QuoinElement` children of `FacadeElement`, one at each outer x edge, spanning from canvas_bottom to canvas_top. They're `Material.ORNAMENT` — render in front of walls.

`QuoinElement` renders alternating large/small rusticated blocks (12mm / 6mm alternating heights) with V-grooved joints.

## Part 4 — Door vs window differentiation

**Problem:** central bay door architrave looks identical to side-bay window architrave.

**Fix:** When `Opening.kind in ("door", "arch_door")`:
- Architrave stroke bumped to MEDIUM (0.35) instead of FINE (0.25)
- Architrave width fraction bumped from 1/12 to 1/8 of opening width
- Optional pediment hood automatically set to "triangular" if `hood == "none"`
- Keystone rendered heavier

Small details, but accumulate to visual hierarchy.

## Part 5 — Piano nobile wall banding (optional)

**Problem:** the piano nobile wall is a white void between the windows — real palazzi often show subtle horizontal channels (bosses) or vertical channels (piers) around each pilaster.

**Fix:** Allow `StoryPlan.wall = "bossed_smooth"` as a new variant — smooth wall with very shallow horizontal channels at each course level (roughly 1 channel per 15mm of story height). Renders as hairline horizontal rules only, no vertical joints.

## Implementation schedule

| Part | Effort | Blocks |
|---|---|---|
| 1 Tight void footprints | 1 hr | Biggest visual win; do first |
| 2 Real entablature bands | 3 hr | Needs StoryPlan extension |
| 3 Quoins | 2 hr | New Element subclass |
| 4 Door vs window | 1 hr | Small tweaks |
| 5 Piano nobile banding | 1 hr | Optional polish |

**Total: ~8 hours.** Part 1 alone will make a visible difference on the next render.

## Acceptance criteria

After all 5 parts:
- No rectangular edges visible above arch openings
- Piano nobile has a proper 3-part entablature (architrave/frieze/cornice) crowning it
- Building has strong vertical corner quoins at the two outer edges
- Central door reads as visibly more important than flanking windows
- Piano nobile wall shows subtle horizontal detailing, not empty whitespace

Then the next render should be indistinguishable from a late-18th-century architectural engraving at a glance.
