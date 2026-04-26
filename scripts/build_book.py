"""Build a bound multi-plate PDF.

Usage:
    .venv/bin/python scripts/build_book.py
    # Produces out/engraving_book.pdf containing all 9 plates.
"""
import importlib
import sys
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from engraving.export import render_plate_to_print, concat_pdfs

PLATES = [
    # Opening matter
    "plate_01",
    "plate_schematic",

    # The orders, in canonical progression
    "plate_doric",
    "plate_ionic",
    "plate_corinthian",
    "plate_composite",
    "plate_greek_orders",
    "plate_five_orders",
    "plate_five_orders_porticos",
    "plate_capitals_closeup",
    "plate_corinthian_capital_detail",
    "plate_acanthus_leaf_detail",

    # Building types (declarative plans)
    "plate_portico",
    "plate_portico_plan",
    "plate_palazzo_plan",
    "plate_boathouse_plan",

    # Motif plates and detail studies
    "plate_arcade",
    "plate_blocking_course",
    "plate_cartouche",
    "plate_rinceau",
    "plate_ornament",
    "plate_stairs",
    "plate_grand_stair",
]


def main() -> int:
    out_dir = Path(__file__).parent.parent / "out"
    out_dir.mkdir(exist_ok=True)
    pdfs: list[Path] = []
    for name in PLATES:
        print(f"=== {name} ===")
        mod = importlib.import_module(f"plates.{name}")
        if hasattr(mod, "build_validated"):
            svg, _ = mod.build_validated()
        else:
            svg = mod.build()
        print(f"  SVG: {svg}")
        result = render_plate_to_print(svg, optimize=True, export_pdf=True)
        pdfs.append(result["pdf"])
        print(f"  PDF: {result['pdf']}")

    book_pdf = out_dir / "engraving_book.pdf"
    concat_pdfs(pdfs, book_pdf)
    size_kb = book_pdf.stat().st_size / 1024
    print(f"\nBook: {book_pdf} ({size_kb:.1f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
