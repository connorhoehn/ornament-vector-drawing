"""Regression tests for engraving.elements builders.

Focused on shape invariants that are easy to assert and hard to eyeball —
e.g. the pedestal should be a classical plinth + dado + cornice block, not
a stepped pyramid, and its outline should be a single closed polyline.

Run with: .venv/bin/python -m pytest tests/test_elements.py -v
"""
from __future__ import annotations

import pytest

from engraving import canon, elements


# --------------------------------------------------------------------------
# Pedestal silhouette
# --------------------------------------------------------------------------

class TestPedestalOutline:
    """The pedestal outline must read as a classical three-band block.

    Classical Roman pedestals (Vignola / Ware) have the plinth (base) and
    cornice (cap) projecting equally beyond the narrower dado (body). Earlier
    versions of ``elements.pedestal`` had the cornice narrower than the
    plinth, which read as a stepped-pyramid stylobate. These tests pin the
    invariants so that regression never returns silently.
    """

    @pytest.fixture
    def ped(self):
        dims = canon.Tuscan(D=10.0)
        return elements.pedestal(cx=0.0, ground_y=0.0, dims=dims)

    def test_returns_outline_key(self, ped):
        assert "outline" in ped
        assert "top_y" in ped

    def test_outline_is_closed(self, ped):
        outline = ped["outline"]
        assert outline[0] == outline[-1], (
            "Pedestal outline must start and end at the same point so it "
            "renders as a single closed silhouette."
        )

    def test_outline_is_single_polyline(self, ped):
        # ``outline`` is expected to be a flat list of (x, y) tuples, not a
        # list-of-polylines. If the builder is ever refactored to return
        # nested rectangles, this test will catch it.
        outline = ped["outline"]
        assert all(len(pt) == 2 for pt in outline), (
            "Outline must be a flat list of (x, y) points."
        )

    def test_plinth_wider_than_dado(self, ped):
        assert ped["half_plinth"] > ped["half_dado"], (
            "Plinth must project beyond dado."
        )

    def test_cornice_wider_than_dado(self, ped):
        assert ped["half_cornice"] > ped["half_dado"], (
            "Cornice must project beyond dado (not stepped pyramid)."
        )

    def test_plinth_and_cornice_project_equally(self, ped):
        # Symmetric base-and-cap profile — not a pyramid tapering upward.
        assert abs(ped["half_plinth"] - ped["half_cornice"]) < 1e-6, (
            "Classical pedestal has plinth and cornice at equal width; "
            "otherwise silhouette reads as a stepped pyramid."
        )

    def test_outline_has_12_segments(self, ped):
        # 12 unique vertices + 1 closing vertex = 13 points.
        outline = ped["outline"]
        assert len(outline) == 13, (
            "Canonical three-band pedestal silhouette has 12 corners."
        )


# --------------------------------------------------------------------------
# Greek Doric stoutness
# --------------------------------------------------------------------------

class TestGreekDoricStoutness:
    """Greek Doric must render visibly stouter than Roman Doric.

    Canon (Ware pp. 33-36): Greek Doric column_D = 5.5 (Parthenon); Roman
    Doric column_D = 8 (Vignola). At the SAME D, the Greek column must be
    ~5.5/8 = 0.688 the height of the Roman column. If the silhouette builder
    ever inflates Greek column_h or loses the no-base convention, both the
    ratio and the base height assertions below will catch it.
    """

    def test_greek_doric_shorter_than_roman_at_same_D(self):
        from engraving import canon
        from engraving.order_greek_doric import greek_doric_column_silhouette
        from engraving.order_doric import doric_column_silhouette
        D = 20.0
        gr = greek_doric_column_silhouette(
            canon.GreekDoric(D=D), 0, 0, return_result=True)
        ro = doric_column_silhouette(
            canon.Doric(D=D), 0, 0, return_result=True)
        ratio = gr.metadata["column_h"] / ro.metadata["column_h"]
        assert 0.65 <= ratio <= 0.72, (
            f"Greek/Roman Doric height ratio {ratio:.3f} not "
            f"~0.69 (5.5/8)"
        )

    def test_greek_doric_no_base(self):
        from engraving import canon
        from engraving.order_greek_doric import greek_doric_column_silhouette
        gr = greek_doric_column_silhouette(
            canon.GreekDoric(D=20), 0, 0, return_result=True)
        # Greek Doric has NO base — base_h should be 0.
        assert gr.metadata["base_h"] == 0.0, (
            f"Greek Doric should have no base; "
            f"got base_h={gr.metadata['base_h']}"
        )

    def test_greek_doric_echinus_grows_upward(self):
        """Regression: the echinus arc's `cy` must be `y_echinus_top`, not
        `y_annulets_top`. If it regresses, the echinus sweeps downward into
        the shaft and the silhouette's right edge goes backward in y after
        the annulets — the column visibly breaks."""
        from engraving import canon
        from engraving.order_greek_doric import greek_doric_column_silhouette
        gr = greek_doric_column_silhouette(
            canon.GreekDoric(D=20), 0, 0, return_result=True)
        R = gr.polylines["silhouette"][0]
        # R is built bottom-to-top in SVG coords (y DECREASES going up). No
        # two consecutive points may have y INCREASING — that would mean the
        # silhouette doubled back downward.
        for i in range(1, len(R)):
            assert R[i][1] <= R[i - 1][1] + 1e-6, (
                f"Greek Doric silhouette reverses downward at point {i}: "
                f"{R[i - 1]} → {R[i]} — echinus arc likely growing the "
                f"wrong direction."
            )
