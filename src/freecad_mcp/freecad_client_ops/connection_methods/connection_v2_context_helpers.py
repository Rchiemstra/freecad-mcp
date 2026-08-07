"""Declarative shim — generated connection method lives in generated/capabilities."""

from freecad_mcp.generated.capabilities.connection_methods import (
    connection_v2_context_helpers as _generated,
)

resolve_document_name_sessions = _generated.resolve_document_name_sessions
resolve_selector_session = _generated.resolve_selector_session

__all__ = [
    'resolve_document_name_sessions',
    'resolve_selector_session',
]
