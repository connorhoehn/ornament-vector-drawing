"""Print a tabular summary of which validators are covered by tests.

Run: .venv/bin/python tests/coverage_summary.py
"""
import inspect
import pathlib
import sys

# Allow `python tests/coverage_summary.py` to import `engraving.*` without
# requiring the user to set PYTHONPATH manually.
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from engraving.validate import (
    approx_equal, aligned_vertical, meets, is_closed,
    no_self_intersection, no_duplicate_lines, monotonic_in_radius,
    mirror_symmetric, count_equals, voussoirs_above_springing,
    opening_cleared_from_wall, triglyph_over_every_column,
    dentil_spacing_matches,
)
from engraving.validate import orders, elements, composition, entablatures


def list_validators() -> None:
    primitives = [
        "approx_equal", "aligned_vertical", "meets", "is_closed",
        "no_self_intersection", "no_duplicate_lines",
        "monotonic_in_radius", "mirror_symmetric", "count_equals",
        "voussoirs_above_springing", "opening_cleared_from_wall",
        "triglyph_over_every_column", "dentil_spacing_matches",
    ]
    schemas = [
        f.__name__
        for f in [
            orders.TuscanValidation, orders.DoricValidation,
            orders.IonicValidation, orders.CorinthianValidation,
            orders.CompositeValidation,
        ]
    ]
    element_fns = [
        n for n, f in inspect.getmembers(elements, inspect.isfunction)
        if n.startswith("validate_")
    ]
    comp_fns = [
        n for n, f in inspect.getmembers(composition, inspect.isfunction)
        if n.startswith("validate_")
    ]
    ent_fns = [
        n for n, f in inspect.getmembers(entablatures, inspect.isfunction)
        if n.startswith("validate_")
    ]
    print("Primitives:", primitives)
    print("Order schemas:", schemas)
    print("Element validators:", element_fns)
    print("Composition validators:", comp_fns)
    print("Entablature validators:", ent_fns)


if __name__ == "__main__":
    list_validators()
