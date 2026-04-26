"""Plate — Cartouche variations.

Three cartouche styles side-by-side on a landscape plate: a plain oval
(two concentric ellipses), a rounded rectangular frame, and a baroque
scroll cartouche with a fan-shell embellishment.

Each inscription field carries a placeholder italic "TITULUS EXEMPLI"
block until typography.title integration lands.
"""
from __future__ import annotations

import config
from engraving.cartouche import cartouche
from engraving.render import Page, frame
from engraving.typography import title
from engraving.validate.plates import validate_plate_result


def build_validated() -> tuple[str, "object"]:
    """Render + validate. Returns (svg_path, ValidationReport)."""
    page = Page()
    frame(page)

    # --- Title band --------------------------------------------------------
    title(page, "CARTOUCHE  VARIATIONS",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 8,
          font_size_mm=5.0, anchor="middle",
          stroke_width=config.STROKE_FINE)
    title(page, "\u2014 oval, rectangular, baroque scroll \u2014",
          x=config.PLATE_W / 2, y=config.FRAME_INSET + 14,
          font_size_mm=2.8, anchor="middle",
          stroke_width=config.STROKE_HAIRLINE)

    # --- Cartouche row -----------------------------------------------------
    plate_w = config.PLATE_W
    plate_h = config.PLATE_H
    center_y = plate_h / 2.0
    cart_w = 60.0
    cart_h = 35.0

    specs = [
        ("oval",           plate_w / 4.0,        False),
        ("rectangular",    plate_w / 2.0,        False),
        ("baroque_scroll", 3.0 * plate_w / 4.0,  True),
    ]

    # Per-layer stroke weights. The cartouche module tags its polylines with
    # layer names; we fan each layer out to the appropriate engraving weight.
    #   field          — both frames (outer + inner inscription border)
    #   wings          — three polylines per wing: spine, offset, eye
    #                    (spine + offset = STROKE_FINE, eye = STROKE_ORNAMENT)
    #   embellishment  — shell outline, inner rim, radial ribs
    #                    (outlines = STROKE_FINE, ribs = STROKE_HAIRLINE)
    layer_base_weights = {
        "field":         config.STROKE_MEDIUM,
        "wings":         config.STROKE_FINE,
        "embellishment": config.STROKE_FINE,
        "ornament":      config.STROKE_FINE,
        "volutes":       config.STROKE_FINE,
    }

    for style, cx, with_shell in specs:
        cart = cartouche(cx=cx, cy=center_y,
                         width=cart_w, height=cart_h,
                         style=style, with_shell=with_shell)

        for layer, lines in cart.polylines.items():
            base_sw = layer_base_weights.get(layer, config.STROKE_FINE)
            if layer == "wings":
                # A wing group is 3 polylines: spine, inner offset, eye.
                # The first two get STROKE_FINE (spine/offset); every third
                # (the little closed eye circle) gets STROKE_ORNAMENT so the
                # focal point of the spiral reads as a distinct dot.
                for i, pl in enumerate(lines):
                    sw = (config.STROKE_ORNAMENT if i % 3 == 2
                          else config.STROKE_FINE)
                    page.polyline(pl, stroke_width=sw)
            elif layer == "embellishment":
                # A shell group is 2 scalloped arcs + 6 radial ribs. Outline
                # arcs draw at STROKE_FINE; the radiating ribs drop to
                # STROKE_HAIRLINE so they read as texture.
                for i, pl in enumerate(lines):
                    # First two per shell are the outer + inner scalloped
                    # arcs (len ~ scallops+1); ribs are short 2-point lines.
                    sw = (config.STROKE_HAIRLINE if len(pl) == 2
                          else config.STROKE_FINE)
                    page.polyline(pl, stroke_width=sw)
            else:
                for pl in lines:
                    page.polyline(pl, stroke_width=base_sw)

        # Placeholder inscription text, italicized via a small run of text
        # styled with the default serif; typography.title integration will
        # replace this with proper relief lettering later.
        page.text("TITULUS  EXEMPLI",
                  x=cx, y=center_y + 1.5,
                  font_size=2.6, anchor="middle")

    # --- Scale bar ---------------------------------------------------------
    cap_y = plate_h - config.FRAME_INSET - 6
    page.polyline([(plate_w / 2 - 25, cap_y), (plate_w / 2 + 25, cap_y)],
                  stroke_width=config.STROKE_FINE)
    for i in range(6):
        x = plate_w / 2 - 25 + i * 10
        page.polyline([(x, cap_y - 1.5), (x, cap_y)],
                      stroke_width=config.STROKE_HAIRLINE)
    page.text("50 mm", x=plate_w / 2, y=cap_y + 4,
              font_size=2.4, anchor="middle")

    svg_path = str(page.save_svg("plate_cartouche"))

    # Cartouches aren't in the order/entablature/facade buckets — run through
    # validate_plate_result with an empty collection so the plumbing stays
    # uniform across plates.
    report = validate_plate_result("plate_cartouche", {})
    return svg_path, report


def build() -> str:
    """Legacy API — return only the SVG path."""
    svg_path, _ = build_validated()
    return svg_path


if __name__ == "__main__":
    print(build())
