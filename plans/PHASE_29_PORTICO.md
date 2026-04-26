# Phase 29 — Portico as a first-class declarative plan

## Problem

Porticos (Roman-temple fronts, Pantheon-style loggias, colonnaded entry
pavilions) are a different building archetype than a palazzo facade.
They consist of a free-standing column colonnade crowned by an
entablature and a triangular pediment — not an ordered stack of stories
with bays cut into walls. The existing `FacadePlan` and its solver
assume story stacks and bay rhythms; there is no way to declare
"tetrastyle Tuscan portico on a pedestal with a 15° pediment" without
falling back to hard-coded coordinates (see `plates/plate_portico.py`).

## Goal

Introduce a sibling plan type, `PorticoPlan`, parallel to `FacadePlan`.
It carries a column order, a column count + intercolumniation, an
optional pedestal, an optional plinth, and an optional `PedimentPlan`.
Its `solve()` method builds a validated `Element` tree of the same
shape used by the rest of the pipeline: columns are rendered via the
existing `ColumnElement` subclasses; the entablature uses
`EntablatureBandElement`; the new `PedimentElement` draws the gable.

## Deliverables

- `PedimentPlan` + `PorticoPlan` dataclasses in
  `engraving/planner/plan.py`.
- `PedimentElement` + `ColumnRunElement` + `PorticoElement` in
  `engraving/planner/elements.py`.
- `solve_portico()` in `engraving/planner/solver.py`, raising
  `PlanInfeasible` when the canvas is too small.
- `plates/plate_portico_plan.py` — a declarative tetrastyle Tuscan
  portico, ~600 mm wide, with pedestal, plinth, and pediment.
- `tests/test_portico_plan.py` — plan validation, infeasibility,
  end-to-end plate render, and tree containment.

Palazzo code, tests, and existing plates are untouched.
