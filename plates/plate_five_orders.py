"""Plate — the five classical orders side-by-side, at matched lower diameter.

A Vignola-style comparison plate showing Tuscan, Doric, Ionic, Corinthian,
and Composite in canonical progression from left to right. All columns share
the same lower diameter D, so their heights differ (7D, 8D, 9D, 10D, 10D) —
the viewer can directly compare the native proportions.

Each bay: pedestal + column + a small entablature stub (no full span).
"""
from __future__ import annotations

import config
from engraving import canon, elements
from engraving.order_corinthian import corinthian_column_silhouette
from engraving.order_composite import composite_column_silhouette
from engraving.order_ionic import ionic_column_silhouette
from engraving.order_doric import doric_column_silhouette
from engraving.orders import tuscan_column_silhouette
from engraving.render import Page, frame
from engraving.typography import title
from engraving.validate.composition import validate_comparative_plate
from engraving.validate.plates import validate_plate_result


# Silhouette builders keyed by order name. Each supports return_result=True,
# emitting an ElementResult with categorized layers: silhouette (2), rules
# (5), and order-specific ornament layers.
_BUILDERS = {
    "Tuscan":     tuscan_column_silhouette,
    "Doric":      doric_column_silhouette,
    "Ionic":      ionic_column_silhouette,
    "Corinthian": corinthian_column_silhouette,
    "Composite":  composite_column_silhouette,
}


def build_validated() -> tuple[str, "object"]:
    """Render + validate. Returns (svg_path, ValidationReport)."""
    page = Page()
    frame(page)

    # ── Titles ────────────────────────────────────────────────────────────
    title_y = config.FRAME_INSET + 7
    title(page, "THE  FIVE  ORDERS",
          x=config.PLATE_W / 2, y=title_y,
          font_size_mm=5.5, anchor="middle",
          stroke_width=config.STROKE_FINE)
    title(page, "— after Vignola, at matched lower diameter —",
          x=config.PLATE_W / 2, y=title_y + 5,
          font_size_mm=2.5, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    # ── Layout ────────────────────────────────────────────────────────────
    # All orders share this D. Tallest columns (Corinthian/Composite) span
    # 10D (column) + 10/3 D (pedestal) + 10/4 D (entablature) ≈ 15.8D, which
    # must fit under the title band and above the ground-line / label band.
    # 9 mm × 15.8 = 142 mm; combined with the title taking ≈ 13 mm from the
    # frame-inset top we need ground_y at 203 − 19 − 13.2 = ~171, and the
    # label band trimmed to 13 mm below ground — tuned below.
    D = 9.0

    usable_w = config.PLATE_W - 2 * config.FRAME_INSET
    slot_w = usable_w / 5
    slot_xs = [config.FRAME_INSET + slot_w * (i + 0.5) for i in range(5)]

    # Ground line: leave ~14 mm below for labels + scale bar. With D=9 the
    # tallest columns are 142 mm, so moving the ground line down by 4 mm
    # creates the vertical headroom needed for the capital to clear the
    # title band.
    ground_y = config.PLATE_H - config.FRAME_INSET - 14

    progression = [
        ("Tuscan", canon.Tuscan),
        ("Doric", canon.Doric),
        ("Ionic", canon.Ionic),
        ("Corinthian", canon.Corinthian),
        ("Composite", canon.Composite),
    ]

    # Horizontal ground-line underlining all five bays — ties the composition.
    page.polyline([(config.FRAME_INSET + 3, ground_y),
                   (config.PLATE_W - config.FRAME_INSET - 3, ground_y)],
                  stroke_width=config.STROKE_MEDIUM)

    column_results = []
    for i, (name, cls) in enumerate(progression):
        dims = cls(D=D)
        cx = slot_xs[i]

        # Pedestal
        ped_data = elements.pedestal(cx, ground_y, dims)
        page.polyline(ped_data["outline"], stroke_width=config.STROKE_FINE)

        top_of_ped = ped_data["top_y"]

        # Column silhouette via return_result=True so we can both categorize
        # the strokes AND collect the ElementResult for validation. The
        # legacy code stroked polys[:2] FINE (silhouettes), polys[2:7] FINE
        # (rules), polys[7:] HAIRLINE (ornament) — we replicate exactly.
        col_result = _BUILDERS[name](dims, cx, top_of_ped, return_result=True)
        column_results.append(col_result)
        for sil in col_result.polylines.get("silhouette", []):
            page.polyline(sil, stroke_width=config.STROKE_FINE)
        for rule in col_result.polylines.get("rules", []):
            page.polyline(rule, stroke_width=config.STROKE_FINE)
        # Per-layer ornament weights. At this comparative scale HAIRLINE
        # (0.18 mm) is the dense-layer floor — thinner and volutes/acanthus
        # disappear. Dense tone layers (acanthus, caulicoli, bell_guides)
        # sit at ORNAMENT so they read as texture; LINE layers (abacus,
        # volutes, echinus) at FINE so they read as outline.
        ornament_weights = {
            "acanthus":    config.STROKE_ORNAMENT,
            "caulicoli":   config.STROKE_ORNAMENT,
            "bell_guides": config.STROKE_ORNAMENT,
            "helices":     config.STROKE_ORNAMENT,
            "fleuron":     config.STROKE_ORNAMENT,
            "volutes":     config.STROKE_FINE,
            "echinus":     config.STROKE_FINE,
            "abacus":      config.STROKE_FINE,
        }
        ornament_layer_order = {
            "Tuscan":     [],
            "Doric":      [],
            "Ionic":      ["volutes", "echinus"],
            "Corinthian": ["acanthus", "helices", "caulicoli",
                           "bell_guides", "abacus", "fleuron"],
            "Composite":  ["acanthus", "caulicoli", "echinus", "volutes",
                           "abacus", "fleuron"],
        }[name]
        for layer_name in ornament_layer_order:
            sw = ornament_weights.get(layer_name, config.STROKE_FINE)
            for pl in col_result.polylines.get(layer_name, []):
                page.polyline(pl, stroke_width=sw)

        # Entablature stub — 2D wide, centered on the column. The fascia rule
        # inside the architrave (index 4) and the three interior cornice
        # moldings (indices 13, 14, 15) are hairline; the main band outlines
        # are fine. (elements.entablature is Tuscan-style and does not expose
        # return_result; entablature validation is skipped for this plate.)
        top_cap_y = top_of_ped - dims.column_h
        ent = elements.entablature(cx - dims.D, cx + dims.D, top_cap_y, dims,
                                   with_dentils=False)
        ent_polys = ent["polylines"]
        fascia_idx = {4, 13, 14, 15}
        for j, p in enumerate(ent_polys):
            sw = (config.STROKE_HAIRLINE if j in fascia_idx
                  else config.STROKE_FINE)
            page.polyline(p, stroke_width=sw)

        # Label under pedestal
        page.text(name.upper(), x=cx, y=ground_y + 4.5,
                  font_size=2.8, anchor="middle")

        # Proportion sub-label (e.g. "7 D")
        page.text(f"{dims.column_D:g} D",
                  x=cx, y=ground_y + 8.0,
                  font_size=2.2, anchor="middle")

    # ── Scale bar at bottom centre ───────────────────────────────────────
    cap_y = config.PLATE_H - config.FRAME_INSET - 2.5
    bar_half = 20
    page.polyline([(config.PLATE_W / 2 - bar_half, cap_y),
                   (config.PLATE_W / 2 + bar_half, cap_y)],
                  stroke_width=config.STROKE_FINE)
    for k in range(9):  # 8 ticks, 5-mm spacing across 40 mm
        x = config.PLATE_W / 2 - bar_half + k * (2 * bar_half / 8)
        page.polyline([(x, cap_y - 1.3), (x, cap_y)],
                      stroke_width=config.STROKE_HAIRLINE)
    page.text("40 mm", x=config.PLATE_W / 2, y=cap_y + 2.6,
              font_size=2.2, anchor="middle")

    svg_path = str(page.save_svg("plate_five_orders"))

    # Each column gets its order validator via validate_plate_result.
    # Entablature stubs use elements.entablature (Tuscan-style) which has
    # no return_result API, so we only validate the columns.
    collected = {"order_results": column_results}
    report = validate_plate_result("plate_five_orders", collected)
    # Cross-order proportion check: at matched D the column heights must
    # follow the canonical 7/8/9/10/10 progression.
    cross_report = validate_comparative_plate(column_results)
    report.errors.extend(cross_report.errors)
    return svg_path, report


def build() -> str:
    """Legacy API — return only the SVG path."""
    svg_path, _ = build_validated()
    return svg_path


if __name__ == "__main__":
    print(build())
