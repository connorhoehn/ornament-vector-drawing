"""Debug overlay for Element trees. Renders the normal plate SVG with
colored violation annotations overlaid.

Layer A violations (structural) are drawn in RED — these mean the geometry
cannot be rendered without fixing. Layer B (architectural/canonical) are
drawn in ORANGE — should probably fix. Layer C (aesthetic) are drawn in
BLUE — advisory only.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ..element import Element, Violation
from ..containment import validate_tree


LAYER_COLORS = {
    "A": "red",        # structural — can't render without fixing
    "B": "orange",     # canonical — probably should fix
    "C": "blue",       # aesthetic — advisory
}


def render_debug(element_tree: Element, source_svg: str | Path,
                 output_svg: str | Path,
                 include_layers: Iterable[str] = ("A", "B", "C"),
                 extra_violations: list[Violation] | None = None) -> Path:
    """Re-render ``source_svg`` with violation annotations overlaid.

    For each violation, paint:
      - the offending element's bbox (dashed rect in layer color)
      - a small text label with the rule name and axis (if any)

    The output is a copy of ``source_svg`` with an ``<!-- DEBUG OVERLAY -->``
    block injected just before ``</svg>``. Plate SVGs use 1:1 mm units so
    world coordinates map directly to SVG user units (no transform needed).

    Parameters
    ----------
    element_tree : Element
        The solved Element tree to inspect.
    source_svg : str | Path
        Path to the plate's normal-rendered SVG.
    output_svg : str | Path
        Where to write the overlaid SVG.
    include_layers : Iterable[str]
        Which violation layers to render (default: all three A/B/C).
    extra_violations : list[Violation] | None
        Additional Violation objects (e.g. from aesthetic / orders
        validators) to overlay. Layer-A violations are computed
        automatically via ``validate_tree``.

    Returns
    -------
    Path
        The ``output_svg`` path (Path object).
    """
    source_svg = Path(source_svg)
    output_svg = Path(output_svg)

    src_text = source_svg.read_text()

    # Collect violations — Layer A from containment validator, plus any extras
    all_violations: list[Violation] = []
    all_violations.extend(validate_tree(element_tree))
    if extra_violations:
        all_violations.extend(extra_violations)

    # Build SVG overlay
    overlay: list[str] = []
    for v in all_violations:
        if v.layer not in include_layers:
            continue
        color = LAYER_COLORS.get(v.layer, "red")
        # Locate the element that failed
        elem = element_tree.find(v.element_id)
        if elem is None:
            continue
        try:
            bx = elem.effective_bbox()
        except Exception:
            continue
        x0, y0, x1, y1 = bx
        w = x1 - x0
        h = y1 - y0
        # Dashed rect around the offending element
        overlay.append(
            f'<rect x="{x0:.2f}" y="{y0:.2f}" '
            f'width="{w:.2f}" height="{h:.2f}" '
            f'fill="{color}" fill-opacity="0.08" stroke="{color}" '
            f'stroke-width="0.2" stroke-dasharray="2,1" />'
        )
        # Label with rule name + axis (if any) + overshoot
        axis_part = f" {v.axis}" if v.axis else ""
        over_part = f" ({v.overshoot_mm:.2f}mm)" if v.overshoot_mm else ""
        label_text = f"{v.rule}{axis_part}{over_part}"
        overlay.append(
            f'<text x="{x0 + 0.5:.2f}" y="{y0 - 1:.2f}" font-size="1.8" '
            f'fill="{color}" font-family="serif">{_esc(label_text)}</text>'
        )

    # Inject before </svg>
    if overlay:
        block = ('\n<!-- DEBUG OVERLAY -->\n'
                 '<g id="debug-overlay" fill="none">\n')
        block += "\n".join(overlay) + "\n</g>"
        if "</svg>" in src_text:
            src_text = src_text.replace("</svg>", block + "\n</svg>")
    output_svg.write_text(src_text)
    return output_svg


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;"))
