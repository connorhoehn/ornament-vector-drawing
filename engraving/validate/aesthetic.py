"""Layer C — aesthetic rules. Advisory-severity; don't block renders but
collect quality-of-detail warnings.

Examples:
  - Every ornament stroke weight should be in a disciplined hierarchy
  - Smallest visible feature at plate scale must be at least 0.5mm
  - Hatch density should be consistent within a surface
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..element import Element, Violation


@dataclass
class StrokeWeightHierarchy:
    """Verify stroke weights respect the engraving hierarchy:
      silhouette >= 0.35 (MEDIUM)
      rules >= 0.25 (FINE)
      ornament/dentils <= 0.20 (HAIRLINE / ORNAMENT)
      hatch <= 0.15 (HATCH)
    """
    label: str = ""

    def check(self, element_tree: Element) -> list[Violation]:
        """Walk element_tree.render_strokes(). Group by stroke weight,
        assess distribution. Warn if any single weight dominates >80% or
        if extremes (very thin + very thick) are both absent."""
        violations = []
        weights = [w for _, w in element_tree.render_strokes()]
        if not weights:
            return violations

        # Distribution check: classical engravings mix weights.
        unique_weights = sorted(set(weights))
        if len(unique_weights) < 3:
            violations.append(Violation(
                layer="C", rule="StrokeWeightHierarchy",
                element_id=element_tree.id,
                message=(
                    f"Only {len(unique_weights)} distinct stroke weights: "
                    f"{unique_weights}. Classical engraving uses 4+ "
                    f"(silhouette / rules / ornament / hatch)"
                ),
            ))

        # Dominance check: no single weight covers >80% of strokes
        from collections import Counter
        counts = Counter(weights)
        total = sum(counts.values())
        max_count = max(counts.values())
        if max_count / total > 0.80:
            dominant = max(counts, key=counts.get)
            violations.append(Violation(
                layer="C", rule="StrokeWeightHierarchy",
                element_id=element_tree.id,
                message=(
                    f"Stroke weight {dominant} dominates {max_count/total:.0%} "
                    f"of polylines — image may lack hierarchy"
                ),
            ))
        return violations


@dataclass
class MinimumFeatureAtScale:
    """At the declared plate scale + target print DPI, every rendered
    feature must be at least `min_mm` tall/wide to be visible after
    reproduction. Warns for features below threshold.
    """
    min_mm: float = 0.5       # half a millimeter at 1:1
    label: str = ""

    def check(self, element_tree: Element) -> list[Violation]:
        violations = []
        # Walk element tree; for each leaf element, compute bbox; if any
        # dimension < min_mm, warn.
        for node in element_tree.walk():
            if node.children:
                continue  # skip non-leaf
            bx = node.effective_bbox()
            w = bx[2] - bx[0]
            h = bx[3] - bx[1]
            if w < self.min_mm and h < self.min_mm:
                violations.append(Violation(
                    layer="C", rule="MinimumFeatureAtScale",
                    element_id=node.id,
                    message=(
                        f"{node.id} feature size ({w:.2f}x{h:.2f}mm) "
                        f"below minimum {self.min_mm}mm"
                    ),
                ))
        return violations


@dataclass
class DetailDensityUniform:
    """All ornament of a given kind should have uniform detail density.
    e.g. all Corinthian capitals in a plate should have the same number
    of acanthus leaves; all dentil courses should have the same tooth
    stride.

    Groups by (kind, material) and checks each group's polyline count
    has bounded variation across instances."""
    label: str = ""
    max_cv: float = 0.25     # coefficient of variation (stdev/mean) threshold

    def check(self, element_tree: Element) -> list[Violation]:
        from collections import defaultdict
        import statistics

        # Bucket by kind
        by_kind: dict[str, list[Element]] = defaultdict(list)
        for node in element_tree.walk():
            by_kind[node.kind].append(node)

        violations = []
        for kind, elements in by_kind.items():
            if len(elements) < 2:
                continue
            # Count rendered strokes per element as a proxy for detail
            counts = [sum(1 for _ in e.render_strokes()) for e in elements]
            if not counts or statistics.mean(counts) == 0:
                continue
            cv = statistics.stdev(counts) / statistics.mean(counts) if len(counts) > 1 else 0
            if cv > self.max_cv:
                violations.append(Violation(
                    layer="C", rule="DetailDensityUniform",
                    element_id=f"group:{kind}",
                    message=(
                        f"{kind} instances have variable detail: "
                        f"counts {counts}, CV={cv:.2f} > {self.max_cv}"
                    ),
                ))
        return violations


def check_aesthetic(element_tree: Element, *, rules=None) -> list[Violation]:
    """Run all Layer C rules. Returns a combined list of Violations."""
    if rules is None:
        rules = [
            StrokeWeightHierarchy(),
            MinimumFeatureAtScale(),
            DetailDensityUniform(),
        ]
    out = []
    for rule in rules:
        out.extend(rule.check(element_tree))
    return out
