# Phase 30 — Boathouse as a first-class declarative plan

## Problem

McKim-Mead-White boathouses (Harvard Newell, NYAC, Columbia) are a
distinct building archetype: a tall ground-floor run of arched (or
trabeated) boat bays where crew shells launch, an upper clerestory
story, and a steep gabled shingle roof with deep eaves and exposed
rafter tails. Neither `FacadePlan` (palazzo: ordered story stack with
flat parapet) nor `PorticoPlan` (free-standing colonnade + pediment)
expresses this. There is no primitive for a pitched roof — everything
above the top story is currently `ParapetElement` (flat top:
balustrade / attic / cornice).

## Goal

Introduce a sibling plan type, `BoathousePlan`, parallel to `FacadePlan`
and `PorticoPlan`. It carries a bay count + bay kind, an optional
clerestory, a required `RoofPlan`, and an optional `PlinthPlan`. Its
`solve()` method builds a validated `Element` tree of the same shape
used by the rest of the pipeline: boat bays use the existing
`SemicircularArchElement` (arched) or `WindowElement` (trabeated);
clerestory windows use `WindowElement`; the new `RoofElement` draws the
gable + shingle hatch + rafter-tail ticks.

## Deliverables

- `RoofPlan` + `BoathousePlan` dataclasses in
  `engraving/planner/plan.py`.
- `BoathouseElement` + `RoofElement` in
  `engraving/planner/elements.py`.
- `solve_boathouse()` in `engraving/planner/solver.py`, raising
  `PlanInfeasible` when the canvas cannot fit the stack.
- `plates/plate_boathouse_plan.py` — a declarative 3-bay arched
  boathouse with 5-window clerestory, gabled roof at 22°, plinth.
- `tests/test_boathouse_plan.py` — RoofPlan slope validation,
  solver infeasibility (too short / too narrow), end-to-end plate
  render, tree containment, vertical-stack budget arithmetic.
- Public API: `RoofPlan`, `BoathousePlan` exported from
  `engraving/planner/__init__.py`.

## Solver math

Vertical budget (SVG y-down):

    canvas_h = plinth_h + boat_bay_h + upper_story_h + gable_h

with `gable_h = (canvas_w / 2) * tan(slope)` for a gable-end-on
elevation. `boat_bay_h : upper_story_h = 1.6 : 1.0` so the boat bays
read taller than the clerestory.

Horizontal budget: `wall_w = canvas_w - 2 * overhang_mm` (eaves
project past the wall to the canvas edge). Bays tile `wall_w`
exactly. Upper-story windows are evenly spaced inside `wall_w`.

Palazzo / portico code, existing plates, and existing tests are
untouched.
