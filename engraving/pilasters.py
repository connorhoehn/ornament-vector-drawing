"""Classical pilasters (flattened columns attached to a wall).

After Ware, *The American Vignola*, p. 37. A pilaster is a shallow
rectangular projection from a wall that follows the proportions of a
classical order. Unlike a round column, it is drawn in ELEVATION as a flat
rectangle with the capital and base profiles projecting slightly forward of
the shaft face — there is no curved silhouette.

For v1 we render every order (Tuscan, Doric, Ionic, Corinthian, Composite)
as a rectangle with horizontal rules subdividing the base and capital. The
finer ornamentation (acanthus leaves, Ionic volutes) is intentionally
deferred: at the scale of a pilaster in an engraving it would read as noise.
Hooks for adding that detail live at the end of each order branch.
"""
from __future__ import annotations

from . import canon
from .geometry import Polyline, line


# ─── Dispatch ────────────────────────────────────────────────────────────

def pilaster(order: canon.Order, cx: float, base_y: float,
             width: float | None = None,
             projection: float = 0.15) -> list[Polyline]:
    """Pilaster in elevation.

    order: any canon.Order instance.
    cx: pilaster centerline x.
    base_y: bottom of pilaster (top of pedestal). The shaft grows UPWARD
        from this line (y decreases), since y-down is our SVG convention.
    width: pilaster face width in mm; defaults to order.D.
    projection: forward projection of base/cap moldings, fraction of width.

    Returns a list of polylines:
      * Two vertical shaft edges (left, right).
      * Plinth outline (small rectangle at the base).
      * Base moldings as horizontal rules, each slightly wider than the
        shaft by (projection * width) on each side.
      * Capital moldings as horizontal rules at the top (order-specific
        subdivisions: neck/echinus/abacus for Tuscan-Doric; a richer stack
        for Ionic/Corinthian/Composite).
      * Abacus top edge (closes the cap rectangle).
    """
    if width is None:
        width = order.D

    polylines: list[Polyline] = []

    # --- Geometry ---------------------------------------------------------
    half_w = width / 2.0
    proj = projection * width
    half_p = half_w + proj  # projecting half-width for base/cap moldings

    left = cx - half_w
    right = cx + half_w
    left_p = cx - half_p
    right_p = cx + half_p

    base_h = order.base_h
    cap_h = order.capital_h
    col_h = order.column_h

    # Shaft top/bottom (y-down: "up" is smaller y).
    shaft_bot_y = base_y - base_h
    shaft_top_y = base_y - col_h + cap_h
    cap_top_y = base_y - col_h  # abacus top

    # --- Shaft edges (verticals from base top to cap bottom) -------------
    polylines.append(line((left, shaft_bot_y), (left, shaft_top_y)))
    polylines.append(line((right, shaft_bot_y), (right, shaft_top_y)))

    # --- Base ------------------------------------------------------------
    polylines.extend(_base_rules(order, cx, base_y, half_w, half_p))

    # --- Capital ---------------------------------------------------------
    polylines.extend(_capital_rules(order, cx, base_y, half_w, half_p))

    return polylines


# ─── Base ────────────────────────────────────────────────────────────────

def _base_rules(order: canon.Order, cx: float, base_y: float,
                half_w: float, half_p: float) -> list[Polyline]:
    """Horizontal rules for the pilaster base.

    The base occupies the full ``order.base_h``. In elevation we render it
    as a plinth (closed rectangle) plus a stack of horizontal rules that
    stand in for the torus / fillet / cincture profile of a column base.
    Every rule is drawn at ``half_p`` (projected) except the uppermost
    cincture, which ties back to the shaft width ``half_w``.
    """
    base_h = order.base_h
    left_p = cx - half_p
    right_p = cx + half_p
    left = cx - half_w
    right = cx + half_w

    # Plinth occupies the lower ~45% of the base (listel proportions vary
    # by order but this keeps the visual weight right for v1).
    plinth_h = base_h * 0.45
    plinth_top = base_y - plinth_h

    polylines: list[Polyline] = []

    # Plinth outline: closed rectangle at the projected width.
    polylines.append([
        (left_p, base_y),
        (right_p, base_y),
        (right_p, plinth_top),
        (left_p, plinth_top),
        (left_p, base_y),
    ])

    # Torus/fillet stack above the plinth.
    # Divide the remaining base height into N horizontal rules.
    remaining = base_h - plinth_h
    n_rules = _base_rule_count(order)
    if n_rules > 0 and remaining > 0:
        step = remaining / n_rules
        for i in range(1, n_rules + 1):
            y = plinth_top - step * i
            polylines.append(line((left_p, y), (right_p, y)))

    # Cincture (apophyge) — the shaft meets the base at its own width.
    shaft_bot_y = base_y - base_h
    polylines.append(line((left, shaft_bot_y), (right, shaft_bot_y)))

    return polylines


def _base_rule_count(order: canon.Order) -> int:
    """How many horizontal rules to draw above the plinth.

    Tuscan/Doric bases are simple (torus + fillet). Ionic/Corinthian use
    the 'Attic' base (torus, scotia, torus) and so deserve more rules.
    """
    if isinstance(order, (canon.Tuscan, canon.Doric)):
        return 2
    return 3  # Ionic, Corinthian, Composite (Attic-ish base)


# ─── Capital ─────────────────────────────────────────────────────────────

def _capital_rules(order: canon.Order, cx: float, base_y: float,
                   half_w: float, half_p: float) -> list[Polyline]:
    """Horizontal rules for the pilaster capital.

    The capital occupies ``order.capital_h`` below the top of the column.
    Every order gets a different subdivision:

    * Tuscan / Doric: neck, echinus, abacus (3 rules + abacus top).
    * Ionic: neck, echinus, volute band, abacus (4 rules). Volute geometry
      itself is deferred — at pilaster scale, "angle volutes" read as a
      single horizontal band.
    * Corinthian / Composite: taller bell → two leaf rows + helices +
      abacus (4 rules). Acanthus silhouette is deferred.
    """
    cap_h = order.capital_h
    col_h = order.column_h

    left = cx - half_w
    right = cx + half_w
    left_p = cx - half_p
    right_p = cx + half_p

    shaft_top_y = base_y - col_h + cap_h  # neck / bottom of capital
    cap_top_y = base_y - col_h            # abacus top

    polylines: list[Polyline] = []

    # Neck (bottom of capital) — shaft width, closes the shaft rectangle.
    polylines.append(line((left, shaft_top_y), (right, shaft_top_y)))

    # Order-specific subdivision rules (fractions measured from the neck
    # upward, i.e. from shaft_top_y toward cap_top_y).
    fracs = _capital_fractions(order)
    for frac in fracs:
        y = shaft_top_y - cap_h * frac
        polylines.append(line((left_p, y), (right_p, y)))

    # Abacus top edge — closes the projecting cap rectangle.
    polylines.append([
        (left_p, cap_top_y),
        (right_p, cap_top_y),
    ])

    # Left/right edges of the projected cap (tie the rules together).
    polylines.append(line((left_p, shaft_top_y), (left_p, cap_top_y)))
    polylines.append(line((right_p, shaft_top_y), (right_p, cap_top_y)))

    # --- Ornamentation hooks (deferred for v1) ---------------------------
    # Ionic: add small angle-volute glyphs at (left_p, cap_top_y) and
    #        (right_p, cap_top_y). At pilaster scale these are ~1 mm.
    # Corinthian/Composite: add two rows of acanthus leaf silhouettes
    #        within the bell (shaft_top_y .. mid-cap). Also deferred.

    return polylines


def _capital_fractions(order: canon.Order) -> list[float]:
    """Intermediate horizontal rules within the capital, as fractions of
    capital_h measured upward from the neck (0.0 = neck, 1.0 = abacus top).

    Chosen so each order's rule stack visually reads as its characteristic
    silhouette, even without the ornamentation.
    """
    if isinstance(order, canon.Tuscan):
        # neck already drawn; echinus top, abacus bottom.
        return [1.0 / 3.0, 2.0 / 3.0]
    if isinstance(order, canon.Doric):
        # annulets, echinus, abacus bottom.
        return [0.25, 0.5, 0.75]
    if isinstance(order, canon.Ionic):
        # astragal, echinus, volute band, abacus bottom.
        return [0.2, 0.4, 0.75]
    if isinstance(order, (canon.Corinthian, canon.Composite)):
        # two leaf rows + helices band + abacus bottom (Corinthian bell
        # is ⁷⁄₆ D tall so it carries more subdivisions).
        return [1.0 / 4.0, 2.0 / 4.0, 3.0 / 4.0]
    # Fallback: midpoint only.
    return [0.5]


# ─── Smoke test ──────────────────────────────────────────────────────────

def _smoke_test() -> None:
    """Build a pilaster for each order at D=20 and print the polyline count."""
    cx = 50.0
    base_y = 200.0
    D = 20.0

    for cls in (canon.Tuscan, canon.Doric, canon.Ionic,
                canon.Corinthian, canon.Composite):
        order = cls(D=D)
        polys = pilaster(order, cx=cx, base_y=base_y)
        print(f"{order.name:<11} pilaster: {len(polys):>3} polylines "
              f"(column_h={order.column_h:.1f} mm, "
              f"cap_h={order.capital_h:.2f} mm, "
              f"base_h={order.base_h:.2f} mm)")


if __name__ == "__main__":
    _smoke_test()
