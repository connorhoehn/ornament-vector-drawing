"""Parametric variation catalog — generate N plates from one declarative
base plan plus a set of parameter sweeps.

    ./ornament catalog --base palazzo.yaml \\
        --sweep bays:3,5,7 --sweep piano_nobile_order:doric,ionic \\
        -o out/catalog/

produces 6 plates (3 bay-counts × 2 orders) each named deterministically,
plus an ``index.md`` mapping name → parameter label, plus the
un-expanded ``base.yaml`` so the run is reproducible.

Infeasible combinations (e.g. 3 bays at a very small canvas that can't
fit three arched doors) are recorded in the index but don't halt the
batch.

Supported sweep keys in v1:
    bays                — int; expands / contracts ``plan.bays`` uniformly
    piano_nobile_order  — order name; sets the ordered story's has_order
    ground_wall         — wall variant on the ground (lowest) story
    parapet_kind        — "balustrade" | "attic" | "cornice" | "none"
    plinth_kind         — "smooth" | "banded" | "chamfered" | "none"
    quoins              — "yes" | "no"

Unknown sweep keys are rejected upfront so typos don't silently fail.
"""
from __future__ import annotations

import copy
import itertools
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Iterator

from .plan import (
    FacadePlan, BayPlan, OpeningPlan, ParapetPlan, PlinthPlan, PilasterPlan,
    StoryPlan, PlanInfeasible,
)


SUPPORTED_SWEEP_KEYS = frozenset({
    "bays",
    "piano_nobile_order",
    "ground_wall",
    "parapet_kind",
    "plinth_kind",
    "quoins",
})


class UnknownSweepKey(ValueError):
    """Raised when a sweep spec names a parameter the catalog doesn't
    know how to apply. Points at typos early."""


def validate_sweep_keys(keys: Iterable[str]) -> None:
    unknown = [k for k in keys if k not in SUPPORTED_SWEEP_KEYS]
    if unknown:
        raise UnknownSweepKey(
            f"unknown sweep key(s): {unknown}. "
            f"supported: {sorted(SUPPORTED_SWEEP_KEYS)}"
        )


def _parse_scalar(v: str):
    """Try int → float → keep as str. Catalog CLI values arrive as strings."""
    try:
        return int(v)
    except ValueError:
        try:
            return float(v)
        except ValueError:
            return v


def parse_sweep_spec(specs: Iterable[str]) -> dict[str, list]:
    """Turn CLI-form strings ("bays:3,5,7") into a {key: [values]} dict.

    Values are coerced to int / float when they parse cleanly, else left
    as strings.
    """
    out: dict[str, list] = {}
    for s in specs:
        if ":" not in s:
            raise ValueError(f"sweep spec must be 'key:val1,val2,...': {s!r}")
        key, vals = s.split(":", 1)
        key = key.strip()
        value_list = [_parse_scalar(v.strip()) for v in vals.split(",")]
        out[key] = value_list
    validate_sweep_keys(out.keys())
    return out


def sweep_combinations(sweep: dict[str, list]) -> Iterator[dict]:
    """Yield each Cartesian combination of sweep values as a label dict."""
    keys = list(sweep)
    for combo in itertools.product(*[sweep[k] for k in keys]):
        yield dict(zip(keys, combo))


def apply_overrides(base_plan: FacadePlan, overrides: dict) -> FacadePlan:
    """Produce a deep copy of base_plan with sweep overrides applied.

    Each override mutates the plan structure in a documented way:
      * ``bays`` uniformly re-tiles bays around the centre door bay
      * ``piano_nobile_order`` sets has_order on the first ordered story
      * ``ground_wall`` overrides the lowest story's wall variant
      * ``parapet_kind`` switches or drops the parapet
      * ``plinth_kind`` swaps / drops the plinth
      * ``quoins`` = "yes"/"no"/True/False toggles corner quoins
    """
    plan = copy.deepcopy(base_plan)

    if "bays" in overrides:
        target = int(overrides["bays"])
        if target < 1:
            raise ValueError(f"bays must be >= 1, got {target}")
        if not plan.bays:
            raise ValueError("base plan has zero bays; cannot scale")
        centre_idx = len(plan.bays) // 2
        centre_template = plan.bays[centre_idx]
        # First non-centre bay becomes the side template.
        side_template = next(
            (b for i, b in enumerate(plan.bays) if i != centre_idx),
            plan.bays[0],
        )
        new_centre = target // 2
        new_bays: list[BayPlan] = []
        for i in range(target):
            if i == new_centre:
                new_bays.append(copy.deepcopy(centre_template))
            else:
                b = copy.deepcopy(side_template)
                b.label = f"bay_{i}"
                new_bays.append(b)
        plan.bays = new_bays

    if "piano_nobile_order" in overrides:
        order = overrides["piano_nobile_order"]
        # Find the first story that already has_order set (the "ordered"
        # story) and swap it. Fall back to the middle story if none do.
        target_story: StoryPlan | None = None
        for s in plan.stories:
            if s.has_order is not None:
                target_story = s
                break
        if target_story is None and plan.stories:
            target_story = plan.stories[len(plan.stories) // 2]
        if target_story is not None:
            target_story.has_order = order
        # Also update pilaster order on every bay so they agree.
        for b in plan.bays:
            if b.pilasters is not None:
                b.pilasters.order = order

    if "ground_wall" in overrides:
        wall = overrides["ground_wall"]
        if plan.stories:
            plan.stories[0].wall = wall

    if "parapet_kind" in overrides:
        kind = overrides["parapet_kind"]
        if kind == "none":
            plan.parapet = None
        else:
            existing = plan.parapet or ParapetPlan()
            plan.parapet = replace(existing, kind=kind)

    if "plinth_kind" in overrides:
        kind = overrides["plinth_kind"]
        if kind == "none":
            plan.plinth = None
        else:
            existing = plan.plinth or PlinthPlan()
            plan.plinth = replace(existing, kind=kind)

    if "quoins" in overrides:
        val = overrides["quoins"]
        if isinstance(val, str):
            val = val.lower() in ("yes", "true", "1", "on")
        plan.with_quoins = bool(val)

    return plan


def catalog_name(overrides: dict, *, prefix: str = "palazzo") -> str:
    """Deterministic filename for a set of overrides. Sorted keys so a
    given label always lands in the same file."""
    parts = [f"{k}={overrides[k]}" for k in sorted(overrides)]
    stem = "_".join(parts).replace("/", "-")
    return f"{prefix}__{stem}" if stem else prefix


def render_catalog(
    base_plan: FacadePlan,
    sweep: dict[str, list],
    output_dir: Path,
    *,
    prefix: str = "palazzo",
    write_index: bool = True,
) -> dict:
    """Iterate every combination, render each to ``output_dir/<name>.svg``,
    and write an ``index.md`` listing every plate with its parameter
    label and infeasibility reason (if any). Returns a summary dict.

    Infeasible combinations are recorded but don't halt the batch; the
    caller can inspect the returned summary for failures.
    """
    from engraving.render import Page, frame
    from engraving.typography import title
    from engraving.planner.io import embed_plan_in_svg, plan_to_yaml
    import config as _cfg

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "base.yaml").write_text(plan_to_yaml(base_plan))

    summary = {"total": 0, "ok": [], "infeasible": []}
    index_rows: list[str] = [
        "# Catalog index",
        "",
        f"Base plan saved as `base.yaml` ({len(base_plan.bays)} bays, "
        f"{len(base_plan.stories)} stories).",
        "",
        f"Sweep: " + ", ".join(
            f"**{k}** ∈ {{{', '.join(str(v) for v in vs)}}}"
            for k, vs in sweep.items()
        ),
        "",
        "| plate | label | status |",
        "|---|---|---|",
    ]

    for overrides in sweep_combinations(sweep):
        summary["total"] += 1
        name = catalog_name(overrides, prefix=prefix)
        label_str = ", ".join(f"{k}={v}" for k, v in overrides.items())
        try:
            plan = apply_overrides(base_plan, overrides)
            facade = plan.solve()
        except PlanInfeasible as e:
            summary["infeasible"].append({"name": name, "label": overrides,
                                           "reason": e.reason})
            index_rows.append(f"| {name} | {label_str} | ⚠️ infeasible: {e.reason} |")
            continue
        except (ValueError, KeyError) as e:
            summary["infeasible"].append({"name": name, "label": overrides,
                                           "reason": str(e)})
            index_rows.append(f"| {name} | {label_str} | ⚠️ error: {e} |")
            continue

        page = Page()
        frame(page)
        title(page, f"Palazzo — {label_str}",
              x=_cfg.PLATE_W / 2, y=_cfg.FRAME_INSET + 10,
              font_size_mm=3.5, anchor="middle",
              stroke_width=_cfg.STROKE_FINE)
        for pl, stroke in facade.render_strokes():
            page.polyline(pl, stroke_width=stroke)

        svg_path = output_dir / f"{name}.svg"
        svg_text = page.d.as_svg()
        svg_text = embed_plan_in_svg(svg_text, plan)
        svg_path.write_text(svg_text)

        summary["ok"].append({"name": name, "label": overrides,
                               "path": str(svg_path)})
        index_rows.append(f"| {name} | {label_str} | ok |")

    if write_index:
        (output_dir / "index.md").write_text("\n".join(index_rows) + "\n")

    return summary
