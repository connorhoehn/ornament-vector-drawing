"""Plate — The Greek Orders. Greek Doric and Greek Ionic side-by-side
on a shared stylobate.

Elevation study showing the canonical Greek variants next to each other so
the proportional differences from the Roman canon read immediately:
  - Greek Doric is stout (5.5 D) and springs directly from the stylobate.
  - Greek Ionic is slender (9 D) with an attic base, but still no pedestal.
Title "THE  GREEK  ORDERS", subtitle references Parthenon + Erechtheion.
"""
from __future__ import annotations

import config
from engraving import canon, elements
from engraving.fluting import flutes
from engraving.order_greek_doric import greek_doric_column_silhouette
from engraving.order_greek_ionic import greek_ionic_column_silhouette
from engraving.render import Page, frame
from engraving.typography import title
from engraving.validate.composition import validate_comparative_plate
from engraving.validate.plates import validate_plate_result


def build_validated() -> tuple[str, "object"]:
    """Render + validate. Returns (svg_path, ValidationReport)."""
    page = Page()
    frame(page)

    title_y = config.FRAME_INSET + 8
    title(page, "THE  GREEK  ORDERS",
          x=config.PLATE_W / 2, y=title_y,
          font_size_mm=5.0, anchor="middle",
          stroke_width=config.STROKE_FINE)
    title(page,
          "\u2014 Doric after the Parthenon, Ionic after the Erechtheion \u2014",
          x=config.PLATE_W / 2, y=title_y + 6,
          font_size_mm=2.8, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    # ── Drawing budget ──────────────────────────────────────────────────
    # Greek Doric is 5.5 D tall; Greek Ionic is 9 D. We size each order's D
    # independently so both columns read at useful scale while the Ionic's
    # 9:5.5 slenderness vs the Doric's stoutness remains unmistakable.
    top_margin = 24.0       # title band
    bottom_margin = 26.0    # stylobate + scale bar
    draw_h = config.PLATE_H - 2 * config.FRAME_INSET - top_margin - bottom_margin

    # Common stylobate (three steps) — both columns spring from its top.
    # We choose a single D so the Ionic column (9D) plus its entablature
    # fragment (2.25D) fit inside the drawing region with a little cushion
    # for the volute abacus. Doric (5.5D) + entablature (2D) fits comfortably.
    D = draw_h / 11.4
    greek_doric = canon.GreekDoric(D=D)
    greek_ionic = canon.GreekIonic(D=D)

    ground_y = (config.PLATE_H - config.FRAME_INSET - bottom_margin
                + 10.0)               # floor of stylobate
    step_h = 0.35 * D
    step_inset_per_side = 0.30 * D
    stylobate_top_y = ground_y - 3 * step_h

    frame_left = config.FRAME_INSET + 18
    frame_right = config.PLATE_W - config.FRAME_INSET - 18
    doric_cx = frame_left + 0.30 * (frame_right - frame_left)
    ionic_cx = frame_left + 0.72 * (frame_right - frame_left)

    # ── Columns ─────────────────────────────────────────────────────────
    column_results = []
    doric_res = greek_doric_column_silhouette(
        greek_doric, doric_cx, stylobate_top_y, return_result=True)
    ionic_res = greek_ionic_column_silhouette(
        greek_ionic, ionic_cx, stylobate_top_y, return_result=True)
    column_results.extend([doric_res, ionic_res])

    for col_res in column_results:
        for layer in ("silhouette",):
            for pl in col_res.polylines.get(layer, []):
                page.polyline(pl, stroke_width=config.STROKE_MEDIUM)
        for pl in col_res.polylines.get("rules", []):
            page.polyline(pl, stroke_width=config.STROKE_FINE)
        for pl in col_res.polylines.get("annulets", []):
            page.polyline(pl, stroke_width=config.STROKE_FINE)
        for pl in col_res.polylines.get("volutes", []):
            page.polyline(pl, stroke_width=config.STROKE_ORNAMENT)
        for pl in col_res.polylines.get("echinus", []):
            page.polyline(pl, stroke_width=config.STROKE_ORNAMENT)

    # ── Entablature fragments ────────────────────────────────────────────
    # Fill the upper composition with a plain entablature stub over each
    # column — architrave block + plain frieze + cornice (no triglyphs,
    # since these are fragments showing just the order).
    for col_res, dims, cx in (
        (doric_res, greek_doric, doric_cx),
        (ionic_res, greek_ionic, ionic_cx),
    ):
        top_of_cap_y = col_res.anchors["top_center"].y
        ent_left = cx - dims.D * 1.0
        ent_right = cx + dims.D * 1.0
        ent = elements.entablature(ent_left, ent_right, top_of_cap_y, dims)
        for pl in ent["polylines"]:
            page.polyline(pl, stroke_width=config.STROKE_FINE)

    # ── Fluting ─────────────────────────────────────────────────────────
    # Greek Doric — sharp arrises (no fillet), 20 flutes, no base so
    # y_bot is the stylobate. Shaft terminates at shaft_top (no astragal).
    gd_r_lo = greek_doric.D / 2
    gd_r_up = greek_doric.upper_diam / 2
    gd_flutes = flutes(
        cx=doric_cx,
        y_bot=stylobate_top_y,
        y_top=stylobate_top_y - greek_doric.shaft_h,
        r_lower=gd_r_lo,
        r_upper=gd_r_up,
        flute_count=greek_doric.flute_count,
        with_fillet=False,
    )
    for fl in gd_flutes:
        page.polyline(fl, stroke_width=config.STROKE_ORNAMENT)

    # Greek Ionic — 24 flutes with fillets; shaft begins at top of base and
    # ends at the astragal below the capital.
    gi_r_lo = greek_ionic.D / 2
    gi_r_up = greek_ionic.upper_diam / 2
    gi_shaft_bot_y = stylobate_top_y - greek_ionic.base_h
    gi_shaft_top_y = gi_shaft_bot_y - greek_ionic.shaft_h
    gi_flutes = flutes(
        cx=ionic_cx,
        y_bot=gi_shaft_bot_y,
        y_top=gi_shaft_top_y,
        r_lower=gi_r_lo,
        r_upper=gi_r_up,
        flute_count=greek_ionic.flute_count,
        with_fillet=True,
    )
    for fl in gi_flutes:
        page.polyline(fl, stroke_width=config.STROKE_ORNAMENT)

    # ── Stylobate (three-step platform under both columns) ───────────────
    # Simple nested rectangles, each a step taller than the one below it.
    stylobate_half_top = (ionic_cx - doric_cx) / 2 + 4.5 * D
    stylobate_cx = (doric_cx + ionic_cx) / 2
    for i in range(3):
        # Step i from the top (i=0 top, i=2 bottom).
        half_w = stylobate_half_top + i * step_inset_per_side
        y_top = stylobate_top_y + i * step_h
        y_bot = y_top + step_h
        # top rule
        page.polyline([(stylobate_cx - half_w, y_top),
                       (stylobate_cx + half_w, y_top)],
                      stroke_width=config.STROKE_MEDIUM)
        # left vertical
        page.polyline([(stylobate_cx - half_w, y_top),
                       (stylobate_cx - half_w, y_bot)],
                      stroke_width=config.STROKE_MEDIUM)
        # right vertical
        page.polyline([(stylobate_cx + half_w, y_top),
                       (stylobate_cx + half_w, y_bot)],
                      stroke_width=config.STROKE_MEDIUM)
    # Ground line
    ground_half = stylobate_half_top + 3 * step_inset_per_side + 6.0
    page.polyline([(stylobate_cx - ground_half, ground_y),
                   (stylobate_cx + ground_half, ground_y)],
                  stroke_width=config.STROKE_MEDIUM)

    # ── Column labels under the stylobate ──────────────────────────────
    label_y = ground_y + 6.0
    title(page, "GREEK  DORIC",
          x=doric_cx, y=label_y,
          font_size_mm=2.6, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)
    title(page, "GREEK  IONIC",
          x=ionic_cx, y=label_y,
          font_size_mm=2.6, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    # ── Scale bar ──────────────────────────────────────────────────────
    cap_y = config.PLATE_H - config.FRAME_INSET - 6
    page.polyline([(config.PLATE_W / 2 - 25, cap_y),
                   (config.PLATE_W / 2 + 25, cap_y)],
                  stroke_width=config.STROKE_FINE)
    for i in range(6):
        x = config.PLATE_W / 2 - 25 + i * 10
        page.polyline([(x, cap_y - 1.5), (x, cap_y)],
                      stroke_width=config.STROKE_HAIRLINE)
    page.text("50 mm", x=config.PLATE_W / 2, y=cap_y + 4,
              font_size=2.4, anchor="middle")

    svg_path = str(page.save_svg("plate_greek_orders"))

    collected = {"order_results": column_results}
    report = validate_plate_result("plate_greek_orders", collected)
    # Cross-order proportion check — Greek Doric (5.5 D) vs Greek Ionic (9 D)
    # both share the same D here.
    cross_report = validate_comparative_plate(column_results)
    report.errors.extend(cross_report.errors)
    return svg_path, report


def build() -> str:
    """Legacy API — return only the SVG path."""
    svg_path, _ = build_validated()
    return svg_path


if __name__ == "__main__":
    print(build())
