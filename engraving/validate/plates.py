"""Top-level plate validation orchestration.

Usage:
    from engraving.validate.plates import validate_plate_result

    # In each plate's build():
    #   result_dict = {"columns": [...], "entablature": {...}, "facade": ...}
    # Plate modules return these as side-info from build_validated() functions.

    report = validate_plate_result(plate_name, collected_results)
    if report:
        print(f"{plate_name} has {len(report)} validation errors")
"""
from __future__ import annotations

from . import ValidationReport
from .orders import (TuscanValidation, DoricValidation, IonicValidation,
                     CorinthianValidation, CompositeValidation,
                     GreekDoricValidation, GreekIonicValidation)
from .composition import validate_facade_render

# entablatures.py is written by a parallel agent — import lazily so this
# module is usable even before that file lands. If it's missing, entablature
# validation is silently skipped (with a note in the report).
try:
    from .entablatures import (validate_doric_entablature,
                                validate_ionic_entablature,
                                validate_corinthian_entablature)
    _HAS_ENTABLATURE_VALIDATORS = True
except ImportError:  # pragma: no cover — transient during Phase 5 build-out
    _HAS_ENTABLATURE_VALIDATORS = False

    def validate_doric_entablature(*_a, **_kw):  # type: ignore[misc]
        return ValidationReport()

    def validate_ionic_entablature(*_a, **_kw):  # type: ignore[misc]
        return ValidationReport()

    def validate_corinthian_entablature(*_a, **_kw):  # type: ignore[misc]
        return ValidationReport()


def validate_plate_result(plate_name: str, collected: dict) -> ValidationReport:
    """Run order + entablature + facade validators as applicable.

    ``collected`` is a dict with any of these keys:
      - ``"order_results"``: list of ElementResult for columns (by order name)
      - ``"entablature_results"``: list of
        ``(order_name, ElementResult, column_axes)`` tuples
      - ``"facade"``: tuple ``(facade_instance, render_result)``
    """
    report = ValidationReport()

    # Validate each column
    for order_result in collected.get("order_results", []):
        order_name = order_result.kind.replace("_column", "")
        schema_cls = {
            "tuscan":       TuscanValidation,
            "doric":        DoricValidation,
            "ionic":        IonicValidation,
            "corinthian":   CorinthianValidation,
            "composite":    CompositeValidation,
            "greek_doric":  GreekDoricValidation,
            "greek_ionic":  GreekIonicValidation,
        }.get(order_name)
        if schema_cls:
            try:
                v = schema_cls(result=order_result, order_name=order_name)
                sub = v.full_report()
                report.errors.extend(sub.errors)
            except Exception as e:
                report.errors.append(f"[{plate_name}] order schema failed: {e}")

    # Validate each entablature
    if not _HAS_ENTABLATURE_VALIDATORS and collected.get("entablature_results"):
        report.errors.append(
            f"[{plate_name}] entablature validators not available "
            f"(engraving.validate.entablatures not importable)"
        )
    for order_name, ent_result, col_axes in collected.get(
            "entablature_results", []):
        try:
            if order_name == "doric":
                sub = validate_doric_entablature(ent_result, col_axes)
            elif order_name == "ionic":
                sub = validate_ionic_entablature(ent_result)
            elif order_name == "corinthian":
                sub = validate_corinthian_entablature(ent_result, col_axes)
            else:
                continue
            report.errors.extend(sub.errors)
        except Exception as e:
            report.errors.append(
                f"[{plate_name}] entablature validation failed: {e}"
            )

    # Validate facade
    if "facade" in collected:
        facade, render_result = collected["facade"]
        try:
            sub = validate_facade_render(facade, render_result)
            report.errors.extend(sub.errors)
        except Exception as e:
            report.errors.append(
                f"[{plate_name}] facade validation failed: {e}"
            )

    return report
