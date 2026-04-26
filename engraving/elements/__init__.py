"""Elements package.

Re-exports legacy builder symbols (`Shadow`, `pedestal`, `column`, …) from
``_legacy`` so existing imports like ``from engraving.elements import Shadow``
continue to work unmodified during the Phase 19 overhaul.

New Element-subclass wrappers live in submodules (e.g. ``.arches``).
"""
from ._legacy import (
    Shadow,
    pedestal,
    column,
    entablature,
    pediment,
    tetrastyle_portico,
    rusticated_block_wall,
)

__all__ = [
    "Shadow",
    "pedestal",
    "column",
    "entablature",
    "pediment",
    "tetrastyle_portico",
    "rusticated_block_wall",
]
