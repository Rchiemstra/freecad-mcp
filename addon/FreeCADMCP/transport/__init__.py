"""Authority-free transport layer for the FreeCAD MCP add-on."""

from .authentication import SessionManager, load_profile_secret, make_runtime_manifest
from .ip_filter import validate_allowed_ips
from .json_rpc_errors import json_rpc_error_from_result
from .json_rpc_transport import JsonRpcError, JsonRpcTransport
from .listener import JsonRpcListener
from .replay import RequestReplayCache
from .request_handler import JsonRpcRequestHandler

__all__ = [
    "JsonRpcError",
    "JsonRpcListener",
    "JsonRpcRequestHandler",
    "JsonRpcTransport",
    "RequestReplayCache",
    "SessionManager",
    "json_rpc_error_from_result",
    "load_profile_secret",
    "make_runtime_manifest",
    "validate_allowed_ips",
]
