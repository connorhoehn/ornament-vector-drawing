"""Architectural elements — compositions of profiles and orders in elevation.

Each builder function returns a dict of named polylines / shapely regions so
callers (plates) can stroke silhouettes and fill shadow regions separately.

Coordinate convention: elevation drawings. Ground line at y = ground_y.
Elements are placed with their base at ground_y and grow upward (negative y).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from .. import profiles as P
from .. import orders as O
from ..geometry import Point, Polyline, mirror_path_x, translate_path


@dataclass
class Shadow:
    """A shadow region (shapely Polygon) + preferred hatch angle in degrees."""
    polygon: Polygon
    angle_deg: float = 45.0
    density: str = "medium"  # light/medium/dark → spacing


def pedestal(cx: float, ground_y: float, dims: O.TuscanDims) -> dict:
    """Classical pedestal (plinth + dado + cornice). Returns a single closed
    silhouette polyline plus shadow regions.

    Proportions follow Ware's *American Vignola* convention: the dado is the
    narrow rectangular "body" of the pedestal; the plinth and cornice project
    equally beyond it, forming a symmetric base-and-cap profile. Earlier
    versions had the cornice narrower than the plinth, which read as a
    stepped-pyramid stylobate instead of a Roman pedestal.
    """
    M = dims.M
    plinth_h = dims.plinth_h
    dado_h = dims.dado_h
    corn_h = dims.cornice_ped_h

    # Dado is the canonical "body"; plinth + cornice project equally beyond
    # it. Projection ≈ 0.18 M ≈ 1/11 D — small but clearly readable.
    half_dado = 1.4 * M
    projection = 0.20 * M
    half_plinth = half_dado + projection
    half_corn = half_dado + projection

    y_top = ground_y - dims.pedestal_h
    y_plinth_top = ground_y - plinth_h
    y_dado_top = y_plinth_top - dado_h

    # Cornice is a single rectangular cap that projects equally with the
    # plinth. The dado is the recessed middle. The outline traces: bottom-
    # left of plinth → up → step-in to dado → up → step-out to cornice → up
    # across top → mirror back down.
    outline = [
        (cx - half_plinth, ground_y),
        (cx - half_plinth, y_plinth_top),
        (cx - half_dado, y_plinth_top),
        (cx - half_dado, y_dado_top),
        (cx - half_corn, y_dado_top),
        (cx - half_corn, y_top),
        (cx + half_corn, y_top),
        (cx + half_corn, y_dado_top),
        (cx + half_dado, y_dado_top),
        (cx + half_dado, y_plinth_top),
        (cx + half_plinth, y_plinth_top),
        (cx + half_plinth, ground_y),
        (cx - half_plinth, ground_y),
    ]

    # Shadow on the right-hand face of the dado (assume light from upper-left)
    right_dado_shadow = Polygon([
        (cx + half_dado - M * 0.25, y_plinth_top),
        (cx + half_dado, y_plinth_top),
        (cx + half_dado, y_dado_top),
        (cx + half_dado - M * 0.25, y_dado_top),
    ])

    # Soffit shadow under the cornice cap
    cornice_soffit = Polygon([
        (cx - half_corn, y_dado_top),
        (cx + half_corn, y_dado_top),
        (cx + half_dado, y_dado_top + M * 0.08),
        (cx - half_dado, y_dado_top + M * 0.08),
    ])

    return {
        "outline": outline,
        "shadows": [
            Shadow(right_dado_shadow, angle_deg=60.0, density="medium"),
            Shadow(cornice_soffit, angle_deg=10.0, density="dark"),
        ],
        "top_y": y_top,
        "half_plinth": half_plinth,
        "half_dado": half_dado,
        "half_cornice": half_corn,
    }


def column(cx: float, base_y: float, dims: O.TuscanDims) -> dict:
    """Tuscan column. base_y is top of pedestal / bottom of column."""
    silhouettes = O.tuscan_column_silhouette(dims, cx, base_y)
    # Cast shadow: right side of the shaft, narrow band
    M = dims.M
    r = dims.lower_diam / 2
    y_shaft_top = base_y - dims.base_h - dims.shaft_h
    shaft_shadow = Polygon([
        (cx + r - M * 0.35, base_y - dims.base_h),
        (cx + r, base_y - dims.base_h),
        (cx + r * dims.upper_diam / dims.lower_diam, y_shaft_top),
        (cx + r * dims.upper_diam / dims.lower_diam - M * 0.28, y_shaft_top),
    ])
    return {
        "silhouettes": silhouettes,
        "shadows": [Shadow(shaft_shadow, angle_deg=80.0, density="light")],
        "capital_top_y": y_shaft_top - dims.capital_h,
    }


def entablature(left_x: float, right_x: float, top_of_capital_y: float,
                dims: O.TuscanDims, with_dentils: bool = False) -> dict:
    """Horizontal entablature: architrave, frieze, cornice. Sits on top of capitals.

    Returns polylines for edges and lists of shadow regions.
    """
    M = dims.M
    arch_h = dims.architrave_h
    fr_h = dims.frieze_h
    corn_h = dims.cornice_h

    y_arch_bot = top_of_capital_y
    y_arch_top = y_arch_bot - arch_h
    y_frieze_top = y_arch_top - fr_h
    y_corn_top = y_frieze_top - corn_h

    # Cornice projects outward from the architrave line.
    project_arch = M * 0.0
    project_fr = M * 0.05
    project_corn = M * 0.45

    polylines: list[Polyline] = []
    # Architrave band
    ax0 = left_x - project_arch
    ax1 = right_x + project_arch
    polylines.append([(ax0, y_arch_bot), (ax1, y_arch_bot)])
    polylines.append([(ax0, y_arch_top), (ax1, y_arch_top)])
    polylines.append([(ax0, y_arch_bot), (ax0, y_arch_top)])
    polylines.append([(ax1, y_arch_bot), (ax1, y_arch_top)])
    # small fascia rule
    polylines.append([(ax0, y_arch_bot - arch_h * 0.35),
                      (ax1, y_arch_bot - arch_h * 0.35)])

    # Frieze band
    fx0 = left_x - project_fr
    fx1 = right_x + project_fr
    polylines.append([(fx0, y_arch_top), (fx1, y_arch_top)])
    polylines.append([(fx0, y_frieze_top), (fx1, y_frieze_top)])
    polylines.append([(fx0, y_arch_top), (fx0, y_frieze_top)])
    polylines.append([(fx1, y_arch_top), (fx1, y_frieze_top)])

    # Cornice
    cx0 = left_x - project_corn
    cx1 = right_x + project_corn
    polylines.append([(cx0, y_frieze_top), (cx1, y_frieze_top)])
    polylines.append([(cx0, y_corn_top), (cx1, y_corn_top)])
    polylines.append([(cx0, y_frieze_top), (cx0, y_corn_top)])
    polylines.append([(cx1, y_frieze_top), (cx1, y_corn_top)])

    # Cornice moldings (cyma reversa + fillet) as horizontal rules within the cornice band
    mid_y = (y_frieze_top + y_corn_top) / 2
    polylines.append([(cx0, mid_y), (cx1, mid_y)])
    polylines.append([(cx0 + project_corn * 0.4, y_frieze_top),
                      (cx0 + project_corn * 0.4, y_corn_top)])  # vertical rule inward step
    polylines.append([(cx1 - project_corn * 0.4, y_frieze_top),
                      (cx1 - project_corn * 0.4, y_corn_top)])

    shadows: list[Shadow] = []
    # Soffit shadow under cornice
    soffit = Polygon([
        (cx0, y_frieze_top),
        (cx1, y_frieze_top),
        (fx1, y_frieze_top + corn_h * 0.18),
        (fx0, y_frieze_top + corn_h * 0.18),
    ])
    shadows.append(Shadow(soffit, angle_deg=10.0, density="dark"))

    # Architrave bottom-edge thin shadow
    arch_shadow = Polygon([
        (ax0, y_arch_bot - arch_h * 0.35),
        (ax1, y_arch_bot - arch_h * 0.35),
        (ax1, y_arch_bot),
        (ax0, y_arch_bot),
    ])
    shadows.append(Shadow(arch_shadow, angle_deg=10.0, density="light"))

    dentils: list[Polyline] = []
    if with_dentils:
        tooth_w = M * 0.3
        gap = M * 0.15
        tooth_h = corn_h * 0.25
        dy = y_frieze_top + corn_h * 0.3
        strip = P.dentil_strip(cx1 - cx0, tooth_w, tooth_h, gap, x0=cx0, y0=dy)
        dentils = strip

    return {
        "polylines": polylines,
        "shadows": shadows,
        "dentils": dentils,
        "top_y": y_corn_top,
        "left_edge": cx0,
        "right_edge": cx1,
    }


def pediment(left_x: float, right_x: float, base_y: float, slope_deg: float = 14.0,
             tympanum_inset: float = 1.2) -> dict:
    """Triangular pediment sitting on top of the cornice. slope in degrees.

    Canonical slope range is ~12°–15° (Ware), up to ~22.5° for steep Doric
    pediments. Values outside [10°, 25°] emit a UserWarning — the geometry
    still renders so no caller breaks, but the caller is told their
    pediment is outside conventional proportions.
    """
    if not (10 <= slope_deg <= 25):
        import warnings
        warnings.warn(
            f"pediment slope_deg={slope_deg} outside canonical [10, 25]",
            stacklevel=2,
        )
    span = right_x - left_x
    apex_x = (left_x + right_x) / 2
    apex_y = base_y - (span / 2) * math.tan(math.radians(slope_deg))

    # Outer triangle
    outer = [(left_x, base_y), (apex_x, apex_y), (right_x, base_y), (left_x, base_y)]
    # Inner (tympanum) triangle inset parallel to the sloped edges
    dy = tympanum_inset
    # rake cornice inset: shift each sloped edge inward by perpendicular dy
    slope = math.tan(math.radians(slope_deg))
    # inset points: move left point right+down, apex down, right point left+down
    dx_edge = dy / math.cos(math.radians(slope_deg))
    inner = [
        (left_x + dx_edge, base_y - dy),
        (apex_x, apex_y + dx_edge),
        (right_x - dx_edge, base_y - dy),
        (left_x + dx_edge, base_y - dy),
    ]

    # Bottom horizontal rule
    bottom = [(left_x, base_y), (right_x, base_y)]

    # Shadow on the right slope interior (light from upper-left)
    shadow_tri = Polygon([
        (apex_x, apex_y + dx_edge),
        (right_x - dx_edge, base_y - dy),
        (apex_x, base_y - dy),
    ])

    return {
        "outer": outer,
        "inner": inner,
        "bottom": bottom,
        "shadows": [Shadow(shadow_tri, angle_deg=50.0, density="light")],
        "apex": (apex_x, apex_y),
    }


def tetrastyle_portico(center_x: float, ground_y: float,
                       dims: O.TuscanDims, intercolumniation_modules: float = 4.0) -> dict:
    """Four-column Tuscan portico, bilaterally symmetric.

    intercolumniation_modules: centre-to-centre column spacing in modules.
    Vignola's Tuscan allows eustyle (2.25D ≈ 4.5M) as the standard.
    """
    M = dims.M
    spacing = intercolumniation_modules * M
    # Column centres at ±0.5s, ±1.5s
    col_xs = [center_x - 1.5 * spacing,
              center_x - 0.5 * spacing,
              center_x + 0.5 * spacing,
              center_x + 1.5 * spacing]

    # Pedestals under each column
    peds = [pedestal(x, ground_y, dims) for x in col_xs]
    top_of_pedestal_y = peds[0]["top_y"]

    # Columns on top of pedestals
    cols = [column(x, top_of_pedestal_y, dims) for x in col_xs]
    top_of_cap_y = cols[0]["capital_top_y"]

    # Entablature spans from outer-left to outer-right edge of flanking columns
    # plus a projection equal to column radius for visual weight.
    ent_left = col_xs[0] - dims.lower_diam * 0.75
    ent_right = col_xs[-1] + dims.lower_diam * 0.75
    ent = entablature(ent_left, ent_right, top_of_cap_y, dims, with_dentils=True)

    # Pediment
    ped = pediment(ent["left_edge"], ent["right_edge"], ent["top_y"], slope_deg=14.0,
                   tympanum_inset=M * 0.35)

    # Ground line
    ground = [(center_x - (ent["right_edge"] - ent["left_edge"]) * 0.65, ground_y),
              (center_x + (ent["right_edge"] - ent["left_edge"]) * 0.65, ground_y)]

    return {
        "pedestals": peds,
        "columns": cols,
        "entablature": ent,
        "pediment": ped,
        "ground": ground,
        "col_xs": col_xs,
    }


def rusticated_block_wall(x0: float, y0: float, width: float, height: float,
                          course_h: float, block_w: float,
                          v_joint_w: float = 0.8,
                          bond: str = "running") -> dict:
    """Rusticated ashlar / blocking course. V-grooved joints between squared stones.

    Returns:
        joints: list of polylines for the V-groove centerlines (draw as fine rules)
        joint_shadows: list of shadow polygons (dark inside the V) for hatching
        block_rects: list of polylines (each block's outline) for optional light rule
    """
    joints: list[Polyline] = []
    joint_shadows: list[Polygon] = []
    block_rects: list[Polyline] = []

    n_courses = int(round(height / course_h))
    actual_course_h = height / n_courses
    y = y0
    for row in range(n_courses):
        # Running bond: alternate rows shift by half a block
        offset = (block_w / 2) if (bond == "running" and row % 2 == 1) else 0.0
        # Horizontal joint (except at very top)
        if row > 0:
            joints.append([(x0, y), (x0 + width, y)])
            # shadow band just below the joint
            joint_shadows.append(Polygon([
                (x0, y), (x0 + width, y),
                (x0 + width, y + v_joint_w), (x0, y + v_joint_w),
            ]))
        # Vertical joints across this row
        x = x0 - offset
        while x <= x0 + width:
            xx = max(x, x0)
            xxe = min(x + block_w, x0 + width)
            if xx < xxe:
                # block rect
                block_rects.append([
                    (xx, y), (xxe, y), (xxe, y + actual_course_h),
                    (xx, y + actual_course_h), (xx, y),
                ])
            # vertical joint at right edge of block
            if x + block_w < x0 + width:
                jx = x + block_w
                if jx > x0:
                    joints.append([(jx, y), (jx, y + actual_course_h)])
                    joint_shadows.append(Polygon([
                        (jx, y), (jx + v_joint_w, y),
                        (jx + v_joint_w, y + actual_course_h),
                        (jx, y + actual_course_h),
                    ]))
            x += block_w
        y += actual_course_h

    # Outer bounding box
    outline = [(x0, y0), (x0 + width, y0),
               (x0 + width, y0 + height), (x0, y0 + height), (x0, y0)]

    return {
        "outline": outline,
        "joints": joints,
        "joint_shadows": joint_shadows,
        "block_rects": block_rects,
    }
