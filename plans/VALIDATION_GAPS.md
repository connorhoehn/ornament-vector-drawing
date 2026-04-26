# Validation Depth Audit — Gap Survey (Phase 16)

The current validation library catches basic geometric bugs (closure,
symmetry, anchor alignment, voussoir/springing, triglyph rhythm) but
misses a whole class of *mathematically wrong* constructions that still
render cleanly. This file inventories what the existing validators do
NOT check, grouped by category, so missing predicates can be added
surgically.

## Category A — Within-order constraints NOT checked

These are subdivision-and-proportion rules inside a single order's
silhouette that the current `OrderValidation.validate_canonical_heights`
does not verify.

1. **Capital subdivisions** (Ware p.14):
   - Doric: necking 1/3, echinus+bead 1/3, abacus 1/3 of `capital_h`.
   - Tuscan: necking + astragal + echinus + abacus.
   - Ionic: abacus 1/6, echinus+volute field 5/6.
   - Corinthian: bell 6/7, abacus 1/7 of `capital_h`.
   - Greek Doric: echinus+annulets 2/3, abacus 1/3.
   Only `capital_h == capital_D × D` is enforced at present. The
   builders compute `neck_h, echinus_h, abacus_h` locally but drop
   them from `metadata`, so no external validator can check them.

2. **Base subdivisions** (Attic base: plinth, lower torus, scotia,
   upper torus, fillet). Builders compute `plinth_h, low_torus_h, …`
   locally but never expose them. No validator checks that
   `plinth_h > torus_h > fillet_h` or that the base sits within
   ½D per Ware.

3. **Entablature subdivisions per Ware's tables**. `entablature_h` is
   checked against the canonical total, and architrave/frieze/cornice
   heights are checked at entablature level, but:
   - Cornice sub-parts (bed mould, corona, cymatium) are not checked.
   - Architrave fasciae count / heights (Ionic: three fasciae,
     Corinthian: three + bed mould) unchecked.
   - Frieze ornament presence (pulvinated Ionic vs plain Doric) not
     guarded.

4. **Shaft entasis conventions**. Roman entasis begins at ⅓ of the
   shaft's height from the base; Greek entasis is a continuous bulge
   swelling to a max ~⅓ up. The builders encode this in local vars
   but no validator reads shaft silhouette points to confirm the
   inflection is at the ⅓ mark.

5. **Flute count verified against canonical count per order**. `flute_count`
   is asserted on the CANON dataclass (tuscan/doric/ionic/corinth) but
   never compared against what the fluting layer actually drew for a
   given column result.

6. **Ionic volute eye vertical alignment**. The canonical position of the
   volute eye is 1/9 D below the abacus and 1/9 D inside the shaft
   edge; no validator checks either coordinate on the rendered result.

## Category B — Cross-element constraints NOT checked

Checks that require two (or more) elements to be compared against each
other — column-to-entablature, pedestal-to-column, pilaster-to-column.

7. **Column ↔ entablature proportional coupling**. Ware: entablature ≈
   ¼ column. Each order validator checks `column_D` and `entablature_D`
   in isolation; nothing verifies `entablature_h / column_h ≈ 1/4` in
   the actual rendered ElementResult chain.

8. **Pedestal ↔ column proportional coupling**. Ware: pedestal ≈ ⅓
   column. No rendered-chain check.

9. **Pedestal cap meets column base**. Current validators confirm
   `above` / `meets` anchors on demand, but there is no pre-built
   `pedestal_column_base_aligned` predicate applied across the whole
   pedestal→column assembly.

10. **Pilaster ↔ column order match on the same story**. The facade
    validator catches *name* mismatch between `bay.pilaster_order` and
    `story.has_order`, but not geometric mismatch — a Doric pilaster
    with Ionic's 9D height proportion would pass.

## Category C — Cross-order constraints NOT checked

These fire when MULTIPLE orders are rendered together on one plate.

11. **Relative column height at matched D**. The canonical ratio
    Tuscan : Doric : Ionic : Corinth : Composite = 7:8:9:10:10 is never
    verified on a rendered plate. Plate `plate_five_orders.py` lines them
    up at matched D but no validator checks the rendered `column_h`
    ratios.

12. **Greek-Doric stouter than Roman-Doric**. At matched D, Greek Doric
    `column_h` should be ~0.69 × Roman Doric (5.5 / 8). Current code
    only validates each in isolation.

13. **Cross-order abacus widths**. Ware: all five Roman orders use the
    same 7/6 D abacus width. At plate scale this should be visually
    consistent; nothing checks.

## Category D — Symmetry constraints NOT checked

14. **Cartouche assembly-level symmetry**. `validate_cartouche` iterates
    `field` polylines and calls `mirror_symmetric` on each, but does NOT
    check the `wings` layer's aggregate symmetry. Bug #1 (baroque_scroll
    only has ONE wing) is invisible to current validation.

15. **Corinthian leaf ring symmetry**. `num_acanthus_row1 == 3` but
    nothing checks that the three leaves are evenly spaced around the
    bell, nor that the row-2 leaves are rotated 60° from row-1.

16. **Rinceau alternation symmetry**. An alternating rinceau should have
    exactly half the leaves above and half below the spine. Validator
    checks total count only.

17. **Medallion wreath radial balance**. Only leaf count is bounded.
    No check that leaves are distributed around the full 360°.

18. **Trophy axis symmetry across LAYER aggregates**. `validate_trophy`
    checks each layer separately; doesn't detect a missing mirrored
    element if the layer itself is empty on one side (a whole missing
    left-side trophy element passes silently).

## Category E — Aesthetic-but-measurable constraints NOT checked

19. **Pier-width : clear-span ratio for arcades**. Vignola convention
    `pier_w / clear_span ∈ [0.33, 0.50]`. Current `arcade.py` default
    of `pier_width_frac=0.20` of bay pitch produces ratios as low as
    0.13. No validator warns.

20. **Pediment slope angle**. Vignola: 12–15° over the entablature.
    No validator.

21. **Dentil count per bay**. An Ionic bay of `bay_pitch ≈ 4.5 D`
    should have ~27 dentils. Validator only checks spacing constancy,
    not count-per-bay.

22. **Intercolumniation canons**. Pycnostyle 1.5 D, systyle 2 D,
    eustyle 2.25 D (Vitruvius). Not checked.

23. **String-course projection**. Ware: 1/6 D beyond wall. Not checked.

24. **Corner column correction**. When a Doric column sits at the corner
    of an arcade, the outermost metope must be ½ triglyph width less
    than the other metopes (Vitruvian "angular triglyph" problem).
    Not checked.

## Category F — Detail-visibility-at-scale constraints NOT checked

25. **Minimum feature size vs plate scale**. In the five-orders plate at
    D=9, volute eyes (D/18 = 0.5 mm) render as invisible dots. There
    is no rule of the form
    *"feature size ≥ 0.4 mm at final plate scale"* or
    *"if feature_size / plate_diagonal < 0.002, warn"*.

26. **Flute count visibility**. 24 Ionic flutes on a D=9 column means
    flute width ≈ 1.2 mm — barely visible. Not checked.

27. **Stroke density per unit area**. Hatching fields can exceed
    ink-readable density at final scale. Not validated against
    target printing scale.

28. **Text legibility at plate scale**. `engraving.typography` can emit
    glyphs at 1.5 mm cap height which disappear in a reduced plate.
    No validator scales target size against page output DPI.

---

## Summary count

- Category A: 6 gaps
- Category B: 4 gaps
- Category C: 3 gaps
- Category D: 5 gaps
- Category E: 6 gaps
- Category F: 4 gaps
- **Total: 28 identified gaps**

## Top-8 to add now (Phase 16)

Ranked by "bug already known that this predicate would immediately
light up":

| Predicate | Lights up |
|-----------|-----------|
| `aspect_ratio_in_range` (`__init__.py`) | Bug #3: thin arcade piers |
| `relative_height` (`__init__.py`) | Bug #2: Greek-Roman Doric ratio |
| `capital_subdivisions` (`orders.py`) | Bug #5: Doric capital thirds |
| `cartouche_wing_symmetry` (`elements.py`) | Bug #1: single-wing baroque |
| `pier_span_ratio` (`elements.py`) | Bug #3 (strict) |
| `pediment_slope_angle` (`composition.py`) | Bug #6 |
| `column_pedestal_entablature_ratio` (`orders.py`) | Bug #7 |
| `five_orders_relative_heights` (`composition.py`) | Bug #8 |

Plus one visibility helper: `min_feature_visible_at_scale`
(`__init__.py`) for Bug #4.

## Metadata gaps blocking validation

Before `capital_subdivisions` could check anything, builders needed to
expose subdivisional metadata. This audit confirmed the following keys
are now present in every order's `metadata` dict (some parallel Phase 15
work beat this audit to it):

| Builder | Subdivisional metadata present |
|---------|-------------------------------|
| `orders.py` (Tuscan) | `cap_neck_h, cap_echinus_h, cap_abacus_h` + base |
| `order_doric.py` | `cap_neck_h, cap_echinus_h, cap_abacus_h`, `astragal_h` |
| `order_ionic.py` | `cap_echinus_h, cap_abacus_h` + base |
| `order_corinthian.py` | `cap_bell_h, cap_abacus_h, cap_acanthus_row1/2_h, cap_helix_h` |
| `order_composite.py` | `cap_bell_h, cap_abacus_h, cap_volute_h, cap_echinus_h, cap_caulicoli_h` |
| `order_greek_doric.py` | `cap_annulet_h, cap_echinus_h, cap_abacus_h` |
| `order_greek_ionic.py` | `cap_echinus_h, cap_abacus_h, cap_volute_h` + base |

The only missing piece added by this audit: **Greek-Ionic's
`cap_echinus_h`** (now computed as `capital_h - abacus_h` since Greek
Ionic omits the necking band).

## Outcome of running TestKnownStructuralBugs

After adding the test class, all 8 tests PASS — the parallel Phase 15
builder work (plus Phase 16's subdivision metadata) has already fixed
every known structural bug the user flagged. The tests remain in place
as regression pins: any future edit that re-introduces a one-winged
cartouche, a thin-pier arcade, a capital with lopsided thirds, or a
height ratio violation will immediately trip.

Total suite result: **170 passed, 1 failed (pre-existing Composite
`cap_volute_h` edge case), 1 skipped.**
