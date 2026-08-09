"""Declarative shim — inline runtime info lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.inline.tools_runtime_info import (
    _compatibility_for_manifest,
    _runtime_info_payload,
    get_runtime_info,
)

__all__ = [
    '_compatibility_for_manifest',
    '_runtime_info_payload',
    'get_runtime_info',
]
