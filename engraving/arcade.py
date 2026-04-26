"""Arcades — sequences of arches on piers or columns.

An arcade is the horizontal sibling of a colonnade: a row of N bays, each
spanned by an arch whose springings rest on piers (or, in richer cases,
columns). It is the unit of every cloister walk, aqueduct, Roman basilica,
and palazzo ground floor. Once arches, pilasters, and columns exist as
primitives, an arcade is simply their composition repeated along a baseline.

Coordinate convention matches the rest of the package: mm, y increases
downward (SVG). The ``y_base`` argument is the ground line; the arcade
grows UPWARD from there (smaller y).

Layout
------
For an arcade of ``bay_count`` bays with ``bay_count + 1`` piers framing
them, we slice the total ``width`` as:

    pier_count       = bay_count + 1
    pier_width       = pier_width_frac * (width / pier_count)
    total_pier_width = pier_width * pier_count
    clear_span       = (width - total_pier_width) / bay_count   # per arch

Each pier's left edge sits at x = x0 + i*(pier_width + clear_span).

Vertical partition (from y_base upward):

    base_course height     = height * 0.04
    spring line height     = height * 0.55      (y_spring = y_base - 0.55h)
    entablature height     = height * 0.08      (optional)

The piers stand between the base-course top and the impost course bottom;
the arches spring above the imposts; an optional entablature caps the
whole arcade.
"""
from __future__ import annotations

from typing import Literal

from .arches import semicircular_arch, segmental_arch
from .geometry import Point, Polyline, rect_corners
from .schema import ElementResult


def arcade(x0: float, y_base: float, width: float, height: float,
           bay_count: int,
           arch_type: Literal["semicircular", "segmental"] = "semicircular",
           pier_width_frac: float = 0.32,
           impost_height_frac: float = 0.04,
           segmental_rise_frac: float = 0.15,
           with_keystones: bool = True,
           with_entablature: bool = False) -> ElementResult:
    """Build an arcade spanning (x0, y_base) to (x0+width, y_base-height).

    Args:
        x0, y_base: bottom-left corner (y_base is the ground line;
            arcade grows up — smaller y).
        width, height: overall arcade dimensions (mm).
        bay_count: number of arch bays (≥1).
        arch_type: "semicircular" (rise=span/2) or "segmental"
            (rise = segmental_rise_frac × clear-span).
        pier_width_frac: pier width as fraction of (width / pier_count).
            Larger values give stockier piers; 0.32 gives pier:clear-span
            ≈ 0.39 (Vignola: pier_width ≈ 1/3 to 1/2 of the clear span).
        impost_height_frac: impost thickness as fraction of height.
        segmental_rise_frac: rise as fraction of clear-span for segmental
            arches (0 < rise_frac < 0.5).
        with_keystones: draw a keystone at each arch apex.
        with_entablature: cap the arcade with a simple entablature running
            above the arch extradoses.

    Returns ElementResult with polyline layers:
        base_course, piers, imposts, arches, voussoirs, keystones,
        entablature, shadows (Shadow instances go into result.shadows).

    Anchors include:
        pier_i_left, pier_i_right, pier_i_center (for i in 0..pier_count-1);
        arch_i_spring_left, arch_i_spring_right, arch_i_apex
            (for i in 0..bay_count-1);
        arcade_bottom_left, arcade_bottom_right,
        arcade_top_left, arcade_top_right.

    Metadata: bay_count, pier_count, arch_count, y_spring, y_base, y_top,
        pier_width, clear_span, bay_pitch, arch_type.
    """
    if bay_count < 1:
        raise ValueError(f"bay_count must be >= 1, got {bay_count}")
    if not (0.0 < pier_width_frac < 1.0):
        raise ValueError(
            f"pier_width_frac must be in (0, 1); got {pier_width_frac}")
    if arch_type == "segmental" and not (0.0 < segmental_rise_frac < 0.5):
        raise ValueError(
            f"segmental_rise_frac must be in (0, 0.5); "
            f"got {segmental_rise_frac}")

    # --- Layout math -----------------------------------------------------
    pier_count = bay_count + 1
    bay_pitch_total = width / pier_count
    pier_width = pier_width_frac * bay_pitch_total
    total_pier_width = pier_width * pier_count
    clear_span = (width - total_pier_width) / bay_count
    if clear_span <= 0:
        raise ValueError(
            f"clear_span nonpositive (pier_width_frac too large for "
            f"bay_count={bay_count}); got clear_span={clear_span}")

    # Vertical partition.
    base_course_h = height * 0.04
    impost_h = height * impost_height_frac
    entablature_h = height * 0.08 if with_entablature else 0.0
    y_top = y_base - height

    # y_spring: position the springing line so the arch extrados (intrados
    # + a small band thickness) just fits below the top of the arcade
    # (minus any entablature and a clearance margin). This makes the
    # drawn geometry fill the declared (x0, y_base, width, height) bbox
    # regardless of bay_count — the piers occupy the bottom portion,
    # arches the top portion, and the whole composition reads as one
    # arcade.
    if arch_type == "semicircular":
        arch_rise = clear_span / 2.0
    else:
        arch_rise = segmental_rise_frac * clear_span
    # The arches module's extrados projects about span/72 beyond the
    # intrados; use span/12 as a conservative margin so the extrados and
    # keystone (which protrudes another span/72) sit below y_top.
    extrados_margin = clear_span / 10.0
    y_spring = y_top + entablature_h + extrados_margin + arch_rise
    # Safety clamps — always leave at least a 15% pier height and a 10%
    # arch fit.
    min_y_spring = y_top + entablature_h + 0.15 * height
    max_y_spring = y_base - base_course_h - 0.15 * height
    y_spring = min(max(y_spring, min_y_spring), max_y_spring)

    # --- Result container ------------------------------------------------
    result = ElementResult(kind="arcade")

    # --- Base course -----------------------------------------------------
    # A continuous rectangular band along the bottom of the arcade.
    y_base_course_top = y_base - base_course_h
    base_course = rect_corners(x0, y_base_course_top, width, base_course_h)
    result.add_polylines("base_course", [base_course])

    # --- Pier positions --------------------------------------------------
    pier_left_xs: list[float] = []
    for i in range(pier_count):
        px_left = x0 + i * (pier_width + clear_span)
        pier_left_xs.append(px_left)

    # Impost: the springing line IS the top of the impost. The impost
    # rests atop the piers and the arches spring off its top face.
    y_impost_top = y_spring                 # smaller y = upper edge
    y_impost_bot = y_spring + impost_h      # larger y = lower edge
    y_pier_top = y_impost_bot               # piers end at impost underside

    for i, px_left in enumerate(pier_left_xs):
        px_right = px_left + pier_width
        pier_poly = rect_corners(px_left, y_pier_top,
                                 pier_width, y_base_course_top - y_pier_top)
        result.add_polylines("piers", [pier_poly])
        # Anchors
        result.add_anchor(f"pier_{i}_left", px_left, y_pier_top, "corner")
        result.add_anchor(f"pier_{i}_right", px_right, y_pier_top, "corner")
        result.add_anchor(f"pier_{i}_center",
                          px_left + pier_width / 2.0, y_pier_top, "center")

    # --- Impost course ---------------------------------------------------
    # One impost block crowning each pier. The impost overhangs the pier
    # by a small amount on each side (a classical capital-like projection)
    # so the springing of each arch visually seats on the impost block.
    # The impost is NOT drawn across the clear bays — the bays must be
    # empty from y_impost_top upward so the arches read as springing
    # directly from the impost top.
    impost_overhang = min(pier_width * 0.15, clear_span * 0.05)
    x_arcade_right = x0 + width
    for i, px_left in enumerate(pier_left_xs):
        # Clamp end-pier overhangs so the impost never extends past the
        # declared arcade bbox.
        left_oh = 0.0 if i == 0 else impost_overhang
        right_oh = 0.0 if i == pier_count - 1 else impost_overhang
        ix_left = px_left - left_oh
        ix_width = pier_width + left_oh + right_oh
        # Guard against numerical drift at the outer edges.
        if ix_left < x0:
            ix_width -= (x0 - ix_left)
            ix_left = x0
        if ix_left + ix_width > x_arcade_right:
            ix_width = x_arcade_right - ix_left
        impost_block = rect_corners(ix_left, y_impost_top,
                                    ix_width, impost_h)
        result.add_polylines("imposts", [impost_block])

    # --- Arches, voussoirs, keystones, shadows ---------------------------
    for i in range(bay_count):
        # Arch springs from top-right of pier i to top-left of pier i+1.
        spring_x_left = pier_left_xs[i] + pier_width
        spring_x_right = pier_left_xs[i + 1]
        arch_cx = 0.5 * (spring_x_left + spring_x_right)
        span = spring_x_right - spring_x_left

        if arch_type == "semicircular":
            arch_out = semicircular_arch(
                cx=arch_cx, y_spring=y_spring, span=span,
                voussoir_count=9,
                with_keystone=with_keystones,
                archivolt_bands=0,
            )
            apex_y = y_spring - span / 2.0
        else:
            rise = segmental_rise_frac * span
            arch_out = segmental_arch(
                cx=arch_cx, y_spring=y_spring, span=span, rise=rise,
                voussoir_count=9,
                with_keystone=with_keystones,
                archivolt_bands=0,
            )
            apex_y = y_spring - rise

        # Collect layers.
        if arch_out.get("intrados"):
            result.add_polylines("arches", arch_out["intrados"])
        if arch_out.get("extrados"):
            result.add_polylines("arches", arch_out["extrados"])
        if arch_out.get("voussoirs"):
            result.add_polylines("voussoirs", arch_out["voussoirs"])
        if with_keystones and arch_out.get("keystone"):
            result.add_polylines("keystones", [arch_out["keystone"]])
        # Shadows — live on result.shadows, not polylines.
        if arch_out.get("shadows"):
            result.shadows.extend(arch_out["shadows"])

        # Anchors for this arch.
        result.add_anchor(f"arch_{i}_spring_left",
                          spring_x_left, y_spring, "spring")
        result.add_anchor(f"arch_{i}_spring_right",
                          spring_x_right, y_spring, "spring")
        result.add_anchor(f"arch_{i}_apex", arch_cx, apex_y, "center")

    # --- Entablature (optional) ------------------------------------------
    if with_entablature:
        ent_bot_y = y_top + entablature_h
        ent_poly = rect_corners(x0, y_top, width, entablature_h)
        result.add_polylines("entablature", [ent_poly])
        # A secondary rule for the architrave/frieze division (one third).
        third = entablature_h / 3.0
        rule_y = y_top + third
        result.add_polylines("entablature",
                             [[(x0, rule_y), (x0 + width, rule_y)]])
        _ = ent_bot_y  # unused; kept for clarity

    # --- Corner anchors --------------------------------------------------
    result.add_anchor("arcade_bottom_left", x0, y_base, "corner")
    result.add_anchor("arcade_bottom_right", x0 + width, y_base, "corner")
    result.add_anchor("arcade_top_left", x0, y_top, "corner")
    result.add_anchor("arcade_top_right", x0 + width, y_top, "corner")

    # --- Metadata --------------------------------------------------------
    result.metadata.update({
        "bay_count": bay_count,
        "pier_count": pier_count,
        "arch_count": bay_count,
        "y_spring": y_spring,
        "y_base": y_base,
        "y_top": y_top,
        "pier_width": pier_width,
        "clear_span": clear_span,
        "bay_pitch": pier_width + clear_span,
        "arch_type": arch_type,
        "with_entablature": with_entablature,
        "with_keystones": with_keystones,
    })

    result.compute_bbox()
    return result


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import drawsvg as dw

    from engraving.preview import render_svg_to_png
    from engraving.validate.elements import validate_arcade

    result = arcade(x0=20, y_base=180, width=220, height=160,
                    bay_count=5, arch_type="semicircular",
                    pier_width_frac=0.32, with_keystones=True)

    d = dw.Drawing(260, 200, origin=(0, 0))
    # White background
    d.append(dw.Rectangle(0, 0, 260, 200, fill="white"))
    for layer_name, lines in result.polylines.items():
        for pl in lines:
            if len(pl) < 2:
                continue
            flat: list[float] = []
            for x, y in pl:
                flat.extend([x, y])
            d.append(dw.Lines(*flat, close=False, fill="none",
                              stroke="black", stroke_width=0.25))
    d.save_svg("/tmp/arcade_test.svg")
    render_svg_to_png("/tmp/arcade_test.svg",
                      "/tmp/arcade_test.png", dpi=200)

    # Validate
    report = validate_arcade(result)
    print(f"Arcade validation: {len(report)} errors")
    for e in report:
        print(f"  - {e}")

    # Summary
    print("--- Layers ---")
    for name, lines in result.polylines.items():
        print(f"  {name}: {len(lines)} polylines")
    print(f"  shadows: {len(result.shadows)}")
    print(f"  anchors: {len(result.anchors)}")
    print(f"  metadata: {result.metadata}")
