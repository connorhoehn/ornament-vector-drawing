"""Global plate configuration. All dimensions in millimeters."""
from pathlib import Path

INCH = 25.4

# Plate: 10 x 8 inches landscape
PLATE_W = 10.0 * INCH   # 254.0 mm
PLATE_H = 8.0 * INCH    # 203.2 mm

MARGIN = 0.5 * INCH     # 12.7 mm — outer whitespace
FRAME_INSET = 0.75 * INCH  # 19.05 mm — where the drawn frame sits

STROKE_HAIRLINE = 0.18
STROKE_FINE = 0.25
STROKE_MEDIUM = 0.35
STROKE_HEAVY = 0.50

# Ornament hairlines (acanthus, volutes, rosettes, dentils, caissons) and
# shadow hatches. Introduced in the polish pass to keep capitals from
# clotting and to let shadows read as tonal bands rather than stripes.
STROKE_ORNAMENT = 0.18  # all ornament rules — same numeric value as HAIRLINE
STROKE_HATCH = 0.12     # hairline for shadow hatch lines only

# Hatching defaults
HATCH_SPACING = 0.45  # mm between parallel lines
HATCH_STROKE = 0.12   # was 0.18; lowered in polish pass

PROJECT_ROOT = Path(__file__).parent
OUT_DIR = PROJECT_ROOT / "out"
OUT_DIR.mkdir(exist_ok=True)
