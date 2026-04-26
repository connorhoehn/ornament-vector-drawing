"""Canonical proportions for the five classical orders, after Vignola via
Ware's *American Vignola* (1903).

Every dimension is a fraction of the **lower column diameter D = 2M** (where M
is the module). Storing fractions rather than pre-multiplied millimeters lets
us instantiate any order at any physical size just by setting D.

Sources cross-referenced:
  - Ware, *The American Vignola, Part I: The Five Orders* (1903), tables on
    pp. 10, 14, 18, 21, 24.
  - Vignola, *Regole delli Cinque Ordini* (1562) — the underlying canon.
  - Alvin Holm / ICAA, *Construction of the Ionic Volute* — volute ratios.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import ClassVar


# ─── Base class ────────────────────────────────────────────────────────────

@dataclass(frozen=True, kw_only=True)
class Order:
    """Base for a classical order. All *_frac fields are fractions of D."""
    name: str
    D: float  # lower column diameter in mm

    # Heights in diameters
    column_D: float       # column height / D (incl. base + cap)
    entablature_D: float  # entablature / D
    pedestal_D: float     # pedestal / D (incl. base + die + cap)

    # Column subdivisions (in D)
    base_D: float
    capital_D: float

    # Upper/lower diameters
    upper_diam_D: float = 5.0 / 6.0  # Tuscan/Doric default; Ionic 5/6; Corinth 5/6; Composite 5/6

    # Entablature subdivisions (fraction of entablature_D) — override as needed
    architrave_frac_of_D: float = 0.5
    frieze_frac_of_D: float = 0.5
    cornice_frac_of_D: float = 0.75

    # Pedestal subdivisions (fraction of pedestal_D). Defaults echo Vignola.
    plinth_frac: float = 0.22
    dado_frac: float = 0.62
    ped_cornice_frac: float = 0.16

    # --- Derived ---------------------------------------------------------
    @property
    def M(self) -> float: return self.D / 2
    @property
    def column_h(self) -> float: return self.column_D * self.D
    @property
    def entablature_h(self) -> float: return self.entablature_D * self.D
    @property
    def pedestal_h(self) -> float: return self.pedestal_D * self.D
    @property
    def base_h(self) -> float: return self.base_D * self.D
    @property
    def capital_h(self) -> float: return self.capital_D * self.D
    @property
    def shaft_h(self) -> float: return self.column_h - self.base_h - self.capital_h
    @property
    def lower_diam(self) -> float: return self.D
    @property
    def upper_diam(self) -> float: return self.upper_diam_D * self.D
    @property
    def architrave_h(self) -> float: return self.architrave_frac_of_D * self.D
    @property
    def frieze_h(self) -> float: return self.frieze_frac_of_D * self.D
    @property
    def cornice_h(self) -> float: return self.cornice_frac_of_D * self.D
    @property
    def plinth_h(self) -> float: return self.plinth_frac * self.pedestal_h
    @property
    def dado_h(self) -> float: return self.dado_frac * self.pedestal_h
    @property
    def cornice_ped_h(self) -> float: return self.ped_cornice_frac * self.pedestal_h


# ─── The five orders ──────────────────────────────────────────────────────
# Numbers straight from Ware's tables; don't "improve" them.

@dataclass(frozen=True, kw_only=True)
class Tuscan(Order):
    name: str = "Tuscan"
    column_D: float = 7.0
    entablature_D: float = 7.0 / 4.0     # 1¾D
    pedestal_D: float = 7.0 / 3.0        # ≈2⅓D; pedestals generally ⅓ column
    base_D: float = 0.5                  # ½D incl. cincture
    capital_D: float = 0.5
    architrave_frac_of_D: float = 0.5     # ½D
    frieze_frac_of_D: float = 0.5         # ½D
    cornice_frac_of_D: float = 0.75       # ¾D
    upper_diam_D: float = 5.0 / 6.0
    # Tuscan specifics
    abacus_width_D: ClassVar[float] = 7.0 / 6.0
    plinth_width_D: ClassVar[float] = 7.0 / 6.0  # plinth of column base
    taenia_D: ClassVar[float] = 1.0 / 22.0       # ~1/22 D
    astragal_D: ClassVar[float] = 1.0 / 18.0


@dataclass(frozen=True, kw_only=True)
class Doric(Order):
    name: str = "Doric"
    column_D: float = 8.0
    entablature_D: float = 2.0            # 2D
    pedestal_D: float = 8.0 / 3.0
    base_D: float = 0.5
    capital_D: float = 0.5
    architrave_frac_of_D: float = 0.5     # ½D
    frieze_frac_of_D: float = 0.75        # ¾D
    cornice_frac_of_D: float = 0.75       # ¾D
    upper_diam_D: float = 5.0 / 6.0
    # Doric specifics
    triglyph_width_D: ClassVar[float] = 0.5   # ½D
    metope_width_D: ClassVar[float] = 0.75    # ¾D
    corner_metope_D: ClassVar[float] = 1.0 / 6.0
    shank_width_D: ClassVar[float] = 1.0 / 12.0
    flute_count: ClassVar[int] = 20
    flute_arc_degrees: ClassVar[float] = 60.0
    gutta_count: ClassVar[int] = 6


@dataclass(frozen=True, kw_only=True)
class Ionic(Order):
    name: str = "Ionic"
    column_D: float = 9.0
    entablature_D: float = 9.0 / 4.0      # 2¼D  = 18/8
    pedestal_D: float = 3.0
    base_D: float = 0.5
    capital_D: float = 2.0 / 3.0          # ⅔D
    architrave_frac_of_D: float = 5.0 / 8.0   # ⅝D
    frieze_frac_of_D: float = 6.0 / 8.0       # ¾D = 6/8
    cornice_frac_of_D: float = 7.0 / 8.0      # ⅞D
    upper_diam_D: float = 5.0 / 6.0
    # Ionic specifics
    volute_height_D: ClassVar[float] = 4.0 / 9.0   # per Holm/ICAA diagram
    volute_eye_D: ClassVar[float] = 1.0 / 18.0
    volute_fillet_D: ClassVar[float] = 1.0 / 9.0
    scroll_width_D: ClassVar[float] = 9.0 / 6.0 - 1.0 / 6.0  # ~8/6 D, "width of Scrolls (minus)"
    flute_count: ClassVar[int] = 24
    # Dentils
    dentil_height_D: ClassVar[float] = 1.0 / 12.0
    dentil_width_D: ClassVar[float] = 1.0 / 18.0
    dentil_oc_D: ClassVar[float] = 1.0 / 6.0       # on-centers


@dataclass(frozen=True, kw_only=True)
class Corinthian(Order):
    name: str = "Corinthian"
    column_D: float = 10.0
    entablature_D: float = 10.0 / 4.0     # 2½D
    pedestal_D: float = 10.0 / 3.0
    base_D: float = 0.5
    capital_D: float = 7.0 / 6.0          # ⁷⁄₆ D (taller than other caps; incl. abacus)
    architrave_frac_of_D: float = 6.0 / 8.0   # ¾D
    frieze_frac_of_D: float = 6.0 / 8.0       # ¾D
    cornice_frac_of_D: float = 1.0             # 1D
    upper_diam_D: float = 5.0 / 6.0
    # Corinthian specifics
    bell_height_D: ClassVar[float] = 1.0
    leaf_height_D: ClassVar[float] = 1.0 / 3.0   # each leaf row ⅓ of bell
    leaf_rows: ClassVar[int] = 2                  # + helices row (implicit)
    leaf_count_per_row: ClassVar[int] = 8
    modillion_length_D: ClassVar[float] = 5.0 / 12.0
    modillion_oc_D: ClassVar[float] = 2.0 / 3.0  # on-centers
    modillion_height_frac_of_cornice: ClassVar[float] = 1.0 / 5.0
    dentil_oc_D: ClassVar[float] = 1.0 / 6.0
    flute_count: ClassVar[int] = 24


@dataclass(frozen=True, kw_only=True)
class Composite(Order):
    """Composite (Scamozzi variant) — Corinthian proportions with Ionic scrolls
    on the capital's upper register."""
    name: str = "Composite"
    column_D: float = 10.0
    entablature_D: float = 10.0 / 4.0     # 2½D (Vignola); Palladio uses 2D
    pedestal_D: float = 10.0 / 3.0
    base_D: float = 0.5
    capital_D: float = 7.0 / 6.0
    architrave_frac_of_D: float = 6.0 / 8.0
    frieze_frac_of_D: float = 6.0 / 8.0
    cornice_frac_of_D: float = 1.0
    upper_diam_D: float = 5.0 / 6.0
    # Composite specifics (Vignola's larger, squarer dentils)
    scroll_height_D: ClassVar[float] = 3.0 / 6.0   # ½D
    scroll_spacing_D: ClassVar[float] = 3.0 / 6.0  # ½D between eyes
    scroll_width_D: ClassVar[float] = 9.0 / 6.0    # 1½D
    dentil_height_D: ClassVar[float] = 1.0 / 5.0
    dentil_width_D: ClassVar[float] = 1.0 / 6.0
    dentil_oc_D: ClassVar[float] = 1.0 / 4.0
    flute_count: ClassVar[int] = 24
    # Composite reuses Corinthian modillion proportions.
    modillion_length_D: ClassVar[float] = 5.0 / 12.0
    modillion_oc_D: ClassVar[float] = 2.0 / 3.0
    modillion_height_frac_of_cornice: ClassVar[float] = 1.0 / 5.0


# ─── Greek variants ───────────────────────────────────────────────────────
# Greek Doric (after the Parthenon) and Greek Ionic (after the Erechtheion)
# — canonical "archaeological" orders, sharply different from Vignola's
# Roman/Renaissance canon. See Ware pp. 33-36.

@dataclass(frozen=True, kw_only=True)
class GreekDoric(Order):
    """Greek Doric order — no base, shorter column (~5.5D), annulated capital.

    Principal differences from Roman/Vignola Doric:
      - Column sits directly on the stylobate (no plinth, no base).
      - Column is stouter: Parthenon is ~5.5 D tall (vs Roman 8 D).
      - Capital echinus is more dramatically convex ("squashed cushion").
      - 3-5 annulet rings at the base of the echinus.
      - Abacus is a plain unmolded block.
      - Entablature has a plain corona (no mutules).
    """
    name: str = "Greek Doric"
    column_D: float = 5.5                   # Parthenon proportion
    entablature_D: float = 2.0              # ~same as Roman Doric
    pedestal_D: float = 0.0                 # no pedestal (stylobate is continuous)
    base_D: float = 0.0                     # no base
    capital_D: float = 0.5
    architrave_frac_of_D: float = 0.5
    frieze_frac_of_D: float = 0.75
    cornice_frac_of_D: float = 0.75
    upper_diam_D: float = 5.0 / 6.0         # same taper
    # Greek Doric specifics
    triglyph_width_D: ClassVar[float] = 0.5
    metope_width_D: ClassVar[float] = 0.75
    flute_count: ClassVar[int] = 20
    annulet_count: ClassVar[int] = 4        # usually 3-5 rings
    echinus_projection_D: ClassVar[float] = 0.25   # noticeably larger than
    # Roman Doric (~0.15-0.20D) but short of the overblown "lid" look produced
    # by pushing past ~0.30D at plate scale. 0.25D keeps the cushion reading
    # clearly while preserving proportion with the shaft upper diameter.


@dataclass(frozen=True, kw_only=True)
class GreekIonic(Order):
    """Greek Ionic order — more organic volute, attic base with 2 tori + 1 scotia.

    Principal differences from Roman/Vignola Ionic:
      - No pedestal; column springs from the stylobate.
      - Attic base only (no sub-plinth elaboration).
      - Necking often decorated with palmettes — v1 leaves it plain.
      - Volute construction identical schema-wise (Holm 12-center method).
    """
    name: str = "Greek Ionic"
    column_D: float = 9.0
    entablature_D: float = 9.0 / 4.0
    pedestal_D: float = 0.0  # usually no pedestal in Greek work
    base_D: float = 0.5
    capital_D: float = 2.0 / 3.0
    architrave_frac_of_D: float = 5.0 / 8.0
    frieze_frac_of_D: float = 6.0 / 8.0
    cornice_frac_of_D: float = 7.0 / 8.0
    upper_diam_D: float = 5.0 / 6.0
    # Greek Ionic specifics
    volute_height_D: ClassVar[float] = 4.0 / 9.0
    volute_eye_D: ClassVar[float] = 1.0 / 18.0
    flute_count: ClassVar[int] = 24
    has_palmette_necking: ClassVar[bool] = False  # v1: keep plain


# Convenience constructors keyed by name.
ORDERS = {cls.__name__.lower(): cls for cls in
          [Tuscan, Doric, Ionic, Corinthian, Composite, GreekDoric, GreekIonic]}
# Also register under the snake-case names callers are likely to use.
ORDERS.setdefault("greek_doric", GreekDoric)
ORDERS.setdefault("greek_ionic", GreekIonic)


def make(order_name: str, D: float) -> Order:
    """Instantiate an order by name at a given lower diameter D (mm)."""
    return ORDERS[order_name.lower()](D=D)
