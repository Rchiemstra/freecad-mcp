"""Declarative shim — generated connection method lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.connection_methods import (
    connection_headers_snapshot_helpers as _generated,
)

is_v2_self_contained_method = _generated.is_v2_self_contained_method
is_direct_read = _generated.is_direct_read
authenticated_request_headers = _generated.authenticated_request_headers
direct_read_request_headers = _generated.direct_read_request_headers
legacy_lease_token_headers = _generated.legacy_lease_token_headers
document_names_from_args = _generated.document_names_from_args
selector_argument = _generated.selector_argument
session_ids_from_selector = _generated.session_ids_from_selector
resolve_session_ids = _generated.resolve_session_ids
manager_request_headers = _generated.manager_request_headers

__all__ = [  # noqa: RUF022
    'is_v2_self_contained_method',
    'is_direct_read',
    'authenticated_request_headers',
    'direct_read_request_headers',
    'legacy_lease_token_headers',
    'document_names_from_args',
    'selector_argument',
    'session_ids_from_selector',
    'resolve_session_ids',
    'manager_request_headers',
]
