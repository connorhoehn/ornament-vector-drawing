# Scaffold roadmap — procedures for scaling to larger designs

A living audit of what the system can produce today and what scaffolds
are needed to produce more ambitious work. Updated after every round of
audit-and-fix.

## What the system can produce today

**Output size:** 1 declarative plan → 1 building → 1 plate at 1:1 print
scale. Four plan types:

| Plan | Kind | Lines of spec | Current state |
|---|---|---|---|
| `FacadePlan` | urban palazzo | ~40 lines | Mature; Phase 31 reservation math locks openings inside stories |
| `PorticoPlan` | temple-front | ~15 lines | Canonical proportions via `canon.py`, correct cornice projection |
| `BoathousePlan` | McKim boathouse | ~15 lines | 3-bay arcade + clerestory + gabled roof |
| (hard-coded) | individual orders | ~150 lines each | Legacy builders with Greek/Tuscan/Doric/Ionic/Corinthian/Composite |

**Element vocabulary** (26 classes):
facade, story, bay, wall, window, door, arch_opening, pilaster, column,
string_course, entablature_band, parapet, plinth, pedestal, pediment,
roof, quoin, shadow, portico, boathouse, column_run, + legacy individual
order builders.

**Rendering stack:**
- Page (drawsvg wrapper, mm units, physical-scale SVG)
- Element tree → walk → polylines with stroke weights → SVG polylines
- Optional ShadowElement with parallel_hatch for tonal fill
- CSG void subtraction through Material.VOID/SOLID
- Plan↔YAML↔SVG roundtrip via embedded `<metadata>` block

**Validation:** 378 automated tests including 3 layers of structural
checks (containment, sibling non-overlap, positivity of dims) plus 11
empirical proportion guards locking `column_h = column_D·D` across every
order.

## What the system CANNOT produce today

### Single plate with multiple buildings

No primitive for "palazzo next to boathouse on the same plate," no
"portico attached to the front of a palazzo." Each plate re-implements
page layout manually. A catalog of buildings becomes N plates, not 1
with N panels.

### Measurement-annotated plates

Vignola's plates are *measurement instruments* — every dimension
labelled, every proportional ratio called out. Current plates show
geometry but not the numbers. (Phase 32, in flight.)

### Documentation suites

Real architectural plates pair elevation + plan view + section. We only
do elevations. There is no `FootprintPlan` (top-down) or `SectionPlan`
(vertical slice through the building).

### Parametric variation / catalog

Generating 10 palazzo variations requires 10 manual CLI invocations.
No way to declare a sweep (`bays ∈ {3,5,7}`, `order ∈ {doric, ionic}`
→ 6 plates) in a single command. (Queued as original Phase 27.)

### Cross-building shared proportions

If I want "palazzo ground story uses same D as attached portico
columns," I must eyeball it. There is no shared-proportion system
binding multiple plans together.

### Plate-level grid / frames with margins and registration

Every plate file hand-codes title position, subtitle position, scale
bar position, margin insets. ~20 lines of boilerplate per plate.

### Richer geometric primitives

The acanthus root-cause fix landed rich leaves, but other ornaments
still have gaps: **volute construction** is a simple spiral instead of
the 12-centre Holm/ICAA construction, **rinceau** scrolls are basic,
**rosettes** on ceiling caissons are placeholders, **grotesques** do
not exist, **human figures** in pediment tympana do not exist (and
probably shouldn't — that's hand-work).

## Phased scaffold roadmap

Each phase is sized for ~3–7 days of focused work. Later phases build
on earlier ones; items within a phase are roughly independent.

### Phase 32 — Dimension annotations  `[IN FLIGHT]`

`DimensionElement` with `p1`, `p2`, `label`, `offset_mm`, tick markers,
extension lines. Integrated into the portico and Corinthian-capital
detail plates first. Unlocks: every plate can now declare what it's
measuring.

### Phase 33 — PlateLayout + title/scale-bar primitives  `[NEXT]`

Centralise the page-scaffolding boilerplate every plate repeats:

```python
@dataclass
class PlateLayout:
    title: str
    subtitle: str | None
    regions: list[DrawingRegion]       # sub-canvases for buildings/details
    scale_bar: ScaleBarSpec | None
    frame_style: Literal["single", "double", "vignola"] = "double"
    margin_mm: float = 12.0
```

Apply to every existing plate; expected ~200 LOC reduction.

### Phase 34 — CompositePlan (multi-building on single plate)

```python
@dataclass
class CompositePlan:
    canvas: BBox
    children: list[PlanAtPosition]     # each child is a Plan + sub-canvas BBox
    shared_D: float | None = None      # bind all children to same module
```

Unlocks plates like "palazzo elevation + its ground-floor detail at
2× scale next to it" or "three boathouses by size."

### Phase 35 — FootprintPlan (plan-view projection)

Top-down view of a building — footprint polygon, wall thicknesses,
column positions, door swings. Siblings FacadePlan; shares bay layout
math. Unlocks elevation+plan pairs.

### Phase 36 — Catalog / parameter sweep (was Phase 27)

```bash
./ornament catalog --base palazzo.yaml \
    --sweep bays:3,5,7 --sweep order:doric,ionic \
    -o out/catalog/
```

Yields 6 plates + an `index.md`. Infeasible combinations listed but
don't halt the batch.

### Phase 37 — Shared proportional binding

Let a PlateLayout declare `shared_D = 14.0` and have every child plan
use that D. No more divergent scales in a multi-building composition.

### Phase 38 — Volute construction (Holm 12-centre method)

Rewrite `order_ionic.volute` from naive spiral to the full
centre-and-radius construction in Alvin Holm / ICAA's diagram. The
existing capital closeup plate will expose the improvement immediately.

### Phase 39 — Cross-section / vertical cut

Section through an arched opening: shows the inside jamb, soffit depth,
return of the hood around the building corner. Most useful when paired
with FootprintPlan for a full documentation suite.

### Phase 40 — Plate book (PDF binding)

Take N SVGs, stitch them into a single PDF with cover / contents /
page numbers. Minimal: cairosvg per-page + pypdf concat. Useful end
state for a catalog: one book file.

## Meta-procedure: continuous audit

After every phase lands:

1. **Render every plate** at 400 dpi and visually inspect. Note gaps in
   a running issue list at the bottom of this document.
2. **Build an opinionated closeup plate** for any motif that reads
   wrong. The closeup exposes both the bug and the rendering scale at
   which it shows up. (Example: `plate_acanthus_leaf_detail.py` was
   what made the SVG-override bug diagnosable.)
3. **Write an empirical measurement probe** for any geometric primitive
   whose layout the solver reserves space for. Hard-code the measured
   coefficient into the solver (like `hood_h = 0.54·w + 0.3` from
   Phase 31). The probe then becomes a regression test.
4. **Add a proportion guard** — a test that locks in a canonical
   invariant (like `column_h == column_D·D`). If a future refactor
   breaks it, the guard flags it before any plate changes.
5. **Update this roadmap** with one-line entries under "What the system
   cannot produce today" as new gaps surface.

## Running issue log

- **Volute construction is a simple spiral** — Holm 12-centre method not
  implemented. Visible in capitals closeup at Ionic + Composite.
  Blocked on: forward work, Phase 38.
- **Rinceau / rosette / grotesque ornaments** are placeholders. Blocked
  on: no immediate demand.
- **No way to CROP a building to a specific rectangle** within a plate
  (currently plate_capitals_closeup hacks this with shapely
  LineString.intersection post-build). Abstract into a helper.
- **Shadow angles are fixed at 45°**; an aesthetic rule in Layer C
  exists but isn't enforced. Forward work when a plate actually
  violates it.
- **Palazzo pilaster stroke weight was 0.50/0.30** — audit every
  element's layer_weights dict and write a canonical hierarchy table
  (who is 0.50? who is 0.35? who is 0.18?).

## Closing

The system crossed a threshold in Phase 28–32: from "one building →
one plate" toward "plans compose into plates." The next threshold is
Phase 34: multi-building compositions on one plate. After that, Phase
36 (catalog) turns every building into a FAMILY of buildings. The
goal is: three months from now, produce a bound catalog of every
classical building type in canonical and generated variations, each
fully dimensioned, from a single declarative codebase.
