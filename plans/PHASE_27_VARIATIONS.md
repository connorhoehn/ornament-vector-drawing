# Phase 27 — Parametric variation generator

## Problem

Right now generating 10 palazzi variations requires running `./ornament generate palazzo --bays X --piano-nobile-order Y ... -o out/N.svg` ten times, tracking parameters by filename. No lineage, no easy comparison, no batch re-rendering.

A drafting office producing architectural catalogs wants: give me a base plan + a parameter sweep, emit N plates with consistent naming, build a numbered book.

## Goal

```bash
./ornament catalog --base palazzo.yaml --sweep bays:3,5,7 --sweep order:doric,ionic,corinthian -o out/catalog/
```

Produces a directory of 9 plates (3 × 3 combinations), each named deterministically, plus an index.md describing what parameter changed per plate.

## Plan — 4 days

### Day 1 — Base plan format

A YAML file that describes a `FacadePlan`:

```yaml
# palazzo.yaml
canvas: [22.75, 34.75, 231.25, 187.2]
stories:
  - height_ratio: 1.3
    wall: arcuated
    min_height_mm: 40
    label: ground
  - height_ratio: 1.4
    wall: bossed_smooth
    has_order: ionic
    label: piano_nobile
  - height_ratio: 0.85
    wall: smooth
    label: attic
bays:
  - openings: [...]
    pilasters: {order: ionic, width_frac: 0.08}
  # ... 5 bays total
parapet:
  kind: balustrade
  height_ratio: 0.25
  baluster_variant: tuscan
with_quoins: true
quoin_width_mm: 8.0
```

Reusing `plan_from_yaml` from Phase 26 for the parser. Each existing plate can export its plan via `plate.make_plan() → plan_to_yaml`.

### Day 2 — Parameter sweeps

```python
# engraving/planner/catalog.py
import itertools
from pathlib import Path
from typing import Iterator

from .io import plan_from_yaml, plan_to_yaml
from .plan import FacadePlan


def sweep_parameters(base_plan: FacadePlan, sweep_specs: dict) -> Iterator[tuple[dict, FacadePlan]]:
    """Given a base plan and a dict of {param_name: list_of_values}, yield
    each combination as a (label_dict, plan) pair.
    
    Supported sweep params:
      bays: int
      piano_nobile_order: order_name
      ground_wall: wall_variant
      quoin_width: float
    """
    keys = list(sweep_specs)
    for combo in itertools.product(*[sweep_specs[k] for k in keys]):
        label = dict(zip(keys, combo))
        plan = _apply_overrides(base_plan, label)
        yield label, plan


def _apply_overrides(base, label):
    # Deepcopy the plan, apply each override
    import copy
    p = copy.deepcopy(base)
    if "bays" in label:
        # Adjust bay count while preserving structure
        target = label["bays"]
        template = p.bays[0]  # use the first bay as a template
        central_template = p.bays[len(p.bays) // 2]  # use center for door bay
        center = target // 2
        p.bays = []
        for i in range(target):
            if i == center:
                p.bays.append(copy.deepcopy(central_template))
            else:
                p.bays.append(copy.deepcopy(template))
    if "piano_nobile_order" in label:
        for s in p.stories:
            if s.has_order is not None:
                s.has_order = label["piano_nobile_order"]
    if "ground_wall" in label:
        for s in p.stories:
            if s.wall in ("arcuated", "banded", "chamfered", "rock_faced"):
                s.wall = label["ground_wall"]
                break
    return p
```

### Day 3 — Renderer + index

```python
# engraving/planner/catalog.py (continued)
def render_catalog(base_plan: FacadePlan, sweep_specs: dict,
                    output_dir: Path) -> Path:
    """Render every combination and write an index."""
    from engraving.render import Page, frame
    from engraving.typography import title
    import config
    
    output_dir.mkdir(exist_ok=True)
    index_lines = ["# Catalog index\n"]
    
    for label, plan in sweep_parameters(base_plan, sweep_specs):
        # Deterministic name: sort label keys
        name_parts = [f"{k}={v}" for k, v in sorted(label.items())]
        name = "palazzo_" + "_".join(name_parts)
        
        try:
            facade = plan.solve()
        except Exception as e:
            index_lines.append(f"- **{name}** — INFEASIBLE: {e}\n")
            continue
        
        # Render
        page = Page()
        frame(page)
        title_text = ", ".join(f"{k}:{v}" for k, v in label.items())
        title(page, title_text, x=config.PLATE_W/2,
              y=config.FRAME_INSET + 10, font_size_mm=3.5,
              anchor="middle", stroke_width=config.STROKE_FINE)
        for pl, stroke in facade.render_strokes():
            page.polyline(pl, stroke_width=stroke)
        
        svg_path = output_dir / f"{name}.svg"
        # Save + embed plan (from Phase 26)
        from engraving.planner.io import embed_plan_in_svg
        text = page.d.as_svg()
        text = embed_plan_in_svg(text, plan)
        svg_path.write_text(text)
        
        index_lines.append(f"- **{name}** — {label}\n")
    
    (output_dir / "index.md").write_text("\n".join(index_lines))
    return output_dir
```

### Day 4 — CLI integration + book

Add `./ornament catalog` subcommand:

```python
def cmd_catalog(args):
    from engraving.planner.io import plan_from_yaml
    from engraving.planner.catalog import render_catalog
    from pathlib import Path
    
    base_yaml = Path(args.base).read_text()
    base_plan = plan_from_yaml(base_yaml)
    
    sweep_specs = {}
    for spec in args.sweep:
        key, values = spec.split(":")
        values = values.split(",")
        # Try int/float conversion
        parsed = []
        for v in values:
            try: parsed.append(int(v))
            except ValueError:
                try: parsed.append(float(v))
                except ValueError: parsed.append(v)
        sweep_specs[key] = parsed
    
    out_dir = Path(args.output or "out/catalog")
    render_catalog(base_plan, sweep_specs, out_dir)
    print(f"Catalog: {out_dir}")
```

Also: `./ornament catalog-book out/catalog -o out/catalog_book.pdf` — concatenates all catalog SVGs into one bound PDF with a title page.

## Acceptance criteria

- Running `./ornament catalog --base palazzo.yaml --sweep bays:3,5,7` produces 3 SVGs in `out/catalog/`
- Each SVG has the plan embedded (Phase 26 integration)
- `index.md` lists every plate with its parameter label
- Infeasible combinations are listed in index.md but don't halt the batch
- `./ornament catalog-book` produces a single bound PDF

## Effort

~4 days. Day 1 (YAML format + reuse of Phase 26 parsing) is fast. Day 2 (sweep semantics) has edge cases. Day 3 is boilerplate. Day 4 is CLI wiring.

## Forward work

Once this ships:
- Generate "morphology studies" automatically: facade proportions over 10 bay counts at a fixed total width, seeing where the solver breaks
- Share templates — a `templates/` directory of YAML files representing specific palazzi (Palazzo Farnese, Farnesina, etc.) that reproduce canonical works
- A `docs/CATALOG_EXAMPLES.md` showing every major variation
