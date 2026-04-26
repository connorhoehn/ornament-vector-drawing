import pytest
from engraving.planner.constraint_solver import ConstraintSolver


class TestConstraintSolver:
    def test_simple_equation(self):
        s = ConstraintSolver()
        s.variable("x", lower=0, upper=100)
        s.variable("y", lower=0, upper=100)
        s.equation([("x", 1), ("y", 1)], rhs=50)
        s.objective([("x", -1)])   # maximize x
        r = s.solve()
        assert r.feasible
        assert abs(r.values["x"] - 50) < 0.01
        assert abs(r.values["y"]) < 0.01

    def test_inequality(self):
        s = ConstraintSolver()
        s.variable("a", lower=0, upper=100)
        s.variable("b", lower=0, upper=100)
        # a + b <= 80
        s.inequality([("a", 1), ("b", 1)], upper_bound=80)
        # a = 40 (fixed)
        s.equation([("a", 1)], rhs=40)
        # maximize b
        s.objective([("b", -1)])
        r = s.solve()
        assert r.feasible
        assert abs(r.values["a"] - 40) < 0.01
        assert abs(r.values["b"] - 40) < 0.01

    def test_infeasible(self):
        s = ConstraintSolver()
        s.variable("x", lower=0, upper=10)
        s.equation([("x", 1)], rhs=100)  # impossible given upper=10
        r = s.solve()
        assert not r.feasible

    def test_architectural_example_three_stories(self):
        """Three stories; total = canvas_h; story_1 >= 1.2 * story_2."""
        s = ConstraintSolver()
        s.variable("canvas_h", lower=200, upper=200)   # fixed
        s.variable("s0", lower=40, upper=300)
        s.variable("s1", lower=40, upper=300)
        s.variable("s2", lower=40, upper=300)
        # s0 + s1 + s2 == canvas_h
        s.equation([("s0", 1), ("s1", 1), ("s2", 1), ("canvas_h", -1)], rhs=0)
        # s1 - 1.2 * s2 >= 0  =>  -s1 + 1.2 * s2 <= 0
        s.inequality([("s1", -1), ("s2", 1.2)], upper_bound=0)
        # Just find any feasible solution
        s.objective([("s0", 1)])  # minimize s0 (prefer small ground floor)
        r = s.solve()
        assert r.feasible
        # Sum is 200
        assert abs(r.values["s0"] + r.values["s1"] + r.values["s2"] - 200) < 0.1
        # s1 >= 1.2 * s2
        assert r.values["s1"] + 0.01 >= 1.2 * r.values["s2"]
