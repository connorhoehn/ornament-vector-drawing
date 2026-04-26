# System audit — extending beyond palazzo facades

Context: user wants to generate porticos and McKim-Mead-White style boat
houses (Harvard Newell, NYAC, Columbia) in addition to urban palazzo
facades. This audit inventories how tightly the current system is coupled
to "palazzo" and proposes the cleanest extension path.

## TL;DR

Of ~40 core classes, **~20 are already building-type-agnostic**, **~10
are palazzo-specific in naming + planning strategy only** (not in data
structure), and **0 are fundamentally incompatible** with other classical
building types.

The cleanest extension path is **sibling Plan subclasses** (`PorticoPlan`,
`BoathousePlan`) that reuse the solver primitives, plus three genuinely
new Element subclasses (`PedimentElement`, `RoofElement`,
`ColumnRunElement`). Palazzo code is not disturbed.

The one missing primitive that requires real design work is a **pitched
roof / pediment** geometry — everything currently above the top story is
`ParapetElement` (flat top: balustrade / attic / cornice). A sloping top
with ridge / eaves / rake is not yet expressible.

## What is agnostic, as-is

- `engraving/element.py` — `Element` base, `Material` enum, `Violation`.
  Pure hierarchy + CSG primitives. No building-type concepts.
- `engraving/containment.py` — Layer A constraints are structural, not
  semantic. The skip-list uses palazzo names (wall, quoin, parapet) but
  generalises trivially (add `roof`, `pediment` when those exist).
- `engraving/canon.py` — Tuscan → Composite Orders. Proportional tables
  are universal.
- `engraving/elements/arches.py`, `columns.py`, `entablatures.py` —
  classical forms parameterised by order + size. Ready to reuse.
- `engraving/planner/constraint_solver.py` — linprog wrapper. Knows only
  about variables + equations.
- `engraving/validate/aesthetic.py` — stroke weight, feature size, detail
  density. No palazzo assumptions.
- `OpeningPlan`, `PilasterPlan` in `plan.py` — pure geometric dataclasses,
  reusable for any building type.

## What is palazzo-specific

### `engraving/planner/plan.py`

- `FacadePlan.stories` assumes **ordered vertical stack**. A portico has 1
  "story" of columns + entablature + pediment — semantically different,
  not a stack. A boathouse has `boat_bay` + `upper_story` + `gable` —
  not three equivalent stories.
- `FacadePlan.bays` assumes **left-to-right horizontal rhythm within a
  story**. Works for portico columns; breaks for boathouse boat bays
  which are structurally ONE zone.
- `FacadePlan.parapet` assumes a **flat top treatment** (balustrade /
  attic / cornice). Porticos need pediments; boathouses need pitched
  gabled roofs.
- `StoryPlan.height_ratio` assumes **constant y-extent across x**. A
  pediment's height is `f(x)` — changes with horizontal position.

### `engraving/planner/solver.py`

- `solve_story_heights()` allocates canvas to horizontal slabs.
  Inapplicable to pediment geometry (non-rectangular) or a boat bay
  (single tall zone).
- `solve_openings()` enforces the **Vignola opening-hierarchy rule**
  (widths descend going up). Inapplicable to single-story porticos;
  wrong for boathouses where upper-clerestory can exceed a boat-bay
  mullion width.
- The solver's primitives (`solve_bay_layout`, `solve_openings`,
  `solve_pilasters`) are actually generic — the coupling is in `solve()`
  ORCHESTRATION, not in the primitives themselves.

### `engraving/planner/elements.py`

Naming coupling (harmless, but worth renaming for clarity):

- `FacadeElement` — root is named "facade." A temple or boathouse is a
  different thing. Rename base → `BuildingElement`, keep `FacadeElement`
  as a palazzo-specific subclass.
- `StoryElement`, `BayElement` — fine as generic names; the concepts
  (horizontal slab, vertical tile) generalise beyond palazzo.
- `ParapetElement` — genuinely palazzo-specific in its variants
  (balustrade / attic / cornice). Needs sibling: `PedimentElement`,
  `RoofElement`.

Fully generic and reusable:

- `WindowElement`, `PilasterElement`, `WallElement`, `QuoinElement`,
  `StringCourseElement`, `EntablatureBandElement`, `ShadowElement`.

## What is missing for porticos

1. **PedimentElement** — triangular gable above entablature. Slope
   12–22.5°, base = span, apex = ridge. Fields: filled (tympanum sculpt
   hatch) vs open, acroterion (apex ornament), antefixae (eave
   ornaments), raking cornice profile.
2. **ColumnRunElement** — free-standing column colonnade with implicit
   entablature above. Not a pilaster (which is attached to a wall).
   Could be a thin wrapper over the existing `ColumnElement` + an
   `EntablatureBandElement`.
3. **PorticoPlan** — Plan subclass with `column_count`,
   `intercolumniation` (modules), `order`, `pedestal` (bool),
   `pediment` (PedimentPlan). `solve_portico()` replaces
   `solve_story_heights()` — portico height budgets are pedestal +
   column + entablature + pediment, not a ratio-weighted story stack.

## What is missing for boat houses

McKim / Gilded-Age boathouse archetype: tall ground-floor boat bays
(open arcade or trussed timber), an upper story with clerestory
windows, a gabled or cross-gabled shingle roof with deep eaves, often
a central pedimented frontispiece.

1. **RoofPlan** — slope angles per face (front / rear / sides can
   differ), overhang mm, ridge height, gable vs hip topology. For a
   boathouse front elevation we only need the gable polygon + eave line.
2. **RoofElement** — polyline envelope (ridge + eaves + rake) plus
   optional shingle hatch, rafter-tail ticks, ridge cap, vent dormer.
3. **RafterElement / TrussElement** — exposed heavy-timber truss inside
   an open boat bay. Structural diagram (king post, struts) drawn at
   engraving stroke weights.
4. **BoathousePlan** — `boat_bays: list[BoatBayPlan]`,
   `upper_story: StoryPlan`, `roof: RoofPlan`, optional
   `central_pediment: PedimentPlan`. Solve order: allocate vertical
   budget (bay + story + roof), then tile boat bays left-right (reuses
   `solve_bay_layout`), then emit roof polygon from upper-story top.

The existing CSG engine handles the "arcaded boat bay" case cleanly:
posts are `WallElement`-like solids, slip openings are `ArchElement`
voids, the whole arcade fits under a common cornice.

## Orthogonal gap: plan view vs elevation

All current renderers assume an **elevation** (vertical slice, SVG
y-down). McKim plates routinely pair plan + elevation. A plan view of
a boathouse shows boat slips, structural posts, access stairs, a
footprint rectangle.

This requires a parallel render path, not a modification to the
elevation system:

- `FacadePlan` → elevation (today)
- `FootprintPlan` → plan view (new) — same Element/Material
  vocabulary, different projection.

Axonometric / isometric is further out and not in scope for this
audit.

## Proposed hierarchy

```
BuildingElement (rename of current FacadeElement base)
├── FacadeElement              (palazzo-specific, today)
│   ├── StoryElement
│   │   ├── BayElement
│   │   │   ├── WindowElement | ArchElement
│   │   │   └── PilasterElement
│   │   ├── WallElement
│   │   ├── StringCourseElement
│   │   └── EntablatureBandElement
│   ├── ParapetElement
│   └── QuoinElement
├── PorticoElement              (new)
│   ├── ColumnRunElement        (new)
│   │   └── ColumnElement × N
│   ├── EntablatureBandElement  (reuse)
│   └── PedimentElement         (new)
└── BoathouseElement            (new)
    ├── BayElement × N          (reuse — boat bays)
    ├── StoryElement            (reuse — clerestory / upper)
    ├── RoofElement             (new — gable or cross-gable)
    │   └── RafterElement × N   (new — optional exposed truss)
    └── PedimentElement         (reuse — if central frontispiece)
```

Palazzo code is untouched. New building types are additive.

## Implementation sketch — Phase 29 (portico) and Phase 30 (boathouse)

### Phase 29 — Portico as first-class plan (~5 days)

- Day 1: `PedimentElement` + `RoofElement` base (just geometry + stroke
  rendering), write unit tests for apex position, rake-cornice
  endpoints.
- Day 2: `PorticoPlan` dataclass + `solve_portico()` function. Reuses
  constraint solver for vertical budget allocation (pedestal / column /
  entablature / pediment).
- Day 3: `ColumnRunElement`. Tile columns by intercolumniation in
  modules. Hook into `PilasterElement`'s existing order-aware renderer.
- Day 4: `plate_portico_plan.py` — the declarative twin of the existing
  hard-coded `plate_portico.py`. Snapshot test.
- Day 5: Replace `plate_portico.py` body with a FacadePlan-style entry
  point (keep name for backwards compat).

### Phase 30 — Boat house (~7 days)

- Day 1: `RoofPlan` dataclass + `RoofElement` (gable polygon + eave
  lines, no shingles yet).
- Day 2: Shingle hatch + rafter-tail ticks on `RoofElement` (reuse
  `parallel_hatch`).
- Day 3: `BoatBayPlan` — tall arched or trabeated opening
  (span × height), arcade layout.
- Day 4: `BoathousePlan` + `solve_boathouse()` orchestration.
- Day 5: `RafterElement` / `TrussElement` — king-post truss diagram
  in open boat bays.
- Day 6: `plate_boathouse_plan.py` — Harvard-Newell-style reference
  plate. Snapshot test.
- Day 7: Aesthetic rules — roof slope must be ≥ 10° and ≤ 30° for
  classical proportion; eave overhang ≥ 2 × rafter depth; etc.

## Risk

**Low.** Every new dataclass and Element subclass is additive. The
constraint solver, containment rules, canon, order library, stroke
renderer, and CSG engine remain untouched. The only rename needed is
`FacadeElement` base → `BuildingElement`, and we can defer that by
simply having `PorticoElement` and `BoathouseElement` also inherit
from `FacadeElement` (a harmless misnomer at first).

## Near-term recommendation

Before Phase 29/30, do Phase 27 (catalog generator) as planned — it
will give us free coverage when adding new building types, because
every variation sweep becomes a visual regression test.
