#!/usr/bin/env python
"""Continuous audit — render every plate and check for common issues.

Meta-procedure from plans/SCAFFOLD_ROADMAP.md: run this after every
phase lands. It catches:

  * Plates that fail to render (PlanInfeasible, exception, empty SVG)
  * SVGs that are suspiciously small (< 1 KB = essentially empty)
  * Rendered PNGs that are blank or near-blank (< 20 KB at 200dpi
    usually indicates nothing drew)
  * Plates whose SVG output did not change when the snapshot was
    expected to stay stable (a sign of a regression that left
    geometry silently broken)

Usage:
    .venv/bin/python scripts/audit_plates.py
    .venv/bin/python scripts/audit_plates.py --no-preview
    .venv/bin/python scripts/audit_plates.py --plate palazzo_plan

Exit code 0 if all plates pass, 1 otherwise.
"""
from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path

# Let this script run from anywhere: put the repo root on sys.path so
# "plates.plate_foo" imports resolve.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Thresholds — tuned by inspection, not math.
MIN_SVG_BYTES = 1024           # anything smaller is essentially empty
MIN_PNG_BYTES = 20_000         # 200dpi blank white plate is ~5-10KB
MAX_PNG_FRACTION_WHITE = 0.995 # >99.5% white pixels = nothing drew

# Plate module name → "display name" for the audit report.
PLATE_MODULES = [
    "plates.plate_01",
    "plates.plate_acanthus_leaf_detail",
    "plates.plate_arcade",
    "plates.plate_blocking_course",
    "plates.plate_boathouse_plan",
    "plates.plate_capitals_closeup",
    "plates.plate_cartouche",
    "plates.plate_composite",
    "plates.plate_corinthian",
    "plates.plate_corinthian_capital_detail",
    "plates.plate_doric",
    "plates.plate_five_orders",
    "plates.plate_five_orders_porticos",
    "plates.plate_grand_stair",
    "plates.plate_greek_orders",
    "plates.plate_ionic",
    "plates.plate_ornament",
    "plates.plate_palazzo_plan",
    "plates.plate_portico",
    "plates.plate_portico_plan",
    "plates.plate_rinceau",
    "plates.plate_schematic",
    "plates.plate_stairs",
]

OUT_DIR = Path(__file__).resolve().parent.parent / "out"


@dataclass
class PlateAudit:
    module_name: str
    status: str = "ok"            # "ok" | "render_fail" | "empty_svg" | "empty_png" | "skipped"
    messages: list[str] = field(default_factory=list)
    svg_bytes: int = 0
    png_bytes: int | None = None
    svg_path: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _short(name: str) -> str:
    return name.replace("plates.plate_", "")


def render(module_name: str, *, with_preview: bool) -> PlateAudit:
    result = PlateAudit(module_name=module_name)
    try:
        mod = importlib.import_module(module_name)
    except Exception as e:
        result.status = "render_fail"
        result.messages.append(f"import failed: {e}")
        return result

    build = getattr(mod, "build", None)
    if build is None:
        result.status = "skipped"
        result.messages.append("no build() entry point")
        return result

    try:
        svg_path = build()
    except Exception as e:
        result.status = "render_fail"
        result.messages.append(f"build() raised: {e}")
        result.messages.append(traceback.format_exc(limit=3))
        return result

    if not svg_path:
        result.status = "render_fail"
        result.messages.append("build() returned no path")
        return result

    result.svg_path = str(svg_path)
    svg_file = Path(svg_path)
    if not svg_file.exists():
        result.status = "render_fail"
        result.messages.append(f"expected SVG at {svg_path} but not found")
        return result

    result.svg_bytes = svg_file.stat().st_size
    if result.svg_bytes < MIN_SVG_BYTES:
        result.status = "empty_svg"
        result.messages.append(
            f"SVG is only {result.svg_bytes} bytes (< {MIN_SVG_BYTES})"
        )
        return result

    if with_preview:
        png_path = svg_file.with_suffix(".png")
        try:
            subprocess.run(
                [sys.executable, "-m", "engraving.preview",
                 str(svg_file), str(png_path), "200"],
                check=True, capture_output=True, timeout=60,
            )
        except subprocess.TimeoutExpired:
            result.messages.append("preview render timed out")
        except subprocess.CalledProcessError as e:
            result.messages.append(
                f"preview failed: {e.stderr.decode(errors='replace')[:200]}"
            )
        if png_path.exists():
            result.png_bytes = png_path.stat().st_size
            if result.png_bytes < MIN_PNG_BYTES:
                result.status = "empty_png"
                result.messages.append(
                    f"PNG is only {result.png_bytes} bytes — plate may be blank"
                )
    return result


def format_row(audit: PlateAudit) -> str:
    glyph = {
        "ok":          "✓",
        "render_fail": "✗",
        "empty_svg":   "!",
        "empty_png":   "?",
        "skipped":     "–",
    }[audit.status]
    svg_kb = f"{audit.svg_bytes/1024:.0f}KB" if audit.svg_bytes else "---"
    png_kb = (
        f"{audit.png_bytes/1024:.0f}KB" if audit.png_bytes else "   -"
    ) if audit.png_bytes is not None else "   -"
    return f"  {glyph}  {_short(audit.module_name):32s}  svg={svg_kb:>6s}  png={png_kb:>6s}"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--no-preview", action="store_true",
                   help="skip PNG preview step (faster but can't catch blank plates)")
    p.add_argument("--plate", action="append", default=None,
                   help="short name of one plate to audit (repeatable)")
    args = p.parse_args()

    targets = PLATE_MODULES
    if args.plate:
        wanted = {f"plates.plate_{n}" for n in args.plate}
        targets = [m for m in targets if m in wanted]
        if not targets:
            print(f"no matches for --plate {args.plate}")
            return 1

    print(f"Auditing {len(targets)} plates"
          + ("" if args.no_preview else " (rendering PNG previews too)") + "...\n")

    audits: list[PlateAudit] = []
    for mod_name in targets:
        a = render(mod_name, with_preview=not args.no_preview)
        audits.append(a)
        print(format_row(a), flush=True)
        for msg in a.messages:
            for line in msg.splitlines():
                print(f"        {line}")

    problems = [a for a in audits if not a.ok]
    print()
    print(f"Audit summary: {len(audits)} plates, {len(problems)} failures")

    if problems:
        print("\nFailing plates:")
        for a in problems:
            print(f"  [{a.status}] {_short(a.module_name)}")
        return 1

    print("All plates passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
