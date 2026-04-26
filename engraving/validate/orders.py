"""Pydantic schemas per order. Enforce Ware's canonical proportions plus
anchor / metadata invariants.

Each subclass of :class:`OrderValidation` wraps an :class:`ElementResult`
and exposes a :meth:`full_report` method returning a
:class:`ValidationReport`. Schemas both validate ``dims_ref`` (the canon
dataclass) against Ware's fractions AND check that the anchors / metadata
on the result respect the structural invariants the builder promised.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

from ..schema import ElementResult
from .. import canon
from . import (
    approx_equal,
    aspect_ratio_in_range,
    count_equals,
    in_range,
    relative_height,
    ValidationReport,
)


# ──────────────────────────────────────────────────────────────────────────
# Generic reusable order predicates. Called from schema.full_report() OR
# directly by plate tests that want to light up a specific failure.
# ──────────────────────────────────────────────────────────────────────────

def capital_subdivisions(order_result: ElementResult,
                         expected: dict[str, float],
                         tol: float = 0.08) -> ValidationReport:
    """Verify per-order capital sub-band fractions.

    ``expected`` is ``metadata_key -> fraction_of_capital_h``. For
    Doric per Ware p.14::

        {"cap_neck_h": 1/3, "cap_echinus_h": 1/3, "cap_abacus_h": 1/3}

    Tolerance defaults to 8% of ``capital_h`` (the astragal bead's
    numerical fudge absorbs up to ~5%; anything beyond that is a real
    subdivision bug).
    """
    r = ValidationReport()
    md = order_result.metadata
    cap_h = md.get("capital_h", 0.0)
    if cap_h <= 0:
        r.errors.append(f"capital_h missing or zero for {order_result.kind}")
        return r
    for key, fraction in expected.items():
        actual = md.get(key)
        if actual is None:
            r.errors.append(
                f"{order_result.kind}: metadata key '{key}' missing — "
                f"cannot validate subdivision"
            )
            continue
        expected_mm = fraction * cap_h
        if abs(actual - expected_mm) > tol * cap_h:
            r.errors.append(
                f"{order_result.kind}: {key} = {actual:.3f} mm "
                f"≠ expected {fraction:.3f} × capital_h = {expected_mm:.3f} mm "
                f"(tol={tol:.2%})"
            )
    return r


def column_pedestal_entablature_ratio(
        column_result: ElementResult,
        pedestal_h: float | None,
        entablature_h: float | None,
        tol: float = 0.15) -> ValidationReport:
    """Ware: entablature ≈ ¼ column, pedestal ≈ ⅓ column.

    Pass the rendered entablature's ``total_h`` and the rendered
    pedestal's height (either may be ``None`` when absent). Tolerance
    is ±15% of ``column_h`` because Ware allows ±⅙ for artistic license.
    """
    r = ValidationReport()
    col_h = column_result.metadata.get("column_h", 0.0)
    if col_h <= 0:
        r.errors.append("column_h missing or zero")
        return r
    if entablature_h is not None and entablature_h > 0:
        expected = col_h / 4.0
        if abs(entablature_h - expected) > tol * col_h:
            r.errors.append(
                f"entablature_h {entablature_h:.2f} ≠ column_h/4 "
                f"({expected:.2f}); column_h={col_h:.2f} tol={tol:.2%}"
            )
    if pedestal_h is not None and pedestal_h > 0:
        expected = col_h / 3.0
        if abs(pedestal_h - expected) > tol * col_h:
            r.errors.append(
                f"pedestal_h {pedestal_h:.2f} ≠ column_h/3 "
                f"({expected:.2f}); column_h={col_h:.2f} tol={tol:.2%}"
            )
    return r


def five_orders_relative_heights(
        order_results: list[ElementResult],
        tol: float = 0.04) -> ValidationReport:
    """Verify 7:8:9:10:10 canonical ratios at matched D.

    ``order_results`` holds Tuscan/Doric/Ionic/Corinthian/Composite
    ``ElementResult`` instances (any subset). Tuscan's column_h is the
    D reference (column_h = 7 D).
    """
    r = ValidationReport()
    expected_ratios = {
        "tuscan":     7.0,
        "doric":      8.0,
        "ionic":      9.0,
        "corinthian": 10.0,
        "composite":  10.0,
    }
    heights: dict[str, float] = {}
    for res in order_results:
        kind = res.kind.replace("_column", "")
        if kind in expected_ratios:
            heights[kind] = res.metadata.get("column_h", 0.0)
    if not heights:
        r.errors.append(
            "five_orders_relative_heights: no Roman order results supplied"
        )
        return r
    if "tuscan" not in heights:
        r.errors.append(
            "five_orders_relative_heights: Tuscan column needed as reference"
        )
        return r
    D_ref = heights["tuscan"] / 7.0
    for kind, h in heights.items():
        expected = expected_ratios[kind] * D_ref
        if abs(h - expected) > tol * expected:
            r.errors.append(
                f"{kind} column_h {h:.2f} ≠ expected "
                f"{expected_ratios[kind]:.0f} × D = {expected:.2f} "
                f"(tol={tol:.1%})"
            )
    return r


class OrderValidation(BaseModel):
    """Base pydantic schema. Subclasses add order-specific rules."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    result: ElementResult
    order_name: str

    @field_validator("result")
    @classmethod
    def must_have_core_anchors(cls, v: ElementResult) -> ElementResult:
        required = {
            "bottom_center",
            "top_center",
            "abacus_top_right",
            "abacus_top_left",
            "axis",
        }
        missing = required - set(v.anchors.keys())
        if missing:
            raise ValueError(f"missing required anchors: {missing}")
        return v

    # ---- structural checks shared by every order ------------------------

    def validate_canonical_heights(self) -> ValidationReport:
        """column_h ≈ column_D × D, base_h ≈ base_D × D, etc."""
        r = ValidationReport()
        d = self.result.dims_ref
        md = self.result.metadata
        r.check(approx_equal, md["column_h"], d.column_h, 0.5,
                f"{d.name} column_h")
        r.check(approx_equal, md["base_h"], d.base_h, 0.3,
                f"{d.name} base_h")
        r.check(approx_equal, md["capital_h"], d.capital_h, 0.3,
                f"{d.name} capital_h")
        r.check(approx_equal, md["shaft_h"], d.shaft_h, 0.5,
                f"{d.name} shaft_h")
        return r

    def validate_symmetry(self) -> ValidationReport:
        """Left and right anchors mirror about the axis."""
        r = ValidationReport()
        axis_x = self.result.anchors["axis"].x
        for key, a in self.result.anchors.items():
            if not key.endswith("_right"):
                continue
            lkey = key[: -len("_right")] + "_left"
            if lkey not in self.result.anchors:
                continue
            lft = self.result.anchors[lkey]
            r.check(approx_equal, a.x - axis_x, axis_x - lft.x, 0.15,
                    f"symmetry x {key}/{lkey}")
            r.check(approx_equal, a.y, lft.y, 0.1,
                    f"symmetry y {key}/{lkey}")
        return r

    def full_report(self) -> ValidationReport:
        r = ValidationReport()
        sub_heights = self.validate_canonical_heights()
        r.errors.extend(sub_heights.errors)
        sub_sym = self.validate_symmetry()
        r.errors.extend(sub_sym.errors)
        return r


# ─── Per-order schemas ────────────────────────────────────────────────────

class TuscanValidation(OrderValidation):
    order_name: Literal["tuscan"] = "tuscan"

    def full_report(self) -> ValidationReport:
        r = super().full_report()
        d = self.result.dims_ref
        assert isinstance(d, canon.Tuscan), "dims_ref must be canon.Tuscan"
        # Column 7D
        r.check(approx_equal, d.column_D, 7.0, 0.0001, "Tuscan column_D")
        # Entablature 7/4 D
        r.check(approx_equal, d.entablature_D, 7.0 / 4.0, 0.0001,
                "Tuscan entab_D")
        # Cornice 3/4 D
        r.check(approx_equal, d.cornice_frac_of_D, 0.75, 0.0001,
                "Tuscan cornice")
        # Abacus width 7/6 D
        r.check(approx_equal, d.abacus_width_D, 7.0 / 6.0, 0.0001,
                "Tuscan abacus_width")
        # Upper diam 5/6 D
        r.check(approx_equal, d.upper_diam_D, 5.0 / 6.0, 0.0001,
                "Tuscan upper_diam")
        # ── Subdivision checks (per Ware p.10) ─────────────────────────
        # Base: plinth ½, torus ~⅓ (0.35), fillet ~⅙ (0.15) of base_h.
        md = self.result.metadata
        bh = md.get("base_h", 0)
        if bh > 0:
            r.check(approx_equal, md.get("base_plinth_h", 0) / bh,
                    0.50, 0.10, "Tuscan base plinth/base_h")
            r.check(approx_equal, md.get("base_torus_h", 0) / bh,
                    0.35, 0.10, "Tuscan base torus/base_h")
            r.check(approx_equal, md.get("base_fillet_h", 0) / bh,
                    0.15, 0.10, "Tuscan base fillet/base_h")
        ch = md.get("capital_h", 0)
        if ch > 0:
            # Vignola Tuscan capital: necking ~⅓, astragal small bead,
            # echinus ~¼, abacus ~⅓ of cap_h.
            r.check(approx_equal, md.get("cap_neck_h", 0) / ch,
                    0.35, 0.10, "Tuscan necking/cap_h")
            r.check(approx_equal, md.get("cap_astragal_h", 0) / ch,
                    0.08, 0.05, "Tuscan astragal/cap_h")
            r.check(approx_equal, md.get("cap_echinus_h", 0) / ch,
                    0.27, 0.10, "Tuscan echinus/cap_h")
            r.check(approx_equal, md.get("cap_abacus_h", 0) / ch,
                    0.30, 0.10, "Tuscan abacus/cap_h")
        return r


class DoricValidation(OrderValidation):
    order_name: Literal["doric"] = "doric"

    def full_report(self) -> ValidationReport:
        r = super().full_report()
        d = self.result.dims_ref
        assert isinstance(d, canon.Doric), "dims_ref must be canon.Doric"
        r.check(approx_equal, d.column_D, 8.0, 0.0001, "Doric column_D")
        r.check(approx_equal, d.frieze_frac_of_D, 0.75, 0.0001,
                "Doric frieze")
        r.check(approx_equal, d.triglyph_width_D, 0.5, 0.0001,
                "Doric triglyph")
        r.check(approx_equal, d.metope_width_D, 0.75, 0.0001,
                "Doric metope")
        r.check(count_equals, d.flute_count, 20, "Doric flute_count")
        # ── Subdivision checks (per Ware p.14) ─────────────────────────
        # Doric base: same plinth/torus/fillet pattern as Tuscan (½, 0.35, 0.15).
        md = self.result.metadata
        bh = md.get("base_h", 0)
        if bh > 0:
            r.check(approx_equal, md.get("base_plinth_h", 0) / bh,
                    0.50, 0.10, "Doric base plinth/base_h")
            r.check(approx_equal, md.get("base_torus_h", 0) / bh,
                    0.35, 0.10, "Doric base torus/base_h")
            r.check(approx_equal, md.get("base_fillet_h", 0) / bh,
                    0.15, 0.10, "Doric base fillet/base_h")
        # Doric capital = ½D split into 3 equal thirds: necking, echinus, abacus.
        ch = md.get("capital_h", 0)
        if ch > 0:
            r.check(approx_equal, md.get("cap_neck_h", 0) / ch,
                    1.0 / 3.0, 0.10, "Doric necking/cap_h")
            r.check(approx_equal, md.get("cap_echinus_h", 0) / ch,
                    1.0 / 3.0, 0.10, "Doric echinus/cap_h")
            r.check(approx_equal, md.get("cap_abacus_h", 0) / ch,
                    1.0 / 3.0, 0.10, "Doric abacus/cap_h")
        return r


class IonicValidation(OrderValidation):
    order_name: Literal["ionic"] = "ionic"

    def full_report(self) -> ValidationReport:
        r = super().full_report()
        d = self.result.dims_ref
        assert isinstance(d, canon.Ionic), "dims_ref must be canon.Ionic"
        r.check(approx_equal, d.column_D, 9.0, 0.0001, "Ionic column_D")
        r.check(approx_equal, d.architrave_frac_of_D, 5.0 / 8.0, 0.0001,
                "Ionic architrave")
        r.check(approx_equal, d.frieze_frac_of_D, 6.0 / 8.0, 0.0001,
                "Ionic frieze")
        r.check(approx_equal, d.cornice_frac_of_D, 7.0 / 8.0, 0.0001,
                "Ionic cornice")
        r.check(approx_equal, d.volute_height_D, 4.0 / 9.0, 0.0001,
                "Ionic volute_h")
        r.check(approx_equal, d.volute_eye_D, 1.0 / 18.0, 0.0001,
                "Ionic eye")
        r.check(count_equals, d.flute_count, 24, "Ionic flute_count")
        # ── Subdivision checks (per Ware p.18) ─────────────────────────
        # Attic base: plinth ⅜, lower torus ⅛, scotia ¼, upper torus ⅛,
        # fillet ⅛ of base_h (rough canonical Attic proportions).
        md = self.result.metadata
        bh = md.get("base_h", 0)
        if bh > 0:
            r.check(approx_equal, md.get("base_plinth_h", 0) / bh,
                    0.30, 0.10, "Ionic base plinth/base_h")
            r.check(approx_equal, md.get("base_lower_torus_h", 0) / bh,
                    0.18, 0.10, "Ionic base lower_torus/base_h")
            r.check(approx_equal, md.get("base_scotia_h", 0) / bh,
                    0.18, 0.10, "Ionic base scotia/base_h")
            r.check(approx_equal, md.get("base_upper_torus_h", 0) / bh,
                    0.22, 0.10, "Ionic base upper_torus/base_h")
            r.check(approx_equal, md.get("base_fillet_h", 0) / bh,
                    0.12, 0.10, "Ionic base fillet/base_h")
        # Capital: volute zone ~5/6 + abacus ~1/6 of cap_h (Ware: abacus
        # is a thin crown of 1/6 D and cap_h = 2/3 D, so abacus / cap_h
        # = 1/6 ÷ 2/3 = 1/4). Be a bit loose (≈0.25).
        ch = md.get("capital_h", 0)
        if ch > 0:
            r.check(approx_equal, md.get("cap_volute_h", 0) / ch,
                    5.0 / 6.0, 0.15, "Ionic volute/cap_h")
            r.check(approx_equal, md.get("cap_abacus_h", 0) / ch,
                    1.0 / 6.0, 0.10, "Ionic abacus/cap_h")
        return r


class CorinthianValidation(OrderValidation):
    order_name: Literal["corinthian"] = "corinthian"

    def full_report(self) -> ValidationReport:
        r = super().full_report()
        d = self.result.dims_ref
        assert isinstance(d, canon.Corinthian), "dims_ref must be canon.Corinthian"
        r.check(approx_equal, d.column_D, 10.0, 0.0001, "Corinth column_D")
        r.check(approx_equal, d.capital_D, 7.0 / 6.0, 0.0001,
                "Corinth capital_D")
        r.check(approx_equal, d.cornice_frac_of_D, 1.0, 0.0001,
                "Corinth cornice")
        r.check(approx_equal, d.modillion_length_D, 5.0 / 12.0, 0.0001,
                "Corinth modillion_len")
        r.check(approx_equal, d.modillion_oc_D, 2.0 / 3.0, 0.0001,
                "Corinth modillion_oc")
        r.check(count_equals, d.leaf_count_per_row, 8,
                "Corinth leaves/row")
        # ── Subdivision checks (per Ware p.21) ─────────────────────────
        # Attic base pattern same as Ionic.
        md = self.result.metadata
        bh = md.get("base_h", 0)
        if bh > 0:
            r.check(approx_equal, md.get("base_plinth_h", 0) / bh,
                    0.35, 0.15, "Corinth base plinth/base_h")
            r.check(approx_equal, md.get("base_lower_torus_h", 0) / bh,
                    0.18, 0.10, "Corinth base lower_torus/base_h")
            r.check(approx_equal, md.get("base_scotia_h", 0) / bh,
                    0.18, 0.10, "Corinth base scotia/base_h")
            r.check(approx_equal, md.get("base_upper_torus_h", 0) / bh,
                    0.18, 0.10, "Corinth base upper_torus/base_h")
            r.check(approx_equal, md.get("base_fillet_h", 0) / bh,
                    0.12, 0.10, "Corinth base fillet/base_h")
        # Capital: bell 1D + abacus 1/6D = 7/6D total ⇒ bell ≈ 6/7 of
        # cap_h ≈ 0.857, abacus ≈ 1/7 ≈ 0.143. Bell subdivides into
        # three equal thirds: acanthus row 1, acanthus row 2, helix zone.
        ch = md.get("capital_h", 0)
        if ch > 0:
            r.check(approx_equal, md.get("cap_bell_h", 0) / ch,
                    6.0 / 7.0, 0.10, "Corinth bell/cap_h")
            r.check(approx_equal, md.get("cap_abacus_h", 0) / ch,
                    1.0 / 7.0, 0.10, "Corinth abacus/cap_h")
            r.check(approx_equal, md.get("cap_acanthus_row1_h", 0) / ch,
                    2.0 / 7.0, 0.10, "Corinth acanthus_row1/cap_h")
            r.check(approx_equal, md.get("cap_acanthus_row2_h", 0) / ch,
                    2.0 / 7.0, 0.10, "Corinth acanthus_row2/cap_h")
            r.check(approx_equal, md.get("cap_helix_h", 0) / ch,
                    2.0 / 7.0, 0.10, "Corinth helix/cap_h")
        return r


class CompositeValidation(OrderValidation):
    order_name: Literal["composite"] = "composite"

    def full_report(self) -> ValidationReport:
        r = super().full_report()
        d = self.result.dims_ref
        assert isinstance(d, canon.Composite), "dims_ref must be canon.Composite"
        r.check(approx_equal, d.column_D, 10.0, 0.0001, "Composite column_D")
        r.check(approx_equal, d.scroll_height_D, 3.0 / 6.0, 0.0001,
                "Composite scroll_h")
        r.check(approx_equal, d.scroll_width_D, 9.0 / 6.0, 0.0001,
                "Composite scroll_w")
        # ── Subdivision checks (per Ware p.24) ─────────────────────────
        # Attic base pattern same as Ionic/Corinthian.
        md = self.result.metadata
        bh = md.get("base_h", 0)
        if bh > 0:
            r.check(approx_equal, md.get("base_plinth_h", 0) / bh,
                    0.30, 0.10, "Composite base plinth/base_h")
            r.check(approx_equal, md.get("base_lower_torus_h", 0) / bh,
                    0.18, 0.10, "Composite base lower_torus/base_h")
            r.check(approx_equal, md.get("base_scotia_h", 0) / bh,
                    0.18, 0.10, "Composite base scotia/base_h")
            r.check(approx_equal, md.get("base_upper_torus_h", 0) / bh,
                    0.22, 0.10, "Composite base upper_torus/base_h")
            r.check(approx_equal, md.get("base_fillet_h", 0) / bh,
                    0.12, 0.10, "Composite base fillet/base_h")
        # Capital = 7/6 D. Each acanthus row = 7/18 D ⇒ 1/3 of cap_h.
        # The Ionic scroll block tops the capital; abacus ≈ 1/7 of cap_h.
        # Volute (scroll zone) is the span from above-caulicoli to below-
        # abacus and should be positive (non-trivial).
        ch = md.get("capital_h", 0)
        if ch > 0:
            r.check(approx_equal, md.get("cap_acanthus_row1_h", 0) / ch,
                    1.0 / 3.0, 0.10, "Composite acanthus_row1/cap_h")
            r.check(approx_equal, md.get("cap_acanthus_row2_h", 0) / ch,
                    1.0 / 3.0, 0.10, "Composite acanthus_row2/cap_h")
            # Scroll/volute zone should be a meaningful fraction (~¼
            # of cap_h ≈ ½D on a 7/6 D capital). If cap_volute_h is
            # zero or negative, the capital is squashed.
            r.check(approx_equal, md.get("cap_volute_h", 0) / ch,
                    3.0 / 14.0, 0.15, "Composite volute/cap_h")
            r.check(approx_equal, md.get("cap_abacus_h", 0) / ch,
                    1.0 / 7.0, 0.10, "Composite abacus/cap_h")
        return r


class GreekDoricValidation(OrderValidation):
    order_name: Literal["greek_doric"] = "greek_doric"

    def full_report(self) -> ValidationReport:
        r = super().full_report()
        d = self.result.dims_ref
        assert isinstance(d, canon.GreekDoric), \
            "dims_ref must be canon.GreekDoric"
        # Greek Doric is stouter than Roman — Parthenon 5.5 D, range 5-6 D.
        r.check(in_range, d.column_D, 5.0, 6.0, "GreekDoric column_D")
        # No base — column sits directly on stylobate.
        r.check(approx_equal, d.base_D, 0.0, 0.001,
                "GreekDoric base_D (no base)")
        r.check(approx_equal, d.pedestal_D, 0.0, 0.001,
                "GreekDoric pedestal_D (no pedestal)")
        r.check(count_equals, d.flute_count, 20, "GreekDoric flute_count")
        r.check(count_in_range_ints, d.annulet_count, 3, 5,
                "GreekDoric annulet_count")
        # Echinus projection noticeably larger than Roman Doric's ~0.15D but
        # bounded on the upper side so the capital doesn't read as an oversized
        # "lid" floating over the shaft at plate scale.
        r.check(in_range, d.echinus_projection_D, 0.20, 0.55,
                "GreekDoric echinus_projection_D")
        # Metadata should confirm no base drawn.
        md = self.result.metadata
        if "num_annulets" in md:
            r.check(count_equals, md["num_annulets"], d.annulet_count,
                    "num_annulets metadata")
        # ── Subdivision checks (per Ware pp.33-36) ─────────────────────
        # Greek Doric capital: annulets (small band), echinus (dominant),
        # abacus (plain block). No base to check. Canonical Parthenon
        # ratios roughly: annulets ~8%, echinus ~55%, abacus ~37%.
        ch = md.get("capital_h", 0)
        if ch > 0:
            r.check(approx_equal, md.get("cap_annulet_h", 0) / ch,
                    0.08, 0.08, "GreekDoric annulet/cap_h")
            r.check(approx_equal, md.get("cap_echinus_h", 0) / ch,
                    0.55, 0.15, "GreekDoric echinus/cap_h")
            r.check(approx_equal, md.get("cap_abacus_h", 0) / ch,
                    0.37, 0.15, "GreekDoric abacus/cap_h")
        return r


class GreekIonicValidation(OrderValidation):
    order_name: Literal["greek_ionic"] = "greek_ionic"

    def full_report(self) -> ValidationReport:
        r = super().full_report()
        d = self.result.dims_ref
        assert isinstance(d, canon.GreekIonic), \
            "dims_ref must be canon.GreekIonic"
        r.check(in_range, d.column_D, 8.5, 9.5, "GreekIonic column_D")
        r.check(approx_equal, d.pedestal_D, 0.0, 0.001,
                "GreekIonic pedestal_D (no pedestal)")
        r.check(approx_equal, d.volute_height_D, 4.0 / 9.0, 0.0001,
                "GreekIonic volute_h")
        r.check(approx_equal, d.volute_eye_D, 1.0 / 18.0, 0.0001,
                "GreekIonic volute_eye")
        r.check(count_equals, d.flute_count, 24, "GreekIonic flute_count")
        # ── Subdivision checks (per Ware pp.33-36, Erechtheion) ────────
        md = self.result.metadata
        # Attic base identical in composition to Roman Ionic.
        bh = md.get("base_h", 0)
        if bh > 0:
            r.check(approx_equal, md.get("base_plinth_h", 0) / bh,
                    0.30, 0.10, "GreekIonic base plinth/base_h")
            r.check(approx_equal, md.get("base_lower_torus_h", 0) / bh,
                    0.18, 0.10, "GreekIonic base lower_torus/base_h")
            r.check(approx_equal, md.get("base_scotia_h", 0) / bh,
                    0.18, 0.10, "GreekIonic base scotia/base_h")
            r.check(approx_equal, md.get("base_upper_torus_h", 0) / bh,
                    0.22, 0.10, "GreekIonic base upper_torus/base_h")
            r.check(approx_equal, md.get("base_fillet_h", 0) / bh,
                    0.12, 0.10, "GreekIonic base fillet/base_h")
        # Capital: volute zone ~5/6 + abacus ~1/6 of cap_h (same split
        # as Roman Ionic; Erechtheion abacus is thinner but v1 matches).
        ch = md.get("capital_h", 0)
        if ch > 0:
            r.check(approx_equal, md.get("cap_volute_h", 0) / ch,
                    5.0 / 6.0, 0.15, "GreekIonic volute/cap_h")
            r.check(approx_equal, md.get("cap_abacus_h", 0) / ch,
                    1.0 / 6.0, 0.10, "GreekIonic abacus/cap_h")
        return r


# Shim: count_in_range_ints mirrors count_in_range but raises
# ValidationError inside a check() block the same way. `count_in_range`
# exists in engraving.validate but isn't imported at module top to avoid
# touching the existing import line — use a tiny local wrapper here.
def count_in_range_ints(actual: int, lo: int, hi: int, label: str = "") -> None:
    from . import count_in_range
    count_in_range(actual, lo, hi, label)


# ─── Smoke test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    from ..orders import tuscan_column_silhouette

    dims = canon.Tuscan(D=20.0)
    res = tuscan_column_silhouette(dims, cx=100.0, base_y=200.0,
                                   return_result=True)
    report = TuscanValidation(result=res).full_report()
    print(f"Tuscan: {len(report)} errors")
    for e in report:
        print(f"  - {e}")
    assert len(report) == 0, "Tuscan should validate cleanly"
    print("TUSCAN VALIDATION: OK")
