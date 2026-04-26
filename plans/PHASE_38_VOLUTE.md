# Phase 38 — Canonical Holm 12-centre Ionic volute

## Why

The Ionic (and Composite, Scamozzi variant) capital's scroll is the
signature of the order. Classical plates (Vignola, Ware, Alvin Holm for
the ICAA) construct it geometrically: 12 successive circular arcs of
quarter-turn each, drawn around 12 centres packed tightly inside the eye.
The characteristic "wound" look — slight radial inflections at each
90-degree junction — is what distinguishes a real volute from a
lathe-turned scroll (or a logarithmic spiral).

Pre-Phase 38 `engraving/volute.py` already carried the general 12-arc
scaffolding but used a grid-search heuristic that could land its centres
outside the eye and never exposed the construction as a public primitive.
The five-orders plates (`plate_ionic`, `plate_composite`, `plate_greek_ionic`,
`plate_capitals_closeup`) therefore drew a flat, log-spiral-looking scroll.

## What changed

`engraving/volute.py` is rewritten around a canonical, closed-form Holm
12-centre construction:

- **New public primitive** `ionic_volute_holm(cx, cy, r_outer, r_eye,
  fillet_frac, hand='right', steps_per_arc=32)`. Returns a dict with
  `"outer"`, `"channel"`, `"eye"` polyline lists in world coordinates.
- **Centre staircase**: each centre is offset from its predecessor by
  `(R_k - R_{k+1}) = R_k * (1 - rho)` in a direction rotating 90° clockwise
  between consecutive arcs (E, S, W, N, …). With `C_0` pinned at the eye
  centre and `R_0 = r_outer`, the chain is fully determined by a single
  ratio `rho`.
- **Ratio**: `rho = 0.84`, pinned by the dual constraint that (1) the
  12-arc endpoint lands inside the eye circle and (2) the spiral wraps
  ~3 full revolutions around the eye centre (total angle sweep ≈ 6π rad —
  the classical Ionic winding count validated by
  `engraving.validate.elements.validate_volute`). Sits within Scamozzi's
  published 12-centre grid ratio range.
- **Inner fillet (channel)**: built from the SAME 12 centres, radii
  shrunk uniformly by `fillet_frac * r_outer`, so the channel winds in
  lockstep with the outer — joins stay tangent-continuous.
- **Handedness**: `hand='left'` returns the x-mirror of `hand='right'`
  so mirror pairs can be requested in a single call.
- **Density**: default 32 samples per arc → 373-point outer spiral (vs
  the ~20 of a pragmatic log spiral), enough to read as a smooth spiral
  at plate scale without visible facets.

`ionic_volute(eye_cx, eye_cy, D, direction, include_channel)` is now a
thin wrapper that fixes the classical proportions (`r_outer = 5/27 D`,
`r_eye = 1/36 D`, channel offset = `1/3 r_outer ≈ 1/9 D`) and appends the
horizontal fillet band above the spiral. The public dict contract is
unchanged — `order_ionic`, `order_composite`, `order_greek_ionic` keep
working as-is.

## Tests

`tests/test_ionic_volute.py` (8 tests): dense-spiral count (>100 pts),
monotonic decreasing radius (with per-arc inflection tolerance), top
start point, end point inside eye, left/right mirror symmetry, Ionic and
Composite column `volutes` layer density, legacy-wrapper key contract.

## Snapshots

Six plates refreshed: `plate_ionic`, `plate_composite`,
`plate_capitals_closeup` (implicit — no prior snapshot),
`plate_greek_orders`, `plate_five_orders`, `plate_five_orders_porticos`.

## Audit

`scripts/audit_plates.py --no-preview` passes 24/24.
`pytest tests/` passes 417/418 (1 skipped — vpype optional path).
