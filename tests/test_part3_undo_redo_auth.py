"""Assert Part 3 undo/redo participate in dispatch session elevation."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops.dispatch_core_enforcement_auth import (
    AUTHENTICATED_METHODS,
    elevate_rpc_session_identity_or_error,
)

pytestmark = pytest.mark.unit


def test_undo_and_redo_are_authenticated_methods() -> None:
    assert "undo" in AUTHENTICATED_METHODS
    assert "redo" in AUTHENTICATED_METHODS


def test_elevate_rpc_session_identity_from_rpc_session_token() -> None:
    session_id = str(uuid.uuid4())
    runtime_id = str(uuid.uuid4())
    session_token = str(uuid.uuid4())
    identity_provider = MagicMock()
    identity_provider.get_request_identity.return_value = {
        "instance_id": runtime_id,
        "rpc_session_token": session_token,
    }
    session_manager = MagicMock()
    session_manager.authenticate.return_value = SimpleNamespace(
        session_id=session_id,
        mcp=SimpleNamespace(process_started_at="2026-08-17T00:00:00Z"),
    )
    collaborators = MagicMock()
    collaborators.session_manager = session_manager
    collaborators.lease_protocol_public_error = MagicMock()

    error = elevate_rpc_session_identity_or_error(collaborators, identity_provider)
    assert error is None
    identity_provider.set_request_identity.assert_called_once()
    elevated = identity_provider.set_request_identity.call_args.kwargs
    assert elevated["authenticated_session_id"] == session_id
