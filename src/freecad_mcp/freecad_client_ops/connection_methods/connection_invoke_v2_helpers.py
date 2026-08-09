"""Declarative shim — generated connection method lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.connection_methods import (
    connection_invoke_v2_helpers as _generated,
)

_redact_native_remote_error = _generated._redact_native_remote_error
invoke_v2_execution_category = _generated.invoke_v2_execution_category
invoke_v2_prepare_telemetry = _generated.invoke_v2_prepare_telemetry
invoke_v2_transport = _generated.invoke_v2_transport
invoke_v2_update_runtime_links = _generated.invoke_v2_update_runtime_links
invoke_v2_session_error_code = _generated.invoke_v2_session_error_code
_refreshed_context = _generated._refreshed_context
invoke_v2_retry_expired_session = _generated.invoke_v2_retry_expired_session
invoke_v2_retry_expired_remote_error = _generated.invoke_v2_retry_expired_remote_error

__all__ = [  # noqa: RUF022
    '_redact_native_remote_error',
    'invoke_v2_execution_category',
    'invoke_v2_prepare_telemetry',
    'invoke_v2_transport',
    'invoke_v2_update_runtime_links',
    'invoke_v2_session_error_code',
    '_refreshed_context',
    'invoke_v2_retry_expired_session',
    'invoke_v2_retry_expired_remote_error',
]
