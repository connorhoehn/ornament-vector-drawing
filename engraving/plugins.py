"""Plugin loader for hand-drawn motif overrides.

The engraving pipeline ships parametric generators for every ornament it
uses (acanthus leaves, rosettes, fleurons, ...).  Some of those ornaments
-- acanthus foliage in particular -- read better when drawn by hand once
and reused, rather than regenerated from a formula each time.  This
module lets the user drop an SVG file into ``engraving/motifs/`` and have
it replace the parametric default at render time.

Usage
-----

::

    from engraving.plugins import load_motifs, get_motif_or_default
    from engraving.acanthus import _parametric_acanthus_leaf

    # At import time (called automatically on module import):
    load_motifs()

    # In code that wants to use a motif:
    leaf_polys = get_motif_or_default(
        "acanthus_leaf",
        default_fn=_parametric_acanthus_leaf,
        width=30, height=40, lobe_count=5,
    )

The override behaviour is:

* If a motif with that name is registered with an ``svg_path``, parse
  and return its polylines scaled to ``width`` / ``height``.
* Else if it is registered with a callable (`fn`), invoke it with the
  kwargs passed in.
* Else invoke ``default_fn`` with the kwargs.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree as ET

from .schema import Anchor, Polyline


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# Maps motif name -> {"fn": callable|None, "svg_path": Path|None,
#                     "anchors": {anchor_name: Anchor}}
_REGISTRY: dict[str, dict[str, Any]] = {}

MOTIFS_DIR = Path(__file__).parent / "motifs"


def register_motif(name: str,
                   fn: Callable[..., list[Polyline]] | None = None,
                   svg_path: Path | None = None,
                   anchors: dict[str, Anchor] | None = None) -> None:
    """Register a motif by name.

    Either ``fn`` (a parametric generator) or ``svg_path`` (a static SVG
    file) must be provided.  If both are given, ``svg_path`` wins at
    resolve time -- that's the whole point of the plugin system: let a
    hand-drawn SVG shadow a parametric default of the same name.

    Registration is **merging**: if a slot already has an ``svg_path``
    and the new call provides only an ``fn``, the existing SVG is
    preserved.  This lets the parametric default be registered at module
    import time without clobbering an SVG plugin that ``load_motifs``
    already picked up.  Passing a non-None value explicitly replaces
    whatever was there.
    """
    existing = _REGISTRY.get(name, {})
    merged_fn = fn if fn is not None else existing.get("fn")
    merged_svg = svg_path if svg_path is not None else existing.get("svg_path")
    if anchors is not None:
        merged_anchors = anchors
    else:
        merged_anchors = existing.get("anchors") or {}
    _REGISTRY[name] = {
        "fn": merged_fn,
        "svg_path": merged_svg,
        "anchors": merged_anchors,
    }


def get_motif(name: str) -> dict[str, Any] | None:
    """Return the registry entry for ``name``, or ``None`` if unknown."""
    return _REGISTRY.get(name)


def registered_names() -> list[str]:
    """All registered motif names, for introspection / tests."""
    return sorted(_REGISTRY.keys())


def clear_registry() -> None:
    """Drop every registered motif (used by tests that reset state)."""
    _REGISTRY.clear()


def load_motifs(directory: Path | None = None) -> None:
    """Scan ``directory`` (default ``engraving/motifs``) for ``*.svg``
    files and register each one as a motif.

    A second call re-scans and overwrites registry entries, so dropping
    a new file in and re-calling this function is a valid hot-reload
    pattern.
    """
    target = directory or MOTIFS_DIR
    if not target.exists():
        return
    for svg_path in sorted(target.glob("*.svg")):
        name = svg_path.stem
        anchors = _parse_anchors(svg_path)
        register_motif(name, svg_path=svg_path, anchors=anchors)


# ---------------------------------------------------------------------------
# Anchor parsing
# ---------------------------------------------------------------------------

_ANCHOR_COORD_RE = re.compile(r"\s*\(?\s*([-\d.eE+]+)\s*,\s*([-\d.eE+]+)\s*\)?\s*")


def _parse_anchors(svg_path: Path) -> dict[str, Anchor]:
    """Read anchor metadata for ``svg_path``.

    Two locations are probed, in order:

    1. ``<stem>.anchors.json`` sidecar next to the SVG.  The JSON is a
       dict mapping anchor name -> ``{"x": float, "y": float, "role": str}``.
    2. Inline ``data-anchor-<name>="(x, y)"`` attributes on any element in
       the SVG.  Parentheses are optional.

    Failures are swallowed -- a motif with no anchors is still loaded;
    validation catches missing required anchors later.
    """
    # 1. Sidecar JSON.
    sidecar = svg_path.with_suffix(".anchors.json")
    if sidecar.exists():
        try:
            raw = json.loads(sidecar.read_text())
            out: dict[str, Anchor] = {}
            for k, v in raw.items():
                out[k] = Anchor(
                    name=k,
                    x=float(v["x"]),
                    y=float(v["y"]),
                    role=v.get("role", ""),
                )
            return out
        except Exception:
            pass

    # 2. Inline attributes.
    anchors: dict[str, Anchor] = {}
    try:
        tree = ET.parse(svg_path)
    except Exception:
        return anchors
    root = tree.getroot()
    for elem in root.iter():
        for attr, val in elem.attrib.items():
            # Namespaced attributes look like "{http://...}data-anchor-name";
            # handle both qualified and bare forms.
            tail = attr.split("}")[-1]
            if not tail.startswith("data-anchor-"):
                continue
            anchor_name = tail[len("data-anchor-"):]
            m = _ANCHOR_COORD_RE.match(val or "")
            if m:
                anchors[anchor_name] = Anchor(
                    name=anchor_name,
                    x=float(m.group(1)),
                    y=float(m.group(2)),
                )
    return anchors


# ---------------------------------------------------------------------------
# SVG -> polylines
# ---------------------------------------------------------------------------


def load_svg_polylines(svg_path: Path,
                       target_width: float,
                       target_height: float) -> list[Polyline]:
    """Parse an SVG file and return its geometry as polylines in mm,
    scaled to ``target_width`` x ``target_height``.

    Supported elements:

    * ``<polyline>`` / ``<polygon>`` (via ``points`` attribute).
    * ``<line>`` (``x1``/``y1``/``x2``/``y2``).
    * ``<path>`` with **only** ``M``/``L``/``Z`` commands.  Paths that
      contain Bezier or elliptical-arc commands (``C``/``Q``/``S``/``A``
      and their lowercase relatives) are silently skipped.  Flatten them
      in the source editor before saving.

      TODO (v2): flatten curved paths via ``svgelements`` so free-hand
      motifs with Beziers load without being pre-flattened.

    Coordinates are transformed from the SVG ``viewBox`` to the caller's
    target box by a uniform-per-axis scale.  No rotation/translation
    beyond the viewBox origin is applied -- this keeps the parser small
    and motif authors are expected to draw in the intended local frame.
    """
    tree = ET.parse(svg_path)
    root = tree.getroot()

    vb = root.get("viewBox")
    if vb:
        parts = [float(v) for v in vb.replace(",", " ").split()]
        if len(parts) == 4:
            vbx, vby, vbw, vbh = parts
        else:
            vbx = vby = 0.0
            vbw = target_width
            vbh = target_height
    else:
        vbx = vby = 0.0
        vbw = target_width
        vbh = target_height

    def scale(x: float, y: float) -> tuple[float, float]:
        # Normalise into [0, 1] viewBox-parametric space, then map to
        # [-target/2, +target/2] so motifs authored around a centred
        # viewBox (e.g. "-1 -1 2 2") land centred on (0, 0) in the
        # returned coordinates.  The caller translates to the desired
        # placement.
        u = (x - vbx) / vbw if vbw else 0.0
        v = (y - vby) / vbh if vbh else 0.0
        return (u * target_width - target_width * 0.5,
                v * target_height - target_height * 0.5)

    polylines: list[Polyline] = []

    for elem in root.iter():
        tag = elem.tag.split("}")[-1]

        if tag in ("polyline", "polygon"):
            pts_str = elem.get("points", "").strip()
            coords = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", pts_str)
            pts: Polyline = []
            for i in range(0, len(coords) - 1, 2):
                pts.append(scale(float(coords[i]), float(coords[i + 1])))
            if not pts:
                continue
            if tag == "polygon" and pts[0] != pts[-1]:
                pts.append(pts[0])
            polylines.append(pts)

        elif tag == "line":
            x1 = float(elem.get("x1", 0))
            y1 = float(elem.get("y1", 0))
            x2 = float(elem.get("x2", 0))
            y2 = float(elem.get("y2", 0))
            polylines.append([scale(x1, y1), scale(x2, y2)])

        elif tag == "path":
            d = elem.get("d", "")
            if not d:
                continue
            # Refuse anything with curves; it would silently flatten to
            # a chord and look wrong.
            if any(c in d for c in ("Q", "q", "C", "c", "S", "s", "A", "a",
                                    "T", "t")):
                # TODO: use svgelements to flatten.
                continue

            tokens = re.findall(
                r"[MLHVZmlhvz]|[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", d
            )
            pts = []
            i = 0
            cx = cy = 0.0
            start_pt: tuple[float, float] | None = None
            while i < len(tokens):
                tok = tokens[i]
                if tok in ("M", "L"):
                    x = float(tokens[i + 1])
                    y = float(tokens[i + 2])
                    cx, cy = x, y
                    pts.append(scale(cx, cy))
                    if tok == "M":
                        start_pt = pts[-1]
                    i += 3
                elif tok in ("m", "l"):
                    x = cx + float(tokens[i + 1])
                    y = cy + float(tokens[i + 2])
                    cx, cy = x, y
                    pts.append(scale(cx, cy))
                    if tok == "m":
                        start_pt = pts[-1]
                    i += 3
                elif tok == "H":
                    cx = float(tokens[i + 1])
                    pts.append(scale(cx, cy))
                    i += 2
                elif tok == "h":
                    cx = cx + float(tokens[i + 1])
                    pts.append(scale(cx, cy))
                    i += 2
                elif tok == "V":
                    cy = float(tokens[i + 1])
                    pts.append(scale(cx, cy))
                    i += 2
                elif tok == "v":
                    cy = cy + float(tokens[i + 1])
                    pts.append(scale(cx, cy))
                    i += 2
                elif tok in ("Z", "z"):
                    if start_pt is not None:
                        pts.append(start_pt)
                    i += 1
                else:
                    # Unknown token or stray number: skip.
                    i += 1
            if len(pts) >= 2:
                polylines.append(pts)

    return polylines


# ---------------------------------------------------------------------------
# Public resolve-and-render helper
# ---------------------------------------------------------------------------


def get_motif_or_default(name: str,
                         default_fn: Callable[..., list[Polyline]],
                         **kwargs: Any) -> list[Polyline]:
    """Return polylines for the named motif.

    Resolution order:

    1. A registered SVG plugin (``svg_path``).  Scaled to ``width`` /
       ``height`` (or ``size`` if the caller passes that instead).
    2. A registered callable (``fn``).  Invoked with ``**kwargs``.
    3. ``default_fn(**kwargs)``.
    """
    entry = _REGISTRY.get(name)
    if entry and entry.get("svg_path"):
        size = kwargs.get("size")
        width = kwargs.get("width", size if size is not None else 30.0)
        height = kwargs.get("height", size if size is not None else 40.0)
        return load_svg_polylines(entry["svg_path"], width, height)
    if entry and entry.get("fn"):
        return entry["fn"](**kwargs)
    return default_fn(**kwargs)


# Populate the registry from disk on import.  Subsequent re-imports during a
# single process are no-ops because Python caches the module; callers that
# need to hot-reload after dropping a new SVG in should invoke
# ``load_motifs()`` explicitly.
load_motifs()
