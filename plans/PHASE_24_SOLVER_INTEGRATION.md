# Phase 24 — Constraint solver integration

## Problem

Phase 20 shipped `engraving/planner/constraint_solver.py` — a linprog-based constraint-propagation primitive. It passes its own tests. But `FacadePlan.solve()` still uses a top-down deterministic approach with an ad-hoc pinning loop for `min_height_mm` redistribution.

This leaves three gaps:

1. **Mixed constraints aren't expressible.** "story_0 height >= 1.2 × story_2 height" has no home.
2. **The pinning loop in `solve_story_heights` is ad-hoc.** It works but feels fragile. A linprog solution would be 10 lines and provably correct.
3. **The 3 known `TestEntablatureBand` failures** (cornice overshoot by 6.64mm) are a symptom: the canvas/entablature widths are computed independently without a shared constraint that says "the cornice projection must NOT exceed the canvas boundary minus the quoin width."

## Goal

- Replace `solve_story_heights` with a constraint-solver call
- Make the entablature cornice projection a SOLVED variable that respects the canvas boundary
- Expose an API for callers to add custom constraints: `plan.add_constraint(...)`
- The 3 pre-existing test failures should pass after the fix

## Scope

### In scope
- Rewire `solve_story_heights` via `ConstraintSolver`
- Add canvas / entablature / quoin width as shared variables
- Allow `FacadePlan.add_constraint(lhs, op, rhs)` for custom bidirectional constraints
- Integrate the 3 failing tests

### Out of scope
- Don't replace `solve_bay_layout` or `solve_openings` (they work fine top-down; bay pitch is genuinely top-down)
- Don't add integer constraints (bay count stays imperative)

## Plan — 4 days

### Day 1 — Rewire `solve_story_heights` via ConstraintSolver

Replace the current pinning loop:

```python
def solve_story_heights(plan):
    solver = ConstraintSolver()
    canvas_h = plan.canvas_height
    
    # One variable per story height
    for i, s in enumerate(plan.stories):
        solver.variable(f"s{i}_h", lower=s.min_height_mm, upper=canvas_h)
    if plan.parapet:
        solver.variable("parapet_h", lower=0, upper=canvas_h)
    
    # Total heights = canvas_h
    total_lhs = [(f"s{i}_h", 1) for i in range(len(plan.stories))]
    if plan.parapet:
        total_lhs.append(("parapet_h", 1))
    solver.equation(total_lhs, rhs=canvas_h)
    
    # Ratios: s_i / s_j = height_ratio_i / height_ratio_j  →
    # s_i * ratio_j - s_j * ratio_i = 0 (as equation)
    for i in range(1, len(plan.stories)):
        r0 = plan.stories[0].height_ratio
        ri = plan.stories[i].height_ratio
        # But this becomes infeasible when min_height_mm kicks in, so we
        # use a WEAKER constraint: ratio proportionality within 15% tolerance
        solver.inequality([(f"s{i}_h", r0), (f"s0_h", -ri)], upper_bound=canvas_h * 0.15)
        solver.inequality([(f"s{i}_h", -r0), (f"s0_h", ri)], upper_bound=canvas_h * 0.15)
    
    # Objective: minimize total deviation from ideal ratios (L1)
    # Implementable as slack variables; or simpler, minimize s0 (arbitrary)
    solver.objective([(f"s0_h", 1)])
    
    result = solver.solve()
    if not result.feasible:
        raise PlanInfeasible(
            reason="insufficient_height",
            details=f"linprog could not satisfy story constraints: {result.errors}",
        )
    
    # Extract heights and build StoryLayouts as before
    ...
```

### Day 2 — Cornice projection as solved variable

Current bug: `EntablatureBandElement` projects its cornice by a fixed ~1D past its `x_left`/`x_right`. When those are `canvas_left`/`canvas_right`, the cornice extends 6.64mm past the canvas → containment violation.

New approach: the entablature's effective `x_left/x_right` is a solved variable, not canvas-edge-pinned. The constraint:

```
entablature_left + cornice_projection >= canvas_left   (cornice doesn't overshoot canvas)
entablature_right - cornice_projection <= canvas_right
entablature_right - entablature_left = canvas_width - 2 * quoin_width  (fits between quoins)
cornice_projection = entablature_h * 0.45   (Vignola proportion)
```

Linprog solves for `entablature_left`, `entablature_right`, `cornice_projection`.

Result: entablature is inset from canvas edges by cornice_projection + quoin_width, so its outermost extent exactly lands at canvas_left / canvas_right.

### Day 3 — Custom constraint API

Add to `FacadePlan`:

```python
@dataclass
class FacadePlan:
    ...
    custom_constraints: list = field(default_factory=list)
    
    def add_constraint(self, expr: str):
        """Add a custom linear constraint in a simple DSL.
        
        Examples:
          plan.add_constraint("story_0.height >= 1.2 * story_2.height")
          plan.add_constraint("bay_2.width == bay_0.width")
          plan.add_constraint("total_arch_span == piano_nobile_intercolumniation")
        """
        self.custom_constraints.append(expr)
```

Implement a simple parser: tokenize on `==`/`<=`/`>=`/`+`/`-`/`*`, resolve variables by walking the plan tree. Skip more complex expressions; document.

### Day 4 — Fix the 3 TestEntablatureBand failures + integration tests

Re-run `pytest tests/test_overhaul_planner.py::TestEntablatureBand` and confirm all 3 pass after Day 2's fix.

Add integration tests:

```python
class TestConstraintIntegration:
    def test_custom_height_ratio_constraint(self):
        plan = FacadePlan(canvas=(0, 0, 200, 300), ...)
        plan.add_constraint("story_0.height >= 1.5 * story_2.height")
        facade = plan.solve()
        s0 = facade.find("facade.story_0")
        s2 = facade.find("facade.story_2")
        s0_h = s0.effective_bbox()[3] - s0.effective_bbox()[1]
        s2_h = s2.effective_bbox()[3] - s2.effective_bbox()[1]
        assert s0_h >= 1.5 * s2_h - 0.1
    
    def test_infeasible_custom_constraint_raises(self):
        plan = FacadePlan(canvas=(0, 0, 200, 300),
                          stories=[StoryPlan(height_ratio=1.0, min_height_mm=200)])
        plan.add_constraint("story_0.height == 50")  # conflicts with min=200
        with pytest.raises(PlanInfeasible):
            plan.solve()
    
    def test_entablature_cornice_stays_in_canvas(self):
        plan = make_standard_palazzo_plan()
        facade = plan.solve()
        for n in facade.descendants():
            if n.kind == "entablature_band":
                bx = n.effective_bbox()
                assert bx[0] >= plan.canvas_left - 0.5
                assert bx[2] <= plan.canvas_right + 0.5
```

## Acceptance criteria

- `pytest tests/` — all 290+ tests pass (287 previous + 3 new)
- `TestEntablatureBand` — all 3 tests now pass (previously flagged as pre-existing failures)
- `FacadePlan.add_constraint(...)` works for simple linear expressions
- `solve_story_heights` no longer contains a hand-rolled pinning loop

## Effort

~4 days. Most complexity is in the DSL parser (Day 3). Days 1 and 2 are mechanical rewires.
