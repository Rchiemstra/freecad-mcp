"""Compatibility import for the renamed JSON-RPC HTTP transport."""

from .json_rpc_http_transport import JsonRpcHttpTransport as TimeoutTransport

__all__ = ("TimeoutTransport",)
