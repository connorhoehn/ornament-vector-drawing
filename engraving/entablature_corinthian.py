"""Corinthian entablature in elevation, after Ware's *American Vignola* (1903),
pp. 19–21.

Proportions (all fractions of the lower diameter D):
  Entablature total .................. 2½ D
  Architrave ......................... ¾ D (3 fasciae + ovolo + fillet crown)
  Frieze ............................. ¾ D (plain; sculpted in advanced work)
  Cornice ............................ 1 D, divided vertically into fifths:
      lower 2/5 .....................  bed mold + dentils (as Ionic)
      middle 1/5 ....................  modillion band crowned by cyma reversa
      upper 2/5 .....................  corona (caissoned soffit) + cymatium

Modillion (scroll bracket with an acanthus leaf underneath):
  length   = 5/12 D (= ½ × upper shaft diameter)
  width    = 2/9 D (visible front face in elevation)
  height   = 1/5 of cornice height = 1/5 D
  on-centers = 2/3 D; interval between = 4/9 D
  one modillion is always centered over each column axis.

Dentils (same proportions as Ionic):
  height = 1/12 D, width = 1/18 D, on-centers = 1/6 D, interdentil = 1/12 D.
  Because modillion o.c. (2/3 D = 4/6 D) is four dentil o.c. (1/6 D), exactly
  four dentils sit between every pair of modillions.

Caissons (square coffers in the corona soffit):
  one square panel between each pair of modillions, centered on the corona.
  Each receives a rosette at its centre (returned for the caller to draw).

Drawing convention mirrors the rest of the package: +y points DOWN (SVG),
so "up the wall" means decreasing y and `top_of_capital_y` is the largest y
value in the returned geometry.
"""
from __future__ import annotations

from typing import Optional

from shapely.geometry import Polygon

from . import canon
from . import profiles as P
from .elements import Shadow
from .geometry import Point, Polyline, cubic_bezier, rect_corners, translate_path

# Optional acanthus hook: engraving.acanthus may not exist yet. When it does,
# callers get a richer leaf silhouette; until then we draw a three-lobed
# triangular placeholder locally (see `_placeholder_acanthus_leaf`).
try:  # pragma: no cover - the presence of this module is environment-dependent
    from . import acanthus as _acanthus  # type: ignore
except Exception:  # pragma: no cover
    _acanthus = None  # type: ignore


# ─── Internal helpers ────────────────────────────────────────────────────

def _closed(poly: Polyline) -> Polyline:
    """Ensure a polyline is closed (first == last)."""
    if not poly:
        return poly
    if poly[0] != poly[-1]:
        return [*poly, poly[0]]
    return poly


def _modillion_axes(left_x: float, right_x: float,
                    column_axes_x: list[float], oc: float) -> list[float]:
    """Compute modillion centre x-values.

    Rules (per Ware):
      - one modillion is centered over each column axis;
      - additional modillions fill the intercolumniations at 2/3 D o.c.;
      - the pattern continues outward past the outermost columns until it
        would overhang the cornice edge, then stops.
    """
    if not column_axes_x:
        # Fall back: evenly stride across the full cornice span.
        xs: list[float] = []
        x = left_x + oc / 2
        while x <= right_x - oc / 2 + 1e-6:
            xs.append(x)
            x += oc
        return xs

    axes_sorted = sorted(column_axes_x)
    centres: list[float] = list(axes_sorted)

    # Fill each interval between successive column axes.
    for a, b in zip(axes_sorted, axes_sorted[1:]):
        gap = b - a
        # Number of *additional* modillions strictly between a and b.
        n_between = max(0, int(round(gap / oc)) - 1)
        if n_between <= 0:
            continue
        step = gap / (n_between + 1)
        for k in range(1, n_between + 1):
            centres.append(a + k * step)

    # Extend outward past the first/last column until the modillion would
    # overhang the cornice. We use the axis-to-axis step for consistency
    # with the intercolumniations; if there is only one axis, use `oc`.
    if len(axes_sorted) >= 2:
        step_left = axes_sorted[1] - axes_sorted[0]
        step_right = axes_sorted[-1] - axes_sorted[-2]
        # Honour the canonical oc of 2/3 D when the spacing already divides
        # evenly into it; otherwise stick with the observed step.
        step_left = step_left / max(1, int(round(step_left / oc)))
        step_right = step_right / max(1, int(round(step_right / oc)))
    else:
        step_left = step_right = oc

    # Walk left.
    x = axes_sorted[0] - step_left
    while x >= left_x:
        centres.append(x)
        x -= step_left
    # Walk right.
    x = axes_sorted[-1] + step_right
    while x <= right_x:
        centres.append(x)
        x += step_right

    centres.sort()
    return centres


def _modillion_outline(cx: float, top_y: float, length: float,
                       width: float, height: float) -> Polyline:
    """Side-elevation outline of a single modillion.

    The modillion is drawn as an S-scroll bracket: a rectangle of `width` wide
    and `height` tall forming the "shank", with a cubic-bezier tail curling
    outward (toward the viewer) at the bottom, like a console. `length` is the
    projection perpendicular to the wall — in elevation we see it foreshortened
    as extra width at the bottom where the scroll curls out.
    """
    half_w = width / 2
    # Top rectangle (front face).
    rect_top = top_y
    rect_bot = top_y + height * 0.65
    x_l = cx - half_w
    x_r = cx + half_w

    # Scroll tail: curl the right side outward with a cubic Bezier. The curl
    # drops down and to the right by (length * 0.2), enough to read as a
    # bracket without overpowering the modillion band.
    curl_drop = height * 0.35
    curl_x_out = length * 0.25
    # Right scroll (bottom-right corner curls outward then back under).
    tail_r = cubic_bezier(
        (x_r, rect_bot),
        (x_r + curl_x_out * 0.6, rect_bot + curl_drop * 0.25),
        (x_r + curl_x_out, rect_bot + curl_drop * 0.7),
        (x_r + curl_x_out * 0.35, rect_bot + curl_drop),
        steps=12,
    )
    # Left scroll (mirror): curl inward on the front face so the modillion
    # silhouette reads symmetrically in elevation.
    tail_l = cubic_bezier(
        (x_l - curl_x_out * 0.35, rect_bot + curl_drop),
        (x_l - curl_x_out, rect_bot + curl_drop * 0.7),
        (x_l - curl_x_out * 0.6, rect_bot + curl_drop * 0.25),
        (x_l, rect_bot),
        steps=12,
    )

    outline: Polyline = [
        (x_l, rect_top),
        (x_r, rect_top),
        *tail_r,
        *tail_l,
        (x_l, rect_top),
    ]
    return outline


def _placeholder_acanthus_leaf(cx: float, top_y: float,
                               width: float, height: float) -> Polyline:
    """Crude three-lobed acanthus placeholder hung below the modillion.

    Replace by `engraving.acanthus.acanthus_leaf(...)` once that module lands.
    The hook above (`_acanthus`) already picks it up if/when present.
    """
    if _acanthus is not None and hasattr(_acanthus, "acanthus_leaf"):
        try:  # pragma: no cover - delegated to the real implementation
            leaf_polys = _acanthus.acanthus_leaf(width=width, height=height)
            if leaf_polys:
                # The acanthus API returns leaves in a local frame whose
                # shape varies (parametric places base at bottom of bbox;
                # SVG motifs centre on viewBox).  Normalize by finding the
                # silhouette's bbox and pinning its bottom-centre to
                # (cx, top_y), with the tip landing at (cx, top_y + height).
                # Use only the first polyline (the outer silhouette) so
                # modillions remains list[Polyline].
                silhouette = leaf_polys[0]
                xs = [p[0] for p in silhouette]
                ys = [p[1] for p in silhouette]
                x_mid = (min(xs) + max(xs)) * 0.5
                y_base = max(ys)   # bottom of leaf (tip points up, negative y)
                placed = [(cx + (x - x_mid), top_y + (y_base - y))
                          for (x, y) in silhouette]
                return _closed(placed)
        except Exception:
            pass
    half = width / 2
    lobe = width / 3
    # Three-lobed silhouette: centre lobe drops longer than the flanks.
    return _closed([
        (cx - half, top_y),
        (cx - half + lobe * 0.25, top_y + height * 0.45),
        (cx - lobe * 0.5, top_y + height * 0.6),
        (cx, top_y + height),                  # tip of centre lobe
        (cx + lobe * 0.5, top_y + height * 0.6),
        (cx + half - lobe * 0.25, top_y + height * 0.45),
        (cx + half, top_y),
    ])


# ─── Main builder ─────────────────────────────────────────────────────────

def corinthian_entablature(left_x: float, right_x: float,
                           top_of_capital_y: float,
                           dims: canon.Corinthian,
                           column_axes_x: list[float],
                           *, return_result: bool = False,
                           dentil_width_D: Optional[float] = None,
                           dentil_height_D: Optional[float] = None,
                           dentil_oc_D: Optional[float] = None,
                           _kind: str = "corinthian_entablature"):
    """Build a Corinthian entablature in elevation.

    Parameters
    ----------
    left_x, right_x      : x-range of the cornice at its widest projection.
    top_of_capital_y     : y-value of the top of the column capitals (the
                           architrave rests on this line).
    dims                 : a `canon.Corinthian` instance (proportions scale by
                           `dims.D`).
    column_axes_x        : list of column centreline x-values; modillions sit
                           one-per-axis, filled at 2/3 D o.c. between.
    dentil_width_D,
    dentil_height_D,
    dentil_oc_D          : optional overrides (as fractions of D). Used by
                           ``composite_entablature`` to inject Vignola's larger,
                           squarer Composite dentils (1/6 × 1/5 D at 1/4 D oc).
                           Defaults to 1/18 D width, ~band height, 1/6 D oc.
    _kind                : internal — ElementResult.kind label; the composite
                           wrapper passes "composite_entablature".

    Returns
    -------
    dict with keys:
      "polylines"  : list[Polyline]              (band edges, fasciae, rules)
      "shadows"    : list[Shadow]                (soffits, side-shadows, gaps)
      "modillions" : list[Polyline]              (one closed outline per mod.)
      "dentils"    : list[Polyline]              (closed tooth rectangles)
      "caissons"   : list[Polyline]              (closed corona-soffit squares)
      "rosettes"   : list[tuple[Point, float]]   (centre, radius)
      "top_y"      : float                       (top of cymatium)
      "left_edge"  : float                       (leftmost x of cornice)
      "right_edge" : float                       (rightmost x of cornice)
    """
    D = dims.D
    M = dims.M

    # ── Vertical ordinates (y grows downward) ──────────────────────────────
    arch_h = dims.architrave_h         # ¾ D
    fr_h = dims.frieze_h               # ¾ D
    corn_h = dims.cornice_h            # 1 D

    # Cornice vertical subdivisions: 2/5, 1/5, 2/5.
    corn_low_h = corn_h * 2.0 / 5.0
    corn_mid_h = corn_h * 1.0 / 5.0
    corn_up_h = corn_h * 2.0 / 5.0

    y_arch_bot = top_of_capital_y
    y_arch_top = y_arch_bot - arch_h
    y_frieze_top = y_arch_top - fr_h
    y_corn_low_top = y_frieze_top - corn_low_h
    y_corn_mid_top = y_corn_low_top - corn_mid_h
    y_corn_top = y_corn_mid_top - corn_up_h
    # (y_corn_top also equals y_frieze_top - corn_h.)

    # ── Horizontal projections (scale with D) ──────────────────────────────
    # Successive bands project further outward the higher they ride.
    project_arch = 0.0
    project_fr = M * 0.05
    project_corn_low = M * 0.40      # bed mold + dentil course
    project_corn_mid = M * 0.70      # modillion band
    project_corn_up = M * 0.95       # corona
    project_cymatium = M * 1.10      # top cymatium flares further yet

    ax0 = left_x - project_arch
    ax1 = right_x + project_arch
    fx0 = left_x - project_fr
    fx1 = right_x + project_fr
    clx0 = left_x - project_corn_low
    clx1 = right_x + project_corn_low
    cmx0 = left_x - project_corn_mid
    cmx1 = right_x + project_corn_mid
    cux0 = left_x - project_corn_up
    cux1 = right_x + project_corn_up
    cyx0 = left_x - project_cymatium
    cyx1 = right_x + project_cymatium

    polylines: list[Polyline] = []
    shadows: list[Shadow] = []

    # ── Architrave: 3 fasciae + ovolo/fillet crown ─────────────────────────
    # Each fascia's height roughly follows 4 : 5 : 6 from bottom to top
    # (Ware's tabulation). The crown takes ~15 % of the architrave height.
    crown_h = arch_h * 0.15
    fasciae_h = arch_h - crown_h
    # Unit = 1 of 4+5+6 = 15.
    unit = fasciae_h / 15.0
    f1_h = 4.0 * unit
    f2_h = 5.0 * unit
    f3_h = 6.0 * unit
    y_f1_top = y_arch_bot - f1_h
    y_f2_top = y_f1_top - f2_h
    y_f3_top = y_f2_top - f3_h       # equals y_arch_top + crown_h

    # Bottom of the architrave.
    polylines.append([(ax0, y_arch_bot), (ax1, y_arch_bot)])
    # Fascia edge lines (horizontal rules between successive bands).
    polylines.append([(ax0, y_f1_top), (ax1, y_f1_top)])
    polylines.append([(ax0, y_f2_top), (ax1, y_f2_top)])
    polylines.append([(ax0, y_f3_top), (ax1, y_f3_top)])
    # Top of the architrave (just above the crown).
    polylines.append([(ax0, y_arch_top), (ax1, y_arch_top)])
    # Sides.
    polylines.append([(ax0, y_arch_bot), (ax0, y_arch_top)])
    polylines.append([(ax1, y_arch_bot), (ax1, y_arch_top)])

    # Thin shadow on the underside of the bottom fascia.
    shadows.append(Shadow(
        Polygon([
            (ax0, y_arch_bot - f1_h * 0.15),
            (ax1, y_arch_bot - f1_h * 0.15),
            (ax1, y_arch_bot),
            (ax0, y_arch_bot),
        ]),
        angle_deg=10.0, density="light",
    ))

    # ── Frieze (plain band) ────────────────────────────────────────────────
    # Canonical shared-y rule: each horizontal shared between adjacent bands is
    # emitted by exactly one of them — the LOWER band's top edge. The
    # architrave above already emits y_arch_top (its top rule), so the frieze
    # does NOT re-emit that same horizontal as its bottom.
    polylines.append([(fx0, y_frieze_top), (fx1, y_frieze_top)])
    polylines.append([(fx0, y_arch_top), (fx0, y_frieze_top)])
    polylines.append([(fx1, y_arch_top), (fx1, y_frieze_top)])

    # ── Cornice, lower 2/5: bed mold + dentil course ───────────────────────
    # Band outline — frieze below already supplies y_frieze_top, so we only
    # emit y_corn_low_top + the two sides.
    polylines.append([(clx0, y_corn_low_top), (clx1, y_corn_low_top)])
    polylines.append([(clx0, y_frieze_top), (clx0, y_corn_low_top)])
    polylines.append([(clx1, y_frieze_top), (clx1, y_corn_low_top)])

    # Bed mold: cyma reversa at the bottom, ovolo above. Their relative
    # heights roughly split the lower cornice 60/40 with the dentil strip
    # sitting between. We draw them as horizontal rules for v1.
    bed_h = corn_low_h * 0.40
    dentil_h_avail = corn_low_h * 0.35
    ovolo_h = corn_low_h - bed_h - dentil_h_avail

    y_bed_top = y_frieze_top - bed_h
    y_dentil_top = y_bed_top - dentil_h_avail
    y_ovolo_top = y_dentil_top - ovolo_h  # == y_corn_low_top

    polylines.append([(clx0, y_bed_top), (clx1, y_bed_top)])
    polylines.append([(clx0, y_dentil_top), (clx1, y_dentil_top)])

    # Dentil course. Corinthian defaults: width 1/18 D, o.c. 1/6 D → gap 1/9 D.
    # Composite (via ``composite_entablature``) injects Vignola's larger,
    # squarer dentils: width 1/6 D, o.c. 1/4 D, height 1/5 D.
    dw_frac = dentil_width_D if dentil_width_D is not None else 1.0 / 18.0
    doc_frac = dentil_oc_D if dentil_oc_D is not None else dims.dentil_oc_D
    dentil_w = D * dw_frac
    dentil_oc = D * doc_frac
    dentil_gap = dentil_oc - dentil_w
    if dentil_height_D is not None:
        tooth_h = min(D * dentil_height_D, dentil_h_avail)
    else:
        tooth_h = dentil_h_avail * 0.85
    dentil_y0 = y_dentil_top + (dentil_h_avail - tooth_h) / 2
    dentils: list[Polyline] = P.dentil_strip(
        length=clx1 - clx0,
        tooth_w=dentil_w,
        tooth_h=tooth_h,
        gap=dentil_gap,
        x0=clx0,
        y0=dentil_y0,
    )
    # Interdentil gap shadows (dark slivers between teeth).
    for a, b in zip(dentils, dentils[1:]):
        # `a` and `b` are closed rectangles; gap is between a's right edge
        # and b's left edge.
        a_right = max(p[0] for p in a)
        b_left = min(p[0] for p in b)
        if b_left - a_right > 1e-6:
            shadows.append(Shadow(
                Polygon([
                    (a_right, dentil_y0),
                    (b_left, dentil_y0),
                    (b_left, dentil_y0 + tooth_h),
                    (a_right, dentil_y0 + tooth_h),
                ]),
                angle_deg=90.0, density="dark",
            ))

    # ── Cornice, middle 1/5: modillion band ────────────────────────────────
    # Band outline — lower cornice already supplies y_corn_low_top.
    polylines.append([(cmx0, y_corn_mid_top), (cmx1, y_corn_mid_top)])
    polylines.append([(cmx0, y_corn_low_top), (cmx0, y_corn_mid_top)])
    polylines.append([(cmx1, y_corn_low_top), (cmx1, y_corn_mid_top)])

    # Modillion placement (centres in x).
    mod_oc = D * dims.modillion_oc_D              # 2/3 D
    mod_length = D * dims.modillion_length_D      # 5/12 D (projection)
    mod_width = D * (2.0 / 9.0)                   # front-face width
    mod_height = corn_h * dims.modillion_height_frac_of_cornice  # 1/5 D
    mod_top_y = y_corn_low_top                   # sits at the top of low band
    # Actually the modillion occupies the middle 1/5 strip, so its top edge
    # aligns with y_corn_low_top and it descends by `mod_height` = 1/5 D
    # (which equals corn_mid_h). Good.

    mod_centres = _modillion_axes(cmx0, cmx1, column_axes_x, mod_oc)

    modillions: list[Polyline] = []
    for cx in mod_centres:
        # Outline.
        outline = _closed(_modillion_outline(
            cx, mod_top_y, mod_length, mod_width, mod_height,
        ))
        modillions.append(outline)

        # Side-shadow on the right face of each modillion.
        half_w = mod_width / 2
        side_shadow = Polygon([
            (cx + half_w * 0.35, mod_top_y),
            (cx + half_w, mod_top_y),
            (cx + half_w, mod_top_y + mod_height * 0.65),
            (cx + half_w * 0.35, mod_top_y + mod_height * 0.65),
        ])
        shadows.append(Shadow(side_shadow, angle_deg=60.0, density="medium"))

        # Acanthus leaf hanging below the modillion (placeholder — replaced by
        # engraving.acanthus.acanthus_leaf once that module is available).
        leaf_h = mod_height * 0.55
        leaf_w = mod_width * 1.05
        modillions.append(_placeholder_acanthus_leaf(
            cx, mod_top_y + mod_height, leaf_w, leaf_h,
        ))

    # Crown of the modillion band: a cyma reversa is understood to ride the
    # top edge. We draw it as a thin rule to mark its presence; the full
    # profile silhouette belongs to a side-section drawing, not this
    # elevation.
    polylines.append([(cmx0, y_corn_mid_top - corn_mid_h * 0.08),
                      (cmx1, y_corn_mid_top - corn_mid_h * 0.08)])

    # ── Cornice, upper 2/5: corona + cymatium ──────────────────────────────
    # Corona occupies the lower ~3/4 of the upper band; cymatium takes the
    # remainder.
    corona_h = corn_up_h * 0.70
    cymatium_h = corn_up_h - corona_h

    y_corona_top = y_corn_mid_top - corona_h
    y_cym_top = y_corona_top - cymatium_h           # = y_corn_top

    # Corona outline (wider than the modillion band). Modillion band supplies
    # y_corn_mid_top already.
    polylines.append([(cux0, y_corona_top), (cux1, y_corona_top)])
    polylines.append([(cux0, y_corn_mid_top), (cux0, y_corona_top)])
    polylines.append([(cux1, y_corn_mid_top), (cux1, y_corona_top)])

    # Cymatium (cyma recta at the top) — mark with a slightly wider band.
    # Corona supplies y_corona_top already.
    polylines.append([(cyx0, y_cym_top), (cyx1, y_cym_top)])
    polylines.append([(cyx0, y_corona_top), (cyx0, y_cym_top)])
    polylines.append([(cyx1, y_corona_top), (cyx1, y_cym_top)])

    # ── Caissons in the corona soffit ──────────────────────────────────────
    # A caisson (square sunken panel) occupies each inter-modillion bay. We
    # inset it from the soffit edges and from the adjacent modillions by a
    # small margin. Each receives a circular rosette at its centre.
    caissons: list[Polyline] = []
    rosettes: list[tuple[Point, float]] = []

    # Margin between caisson and adjacent modillion centre.
    margin = mod_width * 0.9
    caisson_ring_inset = corona_h * 0.18

    # The caisson sits vertically within the corona (centred on it). Remember
    # y grows DOWN: the corona top edge has the smaller y, its bottom edge
    # (y_corn_mid_top) has the larger y.
    cais_y_top = y_corona_top + caisson_ring_inset       # smaller y
    cais_y_bot = y_corn_mid_top - caisson_ring_inset     # larger y
    avail_h = max(0.0, cais_y_bot - cais_y_top)

    for a, b in zip(mod_centres, mod_centres[1:]):
        x_l = a + margin
        x_r = b - margin
        avail_w = x_r - x_l
        if avail_w <= 1e-6 or avail_h <= 1e-6:
            continue
        # Square side = min(width available, height available).
        side = min(avail_w, avail_h)
        cx = (a + b) / 2
        cy = (cais_y_top + cais_y_bot) / 2
        x0 = cx - side / 2
        y0 = cy - side / 2
        caissons.append(rect_corners(x0, y0, side, side))

        # Dark interior shadow for the sunken panel.
        shadows.append(Shadow(
            Polygon([
                (x0, y0), (x0 + side, y0),
                (x0 + side, y0 + side), (x0, y0 + side),
            ]),
            angle_deg=30.0, density="dark",
        ))

        # Rosette centered in the caisson.
        rosette_r = side * 0.28
        rosettes.append(((cx, cy), rosette_r))

    # ── Corona soffit dark shadow (runs from above the modillions up to the
    # front face of the corona, under its projection). ──────────────────────
    shadows.append(Shadow(
        Polygon([
            (cux0, y_corn_mid_top),
            (cux1, y_corn_mid_top),
            (cmx1, y_corn_mid_top + corn_up_h * 0.05),
            (cmx0, y_corn_mid_top + corn_up_h * 0.05),
        ]),
        angle_deg=10.0, density="dark",
    ))

    # Architrave crown rule (very thin ovolo+fillet demarcation).
    polylines.append([(ax0, y_arch_top + crown_h * 0.55),
                      (ax1, y_arch_top + crown_h * 0.55)])

    legacy = {
        "polylines": polylines,
        "shadows": shadows,
        "modillions": modillions,
        "dentils": dentils,
        "caissons": caissons,
        "rosettes": rosettes,
        "top_y": y_cym_top,
        "left_edge": cyx0,
        "right_edge": cyx1,
    }
    if not return_result:
        return legacy

    from .schema import ElementResult
    result = ElementResult(kind=_kind, dims_ref=dims)
    result.add_polylines("fasciae", polylines)
    result.add_polylines("modillions", modillions)
    result.add_polylines("dentils", dentils)
    result.add_polylines("caissons", caissons)
    result.shadows = list(shadows)

    # Attach anchors.
    result.add_anchor("bottom_left", ax0, y_arch_bot, "attach")
    result.add_anchor("bottom_right", ax1, y_arch_bot, "attach")
    result.add_anchor("top_left", cyx0, y_cym_top, "attach")
    result.add_anchor("top_right", cyx1, y_cym_top, "attach")

    # Level anchors
    result.add_anchor("architrave_top", ax0, y_arch_top)
    result.add_anchor("frieze_top", fx0, y_frieze_top)
    result.add_anchor("dentil_band_top", clx0, y_dentil_top)
    result.add_anchor("modillion_band_top", cmx0, y_corn_mid_top)
    result.add_anchor("corona_top", cux0, y_corona_top)

    # Modillion centers as anchors "modillion_i".
    for i, cx in enumerate(mod_centres):
        result.add_anchor(f"modillion_{i}", cx, mod_top_y + mod_height / 2.0,
                          "center")

    # modillions list stores (outline, leaf) pairs — true count is half.
    n_mod = len(modillions) // 2
    result.metadata["num_modillions"] = n_mod
    result.metadata["num_caissons"] = len(caissons)
    result.metadata["num_rosettes"] = len(rosettes)
    result.metadata["num_dentils"] = len(dentils)
    result.metadata["architrave_h"] = y_arch_bot - y_arch_top
    result.metadata["frieze_h"] = y_arch_top - y_frieze_top
    result.metadata["cornice_h"] = y_frieze_top - y_cym_top
    result.metadata["total_h"] = top_of_capital_y - y_cym_top
    result.compute_bbox()
    return result


# ─── Composite entablature ────────────────────────────────────────────────

def composite_entablature(left_x: float, right_x: float,
                          top_of_capital_y: float,
                          dims: canon.Composite,
                          column_axes_x: list[float],
                          *, return_result: bool = False):
    """Build a Composite entablature in elevation.

    The Composite Order (Scamozzi / Vignola) reuses Corinthian proportions for
    its architrave, frieze, and cornice subdivision — but Vignola's tables
    (Ware p.24) specify *larger, squarer dentils*:

        height   = 1/5 D     (vs. ~1/12 D for Corinthian)
        width    = 1/6 D     (vs. 1/18 D)
        oc       = 1/4 D     (vs. 1/6 D)
        gap      = oc - w = 1/12 D

    These values live on ``canon.Composite`` as ``dentil_height_D``,
    ``dentil_width_D``, and ``dentil_oc_D``; we thread them into the
    Corinthian builder via its optional override kwargs.

    All other geometry (modillions, caissons, rosettes, fasciae, bed mold,
    corona, cymatium) remains Corinthian — Ware: "the chief proportions of
    the Composite Order are the same as the Corinthian".
    """
    return corinthian_entablature(
        left_x, right_x, top_of_capital_y,
        dims,                                      # canon.Composite instance
        column_axes_x,
        return_result=return_result,
        dentil_width_D=dims.dentil_width_D,
        dentil_height_D=dims.dentil_height_D,
        dentil_oc_D=dims.dentil_oc_D,
        _kind="composite_entablature",
    )


# ─── Smoke test ────────────────────────────────────────────────────────────

def _smoke() -> None:
    dims = canon.Corinthian(D=20.0)
    result = corinthian_entablature(
        left_x=40.0,
        right_x=260.0,
        top_of_capital_y=200.0,
        dims=dims,
        column_axes_x=[60.0, 120.0, 180.0, 240.0],
    )
    # modillions list contains (outline, leaf) pairs — one leaf per modillion
    # — so the true count is half its length.
    n_mod = len(result["modillions"]) // 2
    n_dentil = len(result["dentils"])
    n_caisson = len(result["caissons"])
    n_rosette = len(result["rosettes"])
    n_shadow = len(result["shadows"])
    print(f"D = {dims.D} mm")
    print(f"cornice span: [{result['left_edge']:.2f}, "
          f"{result['right_edge']:.2f}] mm   "
          f"top_y = {result['top_y']:.2f}")
    print(f"modillions : {n_mod}")
    print(f"dentils    : {n_dentil}")
    print(f"caissons   : {n_caisson}")
    print(f"rosettes   : {n_rosette}")
    print(f"shadows    : {n_shadow}")
    print(f"polylines  : {len(result['polylines'])}")


if __name__ == "__main__":
    _smoke()
