"""Declarative plan dataclasses.

These are DATA. No rendering, no computation beyond trivial validation.
The ``FacadePlan.solve()`` method (in ``solver.py``) turns these into an
Element tree with positions computed.

Users describe a facade in structural terms:
    - canvas: the plate region we have to fill
    - stories (bottom-to-top): each with height_ratio + wall variant + optional order
    - bays (left-to-right): each with openings (one per story) + optional pilasters
    - parapet: optional top treatment (balustrade or attic)

The planner (solver.py) takes these and produces positioned elements.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..schema import BBox


class PlanInfeasible(Exception):
    """Raised by the solver when a plan cannot be satisfied.

    Fields:
      reason: short machine-readable code ("insufficient_height",
              "arch_overflow", "hierarchy_violated", ...)
      element_id: which element caused the infeasibility (if applicable)
      details: free-form explanation
      suggested_fix: what the caller might change
    """
    def __init__(self, reason: str, details: str, element_id: str = "",
                 suggested_fix: str = ""):
        super().__init__(f"[{reason}] {details}"
                         + (f" (in {element_id})" if element_id else "")
                         + (f" — try: {suggested_fix}" if suggested_fix else ""))
        self.reason = reason
        self.details = details
        self.element_id = element_id
        self.suggested_fix = suggested_fix


# ── Opening ────────────────────────────────────────────────────────────

OpeningKind = Literal[
    "arch_window", "arch_door", "window", "door", "niche", "blank",
]

HoodKind = Literal["none", "cornice", "triangular", "segmental"]


@dataclass
class OpeningPlan:
    """One opening in one bay on one story.

    Sizes are FRACTIONS of their container (bay_pitch for width, story_h
    for height). The solver multiplies by actual mm.
    """
    kind: OpeningKind = "window"
    width_frac: float = 0.45        # fraction of bay pitch
    height_frac: float = 0.6        # fraction of story height
    hood: HoodKind = "none"
    has_keystone: bool = False
    # For arched openings: rise is derived from span/2 (semicircular)
    # unless overridden:
    segmental_rise_frac: float | None = None  # fraction of span

    def __post_init__(self):
        if not (0 < self.width_frac <= 1.0):
            raise ValueError(
                f"OpeningPlan.width_frac must be in (0, 1], got {self.width_frac}"
            )
        if not (0 < self.height_frac <= 1.0):
            raise ValueError(
                f"OpeningPlan.height_frac must be in (0, 1], got {self.height_frac}"
            )
        if self.hood not in ("none", "cornice", "triangular", "segmental"):
            raise ValueError(f"OpeningPlan.hood invalid: {self.hood}")

    @property
    def is_arched(self) -> bool:
        return self.kind in ("arch_window", "arch_door")


# ── Pilaster ───────────────────────────────────────────────────────────

OrderName = Literal[
    "tuscan", "doric", "ionic", "corinthian", "composite",
    "greek_doric", "greek_ionic",
]


@dataclass
class PilasterPlan:
    """Optional pilaster on a bay (flanking the opening)."""
    order: OrderName = "tuscan"
    width_frac: float = 0.10       # fraction of bay_pitch

    def __post_init__(self):
        if self.order not in ("tuscan", "doric", "ionic", "corinthian",
                               "composite", "greek_doric", "greek_ionic"):
            raise ValueError(f"PilasterPlan.order invalid: {self.order}")


# ── Bay ────────────────────────────────────────────────────────────────

@dataclass
class BayPlan:
    """A vertical column of openings. ``openings`` is ordered BOTTOM-to-TOP
    (same order as facade.stories). One opening per story."""
    openings: list[OpeningPlan] = field(default_factory=list)
    pilasters: PilasterPlan | None = None   # flanking pilasters (applies to all stories that have an order)
    # width_weight: for non-uniform bay widths. Default 1.0 (equal);
    # set higher for e.g. a wider central door bay.
    width_weight: float = 1.0
    # label for debugging
    label: str = ""

    def __post_init__(self):
        if self.width_weight <= 0:
            raise ValueError(
                f"BayPlan.width_weight must be > 0, got {self.width_weight}"
            )


# ── Story ──────────────────────────────────────────────────────────────

WallVariant = Literal[
    "smooth", "banded", "arcuated", "chamfered", "rock_faced", "vermiculated",
    "bossed_smooth",
]


@dataclass
class StoryPlan:
    """One horizontal story. ``height_ratio`` is relative to other stories;
    solver normalizes against the canvas height."""
    height_ratio: float = 1.0
    wall: WallVariant = "smooth"
    has_order: OrderName | None = None   # if set, this story is "ordered" (has columns/pilasters)
    min_height_mm: float = 0.0           # hard floor; planner raises PlanInfeasible if budget insufficient
    string_course_height: float = 1.8    # thin molding at story top
    label: str = ""

    def __post_init__(self):
        if self.height_ratio <= 0:
            raise ValueError(
                f"StoryPlan.height_ratio must be > 0, got {self.height_ratio}"
            )
        if self.min_height_mm < 0:
            raise ValueError(
                f"StoryPlan.min_height_mm must be >= 0, got {self.min_height_mm}"
            )
        if self.wall not in ("smooth", "banded", "arcuated", "chamfered",
                              "rock_faced", "vermiculated", "bossed_smooth"):
            raise ValueError(f"StoryPlan.wall invalid: {self.wall}")
        if self.has_order is not None and self.has_order not in (
                "tuscan", "doric", "ionic", "corinthian", "composite",
                "greek_doric", "greek_ionic"):
            raise ValueError(f"StoryPlan.has_order invalid: {self.has_order}")


# ── Parapet ────────────────────────────────────────────────────────────

@dataclass
class ParapetPlan:
    """Top treatment of the facade."""
    kind: Literal["balustrade", "attic", "cornice", "none"] = "balustrade"
    height_ratio: float = 0.25    # relative to the unit of story-ratio math
    baluster_variant: Literal["tuscan", "renaissance"] = "tuscan"

    def __post_init__(self):
        if self.kind not in ("balustrade", "attic", "cornice", "none"):
            raise ValueError(f"ParapetPlan.kind invalid: {self.kind}")


# ── Plinth / stylobate ─────────────────────────────────────────────────

@dataclass
class PlinthPlan:
    """Base course at the very bottom of the facade — a stylobate /
    water-table / plinth course. Not a story (no bays, no openings): a
    continuous horizontal band that visually grounds the building.

    ``height_mm`` is absolute (typical: 6–12 mm at 1:200 plate scale).
    The plinth consumes its height from the canvas BEFORE stories are
    allocated, so stories still get their declared ratios of the
    remaining budget.
    """
    kind: Literal["smooth", "banded", "chamfered"] = "smooth"
    height_mm: float = 8.0
    projection_mm: float = 0.0    # how far it steps out past the wall line
                                   # (0 means flush). Positive projects outward.

    def __post_init__(self):
        if self.height_mm <= 0:
            raise ValueError(
                f"PlinthPlan.height_mm must be > 0, got {self.height_mm}"
            )
        if self.kind not in ("smooth", "banded", "chamfered"):
            raise ValueError(f"PlinthPlan.kind invalid: {self.kind}")


# ── Top-level facade ────────────────────────────────────────────────────

@dataclass
class FacadePlan:
    """The top-level declarative plan for a facade.

    Canvas is the BBox inside which the facade must fit. Stories are
    bottom-to-top; bays are left-to-right. Each bay's ``openings`` list
    must have exactly ``len(stories)`` entries.
    """
    canvas: BBox = (0.0, 0.0, 100.0, 100.0)  # (x_min, y_min, x_max, y_max)
    stories: list[StoryPlan] = field(default_factory=list)  # bottom-to-top
    bays: list[BayPlan] = field(default_factory=list)
    parapet: ParapetPlan | None = None
    plinth: "PlinthPlan | None" = None   # optional base course below ground story
    # Phase 22 Part 3: optional corner quoins (rusticated pier stacks at
    # each outer facade edge). Off by default; plates opt in.
    with_quoins: bool = False
    quoin_width_mm: float = 8.0
    # Phase 28: auto-emit ShadowElement children for every shadow-producing
    # element (windows, arches, rusticated walls). Disable for construction
    # drawings where the extra hatch reads as visual noise.
    shadows_enabled: bool = True

    def __post_init__(self):
        # Canvas validity
        x0, y0, x1, y1 = self.canvas
        if x1 <= x0 or y1 <= y0:
            raise ValueError(
                f"FacadePlan.canvas inverted or zero-size: {self.canvas}"
            )
        # Stories
        if not self.stories:
            raise ValueError("FacadePlan needs at least one story")
        # Bays — each must have one opening per story
        for i, bay in enumerate(self.bays):
            if len(bay.openings) != len(self.stories):
                raise ValueError(
                    f"bay[{i}] has {len(bay.openings)} openings; "
                    f"expected {len(self.stories)} (one per story)"
                )

    # --- derived properties ---

    @property
    def canvas_width(self) -> float:
        return self.canvas[2] - self.canvas[0]

    @property
    def canvas_height(self) -> float:
        return self.canvas[3] - self.canvas[1]

    @property
    def canvas_left(self) -> float:
        return self.canvas[0]

    @property
    def canvas_top(self) -> float:
        return self.canvas[1]

    @property
    def canvas_right(self) -> float:
        return self.canvas[2]

    @property
    def canvas_bottom(self) -> float:
        return self.canvas[3]

    @property
    def n_stories(self) -> int:
        return len(self.stories)

    @property
    def n_bays(self) -> int:
        return len(self.bays)

    # --- high-level entry point ---

    def solve(self):
        """Turn this plan into an Element tree. Raises PlanInfeasible on
        violations. The solver lives in ``solver.py`` to keep this file
        pure data."""
        from .solver import solve as _solve
        return _solve(self)

    def explain(self) -> str:
        """Return a comprehensive human-readable summary of the plan.

        Covers canvas dimensions, all stories (with estimated mm heights),
        all bays (with opening kinds), and attempts a solve to report
        feasibility + an element count."""
        w = self.canvas_width
        h = self.canvas_height
        lines: list[str] = []
        lines.append(f"┌ FacadePlan")
        lines.append(f"│  canvas: {w:.1f} × {h:.1f} mm")
        lines.append(f"│  {self.n_stories} stories, {self.n_bays} bays")

        # Total story ratio (plus parapet if present & non-none) → mm per unit
        total_r = sum(s.height_ratio for s in self.stories)
        if self.parapet and self.parapet.kind != "none":
            total_r += self.parapet.height_ratio
        unit = h / total_r if total_r > 0 else 0

        lines.append(f"│")
        lines.append(f"├─ Stories (bottom-to-top):")
        for i, s in enumerate(self.stories):
            estimated_h = s.height_ratio * unit
            order_str = f" order={s.has_order}" if s.has_order else ""
            min_str = f" min={s.min_height_mm:.1f}" if s.min_height_mm else ""
            label = s.label or "—"
            lines.append(
                f"│   [{i}] {label:12s}  h≈{estimated_h:.1f}mm "
                f"wall={s.wall}{order_str}{min_str}"
            )
        if self.parapet and self.parapet.kind != "none":
            par_h = self.parapet.height_ratio * unit
            lines.append(
                f"│   [parapet] {self.parapet.kind}  h≈{par_h:.1f}mm"
            )

        lines.append(f"│")
        lines.append(f"├─ Bays (left-to-right):")
        for i, b in enumerate(self.bays):
            kinds = ",".join(op.kind for op in b.openings)
            label = b.label or "—"
            lines.append(
                f"│   [{i}] {label:10s}  w={b.width_weight}x  "
                f"openings: {kinds}"
            )

        # Try to solve and report feasibility
        lines.append(f"│")
        lines.append(f"├─ Solve:")
        try:
            from .solver import solve
            facade = solve(self)
            n_elems = sum(1 for _ in facade.descendants())
            n_strokes = sum(1 for _ in facade.render_strokes())
            lines.append(
                f"│   ✓ feasible — {n_elems} elements, {n_strokes} strokes"
            )
        except Exception as e:
            lines.append(f"│   ✗ infeasible: {e}")

        lines.append(f"└")
        return "\n".join(lines)


# ── Phase 29: Pediment + Portico ──────────────────────────────────────

@dataclass
class PedimentPlan:
    """Triangular gable crowning a portico.

    ``slope_deg`` is the angle of the raking cornice above horizontal.
    Classical Greek/Roman pediments run 12°-22.5°; Vignola canon is
    closer to 15°. Values outside that band break the proportions and
    are rejected here (ValueError at construction) so solver code can
    assume a sane angle.

    ``fill`` controls the tympanum: False = open (outline only), True
    reserved for a future sculptural hatch fill. ``acroterion`` is a
    future hook for an apex ornament (not rendered in Phase 29).
    """
    slope_deg: float = 15.0
    fill: bool = False
    acroterion: bool = False

    def __post_init__(self):
        if not (12.0 <= self.slope_deg <= 22.5):
            raise ValueError(
                f"PedimentPlan.slope_deg must be in [12, 22.5] deg; got "
                f"{self.slope_deg}. Classical pediments are ~12-22.5°."
            )


@dataclass
class PorticoPlan:
    """Declarative plan for a free-standing classical portico.

    A portico is NOT a facade: there are no stories, no bays with
    openings, no parapet. It is a colonnade (N columns spaced by the
    intercolumniation) crowned by an entablature and optionally a
    pediment, optionally seated on a pedestal course, optionally on a
    plinth (stylobate).

    Vertical stack from bottom to top:
        plinth (optional) + pedestal (optional) + column (base + shaft +
        capital, per the chosen order) + entablature (per order) +
        pediment (optional)

    Fields:
      canvas               — BBox the portico must fit inside
      order                — one of the canonical orders
      column_count         — typically 4 (tetrastyle) or 6 (hexastyle)
      intercolumniation_modules — center-to-center spacing of columns,
                             in modules (M = D/2). Vignola's "eustyle"
                             is ~2.25 M; wider "diastyle" ~3 M. Tuscan
                             canon is 4 M.
      pedestal             — if True, columns sit on a pedestal course
                             of canonical height (order.pedestal_h).
      plinth               — optional PlinthPlan below the pedestal/
                             columns (stylobate course).
      pediment             — optional PedimentPlan gable.
    """
    canvas: BBox = (0.0, 0.0, 100.0, 100.0)
    order: OrderName = "tuscan"
    column_count: int = 4
    intercolumniation_modules: float = 4.0
    pedestal: bool = True
    plinth: "PlinthPlan | None" = None
    pediment: "PedimentPlan | None" = None

    def __post_init__(self):
        x0, y0, x1, y1 = self.canvas
        if x1 <= x0 or y1 <= y0:
            raise ValueError(
                f"PorticoPlan.canvas inverted or zero-size: {self.canvas}"
            )
        if self.order not in ("tuscan", "doric", "ionic", "corinthian",
                               "composite", "greek_doric", "greek_ionic"):
            raise ValueError(f"PorticoPlan.order invalid: {self.order}")
        if self.column_count < 2:
            raise ValueError(
                f"PorticoPlan.column_count must be >= 2, got {self.column_count}"
            )
        if self.intercolumniation_modules <= 0:
            raise ValueError(
                f"PorticoPlan.intercolumniation_modules must be > 0, got "
                f"{self.intercolumniation_modules}"
            )

    # --- derived properties ---

    @property
    def canvas_width(self) -> float:
        return self.canvas[2] - self.canvas[0]

    @property
    def canvas_height(self) -> float:
        return self.canvas[3] - self.canvas[1]

    @property
    def canvas_left(self) -> float:
        return self.canvas[0]

    @property
    def canvas_right(self) -> float:
        return self.canvas[2]

    @property
    def canvas_top(self) -> float:
        return self.canvas[1]

    @property
    def canvas_bottom(self) -> float:
        return self.canvas[3]

    # --- entry point ---

    def solve(self):
        """Turn this plan into an Element tree. Raises PlanInfeasible on
        infeasibility."""
        from .solver import solve_portico as _solve
        return _solve(self)


# ── Phase 30: Roof + Boathouse ────────────────────────────────────────

@dataclass
class RoofPlan:
    """Pitched gable roof, McKim / Shingle-Style boathouse grammar.

    Fields:
      slope_deg     — angle of the rake above horizontal. Boathouses run
                      15-30°; default 22° is a comfortable gable. Values
                      outside [5, 45]° are rejected so the solver can
                      assume a sane pitch.
      overhang_mm   — eave depth projecting past the wall line. Deep
                      eaves are a characteristic McKim detail.
      ridge_height_mm — optional cap. When set, the solver uses it as a
                      hard upper bound on the gable height (rather than
                      the geometric ``width/2 * tan(slope)``). Left at
                      ``None`` the geometry derives naturally from the
                      slope + span.
      has_shingle_hatch — whether to emit parallel shingle stripes across
                      the rake faces (adds engraving texture).
      gable_end     — True means a gable-end faces the viewer (triangular
                      silhouette, two rakes). False reserved for a hip
                      topology (not rendered in Phase 30 — the flag is
                      kept so the dataclass stays forward-compatible).
    """
    slope_deg: float = 22.0
    overhang_mm: float = 6.0
    ridge_height_mm: float | None = None
    has_shingle_hatch: bool = True
    gable_end: bool = True

    def __post_init__(self):
        if not (5.0 <= self.slope_deg <= 45.0):
            raise ValueError(
                f"RoofPlan.slope_deg must be in [5, 45] deg; got "
                f"{self.slope_deg}. Boathouse gables run 15-30°."
            )
        if self.overhang_mm < 0:
            raise ValueError(
                f"RoofPlan.overhang_mm must be >= 0, got {self.overhang_mm}"
            )
        if self.ridge_height_mm is not None and self.ridge_height_mm <= 0:
            raise ValueError(
                f"RoofPlan.ridge_height_mm must be > 0 or None, got "
                f"{self.ridge_height_mm}"
            )


BoatBayKind = Literal["arched", "trabeated"]


@dataclass
class BoathousePlan:
    """Declarative plan for a McKim-Mead-White style boathouse elevation.

    A boathouse is NOT a palazzo and NOT a portico: its ground floor is
    a run of tall boat bays (arched or trabeated) where crew shells
    launch, its upper story is a clerestory over living/locker space,
    and its crown is a steep gabled roof with deep eaves — no balustrade,
    no pediment.

    Vertical stack from bottom to top (SVG y-down):
        plinth (optional) + boat_bay_h + upper_story_h + gable_h = canvas_h
    where ``gable_h = colonnade_w / 2 * tan(slope)`` when the gable end
    faces the viewer.

    Fields:
      canvas                   — BBox the boathouse must fit inside
      bay_count                — number of boat bays across ground floor
                                 (typical: 3-5)
      bay_kind                 — ``"arched"`` (semicircular arches, the
                                 Newell reference) or ``"trabeated"``
                                 (post-and-lintel rectangular openings).
      has_upper_story          — toggle the clerestory. Default True.
      upper_story_window_count — number of clerestory windows
      roof                     — required RoofPlan (the gable)
      plinth                   — optional PlinthPlan (water table)
    """
    canvas: BBox = (0.0, 0.0, 100.0, 100.0)
    bay_count: int = 3
    bay_kind: BoatBayKind = "arched"
    has_upper_story: bool = True
    upper_story_window_count: int = 5
    roof: RoofPlan = field(default_factory=RoofPlan)
    plinth: "PlinthPlan | None" = None

    def __post_init__(self):
        x0, y0, x1, y1 = self.canvas
        if x1 <= x0 or y1 <= y0:
            raise ValueError(
                f"BoathousePlan.canvas inverted or zero-size: {self.canvas}"
            )
        if self.bay_count < 1:
            raise ValueError(
                f"BoathousePlan.bay_count must be >= 1, got {self.bay_count}"
            )
        if self.bay_kind not in ("arched", "trabeated"):
            raise ValueError(
                f"BoathousePlan.bay_kind invalid: {self.bay_kind!r} "
                f"(expected 'arched' or 'trabeated')"
            )
        if self.upper_story_window_count < 0:
            raise ValueError(
                f"BoathousePlan.upper_story_window_count must be >= 0, "
                f"got {self.upper_story_window_count}"
            )
        if self.roof is None:
            raise ValueError("BoathousePlan.roof is required (got None)")

    # --- derived properties ---

    @property
    def canvas_width(self) -> float:
        return self.canvas[2] - self.canvas[0]

    @property
    def canvas_height(self) -> float:
        return self.canvas[3] - self.canvas[1]

    @property
    def canvas_left(self) -> float:
        return self.canvas[0]

    @property
    def canvas_right(self) -> float:
        return self.canvas[2]

    @property
    def canvas_top(self) -> float:
        return self.canvas[1]

    @property
    def canvas_bottom(self) -> float:
        return self.canvas[3]

    # --- entry point ---

    def solve(self):
        """Turn this plan into an Element tree. Raises PlanInfeasible on
        infeasibility."""
        from .solver import solve_boathouse as _solve
        return _solve(self)
