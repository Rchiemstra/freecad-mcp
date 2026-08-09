"""Declarative facade for actor-scoped native collaboration contexts."""

from .collaboration_context_core import redacted_error
from .collaboration_context_dispatch import GuiDispatchFailure, public_error
from .collaboration_context_render import (
    encode_png_bytes,
    render_temporary_context_gui,
)
from .collaboration_context_render import (
    render_personal_context as render_personal_view,
)
from .collaboration_context_view import snapshot_personal_view, update_personal_view

__all__ = [
    "GuiDispatchFailure",
    "encode_png_bytes",
    "public_error",
    "redacted_error",
    "render_personal_view",
    "render_temporary_context_gui",
    "snapshot_personal_view",
    "update_personal_view",
]
