# Codebase analysis — paths to robustness, accuracy, scalability

Session: 2026-04-19. Assessed after Phases 5–22 landed.

## Current size

- **65 Python modules** in engraving/ + planner/ + elements/ + validate/
- **~30,800 lines** across code + tests + plans
- **287 passing tests**, 1 skipped
- **19 plates** registered
- **3 PDFs** buildable (per-plate + bound book)

## Architecture snapshot (after Phase 19/21/22)

```
engraving/
├── element.py              Material enum, Element base, Violation
├── containment.py          Layer-A structural constraints
├── schema.py               Anchor, ElementResult (legacy bridge)
├── canon.py                Ware's order tables
├── render.py               Page / drawsvg wrapper
├── preview.py              Playwright PNG renderer
├── geometry.py             low-level helpers
├── elements/
│   ├── _legacy.py          pedestal, column, entablature, pediment (dict-returning)
│   ├── arches.py           ArchElement, Semicircular/SegmentalArchElement
│   ├── columns.py          7 ColumnElement subclasses
│   └── entablatures.py     5 EntablatureElement subclasses
├── planner/
│   ├── plan.py             FacadePlan, StoryPlan, BayPlan, OpeningPlan, ParapetPlan, PilasterPlan
│   ├── solver.py           top-down: solve_story_heights, solve_bay_layout, solve_openings, solve_pilasters, solve_string_courses, solve()
│   ├── elements.py         FacadeElement, StoryElement, BayElement, WindowElement, PilasterElement, WallElement, StringCourseElement, EntablatureBandElement, QuoinElement, ParapetElement
│   ├── constraint_solver.py linprog-based bidirectional solver (Phase 20)
│   └── debug.py            visual overlay renderer
├── validate/
│   ├── __init__.py         primitive predicates + report collection
│   ├── orders.py           pydantic schemas for 5 orders + Greek variants
│   ├── entablatures.py     doric/ionic/corinthian validators
│   ├── elements.py         arch/window/balustrade/rustication invariants
│   ├── composition.py      facade-level rules
│   ├── motifs.py           SVG motif validation
│   ├── aesthetic.py        Layer-C rules (stroke weight hierarchy, etc.)
│   └── plates.py           top-level orchestration
└── scene.py, scene_constraints.py  legacy scene graph (pre-Phase 19)
```

## What's strong

### 1. Layered validation

Three distinct severity levels (Layer A structural, B canonical, C aesthetic) give callers real flexibility. The `Violation` dataclass carries structured metadata (layer/rule/element_id/axis/overshoot_mm) that makes programmatic filtering trivial. This is better than most CAD systems offer.

### 2. CSG Solid/Void abstraction

`Material` enum + `void_footprint()` + wall auto-discovery of sibling voids is **architecturally correct**. Walls CANNOT render through openings because the booleans subtract them at render time, not post-hoc. Few drafting systems operate this cleanly.

### 3. Declarative plans

`FacadePlan.solve()` either produces valid geometry or refuses with a specific `PlanInfeasible` reason. Generation and validation share the tree — "passed validation but picture wrong" is structurally impossible for the constraints we enforce.

### 4. Order canon

`canon.py` has Ware's fractions as typed dataclasses. Every column silhouette builder reads from it. When Ware disagrees with, say, Vignola — the source of truth is one file, diff-able.

### 5. Test coverage

287 tests is substantial. Regression coverage is particularly good around the bugs you flagged (arches-overlap-piano-nobile, uniform-opening-widths, capital-h-drift, cartouche-one-wing). Adding a new constraint almost always comes with a deliberately-violating fixture that proves the predicate fires.

## Where the codebase is weakest

### 1. Two parallel element systems

There's **`engraving/elements/_legacy.py`** (dict-returning `pedestal`, `entablature`, etc.) AND **`engraving/elements/*.py`** (Element subclasses). The planner uses the new system; legacy plates still use the old. Two code paths to maintain.

**Fix:** migrate every legacy plate to use the planner. Delete `_legacy.py`. One system. `plate_portico.py`, `plate_corinthian.py`, etc. should all go through `FacadePlan` or a new `ColumnPlatePlan`.

### 2. `WindowElement` delegates to legacy `windows.py`

The Element is a thin wrapper around `engraving/windows.py::window_opening()` which returns a dict. The wrapper translates back-and-forth. This adds a layer of indirection and hides bugs — the legacy function has opinions about stroke layers that the wrapper has to reverse-engineer.

**Fix:** port the window-rendering logic directly into `WindowElement.render_strokes()` as native polyline emission. Same for `PilasterElement` (delegates to `pilasters.py`) and `WallElement` (delegates to `rustication.py`). The legacy modules become implementation details that can be removed once ported.

### 3. String-based enums for element kinds

`Element.kind` is a bare `str`. Subclasses set it in `__init__` without a registry. Typos are possible. The `OpeningKind` and `WallVariant` `Literal` types catch some cases but element `kind` is free-form.

**Fix:** make `Element.kind` a proper enum `ElementKind = Enum(...)` with all known values registered at module import. Subclasses set `kind = ElementKind.ARCH`, and validators pattern-match on the enum.

### 4. No `Element.__post_init__` for geometric invariants

Subclasses have various `__post_init__`-like validators but it's not a consistent pattern. `SemicircularArchElement` could check `span > 0` but doesn't. A garbled construction throws later in `_build()` or `effective_bbox()` rather than at construction.

**Fix:** every Element subclass implements `_validate_construction()` called from a base-class `__post_init__`. Failures raise `ConstructionError` with specific reasons.

### 5. Test file is too monolithic

`tests/test_validation.py` is 2383 lines and mixes every domain (primitives, orders, entablatures, plates, CSG, planner). Hard to find failing tests; slow to run focused subsets.

**Fix:** split into:
- `tests/test_schema.py` — Element/Material/Violation/bbox math
- `tests/test_validate_*.py` — one file per validator submodule
- `tests/test_elements_*.py` — element-specific rendering
- `tests/test_plates_*.py` — plate smoke + render
- `tests/test_integration.py` — end-to-end plan → render → validate

Pytest auto-discovers them. Each runs in ~0.3s vs current 6+ sec.

### 6. Constraint solver not integrated with FacadePlan

Phase 20 shipped `ConstraintSolver` as a standalone. It's not wired into `FacadePlan.solve()`. The top-down solver still does all the real work.

**Fix:** use `ConstraintSolver` INSIDE `solve_story_heights()` to handle mixed constraints (min heights + total = canvas + proportional relations). The current ad-hoc pinning + redistribution loop can be replaced with `linprog` — simpler and correct by construction.

### 7. Mostly-rectangular everything

WindowElement/PilasterElement/WallElement render rectangles with some molding rules. The detail is in the legacy builders they wrap, but visually the plates lack the complexity a period engraving shows (fluting, cast shadows at scale, ornamental string courses, etc.). Adding those needs more elements.

**Fix:** three new element types would substantially improve visual quality:
- **ShadowElement** — renders parallel-hatch fills on shapely polygons (the shadows are already generated, they're just not rendered through the Element path)
- **FlutingElement** — draws fluting lines on column shafts (legacy fluting.py exists)
- **BossesElement** — ornamental quoins with carved bosses (vermiculation, diamond-points)

### 8. No unit tests for the plate renders themselves

The planner and elements are well-tested. But `plate_palazzo_plan.py` is tested via `build_validated` returning a report — no test actually inspects the rendered SVG for correctness (e.g. "this plate has N arches with tight voussoir rings; stroke #42 is the keystone of bay 2").

**Fix:** add SVG-parse tests that count polyline instances, validate stroke weights, and assert specific features are present.

### 9. No regression snapshots

If someone refactors a builder and accidentally changes the rendered output subtly, nothing catches it. Only pixel-diff tests would.

**Fix:** pytest-regressions-style snapshot testing. For each plate, record the exact bytes of a canonical render; alert on diff. Costs disk space but catches silent regressions.

### 10. `engraving/scene.py` + `scene_constraints.py` are now dead

Phase 19 superseded the scene-graph approach with `Element` + `validate_tree()`. The scene modules still work but duplicate functionality.

**Fix:** delete them once any remaining references are migrated. Reduces ~1000 lines of dead code.

## Scalability concerns

### 1. `shapely.ops.unary_union` on hundreds of voids

Every WallElement computes `unary_union(voids_in_scope)` at render time. For a 7-bay × 3-story facade that's 21 openings + a few rust blocks. Fine today. For a 20-bay 5-story civic palazzo, it's 100+ polygons — potentially noticeable at interactive speeds.

**Fix:** cache the void union per (parent-element, frame-counter) pair. Invalidate when children change. ~10x speedup for interactive regeneration.

### 2. No rendering pipeline for multi-plate books

`scripts/build_book.py` renders each plate serially via subprocess. For 18 plates that's ~30 seconds. With pytest's `--forked` or asyncio.TaskGroup this could parallelize naturally.

### 3. Path optimization deferred

`vpype` doesn't install on Python 3.14 (shapely/GEOS issue). The book PDF has lots of redundant short segments that would merge into longer polylines. Net effect: the book is 4 MB when it could be ~1.5 MB.

**Fix:** either wait for vpype-on-Py3.14, downgrade to Python 3.12 (where vpype installs), or write a minimal polyline-merger in-tree (100 lines of shapely).

## Accuracy concerns

### 1. Proportion drift across orders

The Composite volute zone bug (surfaced by subdivision tests) is a symptom: Composite's capital subdivisions sum to more than capital_h because acanthus_row1 + row2 + caulicoli + echinus + abacus was never rebalanced. This kind of drift is hard to prevent without an axiom like "subdivisions must sum to parent height exactly" — which we now CAN enforce via `SiblingNonOverlap` + `ChildrenSumToParent` if we introduce the latter as a Layer A rule.

**Fix:** add `ChildrenExactlyTileParent(axis)` — a Layer A constraint asserting children's extents along `axis` sum to the parent's extent. Catches every Composite-volute-style drift.

### 2. No Greek Doric annulet count regression

Greek Doric capital has 3-5 annulet rings. Current builder emits 4. A test asserts count == 4. But if someone wanted 5 for a different Greek Doric example (Paestum has more), there's no parameterization — it's hardcoded. Accuracy only covers one specific variant.

**Fix:** make annulet_count a parameter of `canon.GreekDoric` (already there as ClassVar=4). Let callers override.

### 3. Units and scale checked by convention, not type

Every `float` could be mm, inches, points, or SVG user units. There's no distinguishing. A careless kwarg passing inches to a mm function silently corrupts a plate.

**Fix:** a lightweight `@dataclass class Distance: value: float; unit: Literal['mm']` that's 1-to-1 with float but type-checks. Rejected would be `Distance * Distance`; allowed `Distance + Distance`.

### 4. Arch intrados is sampled, not analytic

`SemicircularArchElement` generates 40 arc points. For a large-span arch at print scale, small sampling glitches show as tiny polygon-edges. A true circular arc is lossless; 40 points isn't.

**Fix:** emit an SVG `<path d="A ...">` arc command where possible. drawsvg supports it. For shapely calculations keep the 40-point approximation but for SVG output use the analytic arc.

## Robustness concerns

### 1. No `PlanInfeasible` → recovery mode

When a plan is infeasible, we raise. No automatic "try these adjustments" mode. The CLI `generate` falls back to reporting the error.

**Fix:** add `FacadePlan.try_solve_with_fallbacks()` that on first failure adjusts the obvious knobs (shrink opening width_frac by 5%, retry; shrink height_ratio; etc.) and reports what it changed.

### 2. No concept of "plate template"

Every plate file is hand-authored. Multiple plates that share a layout (e.g. 5 palazzi variants) have boilerplate. Users who want "give me 10 palazzo variations" have to write 10 files.

**Fix:** `scripts/generate_variations.py` that takes a base `FacadePlan` and sweeps one or two parameters, emitting numbered plates.

### 3. No roundtrip test (SVG → metadata)

Once a plate is rendered to SVG, the Element tree is discarded. You can't read back the SVG and reconstruct the plan. The plan isn't preserved in the file.

**Fix:** emit the serialized FacadePlan as an SVG `<metadata>` block. Add `engraving.planner.load_from_svg(svg_path) → FacadePlan`. Now the SVG is the source of truth AND reproducible.

## Prioritized improvements (if only 3 could be done)

1. **Integrate `ConstraintSolver` into `FacadePlan.solve()`** (Phase 20 finish). Replaces the ad-hoc pinning loop with a principled linprog call. Immediately fixes the 3 TestEntablatureBand containment failures (cornice overhang) by making the canvas/insets a solved variable instead of fixed.

2. **Port WindowElement/PilasterElement/WallElement to native polyline emission**, delete `engraving/elements/_legacy.py`. Unifies the code path. Lets us control stroke weights per layer precisely. Removes a whole class of "legacy returns a dict, wrapper has to reverse-engineer it" fragility.

3. **Split `tests/test_validation.py` into per-domain files, add snapshot regression tests for every plate.** The former makes the test suite navigable; the latter prevents silent visual regressions.

## Prioritized future features (if only 3 could be added)

1. **Roundtrip SVG ↔ FacadePlan.** Embed the plan as metadata. Users can edit plates by modifying the SVG metadata OR by rerunning the CLI. Single source of truth.

2. **Variation generator.** `scripts/generate_variations.py --base palazzo_5bay.yaml --sweep bays:3,5,7,9 --sweep order:doric,ionic,corinthian` → 12 plates. This is the architectural catalog every drafting house wants.

3. **CSG-native shadow rendering.** The wall subtracts voids. Shadows are also CSG regions (light source + occluder → shaded polygon). Integrating shadows into the Element tree means parallel-hatch fills happen automatically for ALL recessed openings — a dramatic visual improvement without per-plate work.

## Architectural debt score: 3/10

The foundation is clean; the legacy-shim layer and the dual-element-system are the main sources of drag. Everything else is "feature-completeness work" rather than "cleanup to stay viable." At 30k lines, the project is maintainable for a single engineer for another 6 months of active development without a major refactor.

If the project stays active beyond that, priority 1-3 above should happen; if it's going dormant, what's shipped today is defensible.
