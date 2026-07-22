"""Contract tests for the model-facing document-lease tools."""

from __future__ import annotations

import inspect

import pytest

from freecad_mcp import server


pytestmark = pytest.mark.unit


def _tool_registry():
    manager = getattr(server.mcp, "_tool_manager", None)
    assert manager is not None
    registry = getattr(manager, "_tools", None) or getattr(manager, "tools", None)
    assert isinstance(registry, dict)
    return registry


def test_public_lease_tools_exclude_control_and_local_recovery_helpers():
    tools = _tool_registry()
    assert {
        "acquire_document_lock",
        "get_document_lock",
        "list_document_locks",
        "update_document_lock",
        "release_document_lock",
        "save_document",
        "save_document_as",
        "finalize_document_edit",
    } <= set(tools)
    assert "heartbeat_document_lock" not in tools
    assert "force_release_stale_lock" not in tools


def test_public_lease_signatures_prefer_typed_v2_and_label_v1_compatibility():
    acquire = inspect.signature(server.acquire_document_lock).parameters
    assert {"selector", "task_description", "agent_id", "hash_policy"} <= set(acquire)
    assert acquire["hash_policy"].default == "sha256"
    assert "deprecated protocol-v1" in inspect.getdoc(server.acquire_document_lock)

    get = inspect.signature(server.get_document_lock).parameters
    assert "selector" in get
    assert "legacy identity arguments" in inspect.getdoc(server.get_document_lock)

    update = inspect.signature(server.update_document_lock).parameters
    assert set(update) == {
        "ctx",
        "selector",
        "task_description",
        "progress_detail",
    }

    release = inspect.signature(server.release_document_lock).parameters
    assert {"selector", "disposition"} <= set(release)
    # Section 16 keeps these fields for one off/observe migration release. The
    # description must make clear that v2 does not select credentials this way.
    assert {"doc_key", "token"} <= set(release)
    assert "deprecated protocol-v1" in inspect.getdoc(server.release_document_lock)


def test_typed_save_and_finalize_signatures_match_lifecycle_contract():
    save = inspect.signature(server.save_document).parameters
    assert set(save) == {"ctx", "selector", "validation_profile"}

    save_as = inspect.signature(server.save_document_as).parameters
    assert set(save_as) == {
        "ctx",
        "selector",
        "destination",
        "overwrite",
        "expected_destination_sha256",
        "validation_profile",
    }

    finalize = inspect.signature(server.finalize_document_edit).parameters
    assert set(finalize) == {
        "ctx",
        "selector",
        "save_mode",
        "destination",
        "overwrite",
        "expected_destination_sha256",
        "validation_profile",
    }

