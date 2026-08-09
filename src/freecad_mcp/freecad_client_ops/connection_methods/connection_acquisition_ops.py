"""Declarative shim — generated connection method lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.connection_methods import (
    connection_acquisition_ops as _generated,
)

_recover_acquisition_after_transport_loss = _generated._recover_acquisition_after_transport_loss
_resolve_locked_error_handoff_pending = _generated._resolve_locked_error_handoff_pending

__all__ = [
    '_recover_acquisition_after_transport_loss',
    '_resolve_locked_error_handoff_pending',
]
