# Phase 32 — Dimension annotations

## Problem

Real Vignola / McKim architectural plates are MEASUREMENT drawings — every
significant span is called out with leader lines, extension ticks, and a
numeric or canonical label (`7·D`, `68.6 mm`, `1/18 D`). Our output to date
has been bare silhouettes: geometrically correct but indistinguishable from
a decorative illustration, not a plate an engraver can read dimensions off.
`plate_corinthian_capital_detail.py` hacks around this with ad-hoc leader
polylines + free-floating `page.text(...)` calls, which is brittle,
un-measured, and not reusable.

## Goal

Introduce `DimensionElement` as a first-class `Element` subclass so any
plate can call `horizontal_dimension(...)` / `vertical_dimension(...)` and
get a proper measurement callout: two extension lines, a parallel dimension
line, end ticks, and an offset label. Render weight is uniformly hairline
so dimensions read as REFERENCE, not structure.

## Dimension anatomy

```
  ext ─────────────┐                            ┌────────────── ext
                   │                            │
        tick ──────┼────────── dim line ────────┼────── tick
                   │                            │
                   ▼                            ▼
          (p1, measured point)         (p2, measured point)
                          label:  "7·D"
```

- **Extension lines** — short perpendicular stubs from p1/p2 out to the
  dimension line (plus a tiny `extension_mm` extension past it).
- **Dimension line** — the parallel line connecting the two extensions,
  offset from the measured geometry by `offset_mm`.
- **Tick markers** — one at each end, style selectable (`tick` = perpendicular
  slash, `arrow` = V-arrowhead, `slash` = 45°).
- **Label** — SVG `<text>` centred on the dimension line, offset slightly
  on the far side so it never overlaps geometry.
- **Signed offset** — negative `offset_mm` flips the whole assembly to the
  other side of the measured line.

## Text rendering — design choice

`render_strokes()` yields `(polyline, stroke_mm)` only; there is no way to
emit an SVG `<text>` element through that iterator without polluting the
stroke stream with magic tuples. The two options:

- **(a)** DimensionElement exposes a parallel `text_labels()` method that
  yields `(text, x, y, size, anchor)` tuples. Plates iterate both streams:
  `page.polyline(...)` for strokes, `page.text(...)` for labels.
- **(b)** Extend `render_strokes()` to accept a typed marker (`("text", x, y,
  size, text_str)`) that the renderer special-cases.

We pick **(a)**. It keeps `render_strokes()` purely geometric (which every
other element relies on), localises the text concern to the plate, and lets
us add a convenience `render_dimensions(page, root)` helper that walks the
tree once and emits both streams. No change to `render.py` is needed.

## Deliverables

- `DimensionElement` in `engraving/planner/elements.py` — fields: `p1`,
  `p2`, `label`, `offset_mm`, `tick_style`, `extension_mm`, `text_size_mm`.
- `horizontal_dimension(...)` / `vertical_dimension(...)` factories
  (same module).
- `render_dimensions(page, root)` helper — walks the tree, emits strokes
  + text for every `DimensionElement`.
- Integrated into `plate_portico_plan.py` (3 dimensions: column_h = 7·D,
  entablature_h = 1.75·D, colonnade_w) and
  `plate_corinthian_capital_detail.py` (replaces the ad-hoc leader-line
  pattern with bell_h / capital_h / D dimensions).
- `tests/test_dimensions.py` — 8 tests.

## Compose into plates

A plate builds its geometry as a tree, calls `root.render_strokes()` to
draw, then attaches `DimensionElement`s as top-level annotations and calls
`render_dimensions(page, root)` once. Dimensions live OUTSIDE the
structural tree (they are reference overlays) so they don't count toward
containment or aesthetic validation.
