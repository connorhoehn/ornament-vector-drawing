"""Declarative planner: turn intent into a validated Element tree.

Users declare a `FacadePlan` (what a palazzo IS — stories, bays, openings,
parapet) and call `plan.solve()` which returns a rendered-ready Element
tree with every HierarchicalContainment constraint satisfied.

If the plan is infeasible — the canvas is too small, ratios don't sum,
openings exceed their stories — `solve()` raises `PlanInfeasible` with a
specific actionable message.

See `plans/OVERHAUL.md` for the full design.
"""
from .plan import (
    FacadePlan, StoryPlan, BayPlan, OpeningPlan, ParapetPlan, PilasterPlan,
    PlinthPlan, PedimentPlan, PorticoPlan, RoofPlan, BoathousePlan,
    PlanInfeasible,
)

__all__ = [
    "FacadePlan", "StoryPlan", "BayPlan", "OpeningPlan", "ParapetPlan",
    "PilasterPlan", "PlinthPlan", "PedimentPlan", "PorticoPlan",
    "RoofPlan", "BoathousePlan",
    "PlanInfeasible",
]
