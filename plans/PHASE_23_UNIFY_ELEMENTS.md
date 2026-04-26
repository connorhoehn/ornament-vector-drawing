# Phase 23 — Unify the Element system (delete `_legacy.py`)

## Problem

Currently there are TWO parallel element systems:

1. **Legacy dict-returning builders** in `engraving/elements/_legacy.py`: `pedestal()`, `column()`, `entablature()`, `pediment()`, `tetrastyle_portico()`, `rusticated_block_wall()`. Return `{"polylines": [...], "shadows": [...], "top_y": ..., ...}`.

2. **Element subclasses** in `engraving/elements/{arches,columns,entablatures}.py`: `ArchElement`, `ColumnElement`, `EntablatureElement`. Inherit from `Element`, expose `render_strokes()` and `effective_bbox()`.

Plus `WindowElement`, `PilasterElement`, `WallElement` in `engraving/planner/elements.py` WRAP legacy dict-returning functions in `engraving/{windows,pilasters,rustication}.py`. Every wrapper reverse-engineers the dict's layer keys → stroke weights.

This causes:
- Cross-cutting bugs: change a legacy builder's dict keys and three wrappers break
- Stroke-weight control is indirect — the wrapper tries to classify polylines after the fact
- The codebase feels like "new wraps old" rather than a clean pyramid

## Goal

One Element system. Every architectural primitive is a subclass of `Element`. The legacy dict-returning builders either don't exist or are internal implementation details hidden behind proper subclasses.

## Scope

### In scope
- Port `pilaster()`, `window_opening()`, `rustication.wall()` rendering logic into native Element subclasses
- Delete or convert `engraving/elements/_legacy.py`
- Delete the wrapper indirection in `engraving/planner/elements.py`

### Out of scope
- Column silhouettes and entablatures (already wrapped; keep)
- Legacy `engraving/arches.py` — small, pure function, keep as helper
- The top-level `engraving/elements.py` (legacy re-export module)

## Plan — 5 days

### Day 1 — Audit + test-surface snapshot

Run a baseline snapshot: re-render every plate, save the byte-exact SVGs to `out/baseline/`. After each day's refactor, re-render and diff. Any unplanned change = bug.

```bash
mkdir -p out/baseline
for p in $(ls plates/plate_*.py | sed 's|plates/||;s|\.py||'); do
  .venv/bin/python -m plates.$p
  cp out/$p.svg out/baseline/
done
```

Write a `tools/svg_diff.py` that compares two SVG files as sorted polylines + text + rect sets. Used at end of each day.

### Day 2 — Port `WallElement` to native polyline emission

`rustication.wall()` is ~300 lines. Port it into `WallElement._emit_geometry()` directly. The rendering logic becomes:

```python
class WallElement(Element):
    def _emit_geometry(self):
        """Yield (polyline, layer_tag) pairs. No dict."""
        if self.variant == "smooth":
            yield self._outline(), "outline"
            return
        if self.variant == "bossed_smooth":
            yield self._outline(), "outline"
            yield from self._emit_horizontal_rules(), "banding"
            return
        if self.variant in ("banded", "chamfered", "rock_faced", "vermiculated"):
            yield from self._emit_ashlar_grid(), "blocks"
            yield from self._emit_joints(), "joints"
            if self.variant == "vermiculated":
                yield from self._emit_vermiculated_carving(), "carving"
            return
        if self.variant == "arcuated":
            yield from self._emit_ashlar_grid(), "blocks"
            yield from self._emit_joints(), "joints"
            yield from self._emit_arch_voussoirs(), "voussoirs"
            return
```

Stroke weights are assigned by `render_strokes()` walking `_emit_geometry()` with a layer→weight map. Direct, no reverse-engineering.

`engraving/rustication.py` becomes a thin legacy module that imports from `WallElement` for backward-compat callers.

Re-render baseline, diff. Any unexpected change → fix.

### Day 3 — Port `WindowElement` to native

Same treatment. `windows.window_opening()` is ~250 lines. Port into `WindowElement._emit_geometry()`:
- opening rect
- architrave (3 fasciae)
- sill + corbels
- hood (none/cornice/triangular/segmental)
- keystone
- brackets (ancones)

Each as a helper method. Stroke weights assigned at the Element layer. The caller chooses `hood="triangular"` and gets a hood without the builder having to know its stroke weight.

Re-render baseline, diff.

### Day 4 — Port `PilasterElement` to native

`pilasters.pilaster()` is ~200 lines. Port. Include order-specific capital moldings (Ionic volutes, Corinthian acanthus) as sub-elements the pilaster composes — `IonicPilaster` has a `VoluteCapitalElement` as a child, etc.

Re-render baseline, diff.

### Day 5 — Delete `_legacy.py`, clean up imports

- Delete `engraving/elements/_legacy.py`
- Grep for any import of `from engraving.elements import ...` that was resolving through `__init__.py`'s re-export. Update every caller to import from the new locations.
- Delete `engraving/rustication.py`, `engraving/windows.py`, `engraving/pilasters.py` OR leave as thin shims that call the Element classes
- Final re-render + diff
- Run full test suite

## Acceptance criteria

- `pytest tests/` — all 287 tests pass
- `engraving/elements/_legacy.py` is GONE
- Every `out/plate_*.svg` byte-matches baseline (modulo any improvements we note)
- `wc -l` shows net code reduction (~500 lines) because the wrapper indirection is gone

## Risk mitigation

- Baseline diff after each day catches unintended visual regressions
- Tests must stay green throughout
- If a day's port goes over budget, revert to baseline and tackle in isolation; don't leave two systems half-migrated

## Effort

~5 days of focused work. Can parallelize Days 2-3-4 (three different files) but the diff-check step is sequential. Realistic: one session per day with agents handling the boilerplate.
