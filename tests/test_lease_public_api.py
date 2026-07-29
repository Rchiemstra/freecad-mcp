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
        "adopt_dirty_document",
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


def test_public_lease_signatures_use_v2_with_deprecated_selector_aliases():
    acquire = inspect.signature(server.acquire_document_lock).parameters
    assert {"selector", "task_description", "agent_id", "hash_policy"} <= set(acquire)
    assert acquire["hash_policy"].default == "sha256"
    acquire_doc = inspect.getdoc(server.acquire_document_lock)
    assert "deprecated selector" in acquire_doc
    assert "authenticated protocol-v2 service" in acquire_doc

    adopt = inspect.signature(server.adopt_dirty_document).parameters
    assert set(adopt) == {
        "ctx",
        "selector",
        "task_description",
        "agent_id",
        "hash_policy",
    }
    assert adopt["hash_policy"].default == "sha256"
    assert "local confirmation dialog" in inspect.getdoc(server.adopt_dirty_document)

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


def test_document_selector_schema_names_fields_and_rejects_unknown_keys():
    tools = _tool_registry()
    expected = {
        "document_name",
        "document_session_uuid",
        "canonical_path",
    }
    for name in {
        "adopt_dirty_document",
        "update_document_lock",
        "save_document",
        "save_document_as",
        "finalize_document_edit",
    }:
        parameters = tools[name].parameters
        selector = parameters["properties"]["selector"]
        schema = parameters["$defs"][selector["$ref"].rsplit("/", 1)[-1]]
        assert set(schema["properties"]) == expected
        assert schema["additionalProperties"] is False

