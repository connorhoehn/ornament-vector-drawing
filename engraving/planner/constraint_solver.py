"""Constraint-propagation solver for facade layout.

Variables are NAMED quantities (e.g. "story_0.height", "bay_2.pitch").
Constraints are linear equations or inequalities over these variables.
The solver uses scipy.optimize.linprog to find values that satisfy the
system.

Example:
    solver = ConstraintSolver()
    solver.variable("canvas_h", lower=100, upper=300)
    solver.variable("story_0_h", lower=40)
    solver.variable("story_1_h", lower=40)
    solver.equation([("story_0_h", 1), ("story_1_h", 1)], rhs=200)
    solver.inequality([("story_1_h", -1), ("story_0_h", 1.2)], upper_bound=0)
    solver.objective([("story_1_h", -1)])  # maximize story_1_h
    result = solver.solve()
    # result.values["story_0_h"], etc.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ConstraintSolverResult:
    feasible: bool
    values: dict[str, float]
    errors: list[str]


class ConstraintSolver:
    """Linear-constraint solver. A thin, architecture-focused wrapper over
    scipy.optimize.linprog."""

    def __init__(self):
        self._vars: dict[str, tuple[float, float]] = {}  # name -> (lower, upper)
        self._equations: list[tuple[list[tuple[str, float]], float]] = []
        # Each equation: (lhs coefficients as (var_name, coeff) pairs, rhs constant)
        # i.e. sum(coeff * var) == rhs
        self._inequalities: list[tuple[list[tuple[str, float]], float]] = []
        # Each inequality: (coefficients, upper_bound) such that sum(coeff * var) <= upper_bound
        self._objective: list[tuple[str, float]] = []  # minimize sum(coeff * var)

    def variable(self, name: str, lower: float = 0.0,
                 upper: float = 1e9) -> None:
        if name in self._vars:
            raise ValueError(f"variable {name!r} already declared")
        self._vars[name] = (lower, upper)

    def equation(self, lhs: list[tuple[str, float]], rhs: float) -> None:
        """Add constraint: sum(coeff * var for var, coeff in lhs) == rhs."""
        self._equations.append((list(lhs), rhs))

    def inequality(self, lhs: list[tuple[str, float]],
                   upper_bound: float) -> None:
        """Add constraint: sum(coeff * var for var, coeff in lhs) <= upper_bound."""
        self._inequalities.append((list(lhs), upper_bound))

    def objective(self, coeffs: list[tuple[str, float]]) -> None:
        """Set the minimization objective. Call once."""
        self._objective = list(coeffs)

    def solve(self) -> ConstraintSolverResult:
        from scipy.optimize import linprog
        import numpy as np

        var_order = list(self._vars)
        var_idx = {name: i for i, name in enumerate(var_order)}
        n = len(var_order)

        if n == 0:
            return ConstraintSolverResult(feasible=True, values={}, errors=[])

        # Objective vector (minimize c @ x). Default: minimize sum of vars
        c = np.zeros(n)
        for var, coeff in self._objective:
            if var not in var_idx:
                return ConstraintSolverResult(
                    feasible=False, values={},
                    errors=[f"objective references unknown variable {var!r}"])
            c[var_idx[var]] = coeff

        # Equality constraints: A_eq @ x == b_eq
        A_eq, b_eq = None, None
        if self._equations:
            A_eq = np.zeros((len(self._equations), n))
            b_eq = np.zeros(len(self._equations))
            for i, (lhs, rhs) in enumerate(self._equations):
                for var, coeff in lhs:
                    if var not in var_idx:
                        return ConstraintSolverResult(
                            feasible=False, values={},
                            errors=[f"equation references unknown variable {var!r}"])
                    A_eq[i, var_idx[var]] = coeff
                b_eq[i] = rhs

        # Inequality: A_ub @ x <= b_ub
        A_ub, b_ub = None, None
        if self._inequalities:
            A_ub = np.zeros((len(self._inequalities), n))
            b_ub = np.zeros(len(self._inequalities))
            for i, (lhs, upper) in enumerate(self._inequalities):
                for var, coeff in lhs:
                    if var not in var_idx:
                        return ConstraintSolverResult(
                            feasible=False, values={},
                            errors=[f"inequality references unknown variable {var!r}"])
                    A_ub[i, var_idx[var]] = coeff
                b_ub[i] = upper

        # Bounds
        bounds = [self._vars[name] for name in var_order]

        result = linprog(c=c, A_ub=A_ub, b_ub=b_ub,
                         A_eq=A_eq, b_eq=b_eq, bounds=bounds,
                         method='highs')

        if not result.success:
            return ConstraintSolverResult(
                feasible=False, values={},
                errors=[result.message]
            )
        values = {var_order[i]: float(result.x[i]) for i in range(n)}
        return ConstraintSolverResult(feasible=True, values=values, errors=[])
