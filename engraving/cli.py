"""CLI entry point for the ornament-vector-drawing pipeline."""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

# Make sure the package root is on sys.path
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

PLATES = {
    "01":             "plates.plate_01",
    "blocking-course": "plates.plate_blocking_course",
    "portico":        "plates.plate_portico",
    "doric":          "plates.plate_doric",
    "ionic":          "plates.plate_ionic",
    "corinthian":     "plates.plate_corinthian",
    "composite":      "plates.plate_composite",
    "five-orders":    "plates.plate_five_orders",
    "greek-orders":   "plates.plate_greek_orders",
    "schematic":      "plates.plate_schematic",
    # Optional new ones — check at runtime
    "arcade":         "plates.plate_arcade",
    "cartouche":      "plates.plate_cartouche",
    "stairs":         "plates.plate_stairs",
    "rinceau":        "plates.plate_rinceau",
    "palazzo":        "plates.plate_palazzo_plan",
    "ornament":       "plates.plate_ornament",
    "grand-stair":    "plates.plate_grand_stair",
}


def _available_plates() -> dict[str, str]:
    """Return plate dict filtered to only those whose modules exist."""
    out = {}
    for name, mod in PLATES.items():
        try:
            importlib.import_module(mod)
            out[name] = mod
        except ImportError:
            continue
    return out


def cmd_list(args) -> int:
    avail = _available_plates()
    print(f"{len(avail)} plates available:")
    for name in sorted(avail):
        print(f"  {name:20s} -> {avail[name]}")
    return 0


def cmd_render(args) -> int:
    avail = _available_plates()
    if args.all:
        targets = list(avail.keys())
    elif args.name:
        if args.name not in avail:
            print(f"unknown plate: {args.name!r}. Use `list` to see options.")
            return 2
        targets = [args.name]
    else:
        print("specify a plate name or --all")
        return 2

    total = 0
    for name in targets:
        mod = importlib.import_module(avail[name])
        if hasattr(mod, "build_validated"):
            svg, report = mod.build_validated()
            err_count = len(report)
            print(f"{name}: {svg}  ({err_count} validation errors)")
            for e in report:
                print(f"    - {e}")
        else:
            svg = mod.build()
            print(f"{name}: {svg}")
        total += 1
    print(f"\nRendered {total} plate(s).")
    return 0


def cmd_validate(args) -> int:
    avail = _available_plates()
    if args.all:
        targets = list(avail.keys())
    elif args.name:
        targets = [args.name]
    else:
        targets = list(avail.keys())

    total_errors = 0
    for name in targets:
        mod = importlib.import_module(avail[name])
        if not hasattr(mod, "build_validated"):
            print(f"{name}: no build_validated (skipping)")
            continue
        svg, report = mod.build_validated()
        total_errors += len(report)
        status = "\u2713" if not len(report) else f"\u26a0 {len(report)} errors"
        print(f"{name}: {status}")
        for e in report:
            print(f"    - {e}")
    print(f"\nTotal: {total_errors} error(s) across {len(targets)} plates")
    return 0 if total_errors == 0 else 1


def cmd_debug(args) -> int:
    """Render a plate's SVG + an overlay of constraint violations.

    Prefers the plan-based path (``make_plan`` + ``FacadePlan.solve``) when
    available; falls back to the legacy Scene-based debug if the plate
    exposes ``build_validated_with_scene``.
    """
    avail = _available_plates()
    if args.name not in avail:
        print(f"unknown plate: {args.name!r}. Use `list` to see options.")
        return 2
    mod = importlib.import_module(avail[args.name])

    # Preferred: plan-based debug
    if hasattr(mod, "make_plan"):
        plan = mod.make_plan()
        print(plan.explain())
        print()

        # Render the base SVG — prefer build_validated, fall back to build
        if hasattr(mod, "build_validated"):
            svg_path, _ = mod.build_validated()
        else:
            svg_path = mod.build()
        svg_path = Path(svg_path)

        # Solve the plan to get an Element tree
        try:
            facade = plan.solve()
        except Exception as e:
            print(f"solve failed: {e}")
            return 1

        # Collect aesthetic (Layer C) violations too
        extra: list = []
        try:
            from engraving.validate.aesthetic import check_aesthetic
            extra.extend(check_aesthetic(facade))
        except Exception:
            pass

        from engraving.planner.debug import render_debug
        debug_path = svg_path.with_name(svg_path.stem + "_debug.svg")
        render_debug(facade, svg_path, debug_path, extra_violations=extra)
        print(f"debug SVG: {debug_path}")

        # PNG preview
        try:
            from engraving.preview import render_svg_to_png
            png_path = debug_path.with_suffix(".png")
            render_svg_to_png(debug_path, png_path, dpi=200)
            print(f"debug PNG: {png_path}")
        except Exception as e:
            print(f"(PNG render skipped: {e})")
        return 0

    # Fall back to legacy Scene-based debug
    if hasattr(mod, "build_validated_with_scene"):
        svg_path, scene = mod.build_validated_with_scene()
        svg_path = Path(svg_path)
        debug_path = svg_path.with_name(svg_path.stem + "_debug.svg")
        scene.render_debug(svg_path, debug_path)
        print(f"Debug overlay: {debug_path}")
        try:
            from engraving.preview import render_svg_to_png
            png_path = debug_path.with_suffix(".png")
            render_svg_to_png(debug_path, png_path, dpi=200)
            print(f"PNG: {png_path}")
        except Exception as e:
            print(f"(PNG render skipped: {e})")
        return 0

    print(f"{args.name}: no debug support "
          f"(needs make_plan or build_validated_with_scene)")
    return 0


def cmd_catalog(args) -> int:
    """Parametric variation sweep — render N plates from a base plan."""
    from pathlib import Path
    from engraving.planner.catalog import (
        parse_sweep_spec, render_catalog, UnknownSweepKey,
    )
    from engraving.planner.io import plan_from_yaml, extract_plan_from_svg

    base_path = Path(args.base)
    if not base_path.exists():
        print(f"base not found: {base_path}")
        return 2

    # Accept either a YAML plan file or an SVG with an embedded plan.
    if base_path.suffix == ".svg":
        base_plan = extract_plan_from_svg(base_path)
        if base_plan is None:
            print(f"no embedded plan in {base_path} (needs Phase-26 metadata)")
            return 2
    else:
        base_plan = plan_from_yaml(base_path.read_text())

    try:
        sweep = parse_sweep_spec(args.sweep)
    except (ValueError, UnknownSweepKey) as e:
        print(f"invalid --sweep: {e}")
        return 2

    if not sweep:
        print("no --sweep specified; nothing to render. "
              "Example: --sweep bays:3,5,7")
        return 2

    out_dir = Path(args.output_dir)
    summary = render_catalog(base_plan, sweep, out_dir, prefix=args.prefix)
    print(
        f"catalog: {len(summary['ok'])} ok, "
        f"{len(summary['infeasible'])} infeasible "
        f"(of {summary['total']} combinations) -> {out_dir}"
    )
    return 0


def cmd_generate(args) -> int:
    """Generate a parametric plate (currently: palazzo)."""
    if args.kind != "palazzo":
        print(f"unknown kind: {args.kind!r}; try 'palazzo'")
        return 2

    from pathlib import Path
    from engraving.planner import (
        FacadePlan, StoryPlan, BayPlan, OpeningPlan, ParapetPlan, PilasterPlan,
        PlanInfeasible,
    )
    from engraving.render import Page, frame
    from engraving.typography import title
    import config

    # Build a plan from CLI args
    margin_x = config.FRAME_INSET + 6
    top_margin = config.FRAME_INSET + 22
    bottom_margin = config.FRAME_INSET + 16

    ground_wall = args.ground_wall   # "smooth" | "banded" | "arcuated" | etc.
    piano_order = args.piano_nobile_order
    parapet_kind = args.parapet
    n_bays = args.bays

    plan = FacadePlan(
        canvas=(margin_x, top_margin,
                config.PLATE_W - margin_x,
                config.PLATE_H - bottom_margin),
        stories=[
            StoryPlan(height_ratio=1.3, wall=ground_wall, label="ground"),
            StoryPlan(height_ratio=1.4, wall="smooth", has_order=piano_order,
                      label="piano_nobile"),
            StoryPlan(height_ratio=0.85, wall="smooth", label="attic"),
        ],
        bays=[],
        parapet=ParapetPlan(kind=parapet_kind, height_ratio=0.25,
                             baluster_variant="tuscan") if parapet_kind != "none" else None,
    )

    # Central bay is the entry door
    central = n_bays // 2
    for i in range(n_bays):
        is_central = (i == central)
        if is_central:
            plan.bays.append(BayPlan(
                openings=[
                    OpeningPlan(kind="arch_door", width_frac=0.55,
                                 height_frac=0.40, has_keystone=True),
                    OpeningPlan(kind="window", width_frac=0.42,
                                 height_frac=0.50, hood="triangular",
                                 has_keystone=True),
                    OpeningPlan(kind="window", width_frac=0.30,
                                 height_frac=0.40, hood="cornice"),
                ],
                pilasters=PilasterPlan(order=piano_order, width_frac=0.08),
                width_weight=1.2, label="entry",
            ))
        else:
            hood = "triangular" if i % 2 == 0 else "segmental"
            plan.bays.append(BayPlan(
                openings=[
                    OpeningPlan(kind="arch_window", width_frac=0.55,
                                 height_frac=0.25, has_keystone=True),
                    OpeningPlan(kind="window", width_frac=0.38,
                                 height_frac=0.46, hood=hood,
                                 has_keystone=True),
                    OpeningPlan(kind="window", width_frac=0.30,
                                 height_frac=0.40, hood="cornice"),
                ],
                pilasters=PilasterPlan(order=piano_order, width_frac=0.08),
                label=f"bay_{i}",
            ))

    try:
        facade = plan.solve()
    except PlanInfeasible as e:
        print(f"PLAN INFEASIBLE: {e}")
        return 1

    # Render
    page = Page()
    frame(page)
    # Title
    title_text = f"PALAZZO \u2014 {n_bays} BAYS, {piano_order.upper()} PIANO NOBILE"
    title(page, title_text, x=config.PLATE_W / 2,
          y=config.FRAME_INSET + 10, font_size_mm=4.0, anchor="middle",
          stroke_width=config.STROKE_FINE)

    for pl, stroke in facade.render_strokes():
        page.polyline(pl, stroke_width=stroke)

    # Scale bar
    cap_y = config.PLATE_H - config.FRAME_INSET - 6
    page.polyline([(config.PLATE_W/2 - 25, cap_y),
                    (config.PLATE_W/2 + 25, cap_y)],
                   stroke_width=config.STROKE_FINE)
    for i in range(6):
        x = config.PLATE_W/2 - 25 + i * 10
        page.polyline([(x, cap_y-1.5), (x, cap_y)],
                       stroke_width=config.STROKE_HAIRLINE)
    page.text("50 mm", x=config.PLATE_W/2, y=cap_y+4,
              font_size=2.4, anchor="middle")

    # Save — embed the FacadePlan as YAML metadata so the SVG can be reloaded.
    from engraving.planner.io import embed_plan_in_svg
    out_path = Path(args.output)
    svg_text = page.d.as_svg()
    svg_text = embed_plan_in_svg(svg_text, plan)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(svg_text)
    print(f"SVG: {out_path}")

    if args.preview:
        from engraving.preview import render_svg_to_png
        png = out_path.with_suffix(".png")
        render_svg_to_png(out_path, png, dpi=200)
        print(f"PNG: {png}")

    return 0


def cmd_reload(args) -> int:
    """Reload an SVG's embedded plan, apply overrides, re-render."""
    from pathlib import Path
    from engraving.planner.io import extract_plan_from_svg

    svg_path = Path(args.svg_path)
    if not svg_path.exists():
        print(f"SVG not found: {svg_path}")
        return 1

    plan = extract_plan_from_svg(svg_path)
    if plan is None:
        print(f"No embedded plan in {svg_path}")
        return 1

    # Apply overrides
    if args.piano_nobile_order is not None:
        for s in plan.stories:
            if s.has_order is not None:
                s.has_order = args.piano_nobile_order
        # Also update any bay pilasters that reference an order
        for bay in plan.bays:
            if bay.pilasters is not None:
                bay.pilasters.order = args.piano_nobile_order

    if args.ground_wall is not None:
        # Override the ground (first) story's wall
        if plan.stories:
            plan.stories[0].wall = args.ground_wall

    if args.bays is not None:
        # Rebuild bays list to the target count. Preserve the template
        # of the first non-central bay + central bay.
        import copy
        n = args.bays
        if n < 1:
            print(f"bays must be >= 1; got {n}")
            return 2

        if len(plan.bays) == 0:
            print("cannot re-bay a plan with no bays")
            return 1

        central_idx_old = len(plan.bays) // 2
        central_template = copy.deepcopy(plan.bays[central_idx_old])
        side_template = copy.deepcopy(plan.bays[0 if central_idx_old > 0 else 0])

        new_bays = []
        new_central = n // 2
        for i in range(n):
            if i == new_central:
                new_bays.append(copy.deepcopy(central_template))
            else:
                new_bays.append(copy.deepcopy(side_template))
        plan.bays = new_bays

    # Re-solve
    from engraving.planner.plan import PlanInfeasible
    try:
        facade = plan.solve()
    except PlanInfeasible as e:
        print(f"PLAN INFEASIBLE after overrides: {e}")
        return 1

    # Re-render
    from engraving.render import Page, frame
    from engraving.typography import title
    import config

    page = Page()
    frame(page)
    title(page, "RELOADED PALAZZO",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 10,
          font_size_mm=4.5, anchor="middle",
          stroke_width=config.STROKE_FINE)

    for pl, stroke in facade.render_strokes():
        page.polyline(pl, stroke_width=stroke)

    # Scale bar
    cap_y = config.PLATE_H - config.FRAME_INSET - 6
    page.polyline([(config.PLATE_W/2 - 25, cap_y),
                   (config.PLATE_W/2 + 25, cap_y)],
                  stroke_width=config.STROKE_FINE)
    for i in range(6):
        x = config.PLATE_W/2 - 25 + i * 10
        page.polyline([(x, cap_y - 1.5), (x, cap_y)],
                      stroke_width=config.STROKE_HAIRLINE)
    page.text("50 mm", x=config.PLATE_W/2, y=cap_y + 4,
              font_size=2.4, anchor="middle")

    # Save
    out = Path(args.output) if args.output else svg_path
    out.parent.mkdir(parents=True, exist_ok=True)
    saved = page.save_svg_with_plan(out.stem, plan)
    # save_svg_with_plan writes under config.OUT_DIR; move if needed
    if Path(saved).resolve() != out.resolve():
        import shutil
        shutil.move(str(saved), str(out))

    print(f"Reloaded SVG: {out}")
    if args.preview:
        from engraving.preview import render_svg_to_png
        png_path = out.with_suffix(".png")
        render_svg_to_png(out, png_path, dpi=200)
        print(f"PNG: {png_path}")
    return 0


def cmd_book(args) -> int:
    from engraving.export import render_plate_to_print, concat_pdfs
    avail = _available_plates()
    out_dir = Path(args.output).parent if args.output else Path("out")
    out_dir.mkdir(exist_ok=True)

    pdfs = []
    for name in sorted(avail):
        print(f"=== {name} ===")
        mod = importlib.import_module(avail[name])
        if hasattr(mod, "build_validated"):
            svg, _ = mod.build_validated()
        else:
            svg = mod.build()
        result = render_plate_to_print(svg, optimize=args.optimize,
                                       export_pdf=True)
        pdfs.append(result["pdf"])

    book_path = Path(args.output or "out/engraving_book.pdf")
    concat_pdfs(pdfs, book_path)
    print(f"\n\u2713 {book_path} ({book_path.stat().st_size / 1024:.1f} KB, {len(pdfs)} pages)")
    return 0


def main(argv: list[str] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ornament",
        description="Generate 18th-c. engraved architectural plates.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list available plate recipes")
    p_list.set_defaults(fn=cmd_list)

    p_render = sub.add_parser("render", help="render a plate to SVG")
    p_render.add_argument("name", nargs="?", help="plate name (e.g. 'portico')")
    p_render.add_argument("--all", action="store_true", help="render every plate")
    p_render.set_defaults(fn=cmd_render)

    p_validate = sub.add_parser("validate", help="run validators")
    p_validate.add_argument("name", nargs="?", help="plate name")
    p_validate.add_argument("--all", action="store_true", help="validate every plate")
    p_validate.set_defaults(fn=cmd_validate)

    p_book = sub.add_parser("book", help="build bound multi-plate PDF")
    p_book.add_argument("-o", "--output", default="out/engraving_book.pdf")
    p_book.add_argument("--optimize", action="store_true", help="run vpype path optimization")
    p_book.set_defaults(fn=cmd_book)

    p_debug = sub.add_parser(
        "debug", help="render plate with constraint failures overlaid"
    )
    p_debug.add_argument("name")
    p_debug.set_defaults(fn=cmd_debug)

    p_generate = sub.add_parser("generate", help="procedurally generate a plate")
    p_generate.add_argument("kind", choices=["palazzo"], help="what to generate")
    p_generate.add_argument("--bays", type=int, default=5,
                             help="number of bays (odd recommended)")
    p_generate.add_argument("--piano-nobile-order", default="ionic",
                             choices=["tuscan", "doric", "ionic", "corinthian", "composite"])
    p_generate.add_argument("--ground-wall", default="arcuated",
                             choices=["smooth", "banded", "arcuated", "chamfered",
                                      "rock_faced", "vermiculated"])
    p_generate.add_argument("--parapet", default="balustrade",
                             choices=["balustrade", "attic", "cornice", "none"])
    p_generate.add_argument("-o", "--output", default="out/generated_palazzo.svg")
    p_generate.add_argument("--preview", action="store_true",
                             help="also render PNG preview")
    p_generate.set_defaults(fn=cmd_generate)

    p_catalog = sub.add_parser(
        "catalog",
        help="parametric variation sweep — N plates from one base plan",
    )
    p_catalog.add_argument(
        "--base", required=True,
        help="base plan: either an .svg with embedded plan (Phase 26) "
             "or a .yaml plan file")
    p_catalog.add_argument(
        "--sweep", action="append", default=[],
        help="sweep spec 'key:val1,val2,val3'; repeat for multi-axis sweep. "
             "supported keys: bays, piano_nobile_order, ground_wall, "
             "parapet_kind, plinth_kind, quoins")
    p_catalog.add_argument("-o", "--output-dir", default="out/catalog/")
    p_catalog.add_argument("--prefix", default="palazzo",
                            help="filename prefix for each generated plate")
    p_catalog.set_defaults(fn=cmd_catalog)

    p_reload = sub.add_parser(
        "reload", help="reload an SVG's embedded plan, override, re-render")
    p_reload.add_argument("svg_path", help="path to the SVG with embedded plan")
    p_reload.add_argument("--bays", type=int, default=None)
    p_reload.add_argument("--piano-nobile-order", default=None,
                           choices=["tuscan", "doric", "ionic", "corinthian", "composite"])
    p_reload.add_argument("--ground-wall", default=None,
                           choices=["smooth", "banded", "arcuated", "chamfered",
                                    "rock_faced", "vermiculated", "bossed_smooth"])
    p_reload.add_argument("-o", "--output", default=None)
    p_reload.add_argument("--preview", action="store_true")
    p_reload.set_defaults(fn=cmd_reload)

    args = parser.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
