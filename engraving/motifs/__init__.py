"""Package marker for the motif-plugin directory.

Drop ``*.svg`` files in this directory; the plugin loader (see
``engraving/plugins.py``) picks them up at import time and registers each one
as an override of the parametric motif whose name matches the SVG filename
stem.  This file is intentionally empty apart from this docstring -- nothing
in the loader depends on it being a real module; it exists only so tooling
treats ``engraving/motifs`` as a Python package alongside the other
sub-packages under ``engraving/``.
"""
