"""Declarative shim — generated connection method lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.connection_methods import (
    connection_v2_ops as _generated,
)

_v2_auth_session = _generated._v2_auth_session
_v2_lease_manager = _generated._v2_lease_manager
_build_v2_context = _generated._build_v2_context
_unwrap_v2_response = _generated._unwrap_v2_response
_invoke_mutation_v2 = _generated._invoke_mutation_v2

__all__ = [  # noqa: RUF022
    '_v2_auth_session',
    '_v2_lease_manager',
    '_build_v2_context',
    '_unwrap_v2_response',
    '_invoke_mutation_v2',
]
