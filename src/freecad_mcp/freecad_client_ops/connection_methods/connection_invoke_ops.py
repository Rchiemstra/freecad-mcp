"""Declarative shim — generated connection method lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.connection_methods import (
    connection_invoke_ops as _generated,
)

set_identity = _generated.set_identity
set_active_lease_token = _generated.set_active_lease_token
_make_proxy = _generated._make_proxy
invoke_rpc = _generated.invoke_rpc

__all__ = [  # noqa: RUF022
    'set_identity',
    'set_active_lease_token',
    '_make_proxy',
    'invoke_rpc',
]
