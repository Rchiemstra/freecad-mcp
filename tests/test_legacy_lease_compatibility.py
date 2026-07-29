"""Regression coverage for the temporary protocol-v1 observe-mode seam."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from freecad_mcp import server
from freecad_mcp.lease_manager import LeaseClientManager
from freecad_mcp.operations.locking import (
    _store_lease_grant,
    legacy_selector_doc_key,
)
from freecad_mcp.server_state import ServerState


pytestmark = pytest.mark.unit


def _legacy_grant(tmp_path):
    model = tmp_path / "Legacy.FCStd"
    return {
        "success": True,
        "token": "legacy-secret",
        "lease": {
            "doc_key": str(model.resolve()),
            "doc_name": "Legacy",
            "document_session_uuid": "11111111-2222-3333-4444-555555555555",
        },
    }


def _store_legacy_grant(state, result):
    _store_lease_grant(
        result,
        lease_manager=state.lease_manager,
        document_sessions=state.document_sessions,
        store_token=state.lease_tokens,
        legacy_document_keys=state.legacy_document_keys,
    )


def test_v1_grant_indexes_every_typed_selector_alias(tmp_path):
    state = ServerState()
    result = _legacy_grant(tmp_path)
    _store_legacy_grant(state, result)
    lease = result["lease"]

    for selector in (
        {"document_name": lease["doc_name"]},
        {"document_session_uuid": lease["document_session_uuid"]},
        {"canonical_path": lease["doc_key"]},
        {
            "document_name": lease["doc_name"],
            "document_session_uuid": lease["document_session_uuid"],
            "canonical_path": lease["doc_key"],
        },
    ):
        assert (
            legacy_selector_doc_key(selector, state.legacy_document_keys)
            == lease["doc_key"]
        )
    assert (
        legacy_selector_doc_key(
            {
                "document_name": lease["doc_name"],
                "document_session_uuid": "different-session",
            },
            state.legacy_document_keys,
        )
        == ""
    )


def test_selector_save_routes_private_v1_token_without_v2_manager(tmp_path):
    compatibility_state = ServerState()
    result = _legacy_grant(tmp_path)
    _store_legacy_grant(compatibility_state, result)
    connection = Mock()
    connection.save_document.return_value = {
        "success": True,
        "save": {"path": result["lease"]["doc_key"]},
    }

    with (
        patch.object(server, "state", compatibility_state),
        patch.object(server, "get_freecad_connection", return_value=connection),
    ):
        response = server.save_document(
            None,
            selector={"document_name": "Legacy"},
        )

    assert response.isError is False
    connection.save_document.assert_called_once_with(
        {"document_name": "Legacy"},
        validation_profile="default",
        legacy_token="legacy-secret",
    )


def test_selector_release_falls_back_to_private_v1_token_when_v2_is_connected(
    tmp_path,
):
    compatibility_state = ServerState(
        lease_manager=LeaseClientManager(session_token="rpc-session")
    )
    result = _legacy_grant(tmp_path)
    _store_legacy_grant(compatibility_state, result)
    connection = Mock()
    connection.release_document_lock.return_value = {
        "success": True,
        "released": result["lease"]["doc_key"],
        "terminal_state": "UNLOCKED_SAVED",
    }

    with (
        patch.object(server, "state", compatibility_state),
        patch.object(server, "get_freecad_connection", return_value=connection),
    ):
        response = server.release_document_lock(
            None,
            selector={"document_name": "Legacy"},
        )

    assert response.isError is False
    connection.release_document_lock.assert_called_once_with(
        result["lease"]["doc_key"],
        "legacy-secret",
        selector=None,
        disposition="saved",
    )
    assert compatibility_state.lease_tokens == {}
    assert compatibility_state.legacy_document_keys == {}


def test_selector_finalize_routes_and_forgets_private_v1_credential(tmp_path):
    compatibility_state = ServerState()
    result = _legacy_grant(tmp_path)
    _store_legacy_grant(compatibility_state, result)
    connection = Mock()
    connection.finalize_document_edit.return_value = {
        "success": True,
        "released": True,
        "save": {"path": result["lease"]["doc_key"]},
        "release": {"terminal_state": "UNLOCKED_SAVED"},
    }

    with (
        patch.object(server, "state", compatibility_state),
        patch.object(server, "get_freecad_connection", return_value=connection),
    ):
        response = server.finalize_document_edit(
            None,
            selector={"document_name": "Legacy"},
        )

    assert response.isError is False
    connection.finalize_document_edit.assert_called_once_with(
        {"document_name": "Legacy"},
        save_mode="save",
        destination="",
        overwrite=False,
        expected_destination_sha256="",
        validation_profile="default",
        legacy_token="legacy-secret",
    )
    assert compatibility_state.lease_tokens == {}
    assert compatibility_state.legacy_document_keys == {}
