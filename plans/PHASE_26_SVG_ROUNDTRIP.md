# Phase 26 — SVG ↔ FacadePlan roundtrip

## Problem

Right now a plate's lineage is one-way: `plate_palazzo_plan.py` (code) → `FacadePlan` (data) → Element tree → SVG (output). Once rendered, the plan is discarded. Can't:

- Load an SVG and get back the plan that produced it
- Edit an SVG's embedded parameters without re-running the CLI
- Diff two plates and see WHAT parameter changed (only raw polyline-level diffs)

A plate that is reproducible *from the SVG itself* is a plate that's durable. You can share an SVG, someone else opens it, sees the plan metadata, understands the design intent, iterates.

## Goal

- Serialize `FacadePlan` as YAML/JSON inside an SVG `<metadata>` block
- `load_plan_from_svg(path) → FacadePlan` reconstructs the plan
- CLI `./ornament reload palazzo.svg --bays 7` edits the embedded plan and re-renders

## Plan — 3 days

### Day 1 — Serialization

`FacadePlan`, `StoryPlan`, `BayPlan`, `OpeningPlan`, `ParapetPlan`, `PilasterPlan` are all `@dataclass`es. Use `dataclasses.asdict` + PyYAML.

```python
# engraving/planner/io.py
import yaml
from dataclasses import asdict, fields
from .plan import (FacadePlan, StoryPlan, BayPlan, OpeningPlan,
                    ParapetPlan, PilasterPlan)


def plan_to_yaml(plan: FacadePlan) -> str:
    """Serialize a FacadePlan to YAML string."""
    return yaml.safe_dump(asdict(plan), sort_keys=False, default_flow_style=False)


def plan_from_yaml(yaml_text: str) -> FacadePlan:
    """Deserialize YAML back to FacadePlan."""
    raw = yaml.safe_load(yaml_text)
    # Reconstruct nested dataclasses
    def mkparapet(d): return ParapetPlan(**d) if d else None
    def mkpilaster(d): return PilasterPlan(**d) if d else None
    def mkopening(d): return OpeningPlan(**d)
    def mkbay(d): return BayPlan(
        openings=[mkopening(o) for o in d["openings"]],
        pilasters=mkpilaster(d.get("pilasters")),
        width_weight=d.get("width_weight", 1.0),
        label=d.get("label", ""),
    )
    def mkstory(d): return StoryPlan(**d)
    return FacadePlan(
        canvas=tuple(raw["canvas"]),
        stories=[mkstory(s) for s in raw["stories"]],
        bays=[mkbay(b) for b in raw["bays"]],
        parapet=mkparapet(raw.get("parapet")),
        with_quoins=raw.get("with_quoins", False),
        quoin_width_mm=raw.get("quoin_width_mm", 8.0),
        custom_constraints=raw.get("custom_constraints", []),
    )


def embed_plan_in_svg(svg_text: str, plan: FacadePlan) -> str:
    """Inject a <metadata> block with plan YAML into an SVG."""
    yaml_text = plan_to_yaml(plan)
    metadata_block = (
        '<metadata id="facade-plan">\n'
        '<!-- FacadePlan (YAML) -->\n'
        '<![CDATA[\n'
        f'{yaml_text}'
        ']]>\n'
        '</metadata>\n'
    )
    if "</svg>" in svg_text:
        svg_text = svg_text.replace("</svg>", metadata_block + "</svg>", 1)
    return svg_text


def extract_plan_from_svg(svg_path: str | Path) -> FacadePlan | None:
    """Read an SVG file and return the FacadePlan stored in its metadata.
    Returns None if no embedded plan."""
    from pathlib import Path
    import re
    text = Path(svg_path).read_text()
    m = re.search(
        r'<metadata[^>]*id="facade-plan"[^>]*>.*?<!\[CDATA\[(.*?)\]\]>.*?</metadata>',
        text, re.DOTALL,
    )
    if not m:
        return None
    return plan_from_yaml(m.group(1))
```

### Day 2 — Wire into rendering

All plate `build_validated()` functions should embed the plan:

```python
# In plate_palazzo_plan.py build_validated:
from engraving.planner.io import embed_plan_in_svg

def build_validated():
    ...
    svg_path = str(page.save_svg("plate_palazzo_plan"))
    # Embed plan for roundtrip
    from pathlib import Path
    text = Path(svg_path).read_text()
    text = embed_plan_in_svg(text, plan)
    Path(svg_path).write_text(text)
    ...
```

Expose a helper in `Page.save_svg_with_plan(name, plan)` so callers don't have to do the post-write edit.

### Day 3 — CLI `reload` command

```bash
./ornament reload out/plate_palazzo_plan.svg --bays 7 --piano-nobile-order corinthian
```

Loads the embedded plan, applies overrides, resolves, re-renders.

```python
def cmd_reload(args):
    from engraving.planner.io import extract_plan_from_svg, embed_plan_in_svg
    from engraving.render import Page, frame
    
    plan = extract_plan_from_svg(args.svg_path)
    if plan is None:
        print(f"No embedded plan in {args.svg_path}")
        return 1
    
    # Apply overrides
    if args.bays is not None:
        # More complex: rebuild bays list to target count
        ...  # use the helpers from cmd_generate
    if args.piano_nobile_order is not None:
        for s in plan.stories:
            if s.has_order is not None:
                s.has_order = args.piano_nobile_order
    
    # Re-solve + re-render
    facade = plan.solve()
    page = Page()
    frame(page)
    for pl, stroke in facade.render_strokes():
        page.polyline(pl, stroke_width=stroke)
    # Save (overwriting or to a new path)
    out = args.output or args.svg_path
    ...  # save + re-embed
    return 0
```

Tests:

```python
def test_plan_roundtrip():
    p1 = FacadePlan(canvas=(0,0,200,150), ..., parapet=ParapetPlan(kind="balustrade"))
    text = plan_to_yaml(p1)
    p2 = plan_from_yaml(text)
    assert p1 == p2


def test_embed_and_extract():
    p = FacadePlan(...)
    page = Page()
    svg = page.save_svg("test_roundtrip")
    import pathlib
    current = pathlib.Path(svg).read_text()
    new_text = embed_plan_in_svg(current, p)
    pathlib.Path(svg).write_text(new_text)
    extracted = extract_plan_from_svg(svg)
    assert extracted == p
```

## Acceptance criteria

- Every `plate_*.svg` embeds its plan as `<metadata>` YAML
- `extract_plan_from_svg()` returns the exact `FacadePlan` used
- `./ornament reload <svg> --bays N` regenerates with a new bay count
- YAML is diffable (sorted keys, no timestamp noise)

## Effort

~3 days. Day 3 (CLI) is the trickiest because the override semantics for `--bays N` requires regenerating the bay list, which isn't just a field swap.

## Forward application

Once plans are in the SVG, we get for free:
- `./ornament lineage plate.svg` — print the plan
- `./ornament diff plate_a.svg plate_b.svg` — show parameter differences
- Git history of SVGs becomes semantic: `git diff` shows the plan yaml change, not opaque polyline reordering
