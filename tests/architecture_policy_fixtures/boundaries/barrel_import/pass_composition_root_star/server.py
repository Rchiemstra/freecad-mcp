"""Composition root that binds tool exports after registration."""

from tool_exports.bind_exports import bind_tool_exports

_TOOL_EXPORTS = {"create_document": object()}
bind_tool_exports(_TOOL_EXPORTS)
from tool_exports import *  # noqa: F403
