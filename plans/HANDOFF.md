# Handoff — ornament-vector-drawing

Session date: 2026-04-20 (late). Next session should read this file first, then `MEMORY.md`.

---

## Session 2026-04-20 (late) — Visual-polish sweep (LANDED)

User flagged four visible issues on rendered plates; all four addressed, all
415 tests green, all 17 plates validate clean, snapshots refreshed.

### 1. Corinthian capital line weights
Capital layers were being stroked uniformly, producing muddy black-mass
capitals at plate scale. Split into tiered weights by layer role:

| Layer | Weight | Role |
|---|---|---|
| silhouette | STROKE_MEDIUM | outline |
| abacus | STROKE_FINE | line |
| helices / fleuron | STROKE_ORNAMENT | line ornament |
| acanthus / caulicoli / bell_guides | STROKE_HATCH | tone |

Applied to `plate_corinthian.py`, `plate_corinthian_capital_detail.py`,
`plate_capitals_closeup.py`, `plate_composite.py`. At the smaller
`plate_five_orders.py` scale, HATCH is too thin — kept dense layers at
ORNAMENT as the floor.

### 2. Stair balusters now touch the handrail
`engraving/stairs.py`: baluster height was `handrail_height * 0.80` —
a 20% vertical gap between every baluster top and the handrail underside
(visible ~2-3mm per step). Replaced with
`bal_h = handrail_height - 0.35 * riser` so the top of each baluster
meets the sloped rail exactly at the baluster's x (the rail is 0.35·riser
higher above the tread at the baluster's offset back from the nosing).

### 3. Arcade has a ceiling
`plates/plate_arcade.py`: flipped `with_entablature=True`. The builder
already supported it and re-fits interior geometry; arches no longer hang
in the air.

### 4. Palazzo arches reach the floor (partial Phase 41 CSG)
`engraving/planner/solver.py` — `solve_openings()`: when a story's wall
is `"arcuated"` AND the opening is `arch_door` / `arch_window`, snap
`y_bottom` to `story.y_bottom`. This:
- Extends arch jambs down to the plinth — no floating arcs.
- Grows `void_footprint` to the full-height opening; the existing CSG
  subtraction in `WallElement.render_strokes` now carves the arch cleanly
  out of the rustication block pattern, so blocks no longer bleed through.

This is a **targeted** Phase 41 fix for the arcaded-wall case the user
reported. Broader Phase 41 (every opening kind in every wall variant
gets CSG'd consistently) is still open — see `plans/PRECISION_REFACTOR_BACKLOG.md`.

### Still open from the backlog

- **Phase 41 (broader CSG enforcement)** — extend the void-subtraction
  discipline to non-arcuated wall+opening combinations; audit every
  wall variant emits joints/blocks through `render_strokes` (which does
  the CSG), not bypassing it.
- **Phase 44** — hero plate composition (fill Doric/Ionic single-column plates).
- **Phase 45** — palazzo pilaster + window unification.
- **Phase 48** — proportion guard tests (measure shaft diameters from
  rendered element tree; assert column_h = 7/8/9/10/10·D etc.).
- **Phase 49** — propagate new discrete-lobe acanthus primitive to
  rinceau/festoons/cartouche.

---

## Phase 38 — Canonical Holm 12-centre Ionic volute (LANDED 2026-04-20)

Replaced the log-spiral Ionic volute with the canonical Holm 12-centre
construction used in Vignola/Scamozzi/ICAA plates. New public primitive
`engraving.volute.ionic_volute_holm(cx, cy, r_outer, r_eye, fillet_frac,
hand)` returns a 12-arc chain (~373 outer-spiral points, 32 samples/arc)
with centres staircasing inside the eye, ratio `rho = 0.84` tuned to
land the endpoint inside the eye after ~3 full revolutions (sweep ≈ 6π).
The legacy `ionic_volute(eye_cx, eye_cy, D, ...)` wrapper preserves the
dict contract used by `order_ionic`, `order_composite`, `order_greek_ionic`.
New tests in `tests/test_ionic_volute.py` (8); snapshots refreshed for
`plate_ionic`, `plate_composite`, `plate_greek_orders`, `plate_five_orders`,
`plate_five_orders_porticos` (and implicit `plate_capitals_closeup`).
Tests: 417 passed, 1 skipped. Audit: 24/24 plates pass.

---

## Phase 32 — Dimension annotations (LANDED 2026-04-20)

Classical plates are MEASUREMENT drawings — Vignola / McKim all labelled
every significant span. The output to date was bare silhouettes with no
dimension callouts; `plate_corinthian_capital_detail.py` had ad-hoc
leader lines + `page.text` calls instead of a real system. Phase 32
introduces `DimensionElement` as a first-class Element subclass plus
factory helpers `horizontal_dimension(...)` / `vertical_dimension(...)`.

Each `DimensionElement` emits (at hairline weight 0.12mm): two extension
lines, a parallel dimension line, two end ticks (style: `tick` / `arrow`
/ `slash`), and a centered SVG text label. Negative `offset_mm` flips
the callout to the opposite side; zero-length dimensions are silently
skipped so defensive callers don't crash.

Text rendering design choice: `render_strokes()` stays polyline-only
(every other element relies on that contract). DimensionElement exposes
a parallel `text_labels()` method; a `render_dimensions(page, root)`
helper walks a tree and emits both streams in one pass. No change to
`render.py`.

New:
- `engraving/planner/elements.py`: `DimensionElement`,
  `horizontal_dimension()`, `vertical_dimension()`, `render_dimensions()`
- `plans/PHASE_32_DIMENSIONS.md`: phase description + design rationale
- `tests/test_dimensions.py`: 10 new tests (strokes, labels, horizontal
  vs vertical placement, negative offset flip, zero-length handling,
  portico plate integration, tree-walk count)

Integrated into two plates:
- `plates/plate_corinthian_capital_detail.py` — replaced the ad-hoc
  leader-line + `page.text` pattern with 3 DimensionElements
  (`bell_h = 1·D`, `capital_h = 7/6·D`, `D`).
- `plates/plate_portico_plan.py` — added 3 DimensionElements
  (`column = 7·D`, `entablature = 1.75·D`, `colonnade_w` in mm).

Palazzo code, existing tests, existing Element subclasses, snapshot
tests, and the render module are all untouched.
Tests: 389 passed, 1 skipped (was 378/1).

---

## Phase 30 — Boathouse as a first-class declarative plan (LANDED 2026-04-20)

`BoathousePlan` is now a sibling of `FacadePlan` and `PorticoPlan`.
McKim-Mead-White boathouses (Harvard Newell, NYAC, Columbia archetype)
are declared as a bay count + bay kind + optional clerestory + required
`RoofPlan`; the solver derives every dimension from the canvas (no
hand-tuned mm in the plate file). The new `RoofElement` draws a gabled
shingle roof with deep eaves and exposed rafter tails.

New:
- `engraving/planner/plan.py`: `RoofPlan`, `BoathousePlan` dataclasses
- `engraving/planner/elements.py`: `BoathouseElement`, `RoofElement`
- `engraving/planner/solver.py`: `solve_boathouse()` raising
  `PlanInfeasible` when the canvas is too narrow / too short / cannot
  fit the bay+clerestory+gable stack
- `engraving/containment.py`: `roof` and `pediment` added to the
  sibling-non-overlap skip list (legitimate visual overlap)
- `plates/plate_boathouse_plan.py`: declarative 3-bay arched boathouse
  with 5-window clerestory, 22° gable, banded plinth
- `tests/test_boathouse_plan.py`: 22 new tests (RoofPlan validation,
  BoathousePlan validation, solver infeasibility, vertical-stack
  budget arithmetic, gable-slope geometry, tree containment, plate
  end-to-end)
- `plans/PHASE_30_BOATHOUSE.md`: phase description

Palazzo/portico code, existing plates, and the snapshot suite are
untouched.
Tests: 378 passed, 1 skipped.

Next candidate: cross-gabled / hip-roof boathouse variants, dormers,
exposed king-post trusses inside the boat bays.

---

## Phase 29 — Portico as a first-class declarative plan (LANDED 2026-04-20)

`PorticoPlan` is now a sibling of `FacadePlan`. Porticos (free-standing
classical colonnades crowned by an entablature and pediment) no longer
require hand-coded coordinates — declare order + column_count +
intercolumniation + optional pedestal/plinth/pediment and call
`plan.solve()` for a validated `Element` tree.

New:
- `engraving/planner/plan.py`: `PedimentPlan`, `PorticoPlan` dataclasses
- `engraving/planner/elements.py`: `PorticoElement`, `ColumnRunElement`,
  `PedestalCourseElement`, `PedimentElement`
- `engraving/planner/solver.py`: `solve_portico()`, raising
  `PlanInfeasible` when the canvas cannot fit the stack
- `plates/plate_portico_plan.py`: declarative tetrastyle Tuscan portico
  twin of the hard-coded `plates/plate_portico.py`
- `tests/test_portico_plan.py`: 18 new tests (slope validation,
  solver infeasibility, tree containment, end-to-end plate)
- `plans/PHASE_29_PORTICO.md`: phase description

Palazzo code, existing plates, and the palazzo snapshot are untouched.
Tests: 345 passed, 1 skipped.

Phase 30 followed: boathouse (`BoathousePlan`, `RoofPlan`,
`RoofElement`) — see entry above. Also see
`plans/SYSTEM_AUDIT_BUILDING_TYPES.md`.

---

## Phase 19 / 21 overhaul — current state (2026-04-19)

| Phase | Status | Summary |
|---|---|---|
| **Phase 19 Week 1 — Foundation** | COMPLETE | `engraving/element.py` (unified `Element` base), `engraving/containment.py` (HierarchicalContainment / SiblingNonOverlap / SharedEdge / CenteredInEnvelope / StackedSiblings / ProportionalSize), first-class bbox math. |
| **Phase 19 Week 2 — Planner** | COMPLETE | `engraving/planner/{plan,solver,elements,debug}.py`: `FacadePlan` / `StoryPlan` / `BayPlan` / `OpeningPlan` / `ParapetPlan` / `PilasterPlan` → `plan.solve()` returns a fully-resolved facade element tree with `PlanInfeasible` errors when constraints cannot be satisfied. |
| **Phase 19 Week 3 — Element enrichment + first plan-based plate** | COMPLETE | `engraving/elements/{arches,columns,entablatures}.py` wrap the legacy builders as Element subclasses. `plates/plate_palazzo_plan.py` is the first plate built entirely via the planner (3 stories, 5 bays, Ionic piano nobile, balustraded parapet). |
| **Phase 19 Week 4 — Aesthetic + CLI generate + debug overlay** | IN PROGRESS | `engraving/validate/aesthetic.py` emits `[A]` advisory warnings (the 19 warnings on palazzo_plan are advisory, not errors). `./ornament generate palazzo --bays … --piano-nobile-order …` wired. `./ornament debug <plate>` renders the scene-graph overlay with failed-constraint highlights. Remaining: tighten story↔string-course tiling so SiblingNonOverlap collapses to zero. |
| **Phase 21 Part 1 — CSG wall-clips-voids** | COMPLETE | Walls now carve out opening voids via boolean subtraction before stroking. No more rustication bands crossing window mullions. |
| **Phase 21 Part 2 — Material enum + auto-discovery** | IN PROGRESS | Material enum landed; plates now declare `material=Material.SMOOTH/BANDED/VERMICULATED/…` on wall elements. Auto-discovery of material-appropriate stroke sets is partway through — `smooth`, `banded`, `arcuated` wired; `rock_faced`, `vermiculated`, `chamfered` still use legacy paths. |
| **Phase 20 — Constraint-propagation solver** | PLANNED | Successor to Week 4. Will replace the current fixed-point planner with a proper constraint-propagation engine (AC-3 / arc consistency over interval domains). Deferred until Week 4 polish + Phase 21 material work lands. |

---

## Current validator status

Last run: 2026-04-19.

```
plates.plate_01              — 0 errors
plates.plate_blocking_course — 0 errors
plates.plate_portico         — 0 errors
plates.plate_doric           — 0 errors
plates.plate_ionic           — 0 errors
plates.plate_corinthian      — 0 errors
plates.plate_composite       — 0 errors
plates.plate_five_orders     — 0 errors
plates.plate_greek_orders    — 0 errors
plates.plate_schematic       — 0 errors
plates.plate_arcade          — 0 errors
plates.plate_cartouche       — 0 errors
plates.plate_stairs          — 0 errors
plates.plate_rinceau         — 0 errors
plates.plate_palazzo_v2      — 0 errors
plates.plate_palazzo_plan    — 0 errors (19 [A] aesthetic advisories — expected)
plates.plate_ornament        — 0 errors
plates.plate_grand_stair     — 0 errors

TOTAL: 0 hard errors across 18 plates
       (19 [A] advisories on palazzo_plan: SiblingNonOverlap tiling +
        HierarchicalContainment slight overshoot on bay_2 of story_1)
```

Run yourself: `.venv/bin/python scripts/validate_all_plates.py`

**Tests: 270 passed, 1 skipped** (optimize_svg skipped because vpype is optional).

---

## Current metrics (as of 2026-04-19)

```
Source files:
  engraving/           — 45 .py modules at top level
  engraving/elements/  — arches.py, columns.py, entablatures.py, _legacy.py (+ __init__)
  engraving/planner/   — plan.py, solver.py, elements.py, debug.py (+ __init__)
  engraving/validate/  — 8 files (orders, entablatures, elements, composition, motifs, plates, aesthetic + __init__)
  engraving/motifs/    — __init__.py + test_rosette.svg
  plates/              — 18 plate modules + __init__.py
  tests/               — 270 passing, 1 skipped
  scripts/             — validate_all_plates.py, build_book.py
  out/                 — 18+ rendered SVGs + PNG previews + engraving_book.pdf

Validator status: 0 hard errors across 18 plates (19 [A] aesthetic advisories on palazzo_plan)

Test suite: 270 passed, 1 skipped (vpype optional path)

Bound book: out/engraving_book.pdf (4083.0 KB, 18 pages)

CLI:
  ./ornament list                          # 18 plates surfaced
  ./ornament render <name>|--all
  ./ornament validate [name]|--all
  ./ornament book -o <output>
  ./ornament debug <name>                  # render scene w/ failed-constraint overlay
  ./ornament generate palazzo --bays N --piano-nobile-order {tuscan,doric,ionic,corinthian,composite}
```

---

## Snapshot (TL;DR)

| | Status |
|---|---|
| **Foundation** (geometry, render, preview, canon) | Done |
| **5 classical orders** (silhouettes + entablatures) | Done |
| **Facade primitives** (arches, windows, balustrades, pilasters, 6-variant rustication) | Done |
| **Facade composition** (Story / Bay / Opening) | Done |
| **Plates** (18 total; palazzo_v2 + palazzo_plan are the heroes) | Done |
| **Geometric acanthus** | Done |
| **Line-weight hierarchy + polish** | Done |
| **Phase 5 — Validation library** | Done — 8 modules, 270 tests |
| **Phase 6 — Structural bug cleanup** | Done |
| **Phase 7 — Motif plugin system** | Foundation — hand-drawn SVGs still pending user |
| **Phase 8 — Typography + cartouche** | Done |
| **Phase 9 — Additional architectural types** | Done |
| **Phase 10 — Ornament expansion** | Done |
| **Phase 11 — Export pipeline** | Done |
| **Phase 12 — CLI + plate catalog** | Done — 18 plates surfaced |
| **Phase 13 — Figure ornament + regional variants** | Future |
| **Phase 14 — Visual layout polish** | Done |
| **Phase 17 — Scene validation** | Done |
| **Phase 19 Week 1-3 — Overhaul foundation + planner + first plan-based plate** | Done |
| **Phase 19 Week 4 — Aesthetic + CLI generate + debug overlay** | In progress |
| **Phase 20 — Constraint-propagation solver** | Planned |
| **Phase 21 Part 1 — CSG (wall clips voids)** | Done |
| **Phase 21 Part 2 — Material enum + auto-discovery** | In progress |

---

## Module inventory

### `engraving/` (45 top-level modules)

Core + orders + facade:
- canon, geometry, render, preview, profiles, hatching, stippling
- orders, order_doric, order_ionic, order_corinthian, order_composite
- order_greek_doric, order_greek_ionic
- entablature_doric, entablature_ionic, entablature_corinthian
- arches, balustrades, borders, facade, fluting, pilasters, rustication, windows, volute
- acanthus, ornament
- arcade, cartouche, typography, cli, export, festoon, medallion, plugins, rinceau, schema, stairs, trophy
- **scene, scene_constraints** (Phase 17)
- **element** (Phase 19 Week 1 — unified Element base)
- **containment** (Phase 19 Week 1 — containment primitives)

### `engraving/elements/` (Phase 19 Week 3)

- `__init__.py`
- `arches.py` — Arch / ArchDoor / ArchWindow Element subclasses
- `columns.py` — Column Element subclass (wraps order silhouettes)
- `entablatures.py` — Entablature Element subclasses (Doric / Ionic / Corinthian / Composite)
- `_legacy.py` — back-compat wrappers over the old ElementResult-returning builders

### `engraving/planner/` (Phase 19 Week 2)

- `__init__.py`
- `plan.py` — FacadePlan / StoryPlan / BayPlan / OpeningPlan / ParapetPlan / PilasterPlan dataclasses
- `solver.py` — Fixed-point solver; resolves ratios → mm, tiles children, propagates envelopes
- `elements.py` — Plan → Element tree materialization
- `debug.py` — Debug overlay: renders each element's envelope outline + marks failed constraints in red

### `engraving/validate/` (8 files)

- `__init__.py`
- `orders.py`
- `entablatures.py`
- `elements.py`
- `composition.py`
- `motifs.py`
- `plates.py`
- `aesthetic.py` (Phase 19 Week 4 — emits `[A]` advisories for non-fatal composition issues)

### `engraving/motifs/` (plugin package)

- `__init__.py`
- `test_rosette.svg` (user-authored hand-drawn SVGs still pending in Inkscape)

### `plates/` (19 files — 18 user-facing plates + __init__.py)

- plate_01
- plate_arcade
- plate_blocking_course
- plate_cartouche
- plate_composite
- plate_corinthian
- plate_doric
- plate_five_orders
- plate_grand_stair
- plate_greek_orders
- plate_ionic
- plate_ornament
- **plate_palazzo_plan** (Phase 19 Week 3 — first plan-based plate)
- plate_palazzo_v2
- plate_portico
- plate_rinceau
- plate_schematic
- plate_stairs

---

## Project in one paragraph

Python-only pipeline generating 18th-century-style engraved architectural plates at 1:1 print size (SVG with mm dimensions). Output is printed on paper → transferred to steel → hand-engraved by the user. Stack: shapely, drawsvg, numpy, scipy, fonttools, playwright. Python 3.14.4 in `.venv/`. No Rhino, no commercial CAD — explicitly rejected. Plate size: 10×8" landscape (254 × 203.2 mm). Stroke hierarchy: 0.35 medium silhouettes, 0.25 fine rules, 0.18 hairline/ornament, 0.12 hatch.

End-goal: generate schematic building elevations (3-story palazzo, portico, Dury-Carondelet-style facades) that the user can print and engrave by hand. The Phase 19 overhaul converts the system from "hardcoded coordinates hoping to validate" to "declare intent (plan), system solves positions with constraint guarantees."

---

## Visual state (spot checks)

- **plate_palazzo_plan** (new, plan-based): 3-story, 5-bay Ionic palazzo generated entirely from `FacadePlan.solve()`. 19 [A] aesthetic advisories (SiblingNonOverlap tiling, 2.7mm overshoot on bay_2 of story_1) — non-fatal, targeted for Week 4 polish.
- **plate_palazzo_v2**: Hero plate (hand-composed). Clean 3-story composition with rusticated arcade ground, Ionic piano nobile, balustraded parapet.
- **plate_five_orders**: Typography title outlined. All 5 columns read correctly.
- **plate_grand_stair / plate_stairs**: 12-step flight with Tuscan balusters and continuous handrail.
- **plate_arcade**: Rhythmic bay composition; Phase 14 impost-spring fix held.
- **plate_greek_orders**: Greek Doric + Greek Ionic side-by-side.

---

## Known issues — still open

| Issue | Where | Status |
|---|---|---|
| palazzo_plan SiblingNonOverlap advisories (wall↔bay tiling at 0.000mm overlap) | `planner/solver.py` | Phase 19 Week 4 — in progress |
| palazzo_plan bay_2 of story_1 overshoots envelope by 2.735mm | `planner/solver.py` (bay-height distribution) | Phase 19 Week 4 — in progress |
| Phase 21 Part 2: rock_faced / vermiculated / chamfered materials still use legacy stroke paths | `rustication.py` | Phase 21 Part 2 — in progress |
| Ionic volute not strict Vignola 12-center | `volute.py` | Documented tradeoff |
| Acanthus parametric default | `acanthus.py` + `plugins.py` | Plugin system primed for hand-drawn override |
| Scotia wobble on Attic base (5-orders plate) | `order_*.py` base | Open — minor, not caught by validator |

---

## Long-term roadmap

### Phases 5-14, 17 — DONE
See Snapshot above.

### Phase 19 — Constraint-first overhaul (IN PROGRESS)
- Week 1 (Foundation): DONE — `Element` base class, containment primitives
- Week 2 (Planner): DONE — `FacadePlan.solve()` returns element tree
- Week 3 (Element enrichment + first plan-based plate): DONE — `plates/plate_palazzo_plan.py`
- Week 4 (Aesthetic + CLI + cleanup): IN PROGRESS — tighten tiling to eliminate `[A]` advisories; `./ornament generate palazzo`; `./ornament debug <plate>`

### Phase 20 — Constraint-propagation solver (PLANNED)
Successor to Week 4. Replace fixed-point planner with AC-3 over interval domains.

### Phase 21 — CSG overhaul
- Part 1 (wall clips voids): DONE
- Part 2 (Material enum + auto-discovery): IN PROGRESS

### Future
- Domes, vaults, towers
- Plan + section views
- Interior features (wainscoting, overmantels, door surrounds)
- Vision-in-the-loop for aesthetics

---

## Quick-reference commands

```bash
# Activate
cd /Users/choehn/Projects/ornament-vector-drawing && source .venv/bin/activate

# Full test suite
.venv/bin/python -m pytest tests/ -v

# Validate all plates end-to-end
.venv/bin/python scripts/validate_all_plates.py

# Build bound-book PDF of all plates
.venv/bin/python scripts/build_book.py

# CLI
./ornament list
./ornament render palazzo-plan
./ornament validate
./ornament book
./ornament debug palazzo-plan
./ornament generate palazzo --bays 5 --piano-nobile-order ionic --ground-wall arcuated --parapet balustrade -o out/my_palazzo.svg --preview

# Render and preview a single plate
.venv/bin/python -m plates.plate_palazzo_plan
.venv/bin/python -m engraving.preview out/plate_palazzo_plan.svg out/plate_palazzo_plan.png 200
```

---

## Snapshot tests (Phase 25 Day 2)

Byte-snapshot regression tests guard every plate against silent visual
drift. Each plate is rendered, the SVG canonicalized (whitespace
stripped, comments removed), and SHA-256 hashed. The hash is stored in
`tests/snapshots/<plate>.sha256`. A subsequent run that produces a
different hash fails with a diff pointing at the offending plate —
catching the kind of 1-mm refactor slip that validators miss.

```bash
# Run the byte-snapshot suite (fast — ~2s for all 18 plates)
.venv/bin/python -m pytest tests/test_plates_snapshot.py -v

# Refresh snapshots when a visual change is intentional
scripts/refresh_snapshots.sh
# (then review `git diff tests/snapshots/` and commit)
```

First-time snapshots are auto-created and the test is skipped; commit
the new `.sha256` file. From then on, the test fails on any rendered-
output change, forcing the author to either fix the regression or
consciously refresh the snapshot.

---

## References (project root)

- `americanvignola01wareuoft.pdf` — Ware's *American Vignola* (1903). Text-extractable. Primary source for `canon.py`.
- `Drawing_Acanthus.pdf` — Page's 1886 *Guide for Drawing the Acanthus*. Image-only. Used for acanthus.py rewrite.

## External references

- `/tmp/volute_ref.png` — Holm / ICAA Ionic volute 12-center diagram

## Memory files (at `~/.claude/projects/-Users-choehn-Projects-ornament-vector-drawing/memory/`)

All pointers in `MEMORY.md` there. Key ones:
- `user_profile.md` — hand engraving as a craft
- `feedback_no_gui_tools.md` — no Rhino, no GUI, pip-installable only
- `feedback_print_ready.md` — 1:1 mm, never scale
- `feedback_line_weights.md` — design feedback from the polish pass
- `project_plate_spec.md` — 10×8" landscape, mm units
- `project_order_defaults.md` — Scamozzi for Composite, Vignola 12-center for Ionic volute
- `project_acanthus_caveat.md` — parametric acanthus is accepted imperfect
- `project_validation_plan.md` — Phase 5 validation library shipped
- `reference_ware_vignola.md`, `reference_acanthus_guide.md`, `reference_volute_construction.md` — primary sources

---

## First actions on session restart

1. Read `plans/HANDOFF.md` (this file) and `MEMORY.md`.
2. Sanity: `.venv/bin/python -m pytest tests/` (expect `415 passed, 1 skipped`).
3. `.venv/bin/python scripts/validate_all_plates.py` (expect `0 errors across 17 plates`).
4. `./ornament list` (expect 17 plates — `plate_palazzo_v2` was removed in Phase 40).

**Next-focus candidates (pick one):**

- **Phase 41 broader CSG enforcement** — today's session fixed the
  arcuated+arch case in `solve_openings`. Audit remaining combinations:
  rock_faced/vermiculated/chamfered walls with rectangular windows,
  smooth walls with cornice-hood windows, upper-story arch_windows (which
  should keep their sill — do NOT accidentally grab the "arcaded" branch).
- **Phase 44 hero plates** — single-order Doric/Ionic plates currently
  read empty; add pedestal + base-line + scale-of-modules column.
- **Phase 45 palazzo pilaster/window unification** — pilaster elements
  and window surrounds are built by different code paths; unify so
  they share the Material/CSG discipline.
- **Phase 48 proportion guard tests** — measure shaft diameters off the
  rendered element tree; assert column_h / entablature_h ratios per order.
- **Phase 49 acanthus propagation** — regenerate rinceau/festoon/
  cartouche with the Phase 42 discrete-lobe acanthus primitive so the
  ornament plates don't read as sawblades.

Any questions? Start a dialogue rather than guess.
