"""Compatibility import for the canonical JSON-RPC error mapper."""

try:
    from ..transport.json_rpc_errors import json_rpc_error_from_result
except ImportError:  # pragma: no cover - flat FreeCAD add-on import path
    from transport.json_rpc_errors import json_rpc_error_from_result

__all__ = ["json_rpc_error_from_result"]
