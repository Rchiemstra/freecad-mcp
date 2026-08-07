"""Declarative shim — generated connection method lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.connection_methods import (
    connection_disconnect_helpers as _generated,
)

mark_connection_disconnected = _generated.mark_connection_disconnected
close_transport_lane = _generated.close_transport_lane

__all__ = [  # noqa: RUF022
    'mark_connection_disconnected',
    'close_transport_lane',
]
