"""Render and validate every plate in one pass. Fail hard if anything invalid.

Usage: .venv/bin/python scripts/validate_all_plates.py
"""
import sys
from pathlib import Path

# Allow running from the project root regardless of cwd. The project has no
# installed package, so we prepend the repo root so ``plates.*`` imports.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


PLATE_MODULES = [
    "plates.plate_01",
    "plates.plate_blocking_course",
    "plates.plate_portico",
    "plates.plate_doric",
    "plates.plate_ionic",
    "plates.plate_corinthian",
    "plates.plate_composite",
    "plates.plate_five_orders",
    "plates.plate_greek_orders",
    "plates.plate_schematic",
    "plates.plate_arcade",
    "plates.plate_cartouche",
    "plates.plate_stairs",
    "plates.plate_rinceau",
    "plates.plate_palazzo_plan",
    "plates.plate_ornament",
    "plates.plate_grand_stair",
]


def main() -> int:
    import importlib
    all_errors = []
    for mod_name in PLATE_MODULES:
        mod = importlib.import_module(mod_name)
        if hasattr(mod, "build_validated"):
            svg_path, report = mod.build_validated()
            err_count = len(report)
            print(f"{mod_name}: {svg_path} — {err_count} errors")
            for e in report:
                print(f"    - {e}")
                all_errors.append(f"{mod_name}: {e}")
        else:
            svg_path = mod.build()
            print(f"{mod_name}: {svg_path} — (no build_validated)")
    print()
    print(f"TOTAL: {len(all_errors)} errors across {len(PLATE_MODULES)} plates")
    return 0 if not all_errors else 1


if __name__ == "__main__":
    sys.exit(main())
