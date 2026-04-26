# Major Overhaul Plan — Constraint-First Architectural Generation

Session: 2026-04-19. Status: proposed, not yet executed.

## Why an overhaul is needed

The current system has the right idea but the wrong shape. We have:

- **Builders** that emit polylines + optional `ElementResult` metadata
- **Validators** that check a node's metadata against canon
- **Scene graph** that expresses hierarchy but isn't populated consistently
- **Constraints** layered on top — tactical predicates checking one relation at a time
- **Plates** that declare raw coordinates and hope it all lines up

Result: the validators pass with 0 errors, but the actual render shows ground-floor arches overlapping the piano nobile. The system checks what I asked it to check, not what matters.

The root cause is that **generation and validation are disconnected**. The plate says "arch height = 0.68 × story_height" and hopes; rustication.wall then draws arches at its own height; nobody checks the rendered bbox against the story envelope. The validators I added check bay axes and symmetry but not "every child fits in its parent."

**The overhaul's thesis:** build a system where you declare *intent* (a 3-story palazzo with Ionic piano nobile) and the system *computes* positions such that every constraint is mathematically satisfied — or reports a specific violation before rendering. Generation, validation, and rendering all operate on the same scene tree with the same bbox math.

---

## The five parts

### Part 1 — Unified `Element` base class

Every architectural thing (column, arch, window, pilaster, story, bay, facade, balustrade) inherits from one base:

```python
@dataclass
class Element:
    """The unit of architectural geometry. Every element has a declared
    envelope it must render inside, named anchors, children, and a
    contribution to the final SVG."""

    id: str                            # path-style, unique in scene
    kind: str                          # element type
    envelope: BBox                     # WORLD-coordinate bbox the element MUST fit inside
    anchors: dict[str, Anchor]         # exposed connection points
    children: list["Element"]          # nested elements (composition)
    parent: "Element | None"

    # Each element renders itself AND declares its effective bbox.
    def render(self) -> list[Polyline]: ...
    def effective_bbox(self) -> BBox: ...   # tightest box covering self + children

    # Every element can be asked: "does your effective bbox fit your envelope?"
    def check_containment(self) -> list[str]: ...
```

This replaces both `ElementResult` (the metadata-returning thing) and ad-hoc dicts. Everything returns an `Element`, which can be asked to render, validate, or expose anchors.

**Migration:** existing builders (`tuscan_column_silhouette`, `corinthian_entablature`, `arcade`, `cartouche`) wrap into `Element` subclasses. Backward-compat shims keep the old APIs working.

### Part 2 — Containment-first constraint system

Before any constraint check, **every parent-child relation is verified:**

```python
class HierarchicalContainment:
    """THE backbone rule. For every element e with parent p:
        e.effective_bbox ⊆ p.envelope  (with tol)
    Violations are reported with exact overshoot mm.
    
    Runs BEFORE any other constraint. If it fails, stop."""
```

Additional mathematical primitives:

- `SiblingNonOverlap(parent)` — children of the same parent don't overlap each other in any axis except explicitly declared
- `SharedEdge(a, b, edge)` — two elements share a common edge (e.g., story's top = next story's bottom)
- `CenteredInEnvelope(child, parent)` — child centered on parent's axis
- `StackedSiblings(parent, axis)` — children tile along the axis with no gaps or overlaps
- `ProportionalSize(element, parent, ratio_range)` — element's size is within a ratio of parent's

Architectural constraints stay as they are (SuperpositionOrder, KeystoneOverDoor, etc.) but now they operate on `Element` objects.

### Part 3 — The Planner / Layout Solver

**Today:** the plate code hard-codes coordinates, then tries to validate.

**After overhaul:** the plate code declares a plan — "3 stories, ratio 1:1.4:0.85, Ionic piano nobile, 5 bays, central door bay wider" — and a **Planner** computes coordinates:

```python
@dataclass
class FacadePlan:
    """Declarative intent. The Planner turns this into an Element tree."""
    canvas: BBox
    stories: list[StoryPlan]          # ordered bottom-to-top
    bays: list[BayPlan]
    parapet: ParapetPlan | None
    
    def solve(self) -> Element:
        """Return a fully-laid-out Element tree where every containment
        constraint is satisfied by construction.
        
        Raises PlanInfeasible if the canvas is too small, story ratios
        don't sum cleanly, etc."""


@dataclass
class StoryPlan:
    height_ratio: float               # relative to other stories; normalized by planner
    wall: str                          # "smooth", "arcuated", etc.
    order: str | None                  # "ionic", etc., for ordered stories
    min_height_mm: float = 0           # hard floor; planner fails if budget can't afford


@dataclass
class BayPlan:
    axis_kind: Literal["regular", "door", "window"]
    openings: list[OpeningPlan]       # one per story, top-to-bottom? or bottom-to-top? (pick one and document)


@dataclass
class OpeningPlan:
    kind: Literal["arch_window", "arch_door", "window", "niche", "blank"]
    width_frac: float                  # fraction of bay_pitch (not raw mm)
    height_frac: float                 # fraction of story_height
    hood: str = "none"
    has_keystone: bool = False
```

The planner computes:
1. Story heights from height_ratio × available canvas, honoring min_height_mm
2. Bay pitch = canvas.width / bay_count
3. Each opening's actual mm size = (width_frac × bay_pitch, height_frac × story_height)
4. Each opening's position within its bay/story
5. Each pilaster/string-course's envelope
6. Builds the Element tree

Then **before returning** it runs every `HierarchicalContainment` check. If anything fails, raise `PlanInfeasible` with the specific violation.

This is the key move: **generation refuses to produce invalid geometry**. No more "passed validation but visually broken."

### Part 4 — Renderer walks the tree

Plates become:

```python
def build_validated():
    plan = FacadePlan(
        canvas=BBox(margin, top, facade_w, floor),
        stories=[
            StoryPlan(height_ratio=1.0, wall="arcuated", min_height_mm=45),
            StoryPlan(height_ratio=1.4, wall="smooth", order="ionic"),
            StoryPlan(height_ratio=0.85, wall="smooth"),
        ],
        bays=[BayPlan(axis_kind="window", openings=[
            OpeningPlan(kind="arch_window", width_frac=0.52, height_frac=0.68),
            OpeningPlan(kind="window", width_frac=0.42, height_frac=0.62, hood="triangular"),
            OpeningPlan(kind="window", width_frac=0.32, height_frac=0.50, hood="cornice"),
        ]) for _ in range(5)],
        parapet=BalustradedParapet(height_ratio=0.25),
    )
    # Central bay gets wider door treatment
    plan.bays[2].openings[0] = OpeningPlan(kind="arch_door", width_frac=0.72, height_frac=0.82)
    
    element_tree = plan.solve()        # raises if infeasible
    
    page = Page()
    frame(page)
    for polyline, weight in element_tree.render_strokes():
        page.polyline(polyline, stroke_width=weight)
    
    # Post-render: run non-containment constraints (symmetry, triglyph-over-column, etc.)
    report = element_tree.validate()
    
    return page.save_svg(...), report
```

Plate code is **declarative**, not imperative. The plate describes what a palazzo *is*, not how to draw it.

### Part 5 — Layered constraint library

Three layers:

**Layer A: Mathematical invariants (always on, checked at plan time)**
- HierarchicalContainment — every child in its parent's envelope
- SiblingNonOverlap — no overlap in x-axis within same story
- AnchorContinuity — stacked elements share edges (story.top = story_above.bottom)
- PositivityOfDims — no negative heights, no inside-out bboxes

**Layer B: Classical canon (checked at plan time, can be relaxed)**
- CanonicalProportions (per order) — column_D, entablature_D, etc. match Ware
- ClassicalHierarchy — opening widths descend going up; piano nobile tallest
- SuperpositionOrder — Tuscan/Doric/Ionic/Corinthian bottom to top
- SymmetryAboutCenter — bilateral facade rules

**Layer C: Aesthetic rules (checked at render time, advisory)**
- StrokeWeightHierarchy — silhouette > fine > ornament > hatch
- MinimumFeatureAtScale — volute eye ≥ 1mm at plate scale
- DetailDensityUniform — hatch spacing consistent across a surface

Each layer has its own mode: `strict` (raise), `report` (collect), `advisory` (log). The plate can tune which layers to enforce.

---

## Implementation plan

Five waves, ~5 hours each. Each wave delivers a working subset; the old system keeps running until the last wave.

### Wave 1 — `Element` base + containment backbone (5 hr)

- `engraving/element.py` — `Element` base class
- `engraving/containment.py` — `HierarchicalContainment`, `SiblingNonOverlap`, `AnchorContinuity`, `PositivityOfDims`
- Wrap one existing builder (e.g. `semicircular_arch`) as an `Element` subclass to prove the pattern
- Tests: deliberately-violating element trees raise specific errors

### Wave 2 — `Planner` + `FacadePlan` (5 hr)

- `engraving/planner.py` — `FacadePlan`, `StoryPlan`, `BayPlan`, `OpeningPlan`, `FacadePlan.solve()`
- Planner's job: distribute canvas height across stories per ratios, compute bay pitch, compute opening mm sizes from fractions, build Element tree, run Layer A checks
- `PlanInfeasible` exception with actionable messages
- Test: feasible plan produces valid tree; infeasible plans raise with correct reason

### Wave 3 — Migrate `plate_schematic.py` and `plate_palazzo_v2.py` (5 hr)

- Rewrite both plates as declarative `FacadePlan` instances
- Render via `element_tree.render_strokes()`
- Verify renders look equivalent or BETTER than current (and that arches no longer overlap piano nobile, because containment would have refused to build that)
- Keep old code paths as `*_legacy.py` for side-by-side comparison

### Wave 4 — Migrate remaining plates + element types (6 hr)

- Wrap column silhouettes (`tuscan_column_silhouette` etc.) as `ColumnElement` subclasses
- Wrap entablatures, arcades, windows, pilasters, balustrades
- Migrate plate_portico, plate_corinthian, plate_arcade, plate_palazzo_v2 etc.
- Each plate becomes a declarative plan

### Wave 5 — Layered constraint library + debug overlay refresh (4 hr)

- Organize existing architectural constraints into Layer B
- Add aesthetic-rule Layer C (stroke weights, min feature size)
- Refresh `Scene.render_debug()` to paint Layer A violations red, Layer B orange, Layer C blue
- Add a `plan.explain()` method that prints human-readable summary: "Story 1 has 5 bays at 45 mm on-centers, each 26 mm clear span, arches 13 mm rise"

---

## What gets deprecated

- `ElementResult.add_polylines/add_anchor/compute_bbox` — replaced by `Element` base methods
- Ad-hoc dict returns from `semicircular_arch`, `window_opening`, `wall`, etc. — all become `Element` subclasses
- Hand-coded bay coordinates in plates — replaced by declarative plans
- The current `Facade.to_scene()` bridge — no longer needed; plans build scenes directly
- Tactical predicates that duplicate containment checks — pruned

All deprecated paths stay working via shims until Wave 5 is complete.

---

## What this solves

| Current problem | How the overhaul solves it |
|---|---|
| Ground arches overlap piano nobile | `HierarchicalContainment` on arch-element catches overshoot at plan time — plan fails before rendering |
| Pilasters render past story floor | Same — pilaster's envelope is its story's bbox, so any overshoot is a hard error |
| Validators pass, renders still wrong | Generation and validation share the same scene tree; can't render invalid geometry |
| Opening widths uniform across stories | `ClassicalHierarchy` check in Layer B; plan refuses to solve if violated |
| No visible piano nobile pilasters | Pilaster elements declared in the plan are rendered or explicitly absent — no silent omission |
| Stories blur into each other (no string course) | String course is a mandatory `SharedEdge` between adjacent stories |
| Scene constraints wired inconsistently | Every plate goes through the planner → same constraint set always applies |
| Pediment hoods oversized | `ProportionalSize(hood, opening, [0.3, 0.6])` enforces reasonable ratios |
| Composite volute zone math weird | Element subclasses declare their own sub-element envelopes; volute has a real, explicit envelope |

---

## What this does NOT solve

- **Aesthetic taste** — this doesn't give us prettier acanthus; parametric ornament still looks parametric
- **Unknown architectural rules** — it enforces the rules we've codified; rules I haven't thought of still slip through
- **3D / side facade consistency** — single-facade only in v1; z-axis support is future work
- **Figure ornament** — putti, human figures still need a hand-drawn motif library

---

## Acceptance tests for the overhaul

When Wave 5 lands, these should all pass:

```python
def test_invalid_palazzo_refuses_to_render():
    """A facade where stories don't sum cleanly should fail BEFORE rendering."""
    plan = FacadePlan(
        canvas=BBox(0, 0, 200, 100),
        stories=[StoryPlan(height_ratio=1.0, min_height_mm=150)],  # can't afford
    )
    with pytest.raises(PlanInfeasible, match="insufficient height"):
        plan.solve()


def test_arches_cannot_overflow_ground_story():
    """Arches whose full rise exceeds the ground story height are rejected."""
    plan = FacadePlan(
        canvas=BBox(0, 0, 300, 200),
        stories=[StoryPlan(height_ratio=0.3, wall="arcuated")],  # very short
        bays=[BayPlan(openings=[
            OpeningPlan(kind="arch_window", width_frac=0.8, height_frac=1.2),  # too tall
        ])],
    )
    with pytest.raises(PlanInfeasible, match="arch_window.*extends.*story"):
        plan.solve()


def test_plate_schematic_renders_valid():
    """The current schematic, rewritten as a plan, produces a render with
    zero Layer A violations (no element extends past its container)."""
    from plates.plate_schematic import build_validated
    svg_path, report = build_validated()
    # Layer A must be empty — containment is inviolable
    assert not any(e.layer == "A" for e in report.errors)


def test_opening_hierarchy_enforced():
    """A plan where upper story has wider windows than ground is rejected."""
    plan = FacadePlan(..., bays=[BayPlan(openings=[
        OpeningPlan(kind="arch_window", width_frac=0.3, height_frac=0.5),
        OpeningPlan(kind="window", width_frac=0.5, height_frac=0.5),  # wider than below
    ])])
    with pytest.raises(PlanInfeasible, match="ClassicalHierarchy"):
        plan.solve()
```

---

## Multi-week schedule

Four weeks, ~15-20 hours each. Each week delivers a coherent subset that can be paused at a clean state without breaking existing plates.

---

### WEEK 1 — Foundation and containment

**Goal:** a working `Element` base class with rigorous `HierarchicalContainment`. Existing builders wrapped but plates still render via legacy paths.

**Day 1 — `Element` base + primitives**
- `engraving/element.py` — `Element`, `Envelope`, `Anchor` (unified with existing `schema.Anchor`), `render_strokes()`, `effective_bbox()`, `check_containment()`
- Backward-compat: `Element.from_element_result(result)` wraps legacy `ElementResult`
- Tests: synthetic elements with explicit bboxes, containment passes/fails detected

**Day 2 — `HierarchicalContainment` + siblings**
- `engraving/containment.py` — `HierarchicalContainment`, `SiblingNonOverlap`, `AnchorContinuity`, `PositivityOfDims`
- Tree walker: `validate_tree(root) -> list[Violation]`
- Structured `Violation` objects with `element_id`, `parent_id`, `axis`, `overshoot_mm` (not just string messages)
- Tests: each constraint has a pass test and a fail test with exact-error-message assertions

**Day 3 — Wrap `semicircular_arch` and `segmental_arch`**
- `engraving/elements/arches.py` — `ArchElement` subclass
- `ArchElement.effective_bbox()` correctly reports the FULL arch bbox (including voussoir ring, impost, keystone projection)
- Test case the user flagged: "ArchElement with h_frac=0.68 of story_h=35mm reports effective_bbox that EXCEEDS 35mm because the semicircle adds w/2 rise" → containment check fires correctly
- Deliverable: a test that FAILS today but PASSES with the Element wrapper (proving the regression is caught)

**Day 4 — Wrap column silhouettes**
- `engraving/elements/columns.py` — `ColumnElement` with order-specific subclasses (TuscanColumn, DoricColumn, IonicColumn, CorinthianColumn, CompositeColumn)
- Each wraps the existing builder and exposes its effective_bbox
- Test: column envelope declared at `(cx-r_lo, base_y-col_h, cx+r_lo+abacus_project, base_y)` triggers containment if the capital's actual abacus exceeds the projection

**Day 5 — Wrap entablatures + integration test**
- `engraving/elements/entablatures.py` — `EntablatureElement` and order-specific subclasses
- End-to-end test: build a mini scene with a pedestal, column, entablature, wrap them in Elements, assert containment passes
- Wave 1 ACCEPTANCE: `pytest tests/test_overhaul_wave1.py` passes; all existing plates still render and their tests still pass

**Risk mitigation (Week 1):**
- `Element.render_strokes()` returns the SAME polylines the legacy path produces (byte-for-byte compatible). Verified by rendering test plates via both paths and diffing.

---

### WEEK 2 — Planner and layout solver

**Goal:** declarative `FacadePlan` that solves canvas allocation and produces a valid Element tree.

**Day 6 — Plan dataclasses**
- `engraving/planner/plan.py` — `FacadePlan`, `StoryPlan`, `BayPlan`, `OpeningPlan`, `ParapetPlan`, `PilasterPlan`, `EntablaturePlan`
- Each has validation (positive ratios, valid order names, etc.)
- `PlanInfeasible` exception with structured `reason` + `element_id` + `suggested_fix` fields

**Day 7 — Story height solver**
- Given `canvas.height`, a list of `StoryPlan`s with `height_ratio` and optional `min_height_mm`, compute actual mm heights
- Handle: normalized ratios, floor constraints, infeasibility detection
- Tests: equal ratios divide evenly; `min_height_mm` floor violates when canvas too small; degenerate cases (zero stories, single story)

**Day 8 — Bay distribution + opening sizing**
- `bay_pitch = canvas.width / bay_count`
- Per-opening mm sizing from `width_frac × bay_pitch`, `height_frac × story_height`
- Tests: 5 bays in 250mm canvas → pitch=50; openings at frac=0.52 → 26mm wide

**Day 9 — Arch rise + containment pre-check**
- Special handling for arched openings: rise = span/2 for semicircular; total vertical = height_frac × story_h + rise (if arch rises above the rectangular portion)
- Pre-check: if total_vertical > story_h, raise `PlanInfeasible` BEFORE building the Element
- This is the fix for the "arches overlap piano nobile" bug

**Day 10 — Plan → Element tree**
- `FacadePlan.solve() -> FacadeElement` — populates the full tree with correctly-sized children
- Runs `HierarchicalContainment` post-build as a double-check
- Tests: deliberately-infeasible plans raise `PlanInfeasible`; feasible plans produce valid trees with zero violations

**Wave 2 ACCEPTANCE:**
- `pytest tests/test_planner.py` passes
- Can instantiate a 3-story palazzo plan and solve it without any containment violations
- Renders produced via `plan.solve().render_strokes()` are visually similar to current plate_schematic but with no arch overflow

**Risk mitigation (Week 2):**
- Plans are data. Easy to unit-test independently of rendering.
- Infeasibility detection is synchronous — never silently succeeds.

---

### WEEK 3 — Plate migration + architectural constraints

**Goal:** every existing plate rewritten as a declarative plan. Legacy paths still available for comparison.

**Day 11 — Migrate plate_schematic**
- New `plates/plate_schematic_v2.py` alongside the legacy
- Same visual output as target, but via `FacadePlan`
- No containment violations; arches confined to ground story

**Day 12 — Migrate plate_palazzo_v2**
- Same pattern
- Integrates an `ArcadePlan` (sub-plan for the arcade-ground variant)

**Day 13 — Migrate order plates (portico, doric, ionic, corinthian, composite, greek_orders, five_orders)**
- These are simpler — single columns with entablatures
- Create `ColumnPlatePlan` for one- or two-column order plates

**Day 14 — Migrate everything else (blocking_course, arcade, cartouche, stairs, rinceau, ornament, grand_stair)**
- Each gets its own plan type, all inheriting from a common `PlatePlan` base
- Registry so the CLI surfaces all of them

**Day 15 — Architectural constraints (Layer B)**
- Port `SuperpositionOrder`, `KeystoneOverDoor`, `ColumnsUnderPediment`, `WindowAxesAlignAcrossStories`, `RusticationCoursesAlign`, `TriglyphOverEachColumn`, `StylobateUnderColumns`, `IntercolumniationConsistent`
- Each rewritten to operate on `Element` objects with structured `Violation` outputs
- Test: each constraint has canonical pass/fail cases

**Wave 3 ACCEPTANCE:**
- All 16 plates migrated
- Side-by-side visual diff shows v2 equal or better than v1 for every plate
- Legacy `plate_*_legacy.py` still runs for historical comparison
- `scripts/validate_all_plates.py` runs on v2 plates and reports 0 Layer A + B violations

---

### WEEK 4 — Aesthetic rules, debug overlay, cleanup

**Goal:** ship the full system, remove legacy code, refresh documentation.

**Day 16 — Aesthetic constraint layer (Layer C)**
- `StrokeWeightHierarchy` — silhouette > fine > ornament > hatch, enforced per element class
- `MinimumFeatureAtScale(plate_dpi)` — smallest visible feature ≥ N pixels
- `DetailDensityUniform` — hatch spacing consistent per surface
- These run at render time with `advisory` severity by default

**Day 17 — Debug overlay refresh**
- `Element.render_debug(source_svg) -> debug_svg` walks the tree, paints Layer A violations red, Layer B orange, Layer C blue
- CLI: `./ornament debug <plate>` outputs both a regular render and a debug render side-by-side
- `plan.explain()` prints a human-readable plan summary

**Day 18 — Procedural generation catalog**
- `./ornament generate palazzo --bays 7 --piano-nobile-order corinthian --output out/custom.svg`
- Parameterized plate catalog: user passes intent, system generates
- Dozens of valid palazzi producible from a small set of plans

**Day 19 — Legacy removal**
- Delete `plate_*_legacy.py` files
- Remove deprecated `ElementResult.add_polylines`, `Facade.to_scene()`, old `Scene.validate()` path (since plans now validate intrinsically)
- Clean up tests; remove outdated regressions
- Remove ~1500 lines of dead code

**Day 20 — Docs + HANDOFF refresh**
- `plans/OVERHAUL.md` → `plans/ARCHITECTURE.md` (the overhaul is now THE architecture)
- Update `plans/HANDOFF.md` to reflect new system
- Add `docs/ADDING_NEW_ELEMENT.md` for future plate authors
- Final rendering pass — produce the bound book PDF at production quality

**Wave 4 ACCEPTANCE:**
- All four acceptance tests in the main plan pass
- 18+ plates render via plans
- No legacy imperative coordinate code remains
- Book PDF ~500KB, 16+ pages, 1:1 mm
- New documentation covers how to add an element and how to author a plate

---

### Schedule summary

| Week | Theme | Hours | Deliverable |
|---|---|---|---|
| 1 | Foundation + containment backbone | 15-20 | `Element` + `HierarchicalContainment`; arches/columns/entablatures wrapped |
| 2 | Planner / layout solver | 15-20 | `FacadePlan` with infeasibility detection before rendering |
| 3 | Migrate every plate to declarative plans | 18-22 | All 16 plates via plans; Layer B constraints ported |
| 4 | Aesthetic layer, debug, cleanup, docs | 15-18 | Production-ready system; legacy code removed |
| **Total** | | **~75 hours** | Constraint-first architectural generation pipeline |

---

### Parallelism opportunities

Waves aren't strictly sequential. Within each week, many days can run in parallel via agents:

- **Week 1:** Days 1–2 sequential, then 3/4/5 parallel (different element types)
- **Week 2:** Days 6–7 sequential, then 8/9 parallel, then 10 (integration)
- **Week 3:** Days 11/12/13/14 mostly parallel (plate migrations are independent); Day 15 separate
- **Week 4:** Days 16/17/18 parallel; 19/20 sequential

Realistic calendar: 4 calendar weeks assuming ~15 agent-hours per week of focused work and some rate-limit spread.

---

### Milestones visible to the user

1. **End of Week 1:** "containment bug the user flagged" can no longer ship — the tree rejects invalid geometry
2. **End of Week 2:** `plan = FacadePlan(...); plan.solve()` works for a 3-story palazzo with no overflow
3. **End of Week 3:** every plate produced via declarative plans, renders preserved
4. **End of Week 4:** user can generate novel palazzi via CLI and print the book

---

## What happens to the existing system

The current system is **not thrown away** — it becomes the implementation detail of specific `Element` subclasses. `semicircular_arch()` still exists; a new `ArchElement` wraps it. The 197 passing tests keep passing during the overhaul. When all plates have migrated to plans, the legacy paths can be removed.

---

## Starting point for next session

1. Read this doc and `plans/PHASE_17_SCENE_VALIDATION.md` (scene-graph already exists, the Element base extends it)
2. Create `engraving/element.py` with the base class and a passing `ArchElement` subclass
3. Write the containment tests first — they must FAIL before the backbone is in place
4. Implement `HierarchicalContainment` so the tests pass
5. One element type per session to start; integrate into a plate once the patterns are proven

The overhaul is not about throwing things away — it's about **moving the validation from post-hoc checking to constructive generation**. The system should refuse to draw the impossible.
