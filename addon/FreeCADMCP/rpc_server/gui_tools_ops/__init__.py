"""GUI-thread helper modules for tree, selection, views, and document focus."""

from .document_focus import activate_document, open_document
from .gui_state import get_gui_state
from .recompute_wait import recompute_and_wait
from .section_view import set_section_view
from .selection_ops import get_selection, select_subshapes
from .tree_ops import set_tree_expanded
from .view_aliases import normalize_view_name

__all__ = [
    "activate_document",
    "get_gui_state",
    "get_selection",
    "normalize_view_name",
    "open_document",
    "recompute_and_wait",
    "select_subshapes",
    "set_section_view",
    "set_tree_expanded",
]
