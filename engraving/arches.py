"""Classical arches in elevation — semicircular and segmental.

Arches are a base primitive for facade composition. This module supplies the
period-standard types with their accompanying ornamental apparatus:
imposts (the molded shelf where the arch springs from the pier), voussoirs
(wedge-shaped stones radiating from the center), a projecting keystone, and
optional nested archivolts (concentric molded bands following the extrados).

Coordinate convention: mm, y increases downward (SVG). The springing line is
at y_spring; the apex of the arch is above it, i.e. at smaller y.

For a semicircular arch the arch's geometric center sits on the springing
line at (cx, y_spring) and the intrados sweeps from angle pi (left springing)
through 3*pi/2 (apex, upward since sin(3*pi/2) = -1 with y-down means y is
smaller) to 2*pi (right springing).

For a segmental arch the center drops below the springing line by h, where
R = (span^2 + 4*rise^2) / (8*rise) and h = R - rise. The intrados then sweeps
a shallower symmetric arc whose chord is the springing line.
"""
from __future__ import annotations

import math

from shapely.geometry import Polygon

from .elements import Shadow
from .geometry import Point, Polyline, arc, line


# ---------------------------------------------------------------------------
# Impost
# ---------------------------------------------------------------------------

def impost(x_center: float, y_spring: float, width: float, height: float) -> Polyline:
    """A plain impost block as a closed rectangle polyline.

    The block sits with its top edge on the springing line y_spring (the
    underside of the arch rests on the top of the impost), centered on
    x_center. width is horizontal, height is vertical.
    """
    x0 = x_center - width / 2
    x1 = x_center + width / 2
    y_top = y_spring - height / 2
    y_bot = y_spring + height / 2
    return [
        (x0, y_top),
        (x1, y_top),
        (x1, y_bot),
        (x0, y_bot),
        (x0, y_top),
    ]


def _impost_bands(x_center: float, y_spring: float, width: float, height: float) -> list[Polyline]:
    """Three-banded stacked impost cornice: fascia, fillet, cyma-ish step.

    Produces a small cornice profile of closed rectangular bands, widest at
    the top (cornice projection), narrower fillet, then the neck band. Used
    as the molded cap of a pier where the arch springs.
    """
    bands: list[Polyline] = []
    # Proportions: top cornice band (widest) 35% of height, fillet 20%, neck 45%.
    h_cornice = height * 0.35
    h_fillet = height * 0.20
    h_neck = height - h_cornice - h_fillet

    w_cornice = width
    w_fillet = width * 0.80
    w_neck = width * 0.72

    y_top = y_spring - height  # top of impost sits this far above springing
    # Actually the springing line is the top of the impost where the arch sits,
    # so the impost itself extends DOWN from y_spring. Top of impost = y_spring.
    y_cornice_top = y_spring
    y_cornice_bot = y_cornice_top + h_cornice
    y_fillet_top = y_cornice_bot
    y_fillet_bot = y_fillet_top + h_fillet
    y_neck_top = y_fillet_bot
    y_neck_bot = y_neck_top + h_neck

    def rect(xc: float, w: float, yt: float, yb: float) -> Polyline:
        x0 = xc - w / 2
        x1 = xc + w / 2
        return [(x0, yt), (x1, yt), (x1, yb), (x0, yb), (x0, yt)]

    bands.append(rect(x_center, w_cornice, y_cornice_top, y_cornice_bot))
    bands.append(rect(x_center, w_fillet, y_fillet_top, y_fillet_bot))
    bands.append(rect(x_center, w_neck, y_neck_top, y_neck_bot))
    _ = y_top  # silence unused; kept for clarity
    return bands


# ---------------------------------------------------------------------------
# Internal: construct an arch given center, radius, and angular extent
# ---------------------------------------------------------------------------

def _build_arch(cx: float,
                cy: float,
                r_intrados: float,
                a_left: float,
                a_right: float,
                y_spring: float,
                span: float,
                voussoir_count: int,
                with_keystone: bool,
                keystone_width: float | None,
                archivolt_bands: int) -> dict:
    """Shared construction for both semicircular and segmental arches.

    cy: y of arch's geometric center (may be above or below y_spring).
    a_left, a_right: angles (radians) at the left springing and right
        springing. Both produce y = y_spring on the intrados. The arc passes
        over the apex going through (a_left + a_right) / 2 which must point
        "upward" in screen coords (sin(angle) < 0).
    """
    steps_arc = 96
    # Outer band thickness. One archivolt band == keystone_w / 6 offset.
    # Even with no archivolts we still want a visible extrados at the same
    # nominal thickness so the arch reads as a molded band.
    ks_w = keystone_width if keystone_width is not None else span / 12.0
    band_step = ks_w / 6.0
    # Always leave room for at least one band thickness as the base extrados.
    extrados_thickness = band_step * (max(1, archivolt_bands + 1))
    r_extrados = r_intrados + extrados_thickness

    # --- Intrados & extrados --------------------------------------------------
    intrados = arc(cx, cy, r_intrados, a_left, a_right, steps=steps_arc)
    extrados = arc(cx, cy, r_extrados, a_left, a_right, steps=steps_arc)

    # --- Archivolt bands ------------------------------------------------------
    archivolts: list[Polyline] = []
    for i in range(1, archivolt_bands + 1):
        r_band = r_intrados + band_step * i
        archivolts.append(arc(cx, cy, r_band, a_left, a_right, steps=steps_arc))

    # --- Voussoirs (radial joint lines) --------------------------------------
    voussoirs: list[Polyline] = []
    # We want lines from intrados to extrados at equal angular spacing,
    # skipping the keystone slot at the middle when with_keystone is True.
    apex_angle = (a_left + a_right) / 2.0
    if voussoir_count > 0:
        # Compute half-angle subtended by the keystone at the intrados.
        # Keystone width is measured along the horizontal at the apex; the
        # corresponding arc subtends ks_w across the intrados. Use the
        # chord-to-angle approximation: theta = 2 * asin((w/2) / r).
        if with_keystone:
            half_ks = min(0.98, (ks_w / 2.0) / r_intrados)
            ks_half_angle = math.asin(half_ks)
        else:
            ks_half_angle = 0.0

        # Even spacing: voussoir_count joints distributed between a_left and
        # a_right, excluding the two springing lines themselves (those are the
        # interface with the impost, not a voussoir joint). We place joints
        # at the boundaries between wedges.
        #
        # If with_keystone: reserve the two joints flanking the apex for the
        # keystone trapezoid; the remaining (voussoir_count - 1) joints are
        # shared between the two haunches. Otherwise voussoir_count joints
        # distribute evenly across the full arc interior.
        total_span = a_right - a_left
        if with_keystone:
            # Angles from apex where keystone edges sit.
            left_ks_angle = apex_angle - ks_half_angle
            right_ks_angle = apex_angle + ks_half_angle
            # Per-haunch interior span:
            haunch_span_left = left_ks_angle - a_left
            haunch_span_right = a_right - right_ks_angle
            # Roughly half the remaining joints per haunch.
            remaining = max(0, voussoir_count - 1)
            per_side = remaining // 2
            # Place per_side interior joints in each haunch at even spacing.
            if per_side > 0:
                for i in range(1, per_side + 1):
                    frac = i / (per_side + 1)
                    a = a_left + haunch_span_left * frac
                    _append_radial(voussoirs, cx, cy, r_intrados, r_extrados, a)
                    a = right_ks_angle + haunch_span_right * frac
                    _append_radial(voussoirs, cx, cy, r_intrados, r_extrados, a)
            # If voussoir_count - 1 is odd, one extra joint at apex-adjacent
            # position; put it in the longer haunch (they're symmetric, so
            # pick left arbitrarily).
            extra = remaining - 2 * per_side
            if extra == 1:
                frac = (per_side + 1) / (per_side + 2)
                a = a_left + haunch_span_left * frac
                _append_radial(voussoirs, cx, cy, r_intrados, r_extrados, a)
        else:
            for i in range(1, voussoir_count + 1):
                frac = i / (voussoir_count + 1)
                a = a_left + total_span * frac
                _append_radial(voussoirs, cx, cy, r_intrados, r_extrados, a)

    # --- Keystone -------------------------------------------------------------
    keystone: Polyline = []
    if with_keystone:
        half_ks = min(0.98, (ks_w / 2.0) / r_intrados)
        ks_half_angle = math.asin(half_ks)
        a_kl = apex_angle - ks_half_angle
        a_kr = apex_angle + ks_half_angle
        # Inner edges sit ON the intrados; outer edges project past the
        # extrados by ks_w/6 (period practice: keystone proud of the archivolt).
        r_ks_out = r_extrados + ks_w / 6.0
        pl_in = (cx + r_intrados * math.cos(a_kl), cy + r_intrados * math.sin(a_kl))
        pr_in = (cx + r_intrados * math.cos(a_kr), cy + r_intrados * math.sin(a_kr))
        pl_out = (cx + r_ks_out * math.cos(a_kl), cy + r_ks_out * math.sin(a_kl))
        pr_out = (cx + r_ks_out * math.cos(a_kr), cy + r_ks_out * math.sin(a_kr))
        # Closed trapezoid (radial sides, curved inner/outer approximated as
        # straight chords — the keystone is narrow enough that this reads
        # cleanly).
        keystone = [pl_in, pl_out, pr_out, pr_in, pl_in]

    # --- Imposts (molded cornice at each springing) ---------------------------
    # Width: pier-ward of the intrados springing by ~span/10, outward by span/10.
    imp_width = max(ks_w * 1.8, span * 0.14)
    imp_height = max(ks_w * 1.2, span * 0.08)
    left_spring_x = cx + r_intrados * math.cos(a_left)
    right_spring_x = cx + r_intrados * math.cos(a_right)

    imposts: list[Polyline] = []
    imposts.extend(_impost_bands(left_spring_x, y_spring, imp_width, imp_height))
    imposts.extend(_impost_bands(right_spring_x, y_spring, imp_width, imp_height))

    # --- Shadows --------------------------------------------------------------
    shadows: list[Shadow] = []
    # 1) Intrados soffit shadow: thin band along the interior of the intrados
    #    near the springing on the right side (light from upper-left).
    #    We approximate with a narrow annular wedge near the right haunch.
    soffit_band = _annular_wedge(cx, cy,
                                 r_intrados, r_intrados + band_step * 0.6,
                                 a_right - (a_right - apex_angle) * 0.55, a_right)
    if soffit_band is not None:
        shadows.append(Shadow(soffit_band, angle_deg=20.0, density="medium"))

    # 2) Keystone side shadow: right flank of the keystone (projection casts).
    if with_keystone and keystone:
        # Right flank of keystone from pr_in to pr_out, extended outward a hair.
        shadow_poly = Polygon([
            pr_in,
            pr_out,
            (pr_out[0] + ks_w * 0.18, pr_out[1] + ks_w * 0.10),
            (pr_in[0] + ks_w * 0.18, pr_in[1] + ks_w * 0.10),
        ])
        if shadow_poly.is_valid and shadow_poly.area > 0:
            shadows.append(Shadow(shadow_poly, angle_deg=60.0, density="dark"))

    # 3) Impost soffit: a thin dark line under each impost's cornice band.
    for spring_x in (left_spring_x, right_spring_x):
        under = Polygon([
            (spring_x - imp_width / 2, y_spring),
            (spring_x + imp_width / 2, y_spring),
            (spring_x + imp_width * 0.42, y_spring + imp_height * 0.10),
            (spring_x - imp_width * 0.42, y_spring + imp_height * 0.10),
        ])
        if under.is_valid and under.area > 0:
            shadows.append(Shadow(under, angle_deg=10.0, density="dark"))

    return {
        "intrados": [intrados],
        "extrados": [extrados],
        "voussoirs": voussoirs,
        "keystone": keystone,
        "archivolts": archivolts,
        "imposts": imposts,
        "shadows": shadows,
    }


def _append_radial(out: list[Polyline], cx: float, cy: float,
                   r_in: float, r_out: float, angle: float) -> None:
    p_in = (cx + r_in * math.cos(angle), cy + r_in * math.sin(angle))
    p_out = (cx + r_out * math.cos(angle), cy + r_out * math.sin(angle))
    out.append(line(p_in, p_out))


def _annular_wedge(cx: float, cy: float, r_in: float, r_out: float,
                   a_start: float, a_end: float, steps: int = 24) -> Polygon | None:
    """Return a shapely Polygon for an annular wedge (donut sector)."""
    if a_end <= a_start or r_out <= r_in:
        return None
    inner = arc(cx, cy, r_in, a_start, a_end, steps=steps)
    outer = arc(cx, cy, r_out, a_end, a_start, steps=steps)
    ring = inner + outer + [inner[0]]
    try:
        poly = Polygon(ring)
        if not poly.is_valid:
            poly = poly.buffer(0)
        if poly.is_empty:
            return None
        return poly
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def semicircular_arch(cx: float, y_spring: float, span: float,
                      voussoir_count: int = 0,
                      with_keystone: bool = True,
                      keystone_width: float | None = None,
                      archivolt_bands: int = 0) -> dict:
    """Semicircular (Roman) arch: rise = span / 2. Center at (cx, y_spring)."""
    r = span / 2.0
    # In screen coords with y down, the top of a circle at (cx, y_spring) with
    # radius r is at (cx, y_spring - r). sin(3*pi/2) = -1, so angle 3*pi/2
    # gives y = y_spring - r (the apex). a_left = pi gives (cx - r, y_spring);
    # a_right = 2*pi gives (cx + r, y_spring).
    return _build_arch(
        cx=cx,
        cy=y_spring,
        r_intrados=r,
        a_left=math.pi,
        a_right=2.0 * math.pi,
        y_spring=y_spring,
        span=span,
        voussoir_count=voussoir_count,
        with_keystone=with_keystone,
        keystone_width=keystone_width,
        archivolt_bands=archivolt_bands,
    )


def segmental_arch(cx: float, y_spring: float, span: float, rise: float,
                   voussoir_count: int = 0,
                   with_keystone: bool = True,
                   keystone_width: float | None = None,
                   archivolt_bands: int = 0) -> dict:
    """Segmental arch: rise < span / 2. Chord = span, rise = y_spring - y_apex.

    Solves R and the center offset h from the standard chord-height relation:
        R = (span^2 + 4*rise^2) / (8*rise)
        h = R - rise  (distance from springing line DOWN to the circle center)
    """
    if rise <= 0:
        raise ValueError("rise must be > 0")
    if rise >= span / 2.0:
        raise ValueError("rise must be < span/2; use semicircular_arch instead")

    R = (span * span + 4.0 * rise * rise) / (8.0 * rise)
    h = R - rise
    # Circle center sits BELOW the springing line (larger y in screen coords).
    cy = y_spring + h

    # Angle at right springing: point (cx + span/2, y_spring) relative to
    # center (cx, cy). dx = span/2, dy = y_spring - cy = -h. In screen coords
    # the angle is atan2(dy, dx) = atan2(-h, span/2), a negative angle between
    # -pi/2 and 0 (because the point is above the center). The left springing
    # mirrors: atan2(-h, -span/2), between -pi and -pi/2.
    a_right = math.atan2(y_spring - cy, span / 2.0)
    a_left = math.atan2(y_spring - cy, -span / 2.0)
    # a_left is in (-pi, -pi/2), a_right is in (-pi/2, 0). The apex angle is
    # (a_left + a_right) / 2 = -pi/2, which gives point (cx, cy - R) —
    # above the center by R, hence y = cy - R = y_spring + h - R = y_spring - rise.

    return _build_arch(
        cx=cx,
        cy=cy,
        r_intrados=R,
        a_left=a_left,
        a_right=a_right,
        y_spring=y_spring,
        span=span,
        voussoir_count=voussoir_count,
        with_keystone=with_keystone,
        keystone_width=keystone_width,
        archivolt_bands=archivolt_bands,
    )


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

def _describe(result: dict, label: str) -> None:
    print(f"--- {label} ---")
    for k, v in result.items():
        if isinstance(v, list):
            if v and isinstance(v[0], tuple):
                # a single polyline stored as list of points
                print(f"  {k}: 1 polyline ({len(v)} pts)")
            else:
                # list of polylines / shadows
                total_pts = 0
                for item in v:
                    if isinstance(item, list):
                        total_pts += len(item)
                print(f"  {k}: {len(v)} entries"
                      + (f" ({total_pts} total pts)" if total_pts else ""))
        else:
            print(f"  {k}: {type(v).__name__}")


def _main() -> None:
    semi = semicircular_arch(cx=100, y_spring=180, span=80,
                             voussoir_count=9,
                             with_keystone=True,
                             archivolt_bands=2)
    print("keys:", list(semi.keys()))
    _describe(semi, "semicircular_arch (span=80, 9 voussoirs, 2 archivolts)")

    seg = segmental_arch(cx=100, y_spring=180, span=80, rise=15,
                         voussoir_count=9)
    _describe(seg, "segmental_arch (span=80, rise=15, 9 voussoirs)")

    # Sanity checks
    # Arcs are sampled discretely (96 steps), so the sampled apex can be
    # slightly below the true apex. Tolerate a fraction of the radius.
    intr = semi["intrados"][0]
    ys = [p[1] for p in intr]
    assert min(ys) < 180, "semicircular apex should be above springing"
    assert abs(min(ys) - (180 - 40)) < 0.05, \
        f"semicircular apex should be near y=140, got {min(ys)}"

    seg_intr = seg["intrados"][0]
    seg_ys = [p[1] for p in seg_intr]
    assert abs(min(seg_ys) - (180 - 15)) < 0.05, \
        f"segmental apex should be near y=165, got {min(seg_ys)}"

    print("smoke test OK")


if __name__ == "__main__":
    _main()
