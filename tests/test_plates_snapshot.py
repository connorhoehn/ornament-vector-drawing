"""Byte-snapshot regression tests for every plate.

Each plate is rendered to SVG; the SVG text is canonicalized (whitespace
stripped, comments removed) and hashed. The hash is stored in
tests/snapshots/<plate>.sha256. Subsequent runs re-render and compare.

When a visual change is intentional:
    rm tests/snapshots/<plate>.sha256
    .venv/bin/python -m pytest tests/test_plates_snapshot.py -v
    # New snapshot is created; commit it.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest


PLATE_MODULES = [
    "plates.plate_01",
    "plates.plate_blocking_course",
    "plates.plate_portico",
    "plates.plate_doric",
    "plates.plate_ionic",
    "plates.plate_corinthian",
    "plates.plate_composite",
    "plates.plate_five_orders",
    "plates.plate_schematic",
    "plates.plate_arcade",
    "plates.plate_cartouche",
    "plates.plate_stairs",
    "plates.plate_rinceau",
    "plates.plate_greek_orders",
    "plates.plate_ornament",
    "plates.plate_grand_stair",
    "plates.plate_palazzo_plan",
]

SNAPSHOTS_DIR = Path(__file__).parent / "snapshots"


def _canonicalize(svg_text: str) -> str:
    """Strip non-structural differences: whitespace on every line,
    comments, blank lines."""
    lines = []
    for line in svg_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("<!--"):
            continue
        lines.append(stripped)
    return "\n".join(lines)


@pytest.mark.snapshot
@pytest.mark.parametrize("mod_name", PLATE_MODULES)
def test_plate_snapshot(mod_name):
    SNAPSHOTS_DIR.mkdir(exist_ok=True)
    import importlib
    mod = importlib.import_module(mod_name)
    svg_path = Path(mod.build())
    assert svg_path.exists(), f"build() returned non-existent path {svg_path}"

    svg_text = svg_path.read_text()
    canonical = _canonicalize(svg_text)
    digest = hashlib.sha256(canonical.encode()).hexdigest()

    short_name = mod_name.split(".")[-1]
    snap_file = SNAPSHOTS_DIR / f"{short_name}.sha256"
    if snap_file.exists():
        expected = snap_file.read_text().strip()
        assert digest == expected, (
            f"\nSVG output for {short_name} changed.\n"
            f"  expected: {expected}\n"
            f"  got:      {digest}\n"
            f"If this change is intentional, refresh the snapshot:\n"
            f"  rm {snap_file}\n"
            f"  pytest tests/test_plates_snapshot.py::test_plate_snapshot[{mod_name}]\n"
        )
    else:
        snap_file.write_text(digest + "\n")
        pytest.skip(f"Snapshot created for {short_name}: {digest}")
