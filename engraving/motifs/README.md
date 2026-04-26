# Motif plugins

This directory holds hand-drawn SVG replacements for the parametric motifs
used throughout the engraving pipeline.  Drop a file here and the plugin
loader (`engraving/plugins.py`) will register it at import time, overriding
the parametric default of the same name.

## What lives here

Files are named after the motif they override.  Current slots the loader
knows how to resolve:

| Filename                     | Replaces                                        |
| ---------------------------- | ----------------------------------------------- |
| `acanthus_leaf.svg`          | `engraving.acanthus.acanthus_leaf`              |
| `acanthus_tip.svg`           | `engraving.acanthus.acanthus_tip`               |
| `rosette_basic.svg`          | future rosette motif in `engraving.ornament`    |
| `rosette_ornate.svg`         | future ornate-rosette motif                     |
| `caisson_rosette.svg`        | coffer rosette used by the Corinthian ceiling   |
| `fleuron_corinthian.svg`     | abacus fleuron on the Corinthian capital        |

Anything else ending in `.svg` is still loaded and made available under its
filename-stem, so experimental motifs can be probed by name with
`engraving.plugins.get_motif("foo")`.

## Expected SVG format

The loader's parser is intentionally small -- just enough to accept
handwritten or Inkscape-exported motifs without pulling in a full SVG
rasteriser:

* A single `<svg>` element.  The `viewBox` attribute is used for scaling;
  if absent the file is assumed to live in the same unit-space the caller
  asks for (pass-through).
* `viewBox` is interpreted in millimetres.  For a unit motif where (0, 0)
  is the point the callsite wants placed against a surface and the tip is
  at (0, -1), use `viewBox="-1 -1 2 2"` and set `width="1mm"
  height="1mm"`.  The runtime re-scales the polylines to whatever
  `width`/`height` the caller asks for.
* Accepted geometry elements, in order of preference:
    * `<polyline points="x,y x,y ...">`
    * `<polygon points="...">` -- auto-closed on load.
    * `<line x1=... y1=... x2=... y2=... />`
    * `<path d="...">` -- **only** `M`/`L`/`Z` commands are flattened.
      Paths that contain `C`/`Q`/`S`/`A` (Bezier or elliptical arcs) are
      silently skipped; flatten them to polylines in your editor before
      dropping the file in.  Flattening curve paths through `svgelements`
      is a TODO for v2.
* By convention the **first** polyline in the file is the outer
  silhouette.  Validators assume this when they check for closedness and
  bilateral symmetry.  Put venation/creases after the silhouette.

## Required anchor metadata

Each motif declares named attachment points so the composition layer can
align it against its surroundings (leaf base against the abacus, rosette
centre inside the coffer, etc.).  Two equivalent mechanisms:

1. **Inline** on any element in the SVG, using `data-anchor-NAME="(x, y)"`
   attributes.  The parentheses are optional; the parser accepts
   `data-anchor-center="0,0"` just as happily.  Coordinates are in the
   same viewBox space as the geometry.
2. **Sidecar** JSON file named `<motif>.anchors.json` living next to the
   SVG.  Useful when the editor strips unknown attributes.  Format:

       {
         "base": { "x": 0.0, "y": 1.0, "role": "attach" },
         "tip":  { "x": 0.0, "y": -1.0, "role": "tip" }
       }

   The `role` field is optional and mirrors `engraving.schema.Anchor.role`.

Anchors expected per motif family:

* **Acanthus leaf** -- `base` (where the stem meets its support) and
  `tip` (the distal point of the leaf).
* **Rosette** -- `center`.
* **Caisson rosette** -- `center`.
* **Corinthian fleuron** -- `base_center` (the middle of the bottom edge
  that sits on the abacus).

## Validation

Before a motif is accepted it is checked by
`engraving.validate.motifs.validate_motif_svg`:

* The silhouette (first polyline) must be closed.
* The silhouette must be bilaterally symmetric about `x = 0` (loose
  tolerance; hand drawing is not pixel-exact).
* Self-intersection is reported where detectable (best-effort; Shapely's
  `LinearRing` check).
* All required anchors for the motif family must be present, either
  inline or in the sidecar file.

Run the full sweep with::

    .venv/bin/python -c "from engraving.validate.motifs import validate_all_motifs; print(list(validate_all_motifs()))"

A healthy directory prints an empty list.

## Limitations in v1

* Only straight-line paths are flattened.  Q/C/S/A path commands are
  skipped -- flatten them to polylines before saving.
* Transforms (`transform="..."`) and nested `<g>` groups are walked but
  any `transform` attribute on them is ignored.  Author motifs in the
  root coordinate frame.
* Stroke/fill styling is ignored; the renderer applies the engraving
  pipeline's own stroke settings.
