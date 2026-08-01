"""GUI-thread helpers for tree, selection, section clip, and document focus."""

from __future__ import annotations

# §3.3 compatibility shims — keep old import paths working.
from .gui_tools_ops.document_focus import activate_document, open_document  # noqa: F401
from .gui_tools_ops.gui_state import get_gui_state  # noqa: F401
from .gui_tools_ops.recompute_wait import recompute_and_wait  # noqa: F401
from .gui_tools_ops.section_view import set_section_view  # noqa: F401
from .gui_tools_ops.selection_ops import get_selection, select_subshapes  # noqa: F401
from .gui_tools_ops.tree_ops import set_tree_expanded  # noqa: F401
from .gui_tools_ops.view_aliases import normalize_view_name  # noqa: F401
