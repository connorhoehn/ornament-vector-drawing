"""Validators for Doric/Ionic/Corinthian entablatures.

These validators run over an ``ElementResult`` (obtained via the
``return_result=True`` kwarg on each builder) and check that:

  * canonical sub-heights (architrave/frieze/cornice/total) match Ware's
    tabulated fractions of the lower diameter D, within a loose tolerance
    that absorbs small numerical drift but catches real proportional bugs;
  * element counts (triglyphs, guttae, dentils, modillions) are internally
    consistent with the order's rhythm rule;
  * the structural alignments the builder promised actually hold
    (triglyphs over column axes, etc.).

Usage
-----
>>> dims = canon.Doric(D=20.0)
>>> col_xs = [60, 120, 180, 240]
>>> result = doric_entablature(40, 260, 200, dims, col_xs, return_result=True)
>>> report = validate_doric_entablature(result, col_xs)
>>> report.raise_if_any()   # or iterate: for err in report: ...
"""
from __future__ import annotations

from ..schema import ElementResult
from .. import canon
from . import (
    ValidationReport,
    approx_equal,
    count_equals,
    count_in_range,
    dentils_per_bay,
    modillion_over_column_axes,
    triglyph_over_every_column,
)


# ─── Doric ────────────────────────────────────────────────────────────────

def validate_doric_entablature(result: ElementResult,
                               column_axes_x: list[float],
                               report: ValidationReport | None = None,
                               ) -> ValidationReport:
    """Structural + proportional checks for a Doric entablature result.

    Parameters
    ----------
    result : ElementResult returned by ``doric_entablature(..., return_result=True)``.
    column_axes_x : the list of column centre-line x-values passed to the
        builder (used to verify the triglyph-over-axis rule).
    report : optional accumulator; a new ValidationReport is created if None.
    """
    if report is None:
        report = ValidationReport()
    d = result.dims_ref
    assert isinstance(d, canon.Doric), "dims_ref must be canon.Doric"

    D = d.D

    # --- canonical heights (Ware: arch ½D, frieze ¾D, cornice ¾D, total 2D) --
    report.check(approx_equal, result.metadata["architrave_h"], 0.5 * D, 0.3,
                 "Doric architrave_h (= ½D)")
    report.check(approx_equal, result.metadata["frieze_h"], 0.75 * D, 0.3,
                 "Doric frieze_h (= ¾D)")
    report.check(approx_equal, result.metadata["cornice_h"], 0.75 * D, 0.3,
                 "Doric cornice_h (= ¾D)")
    report.check(approx_equal, result.metadata["total_h"], 2.0 * D, 0.5,
                 "Doric total entablature_h (= 2D)")

    # --- triglyph count: at least 1 per column + between-pair triglyphs ------
    n_cols = len(column_axes_x)
    report.check(count_in_range, result.metadata["num_triglyphs"],
                 n_cols, n_cols * 3,
                 "Doric num_triglyphs")

    trig_centers = [result.anchors[f"triglyph_{i}"].x
                    for i in range(result.metadata["num_triglyphs"])]
    report.check(triglyph_over_every_column, trig_centers, column_axes_x, 0.5)

    # --- guttae: 6 per triglyph + 18 per mutule (18 = 3×6 stipple) ----------
    expected_regula = 6 * result.metadata["num_triglyphs"]
    expected_mutule = 18 * result.metadata["num_mutules"]
    expected_total = expected_regula + expected_mutule
    report.check(count_equals, result.metadata["num_guttae"], expected_total,
                 "Doric total guttae (regula + mutule)")

    return report


# ─── Ionic ────────────────────────────────────────────────────────────────

def validate_ionic_entablature(result: ElementResult,
                               report: ValidationReport | None = None,
                               ) -> ValidationReport:
    """Structural + proportional checks for an Ionic entablature result."""
    if report is None:
        report = ValidationReport()
    d = result.dims_ref
    assert isinstance(d, canon.Ionic), "dims_ref must be canon.Ionic"
    D = d.D

    report.check(approx_equal, result.metadata["architrave_h"], 5.0 / 8.0 * D,
                 0.3, "Ionic architrave_h (= ⅝D)")
    report.check(approx_equal, result.metadata["frieze_h"], 3.0 / 4.0 * D,
                 0.3, "Ionic frieze_h (= ¾D)")
    report.check(approx_equal, result.metadata["cornice_h"], 7.0 / 8.0 * D,
                 0.3, "Ionic cornice_h (= ⅞D)")
    report.check(approx_equal, result.metadata["total_h"], 9.0 / 4.0 * D,
                 0.5, "Ionic total entablature_h (= 2¼D)")

    # Dentil count: some positive number in a generous range.
    report.check(count_in_range, result.metadata.get("num_dentils", 0),
                 3, 500, "Ionic dentil count reasonable")
    return report


# ─── Corinthian ───────────────────────────────────────────────────────────

def validate_corinthian_entablature(result: ElementResult,
                                    column_axes_x: list[float],
                                    report: ValidationReport | None = None,
                                    ) -> ValidationReport:
    """Structural + proportional checks for a Corinthian entablature."""
    if report is None:
        report = ValidationReport()
    d = result.dims_ref
    assert isinstance(d, canon.Corinthian), "dims_ref must be canon.Corinthian"
    D = d.D

    report.check(approx_equal, result.metadata["architrave_h"], 3.0 / 4.0 * D,
                 0.3, "Corinthian architrave_h (= ¾D)")
    report.check(approx_equal, result.metadata["frieze_h"], 3.0 / 4.0 * D,
                 0.3, "Corinthian frieze_h (= ¾D)")
    report.check(approx_equal, result.metadata["cornice_h"], 1.0 * D,
                 0.3, "Corinthian cornice_h (= 1D)")
    report.check(approx_equal, result.metadata["total_h"], 5.0 / 2.0 * D,
                 0.5, "Corinthian total entablature_h (= 2½D)")

    n_mod = result.metadata.get("num_modillions", 0)
    n_cols = len(column_axes_x)
    report.check(count_in_range, n_mod, n_cols, 50,
                 "Corinthian modillion count reasonable (≥ num columns)")

    # --- Modillion centred over each column axis (Ware p.20) --------------
    # The builder stores modillions as alternating (outline, acanthus leaf)
    # pairs, so the outlines live at even indices.
    mod_layer = result.polylines.get("modillions", [])
    mod_outlines = mod_layer[::2] if mod_layer else []
    if mod_outlines:
        report.check(modillion_over_column_axes,
                     mod_outlines, column_axes_x, 0.5,
                     "Corinthian modillion over each column axis")

    # --- 4 dentils per bay between adjacent modillion axes (Ware p.20) ----
    # Use the modillion centre x-values as the bay partition. If modillion
    # anchors are present (they are, as ``modillion_i``) prefer those; fall
    # back to computing centres from outlines.
    mod_anchor_xs = sorted(
        result.anchors[k].x
        for k in result.anchors
        if k.startswith("modillion_") and k.count("_") == 1
    )
    if not mod_anchor_xs and mod_outlines:
        mod_anchor_xs = sorted(
            sum(p[0] for p in mp) / len(mp) for mp in mod_outlines
        )
    dentil_layer = result.polylines.get("dentils", [])
    if mod_anchor_xs and dentil_layer:
        report.check(dentils_per_bay, dentil_layer, mod_anchor_xs, 4, 1,
                     "Corinthian dentils per modillion bay")
    return report


# ─── Smoke test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    from ..entablature_doric import doric_entablature
    from ..entablature_ionic import ionic_entablature
    from ..entablature_corinthian import corinthian_entablature
    from .. import canon

    # Doric
    dims_d = canon.Doric(D=20.0)
    col_xs = [60, 120, 180, 240]
    result_d = doric_entablature(40, 260, 200, dims_d, col_xs,
                                 return_result=True)
    r_d = validate_doric_entablature(result_d, col_xs)
    print(f"Doric entablature: {len(r_d)} errors")
    for e in r_d:
        print(f"  - {e}")

    # Ionic
    dims_i = canon.Ionic(D=20.0)
    result_i = ionic_entablature(40, 260, 200, dims_i, return_result=True)
    r_i = validate_ionic_entablature(result_i)
    print(f"Ionic entablature: {len(r_i)} errors")
    for e in r_i:
        print(f"  - {e}")

    # Corinthian
    dims_c = canon.Corinthian(D=20.0)
    result_c = corinthian_entablature(40, 260, 200, dims_c, col_xs,
                                      return_result=True)
    r_c = validate_corinthian_entablature(result_c, col_xs)
    print(f"Corinthian entablature: {len(r_c)} errors")
    for e in r_c:
        print(f"  - {e}")
