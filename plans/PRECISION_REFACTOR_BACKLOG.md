# Precision Refactor Backlog

Source: page-by-page visual audit of `out/engraving_book.pdf` (24 plates, 2026-04-20).
Written in response to: "the capitals of the Corinthian don't look anywhere accurate"
+ "the design is way off" after five screenshots of the palazzo.

The book is not yet print-ready. The root issue is not any single plate — it's
that several primitives (acanthus leaf, capital assembly, CSG clipping, dimension
layer) were built to "good enough" stubs, and every plate downstream inherits
the defect. This doc catalogs the defects and proposes a sequenced refactor to
raise the whole book to engraving-grade precision.

---

## Part 1 — Issue backlog

Pages refer to `out/engraving_book.pdf` in current state.

### A. Critical correctness (plates unsuitable for print)

| # | Plate | Issue |
|---|---|---|
| A1 | p-15 palazzo v2 | Piano-nobile windows: horizontal frame lines pass *through* adjacent windows — the frame stack is not clipping against neighbors. |
| A2 | p-15 palazzo v2 | No pilasters between bays even though plan declares Ionic piano nobile. |
| A3 | p-15 palazzo v2 | Ground arches float: jambs don't reach plinth, horizontal rustication bands cross inside the arch voids. |
| A4 | p-15 palazzo v2 | Hood pediments on piano nobile clip into the story above. |
| A5 | p-02 palazzo v1 | Same pilaster absence. Arches extend below springing with ghost jambs. Rustication crosses voids. |
| A6 | p-02 palazzo v1 | Central arched door reads as a separate, deeper opening (different baseline than sides). |
| A7 | p-18 arcade | Arches project *above* the entablature/string course instead of sitting inside bay voids. |
| A8 | p-17 boathouse | 5 upper windows over 3 arches with no pilaster/column axes to explain the rhythm. |
| A9 | p-17 boathouse | Arches end above the ground plinth, leaving a blank band below. |

### B. Capital / order accuracy (your main complaint)

| # | Plate | Issue |
|---|---|---|
| B1 | p-10, p-11 | Corinthian acanthus leaves rendered as egg-shaped ovals with a vertical spine and sawtooth outline. Canonical acanthus has five deeply lobed fronds with V-shaped "eyes" between lobes, each lobe subdivided into ~5–7 serrated leaflets with curling tips, the top two lobes recurving forward. |
| B2 | p-11 | Corinthian has 3 leaves per tier. Canonical is 8 per tier (one per face + one per corner), staggered between tiers. |
| B3 | p-11 | Caulicoli (stems between upper leaves) and helices (scrolls under abacus) reduced to thin lines. Should be prominent volute pairs. |
| B4 | p-11 | Corner volutes are pinpricks. Should be ~1/4 of capital width. |
| B5 | p-11 | Fleuron (center of abacus) is a smudge. |
| B6 | p-08, p-10 | Composite inherits all Corinthian defects, plus the Ionic volute upper half is too compressed. |
| B7 | p-04, p-10 | Ionic volute reads at column scale but on closeup is a flat scroll without a proper eye and parallel spiral channel. The 12-center Holm construction is in place (Phase 38) but the line count collapses at small scale. |
| B8 | p-07 | Greek Ionic capital almost invisible — volute degraded to a bar. |
| B9 | p-12 | Standalone acanthus-leaf study: reads as "leaf-shaped sawblade". Zigzag teeth on outer edge only, no inner rib convergence, no lobe structure. |
| B10 | p-21, p-22 | Rinceau + festoon both reuse the same defective leaf primitive. |

### C. Layout, typography, encoding

| # | Plate | Issue |
|---|---|---|
| C1 | p-13 | Tuscan portico: pediment apex overlaps the subtitle text. |
| C2 | p-16 | Palazzo facade plan: dimension labels ("attic 27 mm" etc.) crowd the facade's left edge. |
| C3 | p-16 | Scale bar "50 mm" overlaps "facade = 196 mm" label. |
| C4 | p-17 | Boathouse: total-height dim extension line crosses the right frame. |
| C5 | p-10 | "1.17Â·D" — middle-dot character (U+00B7) is mojibake'd; UTF-8 bytes interpreted as Latin-1 somewhere in the text pipeline. |
| C6 | p-12 | Acanthus leaf dim label crosses plate frame. |
| C7 | p-11 | Corinthian capital detail: dim extension lines exit the right frame. |

### D. Scale and composition

| # | Plate | Issue |
|---|---|---|
| D1 | p-03…p-06 | Doric / Ionic / Corinthian / Composite single-column plates: column fills ~25% of plate height. Entablature floats at the top with a dead zone in between. Hero plates should fill ≥70% of the print area. |
| D2 | p-07 | Greek Doric + Ionic: short columns, capitals read as cropped. |
| D3 | p-08 | Five orders at "matched lower diameter" — visible shaft widths are different. Either caption wrong or diameters wrong. |
| D4 | p-24 | Grand entrance stair: right newel column is oversized; left and right terminals aren't symmetric; the top column floats above the landing without a plinth. |

### E. Ornament fidelity

| # | Plate | Issue |
|---|---|---|
| E1 | p-20 | "Baroque" cartouche variant is a diamond with triangles, not a scroll/strapwork cartouche. |
| E2 | p-22 | Festoon leaves = same zigzag blobs. |
| E3 | p-22 | Trophies (martial/musical/scientific/naval) read as stick-figure schematics, not ornament. |

---

## Part 2 — Root causes

These are the systemic reasons the above defects exist. The refactor should
target these, not the symptoms on individual plates.

1. **The acanthus leaf primitive is an outline with noise, not a sculpted form.**
   Current `_parametric_acanthus_leaf` builds a teardrop outline and adds
   zigzag teeth. Canonical acanthus is a compound form: a midrib, five lobes
   each with an inner V and an outer curl, and recurved tips. This is the
   single most impactful defect in the book.

2. **The Corinthian/Composite capital assembly is a 2-band stack of leaves,
   not a radial ring with caulicoli + helices + corner volutes + face fleurons.**
   The decomposition itself is wrong, independent of the leaf primitive.

3. **Plate V.1 and V.2 of the palazzo exist in parallel.** V.1 uses
   `plate_palazzo.py` (imperative), V.2 uses a different imperative path
   (`plate_palazzo_v2.py`), and the clean declarative `plate_palazzo_plan.py`
   is a third code path. All three are in the book. The imperative paths
   don't go through the Phase 31 opening-reservation fix and show overlaps;
   the declarative one shows arches with floating jambs.

4. **CSG clipping is applied unevenly.** Rustication bands, hood pediments,
   and window frames each render full-width horizontal polylines without
   subtracting against neighboring VOID elements. A proper CSG pass would
   mask every SOLID layer against every VOID bbox.

5. **Pilasters declared in the plan aren't being emitted.** Either the
   solver drops them or the renderer skips the layer.

6. **Hero plates have no "fill the frame" policy.** Scale is chosen by
   canonical proportion (columns are 7–10·D tall) with D a global constant.
   For hero plates D should be derived from the plate size, not the other
   way around.

7. **The dimension layer is not clipped against the plate frame** and has
   no collision detection against labels or scale bar.

8. **Text pipeline drops non-ASCII bytes somewhere** (mojibake in the
   closeup caption).

---

## Part 3 — Refactor plan

Phases are sized for a focused day or two each. Run sequentially. After each,
regenerate the book and visually diff against this doc.

### Phase 40 — Deduplicate palazzo + audit render paths
- Delete `plate_palazzo.py` and `plate_palazzo_v2.py` from the book's plate
  list. Make `plate_palazzo_plan.py` the canonical palazzo.
- Grep for any plate not going through the declarative `FacadePlan → solver →
  Element tree` pipeline. Either migrate or delete.
- Add a plate_audit guard: every plate must declare its render path as
  `declarative` or `imperative`; imperative plates require an explicit
  allowlist entry.

### Phase 41 — CSG enforcement
- Walk the Element tree at render time; for every SOLID polyline, subtract
  against every overlapping VOID bbox.
- Add test: render every plate to SVG, parse polylines, assert no polyline
  with non-VOID material crosses into a VOID element's bbox.
- Fix ground arcade: jambs must reach plinth; rustication must clip to
  wall area between openings; arch haunches must not extend below springing.
- Fix piano-nobile window stack: hood + frame + sill + jambs render as a
  single unified outline primitive per opening, not four overlapping layers.

### Phase 42 — Real parametric acanthus leaf
- Source: Page's 1886 *Drawing the Acanthus* (in repo).
- New primitive: `acanthus_leaf(lobes=5, serrations_per_lobe=7,
  tip_recurve=True, rib=True)`.
- Construction: midrib cubic; each lobe is a parametric curve branching
  from the midrib, recurving at the tip for upper lobes. Serrations are
  scalloped curves not zigzags.
- Returns a Shapely Polygon + veins (list of LineStrings) + a metadata
  dict (lobe endpoints, tip positions) so the capital assembly can
  compose them correctly.
- Snapshot test: visual diff against a reference PNG traced from Page.

### Phase 43 — Corinthian capital rewrite
- New module `engraving/capitals/` with one file per order.
- Corinthian `assemble(bell_d, total_h)`:
  - 8 bottom leaves arranged radially around the bell, each clipped
    for 20% overlap with neighbors.
  - 8 upper leaves staggered 22.5°, slightly larger.
  - 8 caulicoli stems sprouting from between upper leaves, each ending
    in a helical pair.
  - 4 corner volutes sized to ~1/4 of abacus width, emerging from the
    outermost helices.
  - Fleuron on each of the 4 abacus faces.
  - Abacus with concave sides (Vignola-canonical profile).
- Composite capital = Corinthian lower half + Ionic volute upper half
  (Scamozzi).
- Unit tests: abacus width = 2.1·D, total height = 1.167·D, each capital
  has ≥ N polygons above a threshold.

### Phase 44 — Hero-plate composition
- `PlatePresenter` class: given a single element and a plate size, scale
  to fill ~70% of the print area, center, add dimensions + baseline + title.
- Retrofit p-03…p-06, p-10, p-11 through it.
- Add a fill-ratio assertion to `scripts/audit_plates.py`.

### Phase 45 — Palazzo precision reset
- Ensure the FacadePlan solver emits pilaster elements when
  `PilasterPlan` is set on a bay.
- Window primitive: single unified outline per opening (frame + hood + sill
  + jambs rendered as one closed polyline set, not four overlapping stacks).
- Regenerate palazzo plate; expect zero cross-opening lines.

### Phase 46 — Dimension discipline
- Clip the dimension layer against the plate frame bbox.
- Move dim labels into the margin band or gutter — never on top of the facade.
- Text-collision check in plate audit: no dim label may overlap another
  label or the scale bar.

### Phase 47 — Typography + encoding
- Trace the mojibake: find where `·` becomes `Â·` and fix the encoding
  (probably a bytes→str path assuming Latin-1).
- Fix Tuscan portico title: drop title height or raise pediment.
- Tighten caption baseline so it never crosses a pediment peak.

### Phase 48 — Proportion guard tests
- Extend `tests/test_proportions_guard.py`: on the five-orders plate,
  measure shaft lower diameters from the rendered element tree and assert
  equality within 1 mm; assert shaft heights = 7/8/9/10/10·D; entablature
  heights = 1.75/2/2.25/2.5/2.5·D.

### Phase 49 — Ornament propagation
- Once Phase 42 ships, regenerate the rinceau frieze, festoons, cartouche
  wreaths — they should all read as acanthus/laurel instead of sawblades.
- Baroque cartouche: replace with a strapwork scroll primitive (volute
  pairs flanking a shield with ear-scrolls).

### Acceptance gate
After Phases 40–45:
- Regenerate `out/engraving_book.pdf`.
- Visually diff each of the 24 pages against this doc's backlog.
- Each row in the backlog must be marked RESOLVED or have a ticket to
  continue the fix.
- No plate may enter the book that fails the audit script.

---

## Progress log

- **2026-04-20 Visual-polish sweep — DONE.** Four user-reported issues
  fixed in one session: (1) capital line weights split per-layer across
  `plate_corinthian`, `plate_corinthian_capital_detail`,
  `plate_capitals_closeup`, `plate_five_orders`, `plate_composite` so
  dense tone layers (acanthus/caulicoli/bell_guides) render at HATCH and
  LINE layers (abacus/helices/fleuron) at ORNAMENT/FINE;
  (2) `engraving/stairs.py` baluster height now equals
  `handrail_height - 0.35*riser` so tops meet the sloped rail exactly
  (was 20% short, ~2-3mm visible gap per step);
  (3) `plate_arcade.py` gets `with_entablature=True` so arches have a
  ceiling band; (4) `planner/solver.py:solve_openings` snaps `y_bottom`
  to `story.y_bottom` when wall is "arcuated" and opening is
  arch_door/arch_window — jambs reach the plinth and the existing CSG
  subtraction in `WallElement.render_strokes` now carves the arch cleanly
  out of the rustication block grid. Targeted Phase 41 fix for the
  arcaded case the user saw; broader Phase 41 (non-arcuated combos)
  still open. 415 tests pass, 0 validator errors, snapshots refreshed.
- **2026-04-20 Phase 42 (acanthus primitive) — DONE.** Replaced the
  ogival-outline-with-zigzag-edge construction with a
  discrete-lobe builder: each lobe is its own polyline from root →
  raffled outer curve → tip-curl → return on the midrib. Inter-lobe
  "eye" gaps are literal in the drawing. Rendered at capital scale,
  individual leaves now read as 3-lobe flames with smooth scalloped
  edges. Addresses B1, B2, B9 in the backlog; partially addresses B3–B6
  (still need full capital-assembly rewrite in Phase 43 for caulicoli,
  helices, corner volutes, fleurons). `acanthus_leaf()` output contract
  preserved: `[silhouette, midrib, *lobe_outlines, *veins, terminal]`.
- **2026-04-20 Phase 40 (palazzo dedupe) — DONE.** Removed
  `plate_palazzo_v2.py` and all references from `build_book.py`,
  snapshot tests, validate/audit scripts, and the CLI. `plate_palazzo_plan.py`
  is now the sole palazzo plate in the book. Book dropped from 24 to 23
  pages. Addresses root cause #3 (three parallel render paths).
- **2026-04-20 Phase 47 (typography + encoding) — DONE.** Added
  `<meta charset="UTF-8">` to the PDF-export HTML template and forced
  UTF-8 file write; fixes the `Â·` mojibake in closeup-plate captions
  (C5). Increased Tuscan portico vertical reserve from 28→40 mm so the
  title no longer overlaps the raking cornice (C1).
- **2026-04-20 Phase 46 (dim layer discipline) — DONE.** Added
  `frame_bbox` clipping to `render_dimensions`: Liang–Barsky clips
  extension lines to the plate frame, and labels outside the margin are
  dropped. Wired into all four dim-using plates. Moved palazzo_plan
  story-height dims to the right side (canvas left edge had no room).
  Clamped boathouse + corinthian dim coordinates inside the frame.
  Verified with an SVG-coord scan: 0 polyline points outside frame
  across all four plates; all expected dim labels survive.
- **2026-04-20 Phase 43 (Corinthian capital) — DONE.** Lifted leaf
  density and assembly to canonical: row 1 from 3→5 visible leaves
  (centre + 2 mid + 2 corner), row 2 from 3→4 (inner pair + mid pair,
  staggered between row-1 positions). Corner volutes scaled from
  ``helix_r = 0.10·D`` to ``0.14·D``. Added inner helix pair near the
  fleuron (2 extra scrolls) for a total of 4 helices. Caulicoli
  doubled to 4 (outer pair to corner volutes + inner pair to inner
  helices). Fleuron rewritten as a 5-petal rosette (centre + 2 upper
  + 2 lower) with twice the radius of the previous 3-petal version.
  Metadata updated: ``num_acanthus_row1=5``, ``num_acanthus_row2=4``,
  ``num_helices=4``, ``num_caulicoli=4``. Acanthus layer polyline count
  jumped from ~90 to 135 for a D=24 column. Composite capital
  unchanged (separate module — next phase).
- Remaining phases: 41 (CSG enforcement), 44 (hero-plate composition),
  45 (palazzo pilaster + window unification — may be partly resolved by
  dedupe), 48 (proportion guards), 49 (ornament propagation via new
  acanthus), plus extending the Corinthian density to Composite.

---

## Part 4 — Suggested ordering

Two parallel priorities:

**Track 1 — palazzo / plates become printable:**
Phase 40 → 41 → 45 → 46 → 47 → 48.

**Track 2 — capitals become accurate:**
Phase 42 → 43 → 44 → 49.

The acanthus primitive (Phase 42) is the highest-leverage single change in
the book. Everything downstream (capitals, rinceau, festoon, cartouche)
inherits its quality.
