"""Declarative shim — generated connection method lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.connection_methods import (
    connection_headers_ops as _generated,
)

_refresh_headers = _generated._refresh_headers
configure_rpc_session = _generated.configure_rpc_session
configure_lease_routing = _generated.configure_lease_routing
configure_session_refresher = _generated.configure_session_refresher
configure_stale_recovery = _generated.configure_stale_recovery

__all__ = [  # noqa: RUF022
    '_refresh_headers',
    'configure_rpc_session',
    'configure_lease_routing',
    'configure_session_refresher',
    'configure_stale_recovery',
]
