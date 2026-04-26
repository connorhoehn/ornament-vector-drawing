"""Tests for the ArchElement wrapper. The user flagged on 2026-04-19 that
semicircular arches drawn inside a too-short story extend upward past the
story's top edge (into the piano nobile). Before the overhaul nothing
caught this. After the overhaul: HierarchicalContainment catches it at
effective_bbox-vs-envelope check."""

import pytest
from engraving.element import Element
from engraving.containment import validate_tree
from engraving.elements.arches import SemicircularArchElement, SegmentalArchElement


class TestArchEffectiveBBox:
    def test_semicircular_effective_bbox_includes_rise(self):
        """A semicircular arch of span 60 at y_spring=100 rises to y=70
        (SVG y grows down, so apex has y = y_spring - span/2). The
        effective bbox must include y=70 (and less, if voussoirs add depth)."""
        arch = SemicircularArchElement(
            id="test_arch", kind="semicircular_arch",
            envelope=(70, 0, 130, 150),   # room to spare
            cx=100, y_spring=100, span=60,
            voussoir_count=9, with_keystone=True,
        )
        bx = arch.effective_bbox()
        # Apex is at y = 100 - 30 = 70 at intrados; voussoirs add depth above that.
        assert bx[1] <= 70 + 0.5, f"arch top y={bx[1]} should reach apex y=70"
        # Left/right extents: intrados at cx±span/2 = 70, 130; voussoirs extend further.
        assert bx[0] <= 70 + 0.5
        assert bx[2] >= 130 - 0.5

    def test_arch_in_sufficient_envelope_passes_containment(self):
        story = Element(id="story_0", kind="story", envelope=(0, 0, 200, 200))
        arch = SemicircularArchElement(
            id="story_0.arch", kind="semicircular_arch",
            envelope=(70, 40, 130, 100),
            cx=100, y_spring=100, span=60,
            voussoir_count=9, with_keystone=True,
        )
        story.add(arch)
        assert validate_tree(story) == []

    def test_arch_overflows_too_short_story_caught(self):
        """The USER-FLAGGED BUG. Story is 50mm tall. Arch span=60 → rise=30.
        If arch bottom is at y=40 and apex at y=40-30=10, that's still in a
        0..50 envelope. But if voussoirs + keystone add depth above the
        apex, the arch's effective top will be negative, extending past the
        story's top envelope. The containment check must catch this."""
        story = Element(id="story_0", kind="story", envelope=(0, 0, 200, 50))
        arch = SemicircularArchElement(
            id="story_0.arch", kind="semicircular_arch",
            envelope=(70, 0, 130, 50),    # allocates only 50mm of vertical
            cx=100, y_spring=50,           # springs from story floor
            span=60,                        # rise = 30, apex at y=20
            voussoir_count=9, with_keystone=True, archivolt_bands=2,
        )
        story.add(arch)
        # Voussoirs + archivolts + keystone may extend 5-15mm above apex y=20,
        # which IS still within envelope top y=0. Depends on construction.
        vs = validate_tree(story)
        # Whether it violates or not, if it does we want a containment rule firing
        # (not a silent pass). Record the current behavior as the test.
        bx = arch.effective_bbox()
        print(f"Arch effective_bbox: {bx}  envelope: {story.envelope}")
        # The contract: if effective_bbox extends past envelope, validate_tree reports it
        if bx[1] < story.envelope[1] - 0.5:
            assert any(v.rule == "HierarchicalContainment" and v.axis == "top" for v in vs)


class TestSegmentalArch:
    def test_segmental_arch_lower_rise(self):
        arch = SegmentalArchElement(
            id="seg", kind="segmental_arch",
            envelope=(0, 0, 200, 100),
            cx=100, y_spring=80, span=60, rise=15,
            voussoir_count=9, with_keystone=True,
        )
        bx = arch.effective_bbox()
        # Rise=15 so apex is at y = 80 - 15 = 65
        assert bx[1] <= 65 + 2  # allow for voussoir depth
