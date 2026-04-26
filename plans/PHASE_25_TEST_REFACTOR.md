# Phase 25 — Test reorganization + snapshot regression

## Problem

`tests/test_validation.py` is **2383 lines**, `tests/test_overhaul_planner.py` is **990 lines**. Together they hold ~290 tests mixing every concern:

- primitives (approx_equal, aligned_vertical, ...)
- order canonical validation
- entablature validation
- facade composition
- scene graph (legacy)
- element classes
- planner
- constraint solver
- CSG
- aesthetic rules
- plate render smoke tests
- CLI tests

Running a focused subset requires `pytest -k` with cryptic class-name patterns. Finding a failing test means scrolling through 2000 lines. Pytest collection takes longer than it should.

Additionally: no snapshot regression tests. If someone changes a builder subtly (different Bezier control point, different stroke order), rendered SVGs change byte-for-byte but no test catches it. Only visual inspection does, which is unreliable.

## Goal

1. Split the two monolithic test files into focused per-domain files
2. Add snapshot-regression tests that detect silent visual changes

## Plan — 3 days

### Day 1 — Split tests by domain

Target layout:

```
tests/
├── conftest.py                          shared fixtures
├── test_schema.py                       Anchor, Element, Violation, BBox helpers
├── test_containment.py                  Layer A: HierarchicalContainment, SiblingNonOverlap, SharedEdge
├── test_geometry_primitives.py          Bezier, arc, log_spiral, resample_path
├── test_canon.py                        all 5 Roman orders + 2 Greek orders match Ware
├── test_validate_primitives.py          approx_equal, is_closed, mirror_symmetric, voussoirs_above_springing, etc.
├── test_validate_orders.py              TuscanValidation, DoricValidation, ... pydantic schemas
├── test_validate_entablatures.py        validate_doric_entablature, validate_ionic_..., validate_corinthian_...
├── test_validate_elements.py            acanthus, volute, arch, window, balustrade, rustication, cartouche
├── test_validate_composition.py         facade-level rules (bay alignment, hierarchy, order match)
├── test_validate_aesthetic.py           Layer C rules
├── test_orders.py                       column silhouette builders (all 7)
├── test_entablatures.py                 entablature builders + visual smoke
├── test_acanthus.py                     Page-based acanthus (silhouette closure, lobe count, symmetry)
├── test_volute.py                       volute spiral (monotonic, 3-turn sweep, eye closure)
├── test_arches.py                       ArchElement subclasses + legacy arches module
├── test_cli.py                          list/render/validate/book/generate/debug
├── test_constraint_solver.py            linprog solver (already exists; keep)
├── test_elements_base.py                Element class, Material enum, void_footprint
├── test_elements_columns.py             ColumnElement subclasses
├── test_elements_entablatures.py        EntablatureElement subclasses (already exists; keep)
├── test_elements_arches.py              ArchElement specifics (already exists; keep)
├── test_planner_plan.py                 FacadePlan / StoryPlan / BayPlan / OpeningPlan / PilasterPlan / ParapetPlan dataclass validity
├── test_planner_solver.py               solve_story_heights, solve_bay_layout, solve_openings, solve_pilasters, solve_string_courses
├── test_planner_solve.py                top-level FacadePlan.solve() integration
├── test_planner_elements.py             FacadeElement, StoryElement, WindowElement, PilasterElement, WallElement, QuoinElement, ParapetElement, etc.
├── test_planner_debug.py                explain() + render_debug
├── test_scene_graph.py                  legacy scene graph (to be retired in Phase 23)
├── test_plates_smoke.py                 build() succeeds for every plate
├── test_plates_render.py                SVG renders produced + PNG previews work
└── test_plates_snapshot.py              NEW: byte-snapshot regression for every plate
```

Tooling to help:

```python
# tools/split_tests.py
"""Read tests/test_validation.py, extract each class, write to per-domain files."""
import ast, pathlib

src = pathlib.Path("tests/test_validation.py").read_text()
tree = ast.parse(src)
classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]

CLASS_TO_FILE = {
    "TestPrimitives":              "test_validate_primitives.py",
    "TestContainment":             "test_containment.py",
    "TestCanon":                   "test_canon.py",
    "TestTuscanOrder":             "test_orders.py",
    "TestDoricEntablature":        "test_entablatures.py",
    "TestAllOrderValidators":      "test_validate_orders.py",
    "TestCartouche":               "test_validate_elements.py",
    "TestPalazzoSchemeComposition":"test_validate_composition.py",
    "TestAestheticLayer":          "test_validate_aesthetic.py",
    "TestPlatesStillRender":       "test_plates_smoke.py",
    "TestCLI":                     "test_cli.py",
    "TestCLIGenerate":             "test_cli.py",
    # ...
}

for cls in classes:
    target = CLASS_TO_FILE.get(cls.name, "test_misc.py")
    with open(f"tests/{target}", "a") as f:
        f.write(ast.unparse(cls) + "\n\n")
```

Run the script, inspect each resulting file, add per-file imports + conftest fixtures.

### Day 2 — Snapshot regression tests

For each plate, record the canonical SVG. Any deviation fails the test.

```python
# tests/test_plates_snapshot.py
import hashlib
import pytest
from pathlib import Path

PLATE_MODULES = [
    "plates.plate_01", "plates.plate_blocking_course", "plates.plate_portico",
    "plates.plate_doric", "plates.plate_ionic", "plates.plate_corinthian",
    "plates.plate_composite", "plates.plate_five_orders", "plates.plate_schematic",
    "plates.plate_arcade", "plates.plate_cartouche", "plates.plate_stairs",
    "plates.plate_rinceau", "plates.plate_palazzo_v2", "plates.plate_greek_orders",
    "plates.plate_ornament", "plates.plate_grand_stair", "plates.plate_palazzo_plan",
]

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


@pytest.fixture
def snapshots_dir():
    SNAPSHOTS_DIR.mkdir(exist_ok=True)
    return SNAPSHOTS_DIR


def _canonicalize(svg_text: str) -> str:
    """Strip non-structural differences: whitespace, ordering of attributes,
    timestamps, comments. Keep only the geometry-meaningful content."""
    import re
    # Strip leading/trailing whitespace on every line
    lines = [line.strip() for line in svg_text.splitlines() if line.strip()]
    # Strip comments
    lines = [line for line in lines if not line.startswith("<!--")]
    return "\n".join(lines)


@pytest.mark.snapshot
@pytest.mark.parametrize("mod_name", PLATE_MODULES)
def test_plate_snapshot(mod_name, snapshots_dir):
    import importlib
    mod = importlib.import_module(mod_name)
    svg_path = Path(mod.build())
    assert svg_path.exists()
    
    svg_text = svg_path.read_text()
    canonical = _canonicalize(svg_text)
    digest = hashlib.sha256(canonical.encode()).hexdigest()
    
    snap_file = snapshots_dir / f"{mod_name.split('.')[-1]}.sha256"
    if snap_file.exists():
        expected = snap_file.read_text().strip()
        assert digest == expected, (
            f"SVG output for {mod_name} changed.\n"
            f"  expected: {expected}\n"
            f"  got:      {digest}\n"
            f"If this change is intentional, update the snapshot:\n"
            f"  echo '{digest}' > {snap_file}"
        )
    else:
        snap_file.write_text(digest)
        pytest.skip(f"snapshot created for {mod_name}")
```

Run once to populate snapshots. Commit. Subsequent runs fail on drift.

Add marker to pytest.ini:

```ini
[pytest]
markers =
    slow: long-running tests (plate renders)
    snapshot: byte-exact regression tests
```

### Day 3 — CI integration + doc

Add a `Makefile` or `tests/run.sh`:

```bash
# Fast tests (<1s total): unit tests for primitives, small builders
.venv/bin/python -m pytest tests/ -v -m "not slow and not snapshot"

# Slow tests (renders, plate smoke): 10-20s
.venv/bin/python -m pytest tests/ -v -m "slow and not snapshot"

# Snapshot regression: 30-60s
.venv/bin/python -m pytest tests/ -v -m "snapshot"

# All
.venv/bin/python -m pytest tests/ -v
```

Document in `docs/TESTING.md`:
- How to add a test for a new element
- How to update a snapshot when visual changes are intentional
- How to debug a snapshot failure

## Acceptance criteria

- Each test file ≤ 300 lines
- All existing tests pass (no regressions from the split)
- `pytest -m "not slow and not snapshot"` runs in < 2 seconds
- Every plate has a registered SHA-256 snapshot
- Unintentional SVG drift fails a test with a specific diff message

## Effort

~3 days. Day 1 is the heavy lift (careful mechanical split). Days 2 and 3 are incremental and small.
