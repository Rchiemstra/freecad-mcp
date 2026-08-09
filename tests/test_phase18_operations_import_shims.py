"""Phase 18 compatibility tests for retired operations-root lock imports."""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
from pathlib import Path

import pytest

from freecad_mcp import operations
from freecad_mcp.operations import legacy_locking_deprecations
from tests.helpers.architecture_baseline import FROZEN_DEPRECATION_RESULT

pytestmark = pytest.mark.unit

ROOT_COMPATIBILITY_NAMES = (
    "acquire_document_lock_operation",
    "adopt_dirty_document_operation",
    "claim_acquisition_result_operation",
    "force_release_stale_lock_operation",
    "forget_legacy_document_key",
    "get_document_lock_operation",
    "heartbeat_document_lock_operation",
    "legacy_selector_doc_key",
    "list_document_locks_operation",
    "release_document_lock_operation",
    "update_document_lock_operation",
)

EXPECTED_PARAMETER_CONTRACTS = {
    "acquire_document_lock_operation": [
        {"name": "freecad", "kind": "positional_or_keyword", "required": True},
        {
            "name": "doc_name",
            "kind": "keyword_only",
            "required": False,
            "default": "",
        },
        {
            "name": "file_path",
            "kind": "keyword_only",
            "required": False,
            "default": "",
        },
        {
            "name": "session_id",
            "kind": "keyword_only",
            "required": False,
            "default": "",
        },
        {
            "name": "task_description",
            "kind": "keyword_only",
            "required": False,
            "default": "",
        },
        {
            "name": "client",
            "kind": "keyword_only",
            "required": False,
            "default": "",
        },
        {
            "name": "selector",
            "kind": "keyword_only",
            "required": False,
            "default": None,
        },
        {
            "name": "agent_id",
            "kind": "keyword_only",
            "required": False,
            "default": "",
        },
        {
            "name": "hash_policy",
            "kind": "keyword_only",
            "required": False,
            "default": "sha256",
        },
        {
            "name": "lease_manager",
            "kind": "keyword_only",
            "required": False,
            "default": None,
        },
        {
            "name": "document_sessions",
            "kind": "keyword_only",
            "required": False,
            "default": None,
        },
    ],
    "adopt_dirty_document_operation": [
        {"name": "freecad", "kind": "positional_or_keyword", "required": True},
        {"name": "selector", "kind": "keyword_only", "required": True},
        {
            "name": "task_description",
            "kind": "keyword_only",
            "required": False,
            "default": "",
        },
        {
            "name": "client",
            "kind": "keyword_only",
            "required": False,
            "default": "",
        },
        {
            "name": "agent_id",
            "kind": "keyword_only",
            "required": False,
            "default": "",
        },
        {
            "name": "hash_policy",
            "kind": "keyword_only",
            "required": False,
            "default": "sha256",
        },
        {
            "name": "lease_manager",
            "kind": "keyword_only",
            "required": False,
            "default": None,
        },
        {
            "name": "document_sessions",
            "kind": "keyword_only",
            "required": False,
            "default": None,
        },
        {
            "name": "store_token",
            "kind": "keyword_only",
            "required": False,
            "default": None,
        },
    ],
    "claim_acquisition_result_operation": [
        {"name": "freecad", "kind": "positional_or_keyword", "required": True},
        {"name": "request_id", "kind": "keyword_only", "required": True},
        {
            "name": "lease_manager",
            "kind": "keyword_only",
            "required": False,
            "default": None,
        },
        {
            "name": "document_sessions",
            "kind": "keyword_only",
            "required": False,
            "default": None,
        },
        {
            "name": "store_token",
            "kind": "keyword_only",
            "required": False,
            "default": None,
        },
    ],
    "force_release_stale_lock_operation": [
        {"name": "freecad", "kind": "positional_or_keyword", "required": True},
        {"name": "doc_key", "kind": "keyword_only", "required": True},
    ],
    "forget_legacy_document_key": [
        {"name": "doc_key", "kind": "positional_or_keyword", "required": True},
        {"name": "legacy_document_keys", "kind": "positional_or_keyword", "required": True},
    ],
    "get_document_lock_operation": [
        {"name": "freecad", "kind": "positional_or_keyword", "required": True},
        {
            "name": "doc_name",
            "kind": "keyword_only",
            "required": False,
            "default": "",
        },
        {
            "name": "file_path",
            "kind": "keyword_only",
            "required": False,
            "default": "",
        },
        {
            "name": "session_id",
            "kind": "keyword_only",
            "required": False,
            "default": "",
        },
        {
            "name": "selector",
            "kind": "keyword_only",
            "required": False,
            "default": None,
        },
    ],
    "heartbeat_document_lock_operation": [
        {"name": "freecad", "kind": "positional_or_keyword", "required": True},
        {"name": "doc_key", "kind": "keyword_only", "required": True},
        {"name": "token", "kind": "keyword_only", "required": True},
        {
            "name": "current_operation",
            "kind": "keyword_only",
            "required": False,
            "default": "",
        },
        {
            "name": "state",
            "kind": "keyword_only",
            "required": False,
            "default": "",
        },
        {
            "name": "document_dirty",
            "kind": "keyword_only",
            "required": False,
            "default": None,
        },
    ],
    "legacy_selector_doc_key": [
        {"name": "selector", "kind": "positional_or_keyword", "required": True},
        {"name": "legacy_document_keys", "kind": "positional_or_keyword", "required": True},
    ],
    "list_document_locks_operation": [
        {"name": "freecad", "kind": "positional_or_keyword", "required": True},
    ],
    "release_document_lock_operation": [
        {"name": "freecad", "kind": "positional_or_keyword", "required": True},
        {"name": "doc_key", "kind": "keyword_only", "required": True},
        {"name": "token", "kind": "keyword_only", "required": True},
        {
            "name": "selector",
            "kind": "keyword_only",
            "required": False,
            "default": None,
        },
        {
            "name": "disposition",
            "kind": "keyword_only",
            "required": False,
            "default": "saved",
        },
        {
            "name": "lease_manager",
            "kind": "keyword_only",
            "required": False,
            "default": None,
        },
        {
            "name": "document_sessions",
            "kind": "keyword_only",
            "required": False,
            "default": None,
        },
        {
            "name": "store_token",
            "kind": "keyword_only",
            "required": False,
            "default": None,
        },
    ],
    "update_document_lock_operation": [
        {"name": "freecad", "kind": "positional_or_keyword", "required": True},
        {"name": "selector", "kind": "keyword_only", "required": True},
        {
            "name": "task_description",
            "kind": "keyword_only",
            "required": False,
            "default": "",
        },
        {
            "name": "progress_detail",
            "kind": "keyword_only",
            "required": False,
            "default": "",
        },
    ],
}

RETIRED_LOCKING_MODULE_NAMES = (
    "freecad_mcp.operations.locking",
    "freecad_mcp.operations.locking_ops",
    "freecad_mcp.operations.locking_ops.acquisition_ops",
    "freecad_mcp.operations.locking_ops.lifecycle_ops",
)


def _parameter_contract(value: object) -> list[dict[str, object]]:
    contract: list[dict[str, object]] = []
    for parameter in inspect.signature(value).parameters.values():
        item: dict[str, object] = {
            "name": parameter.name,
            "kind": parameter.kind.name.lower(),
            "required": parameter.default is inspect.Signature.empty,
        }
        if parameter.default is not inspect.Signature.empty:
            item["default"] = parameter.default
        contract.append(item)
    return contract


class _ExplodingFreeCAD:
    def __getattribute__(self, name: str) -> object:
        raise AssertionError(f"compatibility adapter accessed FreeCAD.{name}")


class _ExplodingCustody:
    def __getattribute__(self, name: str) -> object:
        raise AssertionError(f"compatibility adapter accessed custody.{name}")


@pytest.mark.parametrize(
    ("name", "invoke"),
    [
        ("acquire_document_lock_operation", lambda fn: fn(_ExplodingFreeCAD())),
        (
            "adopt_dirty_document_operation",
            lambda fn: fn(_ExplodingFreeCAD(), selector={"document_name": "A"}),
        ),
        (
            "claim_acquisition_result_operation",
            lambda fn: fn(_ExplodingFreeCAD(), request_id="request-1"),
        ),
        (
            "force_release_stale_lock_operation",
            lambda fn: fn(_ExplodingFreeCAD(), doc_key="name:A"),
        ),
        (
            "forget_legacy_document_key",
            lambda fn: fn("name:A", {"name:A": "name:A"}),
        ),
        pytest.param(
            "forget_legacy_document_key",
            lambda fn: fn("name:A", None),
            id="forget_legacy_document_key-null-index",
        ),
        ("get_document_lock_operation", lambda fn: fn(_ExplodingFreeCAD())),
        (
            "heartbeat_document_lock_operation",
            lambda fn: fn(_ExplodingFreeCAD(), doc_key="name:A", token="secret"),
        ),
        (
            "legacy_selector_doc_key",
            lambda fn: fn({"document_name": "A"}, {"name:A": "name:A"}),
        ),
        ("list_document_locks_operation", lambda fn: fn(_ExplodingFreeCAD())),
        (
            "release_document_lock_operation",
            lambda fn: fn(_ExplodingFreeCAD(), doc_key="name:A", token="secret"),
        ),
        (
            "update_document_lock_operation",
            lambda fn: fn(_ExplodingFreeCAD(), selector={"document_name": "A"}),
        ),
    ],
)
def test_retired_root_imports_are_pure_frozen_tombstones(name, invoke) -> None:
    adapter = getattr(operations, name)

    first = invoke(adapter)
    assert first == FROZEN_DEPRECATION_RESULT

    first["success"] = True
    second = invoke(adapter)

    assert second == FROZEN_DEPRECATION_RESULT
    assert second is not first
    assert adapter.__module__ == legacy_locking_deprecations.__name__


@pytest.mark.parametrize("name", ROOT_COMPATIBILITY_NAMES)
def test_retired_root_imports_preserve_legacy_signatures(name: str) -> None:
    adapter = getattr(legacy_locking_deprecations, name)
    assert _parameter_contract(adapter) == EXPECTED_PARAMETER_CONTRACTS[name]


def test_forget_legacy_document_key_does_not_mutate_legacy_document_keys() -> None:
    legacy_document_keys = {"name:A": "name:A"}
    snapshot = dict(legacy_document_keys)

    result = operations.forget_legacy_document_key("name:A", legacy_document_keys)

    assert result == FROZEN_DEPRECATION_RESULT
    assert legacy_document_keys == snapshot


@pytest.mark.parametrize("module_name", RETIRED_LOCKING_MODULE_NAMES)
def test_retired_locking_modules_are_not_importable(module_name: str) -> None:
    sys.modules.pop(module_name, None)
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)


def test_retired_locking_implementation_paths_are_absent() -> None:
    operations_root = (
        Path(__file__).resolve().parents[1] / "src" / "freecad_mcp" / "operations"
    )
    assert not (operations_root / "locking.py").exists()
    assert not (operations_root / "locking_ops").exists()


def test_custody_kwargs_do_not_touch_removed_lease_state() -> None:
    sessions: dict[str, str] = {"A": "session-uuid"}
    store_token: dict[str, str] = {"name:A": "token"}
    freecad = _ExplodingFreeCAD()
    custody = _ExplodingCustody()

    acquire = operations.acquire_document_lock_operation(
        freecad,
        doc_name="A",
        file_path="/tmp/A.FCStd",
        session_id="session-uuid",
        task_description="historic",
        client="cursor",
        selector={"document_name": "A"},
        agent_id="agent-1",
        hash_policy="sha256",
        lease_manager=custody,
        document_sessions=sessions,
    )
    adopt = operations.adopt_dirty_document_operation(
        freecad,
        selector={"document_name": "A"},
        task_description="historic",
        client="cursor",
        agent_id="agent-1",
        hash_policy="sha256",
        lease_manager=custody,
        document_sessions=sessions,
        store_token=store_token,
    )
    claim = operations.claim_acquisition_result_operation(
        freecad,
        request_id="request-1",
        lease_manager=custody,
        document_sessions=sessions,
        store_token=store_token,
    )
    release = operations.release_document_lock_operation(
        freecad,
        doc_key="name:A",
        token="secret",
        selector={"document_name": "A"},
        disposition="saved",
        lease_manager=custody,
        document_sessions=sessions,
        store_token=store_token,
    )

    for result in (acquire, adopt, claim, release):
        assert result == FROZEN_DEPRECATION_RESULT
    assert sessions == {"A": "session-uuid"}
    assert store_token == {"name:A": "token"}


def test_retired_root_imports_preserve_the_phase17_export_names() -> None:
    assert set(ROOT_COMPATIBILITY_NAMES) <= set(operations.__all__)
    assert tuple(legacy_locking_deprecations.__all__) == ROOT_COMPATIBILITY_NAMES


def test_compatibility_module_cannot_import_historic_locking_implementation() -> None:
    tree = ast.parse(inspect.getsource(legacy_locking_deprecations))
    imported = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert not any("locking" in module for module in imported)
    assert "FreeCAD" not in imported

    top_level_imports = [
        node
        for node in tree.body
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert len(top_level_imports) == 2
    assert all(
        isinstance(node, ast.ImportFrom) and node.module in {"__future__", "typing"}
        for node in top_level_imports
    )
    assert "_removed" not in legacy_locking_deprecations.__all__
