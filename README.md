# ornament-vector-drawing

Procedurally generated classical architectural plates rendered as SVG. Inspired by Vignola's *Five Orders* and similar 19th-century engraving books.

The pipeline composes columns, entablatures, capitals, acanthus, volutes, balustrades, arcades, and ornament into 10×8" landscape plates.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

The `ornament` shim invokes the CLI through the project's venv:

```bash
./ornament list                  # show available plates
./ornament render --name doric   # render a single plate
./ornament render --all          # render everything
```

Equivalent without the shim:

```bash
python -m engraving.cli list
python -m engraving.cli render --name corinthian
```

Output SVG/PNG files are written to `out/`.

## Layout

- `engraving/` — rendering primitives (orders, capitals, ornament, hatching, geometry, scene, validation)
- `plates/` — individual plate compositions (one module per plate)
- `scripts/` — utility scripts
- `tests/` — pytest suite (`pytest -m "not slow"` to skip plate renders)
- `plans/` — design notes and phase plans
- `config.py` — global plate dimensions, stroke weights, and output paths

## Tests

```bash
pytest                  # full suite
pytest -m "not slow"    # skip plate-render integration tests
```
