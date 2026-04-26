"""Serialize FacadePlan to/from YAML; embed in SVG metadata; extract.

Enables SVGs to be self-describing: the plate file's plan is preserved as
YAML inside the SVG's <metadata> block, so any rendered SVG can be opened,
parsed, and re-rendered deterministically.
"""
from __future__ import annotations

import re
from dataclasses import is_dataclass
from pathlib import Path

import yaml

from .plan import (FacadePlan, StoryPlan, BayPlan, OpeningPlan,
                   ParapetPlan, PilasterPlan)


def plan_to_yaml(plan: FacadePlan) -> str:
    """Serialize a FacadePlan to a YAML string."""
    raw = _to_dict(plan)
    return yaml.safe_dump(raw, sort_keys=False, default_flow_style=False)


def _to_dict(obj):
    """Recursively convert dataclasses to dicts, preserving None for
    optional fields."""
    if obj is None:
        return None
    if is_dataclass(obj):
        return {f: _to_dict(getattr(obj, f)) for f in obj.__dataclass_fields__}
    if isinstance(obj, (list, tuple)):
        return [_to_dict(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    return obj


def plan_from_yaml(yaml_text: str) -> FacadePlan:
    """Deserialize a FacadePlan from YAML. Inverse of ``plan_to_yaml``."""
    raw = yaml.safe_load(yaml_text)
    return _from_dict_facade(raw)


def _from_dict_facade(d: dict) -> FacadePlan:
    """Reconstruct FacadePlan from a nested dict."""
    canvas = tuple(d["canvas"])
    stories = [_from_dict_story(s) for s in d.get("stories", [])]
    bays = [_from_dict_bay(b) for b in d.get("bays", [])]
    parapet_d = d.get("parapet")
    parapet = _from_dict_parapet(parapet_d) if parapet_d else None
    plinth_d = d.get("plinth")
    plinth = _from_dict_plinth(plinth_d) if plinth_d else None
    return FacadePlan(
        canvas=canvas,
        stories=stories,
        bays=bays,
        parapet=parapet,
        plinth=plinth,
        **{k: v for k, v in d.items()
           if k not in ("canvas", "stories", "bays", "parapet", "plinth")
           and _has_field(FacadePlan, k)}
    )


def _has_field(cls, name: str) -> bool:
    return name in getattr(cls, "__dataclass_fields__", {})


def _from_dict_story(d: dict) -> StoryPlan:
    return StoryPlan(**{k: v for k, v in d.items() if _has_field(StoryPlan, k)})


def _from_dict_bay(d: dict) -> BayPlan:
    openings = [_from_dict_opening(o) for o in d.get("openings", [])]
    pilasters_d = d.get("pilasters")
    pilasters = _from_dict_pilaster(pilasters_d) if pilasters_d else None
    return BayPlan(
        openings=openings,
        pilasters=pilasters,
        width_weight=d.get("width_weight", 1.0),
        label=d.get("label", ""),
    )


def _from_dict_opening(d: dict) -> OpeningPlan:
    return OpeningPlan(**{k: v for k, v in d.items() if _has_field(OpeningPlan, k)})


def _from_dict_pilaster(d: dict) -> PilasterPlan:
    return PilasterPlan(**{k: v for k, v in d.items() if _has_field(PilasterPlan, k)})


def _from_dict_parapet(d: dict) -> ParapetPlan:
    return ParapetPlan(**{k: v for k, v in d.items() if _has_field(ParapetPlan, k)})


def _from_dict_plinth(d: dict) -> "PlinthPlan":
    from .plan import PlinthPlan
    return PlinthPlan(**{k: v for k, v in d.items() if _has_field(PlinthPlan, k)})


# ── SVG embedding ─────────────────────────────────────────────────────

_METADATA_PATTERN = re.compile(
    r'<metadata[^>]*id="facade-plan"[^>]*>.*?<!\[CDATA\[(.*?)\]\]>.*?</metadata>',
    re.DOTALL,
)


def embed_plan_in_svg(svg_text: str, plan: FacadePlan) -> str:
    """Inject a <metadata> block with the plan's YAML into an SVG.

    If a plan metadata block already exists, it's replaced. The new
    block is inserted just before the closing </svg>.
    """
    yaml_text = plan_to_yaml(plan)
    metadata_block = (
        '<metadata id="facade-plan">\n'
        '<!-- FacadePlan (YAML) — round-trip via engraving.planner.io -->\n'
        '<![CDATA[\n'
        f'{yaml_text}'
        ']]>\n'
        '</metadata>\n'
    )
    # Remove any existing facade-plan metadata first
    svg_text = _METADATA_PATTERN.sub('', svg_text)
    # Insert before </svg>
    if "</svg>" in svg_text:
        svg_text = svg_text.replace("</svg>", metadata_block + "</svg>", 1)
    return svg_text


def extract_plan_from_svg(svg_path: str | Path) -> FacadePlan | None:
    """Read an SVG file and return the FacadePlan from its metadata.
    Returns None if no embedded plan."""
    text = Path(svg_path).read_text()
    m = _METADATA_PATTERN.search(text)
    if not m:
        return None
    return plan_from_yaml(m.group(1))
