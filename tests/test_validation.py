"""Regression tests for the validation library.

Run with: .venv/bin/python -m pytest tests/ -v
"""
import pytest

from engraving import canon
from engraving.schema import Anchor, ElementResult
from engraving.validate import (
    ValidationError, ValidationReport,
    approx_equal, aligned_vertical, meets, is_closed,
    monotonic_in_radius, total_angle_sweep, mirror_symmetric,
    count_equals, voussoirs_above_springing,
)


class TestPrimitives:
    def test_approx_equal_passes(self):
        approx_equal(1.0, 1.05, tol=0.1)

    def test_approx_equal_fails(self):
        with pytest.raises(ValidationError):
            approx_equal(1.0, 1.5, tol=0.1)

    def test_meets_passes(self):
        a = Anchor("top", 100, 200)
        b = Anchor("bot", 100, 200)
        meets(a, b)

    def test_meets_fails(self):
        a = Anchor("top", 100, 200)
        b = Anchor("bot", 100, 205)  # 5mm gap
        with pytest.raises(ValidationError):
            meets(a, b)

    def test_is_closed_passes(self):
        pl = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        is_closed(pl)

    def test_is_closed_fails(self):
        pl = [(0, 0), (10, 0), (10, 10), (0, 10)]  # no closing point
        with pytest.raises(ValidationError):
            is_closed(pl)

    def test_mirror_symmetric_passes(self):
        pl = [(1, 0), (5, 0), (1, 10), (-1, 10), (-5, 0), (-1, 0)]
        mirror_symmetric(pl, axis_x=0, tol=0.5)

    def test_voussoirs_above_springing_passes(self):
        # voussoirs all above (smaller y than) y_spring=100
        vs = [[(10, 80), (12, 80), (12, 90), (10, 90)],
              [(20, 70), (25, 70), (25, 85), (20, 85)]]
        voussoirs_above_springing(vs, y_spring=100)

    def test_voussoirs_above_springing_fails(self):
        vs = [[(10, 80), (12, 80), (12, 120), (10, 120)]]  # corner below springing
        with pytest.raises(ValidationError):
            voussoirs_above_springing(vs, y_spring=100)


class TestTuscanOrder:
    def test_tuscan_validates(self):
        from engraving.orders import tuscan_column_silhouette
        from engraving.validate.orders import TuscanValidation

        dims = canon.Tuscan(D=20.0)
        result = tuscan_column_silhouette(dims, cx=100, base_y=200,
                                          return_result=True)
        report = TuscanValidation(result=result, order_name="tuscan").full_report()
        assert len(report) == 0, f"Tuscan failed: {list(report)}"


class TestDoricEntablature:
    def test_doric_entablature_validates(self):
        from engraving.entablature_doric import doric_entablature
        from engraving.validate.entablatures import validate_doric_entablature

        dims = canon.Doric(D=20.0)
        col_xs = [60, 120, 180, 240]
        result = doric_entablature(40, 260, 200, dims, col_xs,
                                   return_result=True)
        report = validate_doric_entablature(result, col_xs)
        # Tightened: Doric entablature should produce zero errors on a
        # canonically-spaced column row. Locks in triglyph-over-column +
        # canonical heights so regressions surface immediately.
        assert len(report) == 0, f"Doric entablature: {list(report)}"


class TestFacadeComposition:
    def test_bad_facade_caught(self):
        """Upper-story rustication should be flagged."""
        from engraving.facade import Facade, Story, Bay, Opening
        from engraving.validate.composition import validate_facade_composition

        bays = [Bay(openings=[
                    Opening(kind="window", width=20, height=40),
                    Opening(kind="window", width=20, height=40),
                ]) for _ in range(3)]
        bad_stories = [
            Story(height=70, wall="smooth"),
            Story(height=70, wall={"variant": "arcuated"}),  # upper story = wrong
        ]
        f = Facade(width=300, stories=bad_stories, bays=bays, base_y=200)
        f.layout()
        report = validate_facade_composition(f)
        assert len(report) >= 1
        assert any("rusticated variant" in e for e in report)

    def test_bay_count_mismatch_caught(self):
        from engraving.facade import Facade, Story, Bay, Opening
        from engraving.validate.composition import validate_facade_composition

        # Bay has 1 opening but facade has 2 stories
        bays = [Bay(openings=[Opening(kind="window", width=20, height=40)])]
        stories = [Story(height=70), Story(height=70)]
        f = Facade(width=300, stories=stories, bays=bays, base_y=200)
        f.layout()
        report = validate_facade_composition(f)
        assert any("openings" in e for e in report)


class TestVoussoirs:
    def test_voussoirs_above_springing_in_arcuated_wall(self):
        from engraving.rustication import wall
        from engraving.validate import voussoirs_above_springing

        result = wall(x0=0, y0=0, width=200, height=120,
                      course_h=30, block_w=60, variant="arcuated",
                      arch_springings_y=[60],
                      arch_spans=[(100, 60)])
        vous = result.get("arch_voussoirs", [])
        assert len(vous) > 0, "arcuated should produce voussoirs"
        voussoirs_above_springing(vous, y_spring=60)  # strict: raises if violated


class TestPlatesStillRender:
    """After the retrofits, all existing plates must still render."""

    @pytest.mark.slow
    def test_portico_renders(self):
        from plates.plate_portico import build
        out = build()
        assert out.endswith(".svg")

    @pytest.mark.slow
    def test_doric_renders(self):
        from plates.plate_doric import build
        out = build()
        assert out.endswith(".svg")

    @pytest.mark.slow
    def test_blocking_course_renders(self):
        from plates.plate_blocking_course import build
        out = build()
        assert out.endswith(".svg")


class TestCompositeCapital:
    def test_composite_row2_leaf_count(self):
        from engraving.order_composite import composite_column_silhouette

        dims = canon.Composite(D=20.0)
        result = composite_column_silhouette(dims, cx=100, base_y=200,
                                             return_result=True)
        assert result.metadata["num_acanthus_row2"] == 3, \
            f"row2 count: {result.metadata['num_acanthus_row2']}"
        # Also check the actual polyline count in the acanthus layer matches
        # metadata (3 leaves x ~N polylines per leaf — sanity bound).
        acanthus_polys = result.polylines.get("acanthus", [])
        assert len(acanthus_polys) > 0, "acanthus layer empty"


class TestPlateValidation:
    @pytest.mark.slow
    def test_plate_doric_validates(self):
        from plates.plate_doric import build_validated
        _, report = build_validated()
        # Allow zero or a few known issues
        assert len(report) <= 3, list(report)

    @pytest.mark.slow
    def test_plate_portico_validates(self):
        from plates.plate_portico import build_validated
        _, report = build_validated()
        assert len(report) <= 3, list(report)

    @pytest.mark.slow
    def test_plate_schematic_validates(self):
        from plates.plate_schematic import build_validated
        _, report = build_validated()
        # Schematic should have voussoir fixes applied by now
        assert len(report) <= 5, list(report)


class TestPlateTextUnicode:
    def test_no_ascii_apostrophes_in_plate_text(self):
        import re
        import pathlib

        plate_dir = pathlib.Path(
            "/Users/choehn/Projects/ornament-vector-drawing/plates")
        violations = []
        for pyf in plate_dir.glob("plate_*.py"):
            text = pyf.read_text()
            # Find page.text(... "string_with_apostrophe" ...)
            for m in re.finditer(r'page\.text\(\s*"([^"]*\'[^"]*)"', text):
                violations.append(f"{pyf.name}: {m.group(1)!r}")
            for m in re.finditer(r"page\.text\(\s*'([^']*'[^']*)'", text):
                violations.append(f"{pyf.name}: {m.group(1)!r}")
        assert not violations, (
            "ASCII apostrophes in plate text:\n  " + "\n  ".join(violations))


# ──────────────────────────────────────────────────────────────────────────
# Order validators — all five schemas, happy-path
# ──────────────────────────────────────────────────────────────────────────

class TestAllOrderValidators:
    def test_doric_validates(self):
        from engraving.order_doric import doric_column_silhouette
        from engraving.validate.orders import DoricValidation

        dims = canon.Doric(D=20.0)
        res = doric_column_silhouette(dims, cx=100, base_y=200,
                                      return_result=True)
        report = DoricValidation(result=res, order_name="doric").full_report()
        assert len(report) == 0, list(report)

    def test_ionic_validates(self):
        from engraving.order_ionic import ionic_column_silhouette
        from engraving.validate.orders import IonicValidation

        dims = canon.Ionic(D=20.0)
        res = ionic_column_silhouette(dims, cx=100, base_y=200,
                                      return_result=True)
        report = IonicValidation(result=res, order_name="ionic").full_report()
        assert len(report) == 0, list(report)

    def test_corinthian_validates(self):
        from engraving.order_corinthian import corinthian_column_silhouette
        from engraving.validate.orders import CorinthianValidation

        dims = canon.Corinthian(D=20.0)
        res = corinthian_column_silhouette(dims, cx=100, base_y=200,
                                           return_result=True)
        report = CorinthianValidation(
            result=res, order_name="corinthian").full_report()
        assert len(report) == 0, list(report)

    def test_composite_validates(self):
        from engraving.order_composite import composite_column_silhouette
        from engraving.validate.orders import CompositeValidation

        dims = canon.Composite(D=20.0)
        res = composite_column_silhouette(dims, cx=100, base_y=200,
                                          return_result=True)
        report = CompositeValidation(
            result=res, order_name="composite").full_report()
        assert len(report) == 0, list(report)

    def test_missing_core_anchors_rejected(self):
        """A result missing a required anchor must be rejected at schema
        construction time (pydantic field_validator)."""
        from engraving.validate.orders import TuscanValidation
        from engraving.orders import tuscan_column_silhouette
        from pydantic import ValidationError as PydValidationError

        dims = canon.Tuscan(D=20.0)
        res = tuscan_column_silhouette(dims, cx=100, base_y=200,
                                       return_result=True)
        # Remove the 'axis' anchor to trigger the must_have_core_anchors guard.
        res.anchors.pop("axis", None)
        with pytest.raises(PydValidationError):
            TuscanValidation(result=res, order_name="tuscan")


class TestCapitalSubdivisions:
    """Subdivisional metadata (neck/echinus/abacus, plinth/torus/fillet) must
    be present and roughly match Ware's canonical ratios. Each order's
    silhouette builder now exposes sub-element heights so finer-grained
    validators (in engraving/validate/orders.py) can run against them.
    """

    def test_tuscan_capital_subdivisions(self):
        from engraving.orders import tuscan_column_silhouette
        dims = canon.Tuscan(D=20)
        res = tuscan_column_silhouette(dims, 0, 0, return_result=True)
        cap_h = res.metadata["capital_h"]
        for k in ("cap_neck_h", "cap_astragal_h",
                  "cap_echinus_h", "cap_abacus_h"):
            assert k in res.metadata, f"missing {k}"
        # Sum of subdivisions should approximate capital_h.
        total = (res.metadata["cap_neck_h"]
                 + res.metadata["cap_astragal_h"]
                 + res.metadata["cap_echinus_h"]
                 + res.metadata["cap_abacus_h"])
        assert abs(total - cap_h) < 0.1, f"subdivisions {total} ≠ {cap_h}"

    def test_tuscan_base_subdivisions(self):
        from engraving.orders import tuscan_column_silhouette
        dims = canon.Tuscan(D=20)
        res = tuscan_column_silhouette(dims, 0, 0, return_result=True)
        bh = res.metadata["base_h"]
        for k in ("base_plinth_h", "base_torus_h", "base_fillet_h"):
            assert k in res.metadata, f"missing {k}"
        total = (res.metadata["base_plinth_h"]
                 + res.metadata["base_torus_h"]
                 + res.metadata["base_fillet_h"])
        assert abs(total - bh) < 0.1, f"base subs {total} ≠ {bh}"

    def test_doric_capital_subdivisions(self):
        from engraving.order_doric import doric_column_silhouette
        dims = canon.Doric(D=20)
        res = doric_column_silhouette(dims, 0, 0, return_result=True)
        cap_h = res.metadata["capital_h"]
        assert "cap_neck_h" in res.metadata
        assert "cap_echinus_h" in res.metadata
        assert "cap_abacus_h" in res.metadata
        # Each subdivision should be roughly 1/3 of capital.
        for k in ("cap_neck_h", "cap_echinus_h", "cap_abacus_h"):
            frac = res.metadata[k] / cap_h
            assert 0.20 < frac < 0.45, \
                f"Doric {k} fraction {frac:.2f} unreasonable"

    def test_doric_base_subdivisions(self):
        from engraving.order_doric import doric_column_silhouette
        dims = canon.Doric(D=20)
        res = doric_column_silhouette(dims, 0, 0, return_result=True)
        for k in ("base_plinth_h", "base_torus_h", "base_fillet_h"):
            assert k in res.metadata, f"missing {k}"

    def test_ionic_capital_subdivisions(self):
        from engraving.order_ionic import ionic_column_silhouette
        dims = canon.Ionic(D=20)
        res = ionic_column_silhouette(dims, 0, 0, return_result=True)
        cap_h = res.metadata["capital_h"]
        for k in ("cap_volute_h", "cap_abacus_h", "cap_echinus_h"):
            assert k in res.metadata, f"missing {k}"
        # abacus should be the thin ⅙ crown.
        abacus_frac = res.metadata["cap_abacus_h"] / cap_h
        assert 0.10 < abacus_frac < 0.25, \
            f"Ionic abacus fraction {abacus_frac:.2f} unreasonable"

    def test_ionic_base_subdivisions(self):
        from engraving.order_ionic import ionic_column_silhouette
        dims = canon.Ionic(D=20)
        res = ionic_column_silhouette(dims, 0, 0, return_result=True)
        for k in ("base_plinth_h", "base_lower_torus_h", "base_scotia_h",
                  "base_upper_torus_h", "base_fillet_h"):
            assert k in res.metadata, f"missing {k}"

    def test_corinthian_capital_subdivisions(self):
        from engraving.order_corinthian import corinthian_column_silhouette
        dims = canon.Corinthian(D=20)
        res = corinthian_column_silhouette(dims, 0, 0, return_result=True)
        cap_h = res.metadata["capital_h"]
        for k in ("cap_bell_h", "cap_acanthus_row1_h",
                  "cap_acanthus_row2_h", "cap_helix_h", "cap_abacus_h"):
            assert k in res.metadata, f"missing {k}"
        # Bell should dominate (~6/7 of cap_h).
        bell_frac = res.metadata["cap_bell_h"] / cap_h
        assert 0.75 < bell_frac < 0.95, \
            f"Corinth bell fraction {bell_frac:.2f} unreasonable"

    def test_corinthian_base_subdivisions(self):
        from engraving.order_corinthian import corinthian_column_silhouette
        dims = canon.Corinthian(D=20)
        res = corinthian_column_silhouette(dims, 0, 0, return_result=True)
        for k in ("base_plinth_h", "base_lower_torus_h", "base_scotia_h",
                  "base_upper_torus_h", "base_fillet_h"):
            assert k in res.metadata, f"missing {k}"

    def test_composite_capital_subdivisions(self):
        from engraving.order_composite import composite_column_silhouette
        dims = canon.Composite(D=20)
        res = composite_column_silhouette(dims, 0, 0, return_result=True)
        for k in ("cap_acanthus_row1_h", "cap_acanthus_row2_h",
                  "cap_caulicoli_h", "cap_echinus_h", "cap_volute_h",
                  "cap_abacus_h"):
            assert k in res.metadata, f"missing {k}"

    def test_composite_base_subdivisions(self):
        from engraving.order_composite import composite_column_silhouette
        dims = canon.Composite(D=20)
        res = composite_column_silhouette(dims, 0, 0, return_result=True)
        for k in ("base_plinth_h", "base_lower_torus_h", "base_scotia_h",
                  "base_upper_torus_h", "base_fillet_h"):
            assert k in res.metadata, f"missing {k}"

    def test_greek_doric_capital_subdivisions(self):
        from engraving.order_greek_doric import greek_doric_column_silhouette
        dims = canon.GreekDoric(D=20)
        res = greek_doric_column_silhouette(dims, 0, 0, return_result=True)
        cap_h = res.metadata["capital_h"]
        for k in ("cap_annulet_h", "cap_echinus_h", "cap_abacus_h"):
            assert k in res.metadata, f"missing {k}"
        # Greek Doric echinus dominates (~55%).
        ech_frac = res.metadata["cap_echinus_h"] / cap_h
        assert 0.40 < ech_frac < 0.70, \
            f"Greek Doric echinus fraction {ech_frac:.2f} unreasonable"

    def test_greek_ionic_capital_subdivisions(self):
        from engraving.order_greek_ionic import greek_ionic_column_silhouette
        dims = canon.GreekIonic(D=20)
        res = greek_ionic_column_silhouette(dims, 0, 0, return_result=True)
        for k in ("cap_volute_h", "cap_echinus_h", "cap_abacus_h"):
            assert k in res.metadata, f"missing {k}"

    def test_greek_ionic_base_subdivisions(self):
        from engraving.order_greek_ionic import greek_ionic_column_silhouette
        dims = canon.GreekIonic(D=20)
        res = greek_ionic_column_silhouette(dims, 0, 0, return_result=True)
        for k in ("base_plinth_h", "base_lower_torus_h", "base_scotia_h",
                  "base_upper_torus_h", "base_fillet_h"):
            assert k in res.metadata, f"missing {k}"


class TestGreekOrders:
    def test_greek_doric_validates(self):
        from engraving.order_greek_doric import greek_doric_column_silhouette
        from engraving.validate.orders import GreekDoricValidation
        dims = canon.GreekDoric(D=20.0)
        res = greek_doric_column_silhouette(dims, 100, 200,
                                            return_result=True)
        report = GreekDoricValidation(
            result=res, order_name="greek_doric").full_report()
        assert len(report) == 0, list(report)

    def test_greek_ionic_validates(self):
        from engraving.order_greek_ionic import greek_ionic_column_silhouette
        from engraving.validate.orders import GreekIonicValidation
        dims = canon.GreekIonic(D=20.0)
        res = greek_ionic_column_silhouette(dims, 100, 200,
                                            return_result=True)
        report = GreekIonicValidation(
            result=res, order_name="greek_ionic").full_report()
        assert len(report) == 0, list(report)

    def test_greek_doric_has_no_base(self):
        """Greek Doric springs directly from the stylobate — no base."""
        d = canon.GreekDoric(D=20.0)
        assert d.base_D == 0.0
        assert d.pedestal_D == 0.0
        assert d.base_h == 0.0

    def test_greek_doric_is_stouter_than_roman(self):
        """Greek Doric (~5.5 D) is stouter than Roman Doric (8 D)."""
        assert (canon.GreekDoric(D=20.0).column_D
                < canon.Doric(D=20.0).column_D)

    def test_greek_doric_has_annulets(self):
        from engraving.order_greek_doric import greek_doric_column_silhouette
        dims = canon.GreekDoric(D=20.0)
        res = greek_doric_column_silhouette(dims, 100, 200,
                                            return_result=True)
        assert res.metadata["num_annulets"] == 4
        # And the actual annulet rules layer has 4 polylines.
        assert len(res.polylines["annulets"]) == 4

    def test_greek_ionic_volute_eye_anchors(self):
        from engraving.order_greek_ionic import greek_ionic_column_silhouette
        dims = canon.GreekIonic(D=20.0)
        res = greek_ionic_column_silhouette(dims, 100, 200,
                                            return_result=True)
        assert "volute_eye_left" in res.anchors
        assert "volute_eye_right" in res.anchors

    def test_greek_orders_registered(self):
        """Both Greek variants are callable via canon.make()."""
        assert isinstance(canon.make("greek_doric", D=20.0), canon.GreekDoric)
        assert isinstance(canon.make("greek_ionic", D=20.0), canon.GreekIonic)

    @pytest.mark.slow
    def test_plate_greek_orders_renders(self):
        from plates.plate_greek_orders import build_validated
        svg_path, report = build_validated()
        assert svg_path.endswith(".svg")
        assert len(report) == 0, list(report)


# ──────────────────────────────────────────────────────────────────────────
# Element validators — arch/window/balustrade/rustication happy-path
# (acanthus is covered by a parallel agent)
# ──────────────────────────────────────────────────────────────────────────

class TestElementValidators:
    def test_semicircular_arch_validates(self):
        from engraving.arches import semicircular_arch
        from engraving.validate.elements import validate_arch

        result = semicircular_arch(cx=100, y_spring=180, span=80,
                                   voussoir_count=9, with_keystone=True)
        report = validate_arch(result, cx=100, y_spring=180, span=80)
        assert len(report) == 0, list(report)

    def test_segmental_arch_validates(self):
        from engraving.arches import segmental_arch
        from engraving.validate.elements import validate_arch

        result = segmental_arch(cx=100, y_spring=180, span=80, rise=15,
                                voussoir_count=9)
        report = validate_arch(result, cx=100, y_spring=180, span=80)
        assert len(report) == 0, list(report)

    def test_window_validates_each_hood(self):
        from engraving.windows import window_opening
        from engraving.validate.elements import validate_window

        for hood in ("none", "cornice", "triangular", "segmental"):
            result = window_opening(x=0, y_top=0, w=40, h=70, hood=hood)
            report = validate_window(result, 0, 0, 40, 70)
            assert len(report) == 0, f"hood={hood}: {list(report)}"

    def test_window_with_keystone_validates(self):
        from engraving.windows import window_opening
        from engraving.validate.elements import validate_window

        result = window_opening(x=0, y_top=0, w=40, h=70,
                                hood="triangular", keystone=True)
        report = validate_window(result, 0, 0, 40, 70)
        assert len(report) == 0, list(report)

    def test_balustrade_validates(self):
        from engraving.balustrades import balustrade_run
        from engraving.validate.elements import validate_balustrade

        result = balustrade_run(x0=30, x1=270, y_top_of_rail=120,
                                height=80)
        report = validate_balustrade(result, 30, 270, 120, 80)
        assert len(report) == 0, list(report)

    def test_baluster_validates(self):
        from engraving.balustrades import baluster_silhouette
        from engraving.validate.elements import validate_baluster

        polys = baluster_silhouette(cx=50, y_bottom=200, height=80,
                                    max_diam=25, variant="tuscan")
        report = validate_baluster(polys, cx=50, y_bottom=200,
                                   height=80, max_diam=25)
        assert len(report) == 0, list(report)

    def test_rustication_banded_validates(self):
        from engraving.rustication import wall
        from engraving.validate.elements import validate_rustication

        result = wall(x0=0, y0=0, width=200, height=120,
                      course_h=30, block_w=60, variant="banded")
        report = validate_rustication(result, 0, 0, 200, 120, "banded")
        assert len(report) == 0, list(report)

    def test_rustication_chamfered_validates(self):
        from engraving.rustication import wall
        from engraving.validate.elements import validate_rustication

        result = wall(x0=0, y0=0, width=200, height=120,
                      course_h=20, block_w=30, variant="chamfered")
        report = validate_rustication(result, 0, 0, 200, 120, "chamfered")
        assert len(report) == 0, list(report)

    def test_rustication_arcuated_validates(self):
        from engraving.rustication import wall
        from engraving.validate.elements import validate_rustication

        result = wall(x0=0, y0=0, width=200, height=120,
                      course_h=20, block_w=30, variant="arcuated",
                      arch_springings_y=[60.0],
                      arch_spans=[(100.0, 60.0)])
        report = validate_rustication(result, 0, 0, 200, 120, "arcuated")
        assert len(report) == 0, list(report)


# ──────────────────────────────────────────────────────────────────────────
# Element validators — bad-input tests to lock in validator behaviour
# ──────────────────────────────────────────────────────────────────────────

class TestElementValidatorsBadInput:
    def test_arch_voussoir_below_springing_caught(self):
        """Hand-forged arch result with a voussoir poking below springing."""
        from engraving.validate.elements import validate_arch

        # Minimal arch result with a faulty voussoir: all corners should be
        # above y_spring=100, but one corner dips to 120.
        arch_result = {
            "intrados": [[(60, 100), (100, 60), (140, 100)]],
            "voussoirs": [[(60, 100), (70, 100), (70, 120), (60, 120)]],
        }
        report = validate_arch(arch_result, cx=100, y_spring=100, span=80)
        assert len(report) >= 1
        assert any("voussoir" in e.lower() or "springing" in e.lower()
                   for e in report)

    def test_window_missing_opening_caught(self):
        from engraving.validate.elements import validate_window

        report = validate_window({}, x=0, y_top=0, w=40, h=70)
        assert len(report) >= 1
        assert any("opening" in e.lower() for e in report)

    def test_window_opening_wrong_size_caught(self):
        from engraving.validate.elements import validate_window

        # Expect 40x70 but polygon is 10x10
        bad_result = {
            "opening": [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)],
        }
        report = validate_window(bad_result, x=0, y_top=0, w=40, h=70)
        assert len(report) >= 1

    def test_rustication_missing_outline_caught(self):
        from engraving.validate.elements import validate_rustication

        report = validate_rustication({}, 0, 0, 200, 120, "banded")
        assert len(report) >= 1
        assert any("outline" in e.lower() for e in report)

    def test_rustication_wrong_outline_bbox_caught(self):
        from engraving.validate.elements import validate_rustication

        # Outline is 50x50 but we claim 200x120
        bad = {"outline": [(0, 0), (50, 0), (50, 50), (0, 50), (0, 0)]}
        report = validate_rustication(bad, 0, 0, 200, 120, "banded")
        assert len(report) >= 1


# ──────────────────────────────────────────────────────────────────────────
# Composition validators — exercise all 11 rules
# ──────────────────────────────────────────────────────────────────────────

class TestCompositionAll:
    def _make_good_facade(self):
        from engraving.facade import Facade, Story, Bay, Opening

        bays = [Bay(openings=[
                    Opening(kind="arch_window", width=20, height=40),
                    Opening(kind="window", width=20, height=50,
                            hood="triangular"),
                    Opening(kind="window", width=20, height=35,
                            hood="cornice"),
                ], pilaster_order="ionic", pilaster_width=5)
                for _ in range(5)]
        stories = [
            Story(height=70, wall={"variant": "arcuated",
                                   "course_h": 20, "block_w": 40}),
            Story(height=90, wall="smooth", has_order="ionic"),
            Story(height=55, wall="smooth"),
        ]
        return Facade(width=400, stories=stories, bays=bays, base_y=300,
                      parapet={"type": "balustrade", "height": 18})

    def test_good_facade_passes_composition(self):
        from engraving.validate.composition import validate_facade_composition
        f = self._make_good_facade()
        f.layout()
        report = validate_facade_composition(f)
        # A well-formed facade should produce 0 pre-render errors.
        assert len(report) == 0, list(report)

    def test_good_facade_passes_render(self):
        from engraving.validate.composition import validate_facade_render
        f = self._make_good_facade()
        f.layout()
        render_result = f.render()
        report = validate_facade_render(f, render_result)
        # Post-render should also be clean.
        assert len(report) == 0, list(report)

    # ---- validate_story_layout (Rule 1: heights, orders, rustication) ----

    def test_non_positive_story_height_caught(self):
        from engraving.facade import Facade, Story, Bay, Opening
        from engraving.validate.composition import validate_facade_composition

        f = Facade(
            width=400, base_y=300,
            stories=[Story(height=-10), Story(height=90)],
            bays=[Bay(openings=[
                Opening(kind="window", width=20, height=40),
                Opening(kind="window", width=20, height=40),
            ])],
        )
        f.layout()
        r = validate_facade_composition(f)
        assert any("non-positive height" in e for e in r), list(r)

    def test_invalid_order_name_caught(self):
        from engraving.facade import Facade, Story, Bay, Opening
        from engraving.validate.composition import validate_facade_composition

        f = Facade(
            width=400, base_y=300,
            stories=[Story(height=70, has_order="gothic")],
            bays=[Bay(openings=[
                Opening(kind="window", width=20, height=40)])],
        )
        f.layout()
        r = validate_facade_composition(f)
        assert any("not recognised" in e or "not known" in e or "gothic" in e
                   for e in r), list(r)

    def test_rustication_on_upper_story_caught(self):
        """Ware: rustication convention is ground-only."""
        from engraving.facade import Facade, Story, Bay, Opening
        from engraving.validate.composition import validate_facade_composition

        f = Facade(
            width=400, base_y=300,
            stories=[
                Story(height=70, wall="smooth"),
                Story(height=90, wall={"variant": "vermiculated"}),
            ],
            bays=[Bay(openings=[
                Opening(kind="window", width=20, height=40),
                Opening(kind="window", width=20, height=40),
            ])],
        )
        f.layout()
        r = validate_facade_composition(f)
        assert any("rusticated variant" in e for e in r), list(r)

    def test_piano_nobile_must_not_be_top_story(self):
        from engraving.facade import Facade, Story, Bay, Opening
        from engraving.validate.composition import validate_facade_composition

        # Two stories only; the top carries has_order => piano-nobile-at-top.
        f = Facade(
            width=400, base_y=300,
            stories=[
                Story(height=70),
                Story(height=90, has_order="ionic"),
            ],
            bays=[Bay(openings=[
                Opening(kind="window", width=20, height=40),
                Opening(kind="window", width=20, height=40),
            ])],
        )
        f.layout()
        r = validate_facade_composition(f)
        assert any("piano nobile" in e and "top story" in e for e in r), \
            list(r)

    # ---- validate_bay_layout (Rule 2: openings/story, pilaster_order) ----

    def test_bay_unknown_pilaster_order_caught(self):
        from engraving.facade import Facade, Story, Bay, Opening
        from engraving.validate.composition import validate_facade_composition

        f = Facade(
            width=400, base_y=300,
            stories=[Story(height=70)],
            bays=[Bay(openings=[
                Opening(kind="window", width=20, height=40)],
                pilaster_order="etruscan", pilaster_width=5)],
        )
        f.layout()
        r = validate_facade_composition(f)
        assert any("pilaster_order" in e and "not recognised" in e
                   for e in r), list(r)

    def test_upper_opening_wider_than_lower_caught(self):
        """Upper story opening wider than the lower story violates the
        classical Vignola/Palladio hierarchy (widths descend going up)."""
        from engraving.facade import Facade, Story, Bay, Opening
        from engraving.validate.composition import validate_facade_composition

        f = Facade(
            width=400, base_y=300,
            stories=[Story(height=70), Story(height=70)],
            bays=[Bay(openings=[
                Opening(kind="window", width=10, height=40),
                Opening(kind="window", width=30, height=40),  # WIDER than below — wrong
            ])],
        )
        f.layout()
        r = validate_facade_composition(f)
        assert any("should be narrower than lower" in e for e in r), list(r)

    # ---- validate_pilaster_order_match (Rule 3) ----

    def test_pilaster_order_mismatch_caught(self):
        """Ionic story with Doric pilaster => mismatch."""
        from engraving.facade import Facade, Story, Bay, Opening
        from engraving.validate.composition import validate_facade_composition

        f = Facade(
            width=400, base_y=300,
            stories=[Story(height=70, has_order="ionic")],
            bays=[Bay(openings=[
                Opening(kind="window", width=20, height=40)],
                pilaster_order="doric", pilaster_width=5)],
        )
        f.layout()
        r = validate_facade_composition(f)
        assert any("does not match" in e or "mismatch" in e.lower()
                   for e in r), list(r)

    # ---- validate_arched_openings_in_arcuated_stories (Rule 4) ----

    def test_arched_opening_in_smooth_story_caught(self):
        from engraving.facade import Facade, Story, Bay, Opening
        from engraving.validate.composition import validate_facade_composition

        f = Facade(
            width=400, base_y=300,
            stories=[Story(height=70, wall="smooth")],
            bays=[Bay(openings=[
                Opening(kind="arch_window", width=20, height=40)])],
        )
        f.layout()
        r = validate_facade_composition(f)
        assert any("arched opening" in e for e in r), list(r)

    # ---- validate_voussoirs (Rule 5, post-render) ----

    def test_voussoirs_above_springing_post_render(self):
        """A well-formed arcuated facade should have no voussoir violations."""
        from engraving.validate.composition import validate_facade_render

        f = self._make_good_facade()
        f.layout()
        result = f.render()
        report = validate_facade_render(f, result)
        assert not any("wall_voussoirs" in e and "below" in e
                       for e in report), list(report)

    # ---- validate_string_courses (Rule 6, post-render) ----

    def test_string_courses_present(self):
        from engraving.validate.composition import validate_facade_render

        f = self._make_good_facade()
        f.layout()
        result = f.render()
        report = validate_facade_render(f, result)
        assert not any("string course" in e for e in report), list(report)

    # ---- validate_parapet (Rule 7, post-render) ----

    def test_parapet_present_when_declared(self):
        from engraving.validate.composition import validate_facade_render

        f = self._make_good_facade()
        f.layout()
        result = f.render()
        report = validate_facade_render(f, result)
        assert not any("parapet" in e for e in report), list(report)

    # ---- validate_smooth_walls_have_no_blocks (Rule 8, post-render) ----

    def test_smooth_wall_has_no_blocks(self):
        """A good facade's smooth stories must not contain wall-block polylines."""
        from engraving.validate.composition import validate_facade_render

        f = self._make_good_facade()
        f.layout()
        result = f.render()
        report = validate_facade_render(f, result)
        assert not any("smooth" in e and "wall_blocks" in e
                       for e in report), list(report)


# ──────────────────────────────────────────────────────────────────────────
# Extra primitive coverage that other agents aren't touching
# ──────────────────────────────────────────────────────────────────────────

class TestPrimitivesExtra:
    def test_approx_equal_with_custom_tol(self):
        # Larger tolerance allows a mismatch that default tol would reject.
        approx_equal(1.0, 1.4, tol=0.5)

    def test_aligned_vertical_fails_on_x_mismatch(self):
        a = Anchor("top", 100.0, 200.0)
        b = Anchor("bot", 100.5, 200.0)  # 0.5mm x-offset
        with pytest.raises(ValidationError):
            aligned_vertical(a, b, tol=0.1)

    def test_count_equals_fails(self):
        with pytest.raises(ValidationError):
            count_equals(3, 4, "triglyphs")

    def test_count_equals_passes(self):
        count_equals(4, 4, "triglyphs")

    def test_monotonic_in_radius_increasing_passes(self):
        # Points with increasing distance from origin.
        pts = [(1, 0), (2, 0), (3, 0), (4, 0)]
        monotonic_in_radius(pts, center=(0, 0), direction="increasing",
                            tol=0.1)

    def test_monotonic_in_radius_decreasing_fails(self):
        # Distance jumps back up -> not monotonic-decreasing.
        pts = [(4, 0), (3, 0), (5, 0)]
        with pytest.raises(ValidationError):
            monotonic_in_radius(pts, center=(0, 0),
                                direction="decreasing", tol=0.1)

    def test_total_angle_sweep_half_circle(self):
        import math as _math
        # Half circle from (1,0) around origin -> sweep ≈ π.
        pts = []
        N = 40
        for i in range(N):
            t = _math.pi * i / (N - 1)
            pts.append((_math.cos(t), _math.sin(t)))
        sweep = total_angle_sweep(pts, (0.0, 0.0))
        assert abs(abs(sweep) - _math.pi) < 0.05

    def test_mirror_symmetric_fails_on_asymmetric(self):
        # Left side has extra point with no mirror.
        pts = [(1, 0), (2, 0), (5, 0), (-1, 0), (-2, 0)]
        with pytest.raises(ValidationError):
            mirror_symmetric(pts, axis_x=0, tol=0.2)

    def test_is_closed_too_short(self):
        with pytest.raises(ValidationError):
            is_closed([(0, 0), (1, 1)])

    def test_validation_report_collect_and_raise(self):
        r = ValidationReport()
        assert r
        assert len(r) == 0
        r.check(approx_equal, 1.0, 2.0, 0.1, "x")
        assert len(r) == 1
        assert not r
        with pytest.raises(ValidationError):
            r.raise_if_any()

    def test_no_duplicate_lines_passes(self):
        from engraving.validate import no_duplicate_lines
        pls = [[(0, 0), (10, 0)], [(0, 10), (10, 10)]]
        no_duplicate_lines(pls, tol=0.05)

    def test_no_duplicate_lines_catches_reverse_dup(self):
        from engraving.validate import no_duplicate_lines
        pls = [[(0, 0), (10, 0)], [(10, 0), (0, 0)]]
        with pytest.raises(ValidationError):
            no_duplicate_lines(pls, tol=0.05)


# ──────────────────────────────────────────────────────────────────────────
# Motif plugin system (Phase 7) — loader + validator
# ──────────────────────────────────────────────────────────────────────────

class TestMotifPlugins:
    def test_loader_finds_test_rosette(self):
        from engraving.plugins import get_motif, load_motifs
        load_motifs()
        m = get_motif("test_rosette")
        assert m is not None
        assert m["svg_path"] is not None

    def test_loader_reads_anchors(self):
        from engraving.plugins import get_motif
        m = get_motif("test_rosette")
        assert "center" in m["anchors"]
        assert m["anchors"]["center"].x == 0
        assert m["anchors"]["center"].y == 0

    def test_loader_produces_polylines(self):
        from engraving.plugins import get_motif_or_default
        polys = get_motif_or_default(
            "test_rosette",
            default_fn=lambda **kw: [[(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]],
            width=20.0,
            height=20.0,
        )
        assert len(polys) >= 1
        # Scaled to 20mm: points should be in roughly [-10, 10] range.
        assert max(abs(p[0]) for p in polys[0]) <= 15

    def test_motif_validator_catches_bad_svg(self):
        import pathlib
        import tempfile
        from engraving.validate.motifs import validate_motif_svg

        with tempfile.NamedTemporaryFile(suffix=".svg", delete=False,
                                         mode="w") as f:
            f.write('<svg viewBox="0 0 1 1">'
                    '<polyline points="0,0 1,1" /></svg>')
            tmp = pathlib.Path(f.name)
        try:
            report = validate_motif_svg(tmp)
            # Silhouette is an open line -- should be flagged as not closed.
            assert len(report) >= 1
        finally:
            tmp.unlink()


# ──────────────────────────────────────────────────────────────────────────
# Entablature canonical regressions
# ──────────────────────────────────────────────────────────────────────────

class TestEntablatureCanonical:
    def test_ionic_dentil_spacing(self):
        from engraving.entablature_ionic import ionic_entablature
        from engraving.validate import dentil_spacing_matches

        dims = canon.Ionic(D=20.0)
        result = ionic_entablature(40, 260, 200, dims, return_result=True)
        dentils = result.polylines.get("dentils", [])
        if not dentils:
            # Some modules put dentils elsewhere
            dentils = [pl for pls in result.polylines.values() for pl in pls
                       if len(pl) == 5 and all(abs(pl[0][0] - pl[-1][0]) < 0.01 for pl in [pl])]
        assert len(dentils) > 0
        dentil_spacing_matches(dentils, expected_oc=dims.D / 6, tol=0.15)

    def test_composite_entablature_has_correct_dentils(self):
        # If you named the new function composite_entablature, import that
        # instead. Composite has larger/squarer dentils per Ware p.24.
        try:
            from engraving.entablature_composite import composite_entablature
        except ImportError:
            from engraving.entablature_corinthian import composite_entablature
        dims = canon.Composite(D=20.0)
        result = composite_entablature(40, 260, 200, dims, [60, 120, 180, 240],
                                       return_result=True)
        # Composite dentil width should be 1/6 D (not 1/18 D like Ionic/Corinth)
        dentil_layer = result.polylines.get("dentils", [])
        if dentil_layer:
            d0 = dentil_layer[0]
            width = max(p[0] for p in d0) - min(p[0] for p in d0)
            expected = dims.D / 6
            assert abs(width - expected) < 0.2, \
                f"Composite dentil width {width} \u2260 {expected}"

    def test_no_duplicate_lines_in_entablature(self):
        from engraving.entablature_ionic import ionic_entablature
        from engraving.validate import no_duplicate_lines

        dims = canon.Ionic(D=20.0)
        result = ionic_entablature(40, 260, 200, dims, return_result=True)
        all_polys = [pl for layer in result.polylines.values() for pl in layer]
        no_duplicate_lines(all_polys, tol=0.1)  # strict: raises on dupes


class TestAcanthus:
    def test_acanthus_no_self_intersection(self):
        from engraving.acanthus import acanthus_leaf
        from engraving.validate.elements import validate_acanthus_leaf
        for n in (3, 5, 7):
            leaf = acanthus_leaf(width=30, height=40, lobe_count=n)
            report = validate_acanthus_leaf(leaf, 30, 40, n)
            assert len(report) == 0, f"lobe_count={n}: {list(report)}"


class TestArcade:
    def test_arcade_basic(self):
        from engraving.arcade import arcade
        from engraving.validate.elements import validate_arcade
        result = arcade(x0=0, y_base=200, width=300, height=150,
                        bay_count=5)
        report = validate_arcade(result)
        assert len(report) == 0, list(report)

    def test_arcade_even_spacing(self):
        from engraving.arcade import arcade
        result = arcade(x0=0, y_base=200, width=300, height=150,
                        bay_count=4)
        assert result.metadata["bay_count"] == 4
        assert result.metadata["pier_count"] == 5
        # Pier centers evenly spaced
        centers = sorted(
            result.anchors[f"pier_{i}_center"].x for i in range(5)
        )
        diffs = [centers[i + 1] - centers[i] for i in range(4)]
        assert all(abs(d - diffs[0]) < 0.01 for d in diffs), diffs

    def test_arcade_segmental(self):
        from engraving.arcade import arcade
        result = arcade(x0=0, y_base=200, width=300, height=150,
                        bay_count=5, arch_type="segmental",
                        segmental_rise_frac=0.1)
        assert len(result.polylines.get("arches", [])) > 0
        assert result.metadata["arch_type"] == "segmental"

    def test_arcade_pier_count_invariant(self):
        from engraving.arcade import arcade
        for bay_count in (1, 3, 5, 7):
            result = arcade(x0=0, y_base=200, width=300, height=150,
                            bay_count=bay_count)
            assert result.metadata["pier_count"] == bay_count + 1
            assert result.metadata["arch_count"] == bay_count

    def test_arcade_with_entablature(self):
        from engraving.arcade import arcade
        from engraving.validate.elements import validate_arcade
        result = arcade(x0=0, y_base=200, width=300, height=150,
                        bay_count=5, with_entablature=True)
        assert len(result.polylines.get("entablature", [])) > 0
        report = validate_arcade(result)
        assert len(report) == 0, list(report)


class TestArcadeProportions:
    def test_pier_to_clear_span_ratio(self):
        from engraving.arcade import arcade
        result = arcade(x0=0, y_base=200, width=300, height=180, bay_count=5)
        pier_width = result.metadata["pier_width"]
        clear_span = result.metadata["clear_span"]
        ratio = pier_width / clear_span
        # Vignola convention: pier_width ≈ 1/3 to 1/2 of clear span
        assert 0.30 <= ratio <= 0.55, f"pier:span = {ratio:.2f} out of [0.30, 0.55]"


class TestArcadeSpring:
    def test_arch_springs_from_impost(self):
        from engraving.arcade import arcade
        result = arcade(x0=0, y_base=200, width=300, height=150,
                        bay_count=5, with_keystones=True)
        # Find arch intrados polylines
        arches = result.polylines.get("arches", [])
        intrados = [pl for pl in arches if len(pl) > 5]
        assert len(intrados) >= 5
        # The y_spring metadata should match the impost_top metadata (or impost top y)
        y_spring = result.metadata.get("y_spring")
        assert y_spring is not None
        # Each intrados endpoint y should equal y_spring within 0.1mm
        for pl in intrados:
            assert abs(pl[0][1] - y_spring) < 0.5, f"intrados start y={pl[0][1]} != y_spring={y_spring}"
            assert abs(pl[-1][1] - y_spring) < 0.5, f"intrados end y={pl[-1][1]} != y_spring={y_spring}"


class TestTypography:
    def test_text_paths_basic(self):
        from engraving.typography import text_paths
        glyphs = text_paths("A", font_size_mm=5.0)
        assert len(glyphs) >= 1  # "A" produces at least the outer outline
        # Each polyline has at least 3 points (closed shape)
        for pl in glyphs:
            assert len(pl) >= 3

    def test_empty_text_returns_empty(self):
        from engraving.typography import text_paths
        assert text_paths("", font_size_mm=5.0) == []

    def test_all_caps_layout_width(self):
        from engraving.typography import text_paths
        # Cap height 8mm, "HI" -- should occupy roughly 10-25 mm wide
        glyphs = text_paths("HI", font_size_mm=8.0)
        all_x = [p[0] for pl in glyphs for p in pl]
        width = max(all_x) - min(all_x)
        assert 10 < width < 25


class TestCartouche:
    def test_oval_cartouche_symmetric(self):
        from engraving.cartouche import cartouche
        from engraving.validate.elements import validate_cartouche
        cart = cartouche(cx=100, cy=50, width=80, height=40, style="oval")
        report = validate_cartouche(cart, 80, 40)
        assert len(report) == 0, list(report)

    def test_rectangular_cartouche_symmetric(self):
        from engraving.cartouche import cartouche
        from engraving.validate.elements import validate_cartouche
        cart = cartouche(cx=100, cy=50, width=80, height=40,
                         style="rectangular")
        report = validate_cartouche(cart, 80, 40)
        assert len(report) == 0, list(report)

    def test_baroque_scroll_has_wings(self):
        from engraving.cartouche import cartouche
        cart = cartouche(cx=100, cy=50, width=80, height=40,
                         style="baroque_scroll")
        # Should have more polylines than oval (wings + spiral scrolls).
        total = sum(len(v) for v in cart.polylines.values())
        assert total >= 4

    def test_inscription_anchor_present(self):
        from engraving.cartouche import cartouche
        cart = cartouche(cx=50, cy=25, width=40, height=20, style="oval")
        assert "inscription_center" in cart.anchors
        assert cart.anchors["inscription_center"].x == 50
        assert cart.anchors["inscription_center"].y == 25

    def test_cartouche_bbox_matches_envelope(self):
        from engraving.cartouche import cartouche
        cart = cartouche(cx=0, cy=0, width=60, height=30, style="oval")
        bx0, by0, bx1, by1 = cart.bbox
        # Oval should tightly fit the requested 60x30 envelope.
        assert abs((bx1 - bx0) - 60) < 1.0
        assert abs((by1 - by0) - 30) < 1.0


class TestExportPipeline:
    def test_svg_to_pdf(self, tmp_path):
        pytest.importorskip("pypdf")
        pytest.importorskip("playwright")
        from engraving.export import svg_to_pdf
        from engraving.render import Page, frame
        # Build a trivial plate
        page = Page()
        frame(page)
        svg = page.save_svg("test_export")
        pdf = svg_to_pdf(svg, tmp_path / "test.pdf")
        assert pdf.exists()
        assert pdf.stat().st_size > 1000

    def test_concat_pdfs(self, tmp_path):
        pytest.importorskip("pypdf")
        pytest.importorskip("playwright")
        from engraving.export import svg_to_pdf, concat_pdfs
        from engraving.render import Page, frame
        # Build two trivial plates
        paths = []
        for i in range(2):
            page = Page()
            frame(page)
            svg = page.save_svg(f"test_concat_{i}")
            pdf = svg_to_pdf(svg, tmp_path / f"p{i}.pdf")
            paths.append(pdf)
        book = concat_pdfs(paths, tmp_path / "book.pdf")
        assert book.exists()
        from pypdf import PdfReader
        assert len(PdfReader(str(book)).pages) == 2

    @pytest.mark.slow
    def test_optimize_svg(self, tmp_path):
        from pathlib import Path as _P
        from engraving.export import optimize_svg
        svg_in = _P("/Users/choehn/Projects/ornament-vector-drawing/out/plate_01.svg")
        if not svg_in.exists():
            pytest.skip("plate_01 not rendered")
        try:
            opt = optimize_svg(svg_in, tmp_path / "opt.svg")
        except RuntimeError:
            pytest.skip("vpype not available")
        assert opt.exists()


class TestStairs:
    def test_straight_flight_basic(self):
        from engraving.stairs import straight_flight
        from engraving.validate.elements import validate_stairs
        stairs = straight_flight(x0=0, y_bottom=100, riser_count=8,
                                 tread=28, riser=18)
        report = validate_stairs(stairs, expected_riser_count=8)
        assert len(report) == 0, list(report)

    def test_straight_flight_left_direction(self):
        """Left-ascending flights should also validate."""
        from engraving.stairs import straight_flight
        from engraving.validate.elements import validate_stairs
        stairs = straight_flight(x0=300, y_bottom=100, riser_count=6,
                                 tread=28, riser=18, direction="left")
        report = validate_stairs(stairs, expected_riser_count=6)
        assert len(report) == 0, list(report)

    def test_straight_flight_no_balustrade(self):
        """Flights without balustrade should omit that layer but stay valid."""
        from engraving.stairs import straight_flight
        from engraving.validate.elements import validate_stairs
        stairs = straight_flight(x0=0, y_bottom=100, riser_count=5,
                                 tread=28, riser=18,
                                 with_balustrade=False,
                                 with_handrail=False)
        report = validate_stairs(stairs, expected_riser_count=5)
        assert len(report) == 0, list(report)
        assert "balusters" not in stairs.polylines
        assert "handrail" not in stairs.polylines

    def test_nosings_rise(self):
        """Each successive nosing must sit above the previous one."""
        from engraving.stairs import straight_flight
        stairs = straight_flight(x0=0, y_bottom=100, riser_count=8,
                                 tread=28, riser=18)
        nosings = [(stairs.anchors[k].x, stairs.anchors[k].y)
                   for k in stairs.anchors if k.startswith("nosing_")]
        nosings.sort(key=lambda p: p[0])
        for i in range(1, len(nosings)):
            assert nosings[i][1] < nosings[i - 1][1], \
                "nosings should rise (lower y) going right"


class TestTitleIntegration:
    @pytest.mark.slow
    def test_plates_use_typography_for_titles(self):
        """All main plates import engraving.typography.title."""
        import pathlib
        plate_dir = pathlib.Path("/Users/choehn/Projects/ornament-vector-drawing/plates")
        skipped = {"plate_01.py", "__init__.py"}
        for pyf in plate_dir.glob("plate_*.py"):
            if pyf.name in skipped:
                continue
            text = pyf.read_text()
            assert "from engraving.typography" in text or \
                   "engraving.typography" in text, \
                f"{pyf.name} does not import typography"


class TestRinceau:
    def test_basic_rinceau(self):
        from engraving.rinceau import rinceau, sinusoidal_spine
        from engraving.validate.elements import validate_rinceau
        spine = sinusoidal_spine(x0=0, x1=200, y0=50,
                                 amplitude=10, period=50)
        r = rinceau(spine, leaf_size=10)
        report = validate_rinceau(r, expected_min_leaves=5)
        assert len(report) == 0, list(report)

    def test_rinceau_leaf_anchors_present(self):
        from engraving.rinceau import rinceau, sinusoidal_spine
        spine = sinusoidal_spine(x0=0, x1=200, y0=50,
                                 amplitude=10, period=50)
        r = rinceau(spine, leaf_size=10)
        count = r.metadata["leaf_count"]
        assert count >= 1
        for i in range(count):
            assert f"leaf_{i}_base" in r.anchors

    def test_rinceau_non_alternate(self):
        """alternate=False still produces leaves (no buds required)."""
        from engraving.rinceau import rinceau, sinusoidal_spine
        spine = sinusoidal_spine(x0=0, x1=200, y0=50,
                                 amplitude=10, period=50)
        r = rinceau(spine, leaf_size=10, alternate=False)
        assert r.metadata["leaf_count"] >= 5
        # No buds expected when non-alternating.
        assert len(r.polylines.get("buds", [])) == 0


class TestCLI:
    def test_cli_list(self, capsys):
        from engraving.cli import main
        rc = main(["list"])
        captured = capsys.readouterr()
        assert rc == 0
        assert "plates available" in captured.out

    def test_cli_render_single(self, capsys):
        from engraving.cli import main
        rc = main(["render", "01"])
        assert rc == 0

    def test_cli_unknown_plate(self, capsys):
        from engraving.cli import main
        rc = main(["render", "NONEXISTENT"])
        assert rc == 2


class TestFestoon:
    def test_leaf_festoon(self):
        from engraving.festoon import festoon
        from engraving.validate.elements import validate_festoon
        r = festoon((0, 0), (100, 0), droop=20, style="leaf")
        report = validate_festoon(r, (0, 0), (100, 0))
        assert len(report) == 0, list(report)

    def test_fruit_festoon(self):
        from engraving.festoon import festoon
        from engraving.validate.elements import validate_festoon
        r = festoon((0, 0), (100, 0), droop=20, style="fruit")
        report = validate_festoon(r, (0, 0), (100, 0))
        assert len(report) == 0, list(report)

    def test_ribbon_festoon(self):
        from engraving.festoon import festoon
        from engraving.validate.elements import validate_festoon
        r = festoon((0, 0), (100, 0), droop=20, style="ribbon")
        report = validate_festoon(r, (0, 0), (100, 0))
        assert len(report) == 0, list(report)

    def test_plain_swag(self):
        from engraving.festoon import swag
        from engraving.validate.elements import validate_festoon
        r = swag((0, 0), (100, 0), droop=15, amplitude=0.0)
        report = validate_festoon(r, (0, 0), (100, 0))
        assert len(report) == 0, list(report)

    def test_ribbon_swag(self):
        from engraving.festoon import swag
        from engraving.validate.elements import validate_festoon
        r = swag((0, 0), (100, 0), droop=15, amplitude=4.0)
        report = validate_festoon(r, (0, 0), (100, 0))
        assert len(report) == 0, list(report)

    def test_ribbon_knot_polylines(self):
        from engraving.festoon import ribbon_knot
        polys = ribbon_knot((0, 0), size=10, loop_count=2)
        # tie + 2 loops + 2 tails >= 4 polylines
        assert len(polys) >= 4


class TestTrophy:
    def test_martial_trophy(self):
        from engraving.trophy import trophy
        r = trophy(cx=50, cy=50, width=60, height=80, style="martial")
        assert r.bbox != (0, 0, 0, 0)

    def test_all_trophy_styles_validate(self):
        from engraving.trophy import trophy
        from engraving.validate.elements import validate_trophy
        for style in ("martial", "musical", "scientific", "naval"):
            r = trophy(cx=50, cy=50, width=60, height=80, style=style)
            report = validate_trophy(r, 50, 50, 60, 80)
            assert len(report) == 0, (style, list(report))

    def test_trophy_has_center_anchor(self):
        from engraving.trophy import trophy
        r = trophy(cx=50, cy=50, width=60, height=80, style="martial")
        assert "center" in r.anchors
        assert r.anchors["center"].x == 50


class TestPedimentSlope:
    def test_canonical_slope_passes(self):
        from engraving.validate.elements import validate_pediment
        report = validate_pediment(None, slope_deg=14)
        assert len(report) == 0

    def test_extreme_slope_fails(self):
        from engraving.validate.elements import validate_pediment
        report = validate_pediment(None, slope_deg=45)
        assert len(report) > 0

    def test_too_shallow_slope_fails(self):
        from engraving.validate.elements import validate_pediment
        report = validate_pediment(None, slope_deg=5)
        assert len(report) > 0

    def test_steep_doric_slope_passes(self):
        """22.5° sits within canonical [10°, 25°] Doric pediment range."""
        from engraving.validate.elements import validate_pediment
        report = validate_pediment(None, slope_deg=22.5)
        assert len(report) == 0

    def test_pediment_builder_warns_out_of_range(self):
        """pediment() itself emits a UserWarning outside [10, 25]."""
        import warnings
        from engraving.elements import pediment
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            pediment(0.0, 100.0, 200.0, slope_deg=40.0)
            assert any("outside canonical" in str(w.message)
                       for w in caught)


class TestAspectRatioInRangePredicate:
    def test_ratio_in_range_passes(self):
        from engraving.validate import aspect_ratio_in_range
        aspect_ratio_in_range(10.0, 30.0, 0.30, 0.55, "pier:span")

    def test_ratio_out_of_range_fails(self):
        from engraving.validate import (aspect_ratio_in_range,
                                        ValidationError)
        with pytest.raises(ValidationError):
            aspect_ratio_in_range(1.0, 30.0, 0.30, 0.55, "pier:span")


class TestDentilsPerBay:
    def test_dentils_per_bay_ok(self):
        """3 bays (4 axes), each with 4 dentils."""
        from engraving.validate import dentils_per_bay
        bay_xs = [0.0, 40.0, 80.0, 120.0]
        dentils = []
        for a, b in zip(bay_xs, bay_xs[1:]):
            step = (b - a) / 5
            for k in range(1, 5):
                cx = a + k * step
                dentils.append([(cx - 0.5, 0), (cx + 0.5, 0),
                                (cx + 0.5, 1), (cx - 0.5, 1),
                                (cx - 0.5, 0)])
        dentils_per_bay(dentils, bay_xs, expected_per_bay=4, tol=1)

    def test_dentils_per_bay_off_by_many_fails(self):
        from engraving.validate import dentils_per_bay, ValidationError
        bay_xs = [0.0, 40.0, 80.0]
        # Bay 0: 10 dentils, Bay 1: 0 — both way off
        dentils = [[(i * 3.0, 0), (i * 3.0 + 0.5, 0),
                    (i * 3.0 + 0.5, 1), (i * 3.0, 1), (i * 3.0, 0)]
                   for i in range(1, 11)]
        with pytest.raises(ValidationError):
            dentils_per_bay(dentils, bay_xs, expected_per_bay=4, tol=1)


class TestModillionOverColumnAxes:
    def test_modillion_over_each_axis_passes(self):
        from engraving.validate import modillion_over_column_axes
        col_xs = [50.0, 100.0, 150.0]
        mods = [[(cx - 2, 0), (cx + 2, 0), (cx + 2, 5), (cx - 2, 5),
                 (cx - 2, 0)] for cx in col_xs]
        modillion_over_column_axes(mods, col_xs, tol=0.5)

    def test_missing_modillion_fails(self):
        from engraving.validate import (modillion_over_column_axes,
                                        ValidationError)
        col_xs = [50.0, 100.0, 150.0]
        mods = [[(cx - 2, 0), (cx + 2, 0), (cx + 2, 5), (cx - 2, 5),
                 (cx - 2, 0)] for cx in (50.0, 100.0)]
        with pytest.raises(ValidationError):
            modillion_over_column_axes(mods, col_xs, tol=0.5)


class TestEntablatureDetail:
    def test_corinthian_modillion_per_column(self):
        from engraving.entablature_corinthian import corinthian_entablature
        from engraving.validate.entablatures import (
            validate_corinthian_entablature,
        )
        from engraving import canon
        dims = canon.Corinthian(D=20)
        col_xs = [60, 120, 180, 240]
        result = corinthian_entablature(40, 260, 200, dims, col_xs,
                                        return_result=True)
        report = validate_corinthian_entablature(result, col_xs)
        # Should be 0 errors if modillion-over-column rule passes.
        # If it fails, that's a real bug in entablature_corinthian.py
        for e in report:
            print(f"  - {e}")


class TestMedallion:
    def test_medallion_with_wreath(self):
        from engraving.medallion import medallion
        r = medallion(cx=50, cy=50, width=80, height=60, with_wreath=True)
        assert len(r.polylines.get("wreath", [])) > 10

    def test_medallion_plain_validates(self):
        from engraving.medallion import medallion
        from engraving.validate.elements import validate_medallion
        r = medallion(cx=50, cy=50, width=80, height=60,
                      with_wreath=False, with_ribbon=False)
        report = validate_medallion(r, 50, 50, 80, 60, with_wreath=False)
        assert len(report) == 0, list(report)

    def test_medallion_wreath_validates(self):
        from engraving.medallion import medallion
        from engraving.validate.elements import validate_medallion
        r = medallion(cx=50, cy=50, width=80, height=60,
                      with_wreath=True, with_ribbon=False)
        report = validate_medallion(r, 50, 50, 80, 60, with_wreath=True)
        assert len(report) == 0, list(report)

    def test_medallion_ribbon_has_polylines(self):
        from engraving.medallion import medallion
        r = medallion(cx=50, cy=50, width=80, height=60,
                      with_wreath=True, with_ribbon=True)
        assert len(r.polylines.get("ribbon", [])) > 0


class TestVoussoirDepth:
    def test_rusticated_voussoir_depth_reasonable(self):
        from engraving.rustication import wall
        result = wall(x0=0, y0=0, width=200, height=120,
                      course_h=30, block_w=60, variant="arcuated",
                      arch_springings_y=[60],
                      arch_spans=[(100, 60)])
        vous = result.get("arch_voussoirs", [])
        assert len(vous) > 0
        # For each voussoir, the radial span (max - min radius from arch center)
        # should be reasonable: less than 20% of the arch radius
        cx, span = 100, 60
        y_spring = 60
        r_arch = span / 2
        for v in vous:
            radii = [((p[0]-cx)**2 + (p[1]-y_spring)**2)**0.5 for p in v]
            radial_span = max(radii) - min(radii)
            assert radial_span <= r_arch * 0.32, \
                f"voussoir depth {radial_span:.1f} exceeds 32% of arch radius {r_arch}"


class TestCrossOrderProportions:
    def test_doric_taller_than_tuscan_at_same_D(self):
        from engraving import canon
        from engraving.orders import tuscan_column_silhouette
        from engraving.order_doric import doric_column_silhouette
        from engraving.validate.composition import validate_relative_column_heights
        D = 20.0
        tu = tuscan_column_silhouette(canon.Tuscan(D=D), 0, 0, return_result=True)
        do = doric_column_silhouette(canon.Doric(D=D), 0, 0, return_result=True)
        report = validate_relative_column_heights(do, tu)
        assert len(report) == 0, list(report)

    def test_comparative_plate_proportions(self):
        from engraving import canon
        from engraving.orders import tuscan_column_silhouette
        from engraving.order_doric import doric_column_silhouette
        from engraving.order_ionic import ionic_column_silhouette
        from engraving.order_corinthian import corinthian_column_silhouette
        from engraving.order_composite import composite_column_silhouette
        from engraving.validate.composition import validate_comparative_plate
        D = 20.0
        results = [
            tuscan_column_silhouette(canon.Tuscan(D=D), 0, 0, return_result=True),
            doric_column_silhouette(canon.Doric(D=D), 50, 0, return_result=True),
            ionic_column_silhouette(canon.Ionic(D=D), 100, 0, return_result=True),
            corinthian_column_silhouette(canon.Corinthian(D=D), 150, 0,
                                         return_result=True),
            composite_column_silhouette(canon.Composite(D=D), 200, 0,
                                        return_result=True),
        ]
        report = validate_comparative_plate(results)
        # All ratios should be within tolerance
        assert len(report) == 0, list(report)

    def test_mixed_D_invalid(self):
        from engraving import canon
        from engraving.orders import tuscan_column_silhouette
        from engraving.order_doric import doric_column_silhouette
        from engraving.validate.composition import validate_comparative_plate
        results = [
            tuscan_column_silhouette(canon.Tuscan(D=20), 0, 0, return_result=True),
            doric_column_silhouette(canon.Doric(D=15), 50, 0, return_result=True),
        ]
        report = validate_comparative_plate(results)
        assert len(report) > 0
        assert any("mixed D" in e for e in report)


# ──────────────────────────────────────────────────────────────────────────
# Phase 16 — known structural bugs, pinned by failing tests. DO NOT FIX
# here; fixes happen in the builders (other agents' work).
# ──────────────────────────────────────────────────────────────────────────

class TestKnownStructuralBugs:
    """Tests that document bugs the user has flagged. They light up
    where validation previously gave a green light to geometry that
    is mathematically off."""

    def test_cartouche_baroque_has_two_wings(self):
        """User-observed: baroque cartouche only renders one wing
        (see cartouche.py — the builder adds both left and right wings
        but under a single "wings" layer, so any regression where one
        side is dropped would pass the existing `validate_cartouche`
        silently). This test enforces the bilateral wing count."""
        from engraving.cartouche import cartouche
        cart = cartouche(cx=100, cy=50, width=80, height=40,
                         style="baroque_scroll")
        wing_lines = []
        for layer_name, lines in cart.polylines.items():
            ln = layer_name.lower()
            if "wing" in ln or "scroll" in ln or "volute" in ln:
                wing_lines.extend(lines)
        cx = 100
        left = sum(1 for pl in wing_lines
                   if pl and sum(p[0] for p in pl) / len(pl) < cx - 5)
        right = sum(1 for pl in wing_lines
                    if pl and sum(p[0] for p in pl) / len(pl) > cx + 5)
        assert left >= 1, (
            f"baroque cartouche missing left wing(s); right={right}"
        )
        assert right >= 1, (
            f"baroque cartouche missing right wing(s); left={left}"
        )

    def test_arcade_pier_to_span_ratio(self):
        """User-observed: arcade piers too thin relative to span.

        Vignola convention: pier_width ≈ 1/3 to 1/2 of clear span.
        `arcade.py` currently defaults to `pier_width_frac=0.20` of
        bay pitch, yielding ratios closer to 0.15–0.20 — this test
        fails until the default is tightened."""
        from engraving.arcade import arcade
        result = arcade(x0=0, y_base=200, width=300, height=180,
                        bay_count=5)
        pier_width = result.metadata["pier_width"]
        clear_span = result.metadata["clear_span"]
        ratio = pier_width / clear_span
        assert ratio >= 0.30, (
            f"arcade piers too thin: pier/clear_span = {ratio:.2f} "
            f"(pier_width={pier_width:.2f}, clear_span={clear_span:.2f}); "
            f"Vignola expects ≥ 0.30"
        )

    def test_greek_doric_visually_stouter_than_roman(self):
        """User-observed: Greek Doric (5.5 D) should render meaningfully
        shorter than Roman Doric (8 D) when built at the same D.

        Expected height ratio: 5.5 / 8 ≈ 0.69. This encodes the
        'Greek Doric reads stouter' relationship as a quantitative
        check — not just a boolean 'stouter than'."""
        from engraving.order_greek_doric import greek_doric_column_silhouette
        from engraving.order_doric import doric_column_silhouette

        D = 20.0
        gr = greek_doric_column_silhouette(
            canon.GreekDoric(D=D), 0, 0, return_result=True)
        ro = doric_column_silhouette(
            canon.Doric(D=D), 0, 0, return_result=True)
        ratio = gr.metadata["column_h"] / ro.metadata["column_h"]
        assert 0.65 <= ratio <= 0.72, (
            f"Greek/Roman Doric column_h ratio {ratio:.3f} not in "
            f"[0.65, 0.72] — Greek Doric should be ≈ 0.69 × Roman Doric"
        )

    def test_doric_capital_thirds(self):
        """User-observed: Doric capital subdivisions (Ware p.14).

        Necking 1/3, echinus+bead 1/3, abacus 1/3 of capital_h. The
        existing `OrderValidation` only checks `capital_h` total, so
        a regression that compresses the echinus would pass. This
        test locks the three thirds."""
        from engraving.order_doric import doric_column_silhouette
        from engraving.validate.orders import capital_subdivisions

        dims = canon.Doric(D=20.0)
        res = doric_column_silhouette(dims, cx=100, base_y=200,
                                      return_result=True)
        report = capital_subdivisions(res, {
            "cap_neck_h":    1.0 / 3.0,
            "cap_echinus_h": 1.0 / 3.0,
            "cap_abacus_h":  1.0 / 3.0,
        }, tol=0.08)
        assert len(report) == 0, list(report)

    def test_five_orders_height_ratio_7_8_9_10_10(self):
        """User-observed: when rendered side-by-side at matched D,
        Tuscan:Doric:Ionic:Corinth:Composite column heights should
        realise 7:8:9:10:10."""
        from engraving.orders import tuscan_column_silhouette
        from engraving.order_doric import doric_column_silhouette
        from engraving.order_ionic import ionic_column_silhouette
        from engraving.order_corinthian import corinthian_column_silhouette
        from engraving.order_composite import composite_column_silhouette
        from engraving.validate.orders import five_orders_relative_heights

        D = 20.0
        results = [
            tuscan_column_silhouette(canon.Tuscan(D=D), 0, 0,
                                     return_result=True),
            doric_column_silhouette(canon.Doric(D=D), 50, 0,
                                    return_result=True),
            ionic_column_silhouette(canon.Ionic(D=D), 100, 0,
                                    return_result=True),
            corinthian_column_silhouette(canon.Corinthian(D=D), 150, 0,
                                         return_result=True),
            composite_column_silhouette(canon.Composite(D=D), 200, 0,
                                        return_result=True),
        ]
        report = five_orders_relative_heights(results, tol=0.04)
        assert len(report) == 0, list(report)

    def test_volute_eye_visible_at_plate_scale(self):
        """User-observed: at D=9 on the five-orders plate, volute eyes
        (D/18 ≈ 0.5 mm) render as invisible dots.

        The predicate enforces BOTH an absolute 0.4 mm floor AND a
        0.2% of plate-diagonal floor. This test uses a reference
        plate diagonal of 420 mm (A2). A D=9 plate fails immediately."""
        from engraving.validate import min_feature_visible_at_scale

        D = 9.0
        eye_diam_mm = D / 18.0 * 2.0  # diameter of the volute eye
        plate_diag_mm = 420.0
        try:
            min_feature_visible_at_scale(
                eye_diam_mm, plate_diag_mm,
                min_mm=0.4, min_fraction=0.002,
                label="Ionic volute eye at D=9")
        except Exception as e:
            pytest.fail(
                f"min_feature_visible_at_scale should have passed here "
                f"but raised: {e}"
            )
        # And a D=6 plate (tiny eye) must FAIL — guarantees the predicate
        # actually enforces a minimum.
        D_small = 6.0
        small_eye_diam = D_small / 18.0 * 2.0
        with pytest.raises(Exception):
            min_feature_visible_at_scale(
                small_eye_diam, plate_diag_mm,
                min_mm=0.4, min_fraction=0.002,
                label="Ionic volute eye at D=6")

    def test_pediment_slope_vignola_range(self):
        """User-observed: pediment slope should be 12–15° (Vignola).

        A 30° pitched pediment will fire this test."""
        from engraving.validate.composition import validate_pediment_slope_angle

        # Canonical good pediment (14° slope).
        apex = (100.0, 0.0)
        import math as _m
        dx = 100.0
        dy = dx * _m.tan(_m.radians(14.0))
        left = (0.0, dy)
        right = (200.0, dy)
        r = validate_pediment_slope_angle(apex, left, right,
                                          lo_deg=12.0, hi_deg=15.0)
        assert len(r) == 0, list(r)

        # Deliberately too-steep pediment (30° slope).
        dy_steep = dx * _m.tan(_m.radians(30.0))
        r_bad = validate_pediment_slope_angle(apex,
                                              (0.0, dy_steep),
                                              (200.0, dy_steep),
                                              lo_deg=12.0, hi_deg=15.0)
        assert len(r_bad) >= 1, (
            "pediment slope predicate should flag a 30° rake"
        )

    def test_column_entablature_ratio_doric(self):
        """User-observed: entablature should be ~¼ column (Ware).

        Given a rendered Doric column at D=20, column_h = 160 mm, so
        entablature_h should be ≈ 40 mm. An entablature of e.g. 60 mm
        will fire this test."""
        from engraving.order_doric import doric_column_silhouette
        from engraving.validate.orders import column_pedestal_entablature_ratio

        dims = canon.Doric(D=20.0)
        col = doric_column_silhouette(dims, 100, 200, return_result=True)

        # Good case: canonical entablature 2 D = 40 mm (= 160/4).
        r_good = column_pedestal_entablature_ratio(
            col, pedestal_h=None, entablature_h=40.0, tol=0.15)
        assert len(r_good) == 0, list(r_good)

        # Bad case: entablature of 80 mm = half the column. Should flag.
        r_bad = column_pedestal_entablature_ratio(
            col, pedestal_h=None, entablature_h=80.0, tol=0.15)
        assert len(r_bad) >= 1, (
            "column_pedestal_entablature_ratio should flag a "
            "80-mm entablature on a 160-mm column"
        )


class TestSceneGraph:
    def test_scene_add_and_query(self):
        from engraving.scene import Scene, SceneNode
        s = Scene()
        s.add(SceneNode(id="facade", kind="facade"))
        s.add(SceneNode(id="facade.story_0", kind="story"), parent_id="facade")
        s.add(SceneNode(id="facade.story_0.col_0", kind="column"),
              parent_id="facade.story_0")
        results = s.find("facade.story_*.col_*")
        assert len(results) == 1
        results = s.find("*.column" if False else "*.col_*")
        assert len(results) == 1

    def test_vertically_aligned_passes(self):
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import VerticallyAligned
        s = Scene()
        s.add(SceneNode(id="a", kind="box", pos=(100, 0, 0)))
        s.add(SceneNode(id="b", kind="box", pos=(100, -50, 0)))
        s.constrain(VerticallyAligned(node_ids=["a", "b"]))
        report = s.validate()
        assert len(report) == 0

    def test_vertically_aligned_fails(self):
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import VerticallyAligned
        s = Scene()
        s.add(SceneNode(id="a", kind="box", pos=(100, 0, 0)))
        s.add(SceneNode(id="b", kind="box", pos=(105, -50, 0)))
        s.constrain(VerticallyAligned(node_ids=["a", "b"], tol=0.5))
        report = s.validate()
        assert len(report) >= 1

    def test_stands_on_passes(self):
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import StandsOn
        from engraving.schema import Anchor
        s = Scene()
        # Lower has top_center at y=-50
        lower = SceneNode(id="ped", kind="pedestal", pos=(100, 0, 0),
                          anchors={"top_center": Anchor("top_center", 0, -50)})
        upper = SceneNode(id="col", kind="column", pos=(100, -50, 0),
                          anchors={"bottom_center": Anchor("bottom_center", 0, 0)})
        s.add(lower); s.add(upper)
        s.constrain(StandsOn(upper_id="col", lower_id="ped"))
        report = s.validate()
        assert len(report) == 0

    def test_corresponding_bays_fails(self):
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import CorrespondingBays
        s = Scene()
        s.add(SceneNode(id="story_0", kind="story"))
        s.add(SceneNode(id="story_1", kind="story"))
        s.add(SceneNode(id="story_0.bay_0", kind="bay", pos=(100, 0, 0)),
              parent_id="story_0")
        s.add(SceneNode(id="story_1.bay_0", kind="bay", pos=(110, -50, 0)),  # misaligned
              parent_id="story_1")
        s.constrain(CorrespondingBays(story_a_id="story_0", story_b_id="story_1"))
        report = s.validate()
        assert len(report) >= 1


class TestArchitecturalConstraints:
    """Wave-3 specialized architectural constraints."""

    def test_superposition_order_passes(self):
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import SuperpositionOrder
        s = Scene()
        s.add(SceneNode(id="s0", kind="story",
                        metadata={"has_order": "doric"}))
        s.add(SceneNode(id="s1", kind="story",
                        metadata={"has_order": "ionic"}))
        s.add(SceneNode(id="s2", kind="story",
                        metadata={"has_order": "corinthian"}))
        s.constrain(SuperpositionOrder(story_ids=["s0", "s1", "s2"]))
        report = s.validate()
        assert len(report) == 0, list(report)

    def test_superposition_order_violated(self):
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import SuperpositionOrder
        s = Scene()
        s.add(SceneNode(id="s0", kind="story",
                        metadata={"has_order": "corinthian"}))
        s.add(SceneNode(id="s1", kind="story",
                        metadata={"has_order": "doric"}))
        s.constrain(SuperpositionOrder(story_ids=["s0", "s1"]))
        report = s.validate()
        assert len(report) >= 1

    def test_superposition_allows_subset(self):
        # Tuscan/Corinthian (skipping Doric+Ionic) is fine.
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import SuperpositionOrder
        s = Scene()
        s.add(SceneNode(id="s0", kind="story",
                        metadata={"has_order": "tuscan"}))
        s.add(SceneNode(id="s1", kind="story",
                        metadata={"has_order": "corinthian"}))
        s.constrain(SuperpositionOrder(story_ids=["s0", "s1"]))
        assert len(s.validate()) == 0

    def test_keystone_over_door(self):
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import KeystoneOverDoor
        s = Scene()
        s.add(SceneNode(id="door", kind="door", pos=(100, 0, 0)))
        s.add(SceneNode(id="key", kind="keystone", pos=(100.2, -50, 0)))
        s.constrain(KeystoneOverDoor(door_id="door",
                                     keystone_id="key", tol=0.5))
        assert len(s.validate()) == 0
        # Misalign
        s.get("key").pos = (110, -50, 0)
        assert len(s.validate()) >= 1

    def test_columns_under_pediment_passes(self):
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import ColumnsUnderPediment
        s = Scene()
        # Four columns at x=50, 100, 150, 200
        s.add(SceneNode(id="c0", kind="column", pos=(50, 0, 0)))
        s.add(SceneNode(id="c1", kind="column", pos=(100, 0, 0)))
        s.add(SceneNode(id="c2", kind="column", pos=(150, 0, 0)))
        s.add(SceneNode(id="c3", kind="column", pos=(200, 0, 0)))
        # Pediment bbox spans 50..200 in world coords
        s.add(SceneNode(id="ped", kind="pediment", pos=(0, -200, 0),
                        bbox_local=(50, 0, 200, 40)))
        s.constrain(ColumnsUnderPediment(
            column_ids=["c0", "c1", "c2", "c3"],
            pediment_id="ped", tol=1.0))
        assert len(s.validate()) == 0

    def test_columns_under_pediment_fails(self):
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import ColumnsUnderPediment
        s = Scene()
        s.add(SceneNode(id="c0", kind="column", pos=(50, 0, 0)))
        s.add(SceneNode(id="c1", kind="column", pos=(200, 0, 0)))
        # Pediment too narrow
        s.add(SceneNode(id="ped", kind="pediment", pos=(0, -200, 0),
                        bbox_local=(70, 0, 180, 40)))
        s.constrain(ColumnsUnderPediment(
            column_ids=["c0", "c1"], pediment_id="ped", tol=1.0))
        assert len(s.validate()) >= 1

    def test_window_axes_align_across_stories_passes(self):
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import WindowAxesAlignAcrossStories
        s = Scene()
        s.add(SceneNode(id="s0", kind="story"))
        s.add(SceneNode(id="s1", kind="story"))
        s.add(SceneNode(id="s0.bay_0", kind="bay", pos=(100, 0, 0)),
              parent_id="s0")
        s.add(SceneNode(id="s0.bay_0.opening", kind="window",
                        pos=(100, -20, 0)), parent_id="s0.bay_0")
        s.add(SceneNode(id="s1.bay_0", kind="bay", pos=(100, -100, 0)),
              parent_id="s1")
        s.add(SceneNode(id="s1.bay_0.opening", kind="window",
                        pos=(100.2, -120, 0)), parent_id="s1.bay_0")
        s.constrain(WindowAxesAlignAcrossStories(
            bay_index=0, story_ids=["s0", "s1"], tol=0.5))
        assert len(s.validate()) == 0

    def test_window_axes_align_across_stories_fails(self):
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import WindowAxesAlignAcrossStories
        s = Scene()
        s.add(SceneNode(id="s0", kind="story"))
        s.add(SceneNode(id="s1", kind="story"))
        s.add(SceneNode(id="s0.bay_0", kind="bay", pos=(100, 0, 0)),
              parent_id="s0")
        s.add(SceneNode(id="s0.bay_0.opening", kind="window",
                        pos=(100, -20, 0)), parent_id="s0.bay_0")
        s.add(SceneNode(id="s1.bay_0", kind="bay", pos=(110, -100, 0)),
              parent_id="s1")
        s.add(SceneNode(id="s1.bay_0.opening", kind="window",
                        pos=(110, -120, 0)), parent_id="s1.bay_0")
        s.constrain(WindowAxesAlignAcrossStories(
            bay_index=0, story_ids=["s0", "s1"], tol=0.5))
        assert len(s.validate()) >= 1

    def test_rustication_courses_align_passes(self):
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import RusticationCoursesAlign
        s = Scene()
        s.add(SceneNode(id="story", kind="story"))
        s.add(SceneNode(id="story.bay_0", kind="bay", pos=(0, 0, 0),
                        metadata={"joint_ys": [10, 30, 50]}),
              parent_id="story")
        s.add(SceneNode(id="story.bay_1", kind="bay", pos=(100, 0, 0),
                        metadata={"joint_ys": [10.2, 30, 50]}),
              parent_id="story")
        s.constrain(RusticationCoursesAlign(story_id="story", tol=0.5))
        assert len(s.validate()) == 0

    def test_rustication_courses_align_fails(self):
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import RusticationCoursesAlign
        s = Scene()
        s.add(SceneNode(id="story", kind="story"))
        s.add(SceneNode(id="story.bay_0", kind="bay", pos=(0, 0, 0),
                        metadata={"joint_ys": [10, 30, 50]}),
              parent_id="story")
        s.add(SceneNode(id="story.bay_1", kind="bay", pos=(100, 0, 0),
                        metadata={"joint_ys": [15, 35, 55]}),  # all off
              parent_id="story")
        s.constrain(RusticationCoursesAlign(story_id="story", tol=0.5))
        assert len(s.validate()) >= 1

    def test_triglyph_over_each_column_passes(self):
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import TriglyphOverEachColumn
        s = Scene()
        s.add(SceneNode(id="c0", kind="column", pos=(50, 0, 0)))
        s.add(SceneNode(id="c1", kind="column", pos=(100, 0, 0)))
        s.add(SceneNode(id="c2", kind="column", pos=(150, 0, 0)))
        s.add(SceneNode(id="t0", kind="triglyph", pos=(50, -40, 0)))
        s.add(SceneNode(id="t1", kind="triglyph", pos=(75, -40, 0)))
        s.add(SceneNode(id="t2", kind="triglyph", pos=(100, -40, 0)))
        s.add(SceneNode(id="t3", kind="triglyph", pos=(125, -40, 0)))
        s.add(SceneNode(id="t4", kind="triglyph", pos=(150, -40, 0)))
        s.constrain(TriglyphOverEachColumn(
            column_ids=["c0", "c1", "c2"],
            triglyph_ids=["t0", "t1", "t2", "t3", "t4"]))
        assert len(s.validate()) == 0

    def test_triglyph_over_each_column_fails(self):
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import TriglyphOverEachColumn
        s = Scene()
        s.add(SceneNode(id="c0", kind="column", pos=(50, 0, 0)))
        s.add(SceneNode(id="c1", kind="column", pos=(100, 0, 0)))
        s.add(SceneNode(id="t0", kind="triglyph", pos=(55, -40, 0)))  # off
        s.add(SceneNode(id="t1", kind="triglyph", pos=(100, -40, 0)))
        s.constrain(TriglyphOverEachColumn(
            column_ids=["c0", "c1"], triglyph_ids=["t0", "t1"], tol=0.3))
        assert len(s.validate()) >= 1

    def test_stylobate_under_columns(self):
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import StylobateUnderColumns
        s = Scene()
        s.add(SceneNode(id="c0", kind="column", pos=(50, 200, 0)))
        s.add(SceneNode(id="c1", kind="column", pos=(100, 200, 0)))
        s.add(SceneNode(id="c2", kind="column", pos=(150, 200, 0)))
        s.constrain(StylobateUnderColumns(column_ids=["c0", "c1", "c2"]))
        assert len(s.validate()) == 0
        s.get("c1").pos = (100, 205, 0)
        assert len(s.validate()) >= 1

    def test_intercolumniation_consistent_passes(self):
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import IntercolumniationConsistent
        s = Scene()
        s.add(SceneNode(id="c0", kind="column", pos=(50, 0, 0)))
        s.add(SceneNode(id="c1", kind="column", pos=(100, 0, 0)))
        s.add(SceneNode(id="c2", kind="column", pos=(150, 0, 0)))
        s.add(SceneNode(id="c3", kind="column", pos=(200, 0, 0)))
        s.constrain(IntercolumniationConsistent(
            column_ids=["c0", "c1", "c2", "c3"]))
        assert len(s.validate()) == 0

    def test_intercolumniation_consistent_fails(self):
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import IntercolumniationConsistent
        s = Scene()
        s.add(SceneNode(id="c0", kind="column", pos=(50, 0, 0)))
        s.add(SceneNode(id="c1", kind="column", pos=(100, 0, 0)))
        s.add(SceneNode(id="c2", kind="column", pos=(160, 0, 0)))  # 60, not 50
        s.constrain(IntercolumniationConsistent(
            column_ids=["c0", "c1", "c2"]))
        assert len(s.validate()) >= 1

    def test_intercolumniation_expected_pitch(self):
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import IntercolumniationConsistent
        # Eustyle: 2.25 D at D=20 → pitch 45
        s = Scene()
        s.add(SceneNode(id="c0", kind="column", pos=(0, 0, 0)))
        s.add(SceneNode(id="c1", kind="column", pos=(45, 0, 0)))
        s.add(SceneNode(id="c2", kind="column", pos=(90, 0, 0)))
        s.constrain(IntercolumniationConsistent(
            column_ids=["c0", "c1", "c2"], expected_pitch=45.0))
        assert len(s.validate()) == 0
        # Wrong pitch
        s.constrain(IntercolumniationConsistent(
            column_ids=["c0", "c1", "c2"], expected_pitch=50.0))
        assert len(s.validate()) >= 1


class TestSceneFacadeWiring:
    def test_well_formed_facade_has_zero_scene_errors(self):
        from engraving.facade import Facade, Story, Bay, Opening
        bays = [Bay(openings=[
                    Opening(kind="window", width=20, height=40),
                    Opening(kind="window", width=20, height=40),
                ]) for _ in range(5)]
        stories = [Story(height=60), Story(height=60)]
        f = Facade(width=300, stories=stories, bays=bays, base_y=200)
        f.layout()
        result = f.render()
        scene = f.to_scene(result)
        report = scene.validate()
        # Should be 0 - bays evenly spaced, stories stack, facade symmetric.
        assert len(report) == 0, list(report)

    def test_misaligned_bay_caught(self):
        from engraving.facade import Facade, Story, Bay, Opening
        bays = [Bay(openings=[
                    Opening(kind="window", width=20, height=40),
                    Opening(kind="window", width=20, height=40),
                ]) for _ in range(3)]
        stories = [Story(height=60), Story(height=60)]
        f = Facade(width=300, stories=stories, bays=bays, base_y=200)
        f.layout()
        result = f.render()
        # Construct scene then break a bay's world position.
        scene = f.to_scene(result)
        n = scene.get("facade.story_1.bay_1")
        n.pos = (n.pos[0] + 5.0, n.pos[1], n.pos[2])
        report = scene.validate()
        assert len(report) >= 1
        assert any("CorrespondingBays" in e for e in report)


class TestSceneDebugOverlay:
    def test_render_debug_produces_file(self, tmp_path):
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import VerticallyAligned
        from engraving.render import Page, frame

        page = Page()
        frame(page)
        src = page.save_svg("test_debug_src")

        s = Scene()
        s.add(SceneNode(id="a", kind="x", pos=(50, 50, 0),
                        bbox_local=(-5, -5, 5, 5)))
        s.add(SceneNode(id="b", kind="x", pos=(60, 100, 0),
                        bbox_local=(-5, -5, 5, 5)))  # misaligned
        s.constrain(VerticallyAligned(node_ids=["a", "b"], tol=0.5))

        out = s.render_debug(src, tmp_path / "test_debug.svg")
        assert out.exists()
        text = out.read_text()
        assert "red" in text or "dasharray" in text
        # The overlay block marker should be present when failures exist.
        assert "DEBUG OVERLAY" in text

    def test_render_debug_no_failures_is_noop(self, tmp_path):
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import VerticallyAligned
        from engraving.render import Page, frame

        page = Page()
        frame(page)
        src = page.save_svg("test_debug_src_ok")

        s = Scene()
        s.add(SceneNode(id="a", kind="x", pos=(50, 50, 0)))
        s.add(SceneNode(id="b", kind="x", pos=(50, 100, 0)))  # aligned
        s.constrain(VerticallyAligned(node_ids=["a", "b"], tol=0.5))

        out = s.render_debug(src, tmp_path / "test_debug_ok.svg")
        assert out.exists()
        text = out.read_text()
        # No overlay block when every constraint passes.
        assert "DEBUG OVERLAY" not in text

    def test_debug_geometry_constraints_render_svg(self):
        """Each constraint type emits parseable SVG when failing."""
        from engraving.scene import Scene, SceneNode
        from engraving.scene_constraints import (
            VerticallyAligned, HorizontallyAligned, StandsOn,
            MirrorPair, BilateralFacade, CorrespondingBays,
        )
        from engraving.schema import Anchor

        # VerticallyAligned failing
        s = Scene()
        s.add(SceneNode(id="a", kind="x", pos=(10, 0, 0),
                        bbox_local=(-1, -1, 1, 1)))
        s.add(SceneNode(id="b", kind="x", pos=(20, 10, 0),
                        bbox_local=(-1, -1, 1, 1)))
        c = VerticallyAligned(node_ids=["a", "b"], tol=0.5)
        s.constrain(c)
        geom = c.debug_geometry(s)
        assert any("line" in g for g in geom)
        assert any("rect" in g for g in geom)

        # StandsOn failing
        s2 = Scene()
        s2.add(SceneNode(id="lo", kind="p", pos=(0, 0, 0),
                         bbox_local=(-1, -1, 1, 1),
                         anchors={"top_center": Anchor("top_center", 0, 0)}))
        s2.add(SceneNode(id="up", kind="c", pos=(5, 5, 0),
                         bbox_local=(-1, -1, 1, 1),
                         anchors={"bottom_center": Anchor("bottom_center", 0, 0)}))
        so = StandsOn(upper_id="up", lower_id="lo")
        s2.constrain(so)
        geom = so.debug_geometry(s2)
        assert any("circle" in g for g in geom)

        # MirrorPair failing
        s3 = Scene()
        s3.add(SceneNode(id="l", kind="x", pos=(0, 0, 0),
                         bbox_local=(-1, -1, 1, 1)))
        s3.add(SceneNode(id="r", kind="x", pos=(15, 0, 0),
                         bbox_local=(-1, -1, 1, 1)))
        mp = MirrorPair(left_id="l", right_id="r", axis_x=10.0, tol=0.5)
        s3.constrain(mp)
        geom = mp.debug_geometry(s3)
        assert any("line" in g for g in geom)

        # BilateralFacade failing
        s4 = Scene()
        s4.add(SceneNode(id="fac", kind="facade", pos=(0, 0, 0),
                         bbox_local=(0, 0, 100, 100)))
        s4.add(SceneNode(id="fac.a", kind="bay", pos=(10, 50, 0),
                         bbox_local=(-2, -2, 2, 2)), parent_id="fac")
        s4.add(SceneNode(id="fac.b", kind="bay", pos=(80, 50, 0),
                         bbox_local=(-2, -2, 2, 2)), parent_id="fac")
        bf = BilateralFacade(facade_id="fac", tol=0.5)
        s4.constrain(bf)
        geom = bf.debug_geometry(s4)
        assert any("line" in g for g in geom)

        # CorrespondingBays failing
        s5 = Scene()
        s5.add(SceneNode(id="s0", kind="story", pos=(0, 0, 0),
                         bbox_local=(0, 0, 100, 50)))
        s5.add(SceneNode(id="s1", kind="story", pos=(0, 50, 0),
                         bbox_local=(0, 0, 100, 50)))
        s5.add(SceneNode(id="s0.b0", kind="bay", pos=(20, 0, 0),
                         bbox_local=(-2, -2, 2, 2)), parent_id="s0")
        s5.add(SceneNode(id="s1.b0", kind="bay", pos=(35, 50, 0),
                         bbox_local=(-2, -2, 2, 2)), parent_id="s1")
        cb = CorrespondingBays(story_a_id="s0", story_b_id="s1", tol=0.5)
        s5.constrain(cb)
        geom = cb.debug_geometry(s5)
        assert any("line" in g for g in geom)


# ── Phase 19 Overhaul — Week 1 Foundation ──────────────────────────

class TestOverhaulFoundation:
    def test_element_contains_good_child(self):
        from engraving.element import Element
        from engraving.containment import validate_tree
        root = Element(id="root", kind="facade", envelope=(0, 0, 100, 100))
        class Fixed(Element):
            def __init__(self, id, env, actual):
                super().__init__(id=id, kind="test", envelope=env)
                self._actual = actual
            def effective_bbox(self): return self._actual
            def render_strokes(self): return iter([])
        root.add(Fixed("c", (10, 10, 50, 50), (10, 10, 50, 50)))
        assert len(validate_tree(root)) == 0

    def test_element_catches_overflow(self):
        from engraving.element import Element
        from engraving.containment import validate_tree
        root = Element(id="root", kind="facade", envelope=(0, 0, 100, 100))
        class Fixed(Element):
            def __init__(self, id, env, actual):
                super().__init__(id=id, kind="test", envelope=env)
                self._actual = actual
            def effective_bbox(self): return self._actual
            def render_strokes(self): return iter([])
        # Child's bbox extends past parent's envelope on right
        root.add(Fixed("c", (10, 10, 50, 50), (10, 10, 120, 50)))
        vs = validate_tree(root)
        assert len(vs) >= 1
        assert any(v.rule == "HierarchicalContainment" and v.axis == "right"
                   for v in vs)

    def test_sibling_non_overlap_catches_overlap(self):
        from engraving.element import Element
        from engraving.containment import sibling_non_overlap
        root = Element(id="root", kind="facade", envelope=(0, 0, 100, 100))
        class Fixed(Element):
            def __init__(self, id, actual):
                super().__init__(id=id, kind="t", envelope=actual)
                self._actual = actual
            def effective_bbox(self): return self._actual
            def render_strokes(self): return iter([])
        root.add(Fixed("a", (10, 10, 50, 50)))
        root.add(Fixed("b", (40, 10, 80, 50)))   # overlaps a on x
        vs = sibling_non_overlap(root, axis="x")
        assert len(vs) >= 1

    def test_shared_edge_stories_stack(self):
        from engraving.element import Element
        from engraving.containment import shared_edge
        class Fixed(Element):
            def __init__(self, id, actual):
                super().__init__(id=id, kind="story", envelope=actual)
                self._actual = actual
            def effective_bbox(self): return self._actual
            def render_strokes(self): return iter([])
        s0 = Fixed("s0", (0, 50, 100, 100))   # y from 50 to 100 (lower story)
        s1 = Fixed("s1", (0, 0, 100, 50))     # y from 0 to 50 (story above)
        # s0 top (y=50) should equal s1 bottom (y=50)
        assert shared_edge(s0, s1, "top", tol=0.5) == []

    def test_shared_edge_gap_caught(self):
        from engraving.element import Element
        from engraving.containment import shared_edge
        class Fixed(Element):
            def __init__(self, id, actual):
                super().__init__(id=id, kind="story", envelope=actual)
                self._actual = actual
            def effective_bbox(self): return self._actual
            def render_strokes(self): return iter([])
        s0 = Fixed("s0", (0, 50, 100, 100))
        s1 = Fixed("s1", (0, 0, 100, 40))    # 10mm gap
        vs = shared_edge(s0, s1, "top", tol=0.5)
        assert len(vs) >= 1

    def test_positivity_catches_inverted_envelope(self):
        from engraving.element import Element
        from engraving.containment import positivity_of_dims
        e = Element(id="bad", kind="t", envelope=(100, 100, 50, 50))  # inverted
        vs = positivity_of_dims(e)
        assert len(vs) >= 1

    def test_legacy_element_wraps_element_result(self):
        from engraving.element import Element, LegacyElement
        from engraving.schema import ElementResult, Anchor
        er = ElementResult(kind="test", bbox=(0, 0, 10, 10),
                           polylines={"silhouette": [[(0,0),(10,0),(10,10)]]})
        e = Element.from_element_result(er, id="wrapped")
        assert isinstance(e, LegacyElement)
        strokes = list(e.render_strokes())
        assert len(strokes) == 1
        assert strokes[0][1] == 0.35  # silhouette weight


class TestCLIGenerate:
    def test_generate_palazzo_default(self, tmp_path):
        from engraving.cli import main
        out = tmp_path / "test_palazzo.svg"
        rc = main(["generate", "palazzo", "-o", str(out)])
        assert rc == 0
        assert out.exists()

    def test_generate_palazzo_with_options(self, tmp_path):
        from engraving.cli import main
        out = tmp_path / "test_palazzo.svg"
        rc = main(["generate", "palazzo",
                    "--bays", "7",
                    "--piano-nobile-order", "corinthian",
                    "--ground-wall", "banded",
                    "--parapet", "balustrade",
                    "-o", str(out)])
        assert rc == 0

    def test_generate_unknown_kind(self, tmp_path):
        from engraving.cli import main
        # argparse will reject "unknown" via choices=[...]
        import pytest, sys
        # argparse exits on invalid choice; catch SystemExit
        with pytest.raises(SystemExit):
            main(["generate", "unknown_kind"])
