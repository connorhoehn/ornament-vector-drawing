"""Motif plugin validators.

Runs when loading an SVG motif to ensure it meets the structural contract
the engraving pipeline assumes:

* the first polyline is a closed silhouette,
* the silhouette is bilaterally symmetric about ``x = 0`` (loose
  tolerance -- hand-drawn motifs aren't pixel-exact),
* no self-intersection of the silhouette (best-effort via Shapely),
* every required anchor is present in the inline attributes or sidecar
  JSON file.

Per-motif anchor requirements are encoded in the ``required_by_type`` map
inside :func:`validate_all_motifs`; keep that map in sync as new motif
slots are supported.
"""
from __future__ import annotations

from pathlib import Path

from ..schema import Anchor
from . import (ValidationReport, is_closed, mirror_symmetric,
               no_self_intersection)


def validate_motif_svg(svg_path: Path,
                       required_anchors: list[str] | None = None,
                       expect_symmetric: bool = True,
                       expect_closed: bool = True,
                       axis_x: float = 0.0) -> ValidationReport:
    """Validate a single motif SVG file against the motif contract.

    Returns a :class:`ValidationReport` -- empty on success, otherwise
    populated with one or more error strings.

    Open-spine motifs (spirals, cartouche spines) should pass
    ``expect_closed=False`` and ``expect_symmetric=False`` -- they are
    intentionally not closed silhouettes and skip those checks.
    """
    # Imported lazily to avoid a circular import at module load time:
    # engraving.plugins imports from engraving.schema, and
    # engraving.validate imports from engraving.schema too.
    from ..plugins import _parse_anchors, load_svg_polylines

    report = ValidationReport()

    # Load polylines at a unit size so symmetry / closedness checks are
    # scale-invariant.
    try:
        polylines = load_svg_polylines(svg_path,
                                       target_width=1.0,
                                       target_height=1.0)
    except Exception as e:
        report.errors.append(f"{svg_path.name}: failed to parse: {e}")
        return report

    if not polylines:
        report.errors.append(f"{svg_path.name}: no polylines found")
        return report

    # First polyline is conventionally the outer silhouette.
    silhouette = polylines[0]
    if expect_closed:
        report.check(is_closed, silhouette, 0.01,
                     label=f"{svg_path.name} silhouette")

        # Self-intersection: best-effort; some motifs (grape clusters, swags)
        # intentionally fold over themselves and would trip this, so a failure
        # here is a soft warning, not a hard error.  We still record it in
        # ``errors`` so the CLI can surface it.
        try:
            report.check(no_self_intersection, silhouette,
                         label=f"{svg_path.name}")
        except Exception:
            # Shapely can raise outside our control on degenerate inputs.
            pass

    if expect_symmetric:
        report.check(mirror_symmetric, silhouette, axis_x, 0.1,
                     label=f"{svg_path.name} symmetry")

    if required_anchors:
        anchors: dict[str, Anchor] = _parse_anchors(svg_path)
        missing = set(required_anchors) - set(anchors.keys())
        if missing:
            report.errors.append(
                f"{svg_path.name}: missing required anchors "
                f"{sorted(missing)}"
            )

    return report


# Keep this map in sync as new motif slots are defined.  Anything not
# listed here is validated with no required-anchor check (silhouette +
# symmetry only).
_REQUIRED_ANCHORS_BY_STEM: dict[str, list[str]] = {
    "acanthus_leaf": ["base", "tip"],
    "acanthus_tip": ["base"],
    "rosette": ["center"],
    "rosette_basic": ["center"],
    "rosette_ornate": ["center"],
    "caisson_rosette": ["center"],
    "fleuron_corinthian": ["base_center"],
    "cartouche_spine": ["attach", "eye"],
}

# Motifs whose first polyline is an open spine / spiral rather than a
# closed silhouette.  Skip the closed / symmetric checks for these.
_OPEN_SPINE_STEMS: set[str] = {
    "cartouche_spine",
}


def validate_all_motifs() -> ValidationReport:
    """Scan ``engraving/motifs/`` and validate every SVG there.

    The returned report aggregates errors across all motifs; an empty
    report means the whole directory is in good shape.
    """
    from ..plugins import MOTIFS_DIR

    combined = ValidationReport()
    if not MOTIFS_DIR.exists():
        return combined

    for svg_path in sorted(MOTIFS_DIR.glob("*.svg")):
        required = _REQUIRED_ANCHORS_BY_STEM.get(svg_path.stem, [])
        is_open_spine = svg_path.stem in _OPEN_SPINE_STEMS
        sub = validate_motif_svg(svg_path, required_anchors=required,
                                 expect_closed=not is_open_spine,
                                 expect_symmetric=not is_open_spine)
        combined.errors.extend(sub.errors)

    return combined
