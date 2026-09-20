"""Declarative shim — inline runtime info lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.inline.tools_runtime_info import (
    _runtime_info_payload,
    get_runtime_info,
)
from freecad_mcp.server_ops.compatibility import (
    compatibility_for_manifest as _compatibility_for_manifest,
)
from freecad_mcp.server_ops.compatibility import (
    normalize_protocol_versions,
    runtime_compatibility,
)

__all__ = [
    '_compatibility_for_manifest',
    '_runtime_info_payload',
    'get_runtime_info',
    'normalize_protocol_versions',
    'runtime_compatibility',
]
