"""Phase 18 coverage for the frozen public lease RPC adapter surface."""

from __future__ import annotations

import ast
import importlib
import inspect
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.helpers.architecture_baseline import (
    FROZEN_DEPRECATION_RESULT,
    load_manifest,
)
from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "addon/FreeCADMCP/rpc_server/methods/lease_methods.py"
MODULE_NAME = "addon.FreeCADMCP.rpc_server.methods.lease_methods"
INSTALLED_NAME = "rpc_server.methods.lease_methods"

# The manifest freezes names, parameter kinds, and whether each parameter is
# required.  These two maps extend that fixture contract to exact default and
# annotation values without maintaining a second copy of the 22-name surface.
EXPECTED_DEFAULTS = {
    "acquire_document_lock": {
        "doc_name": "",
        "file_path": "",
        "session_id": "",
        "task_description": "",
        "client": "",
        "selector": None,
        "agent_id": "",
        "hash_policy": "sha256",
    },
    "acquire_document_lock_v2": {"adopt_dirty": False},
    "adopt_dirty_document": {
        "selector": None,
        "task_description": "",
        "client": "",
        "agent_id": "",
        "hash_policy": "sha256",
    },
    "finalize_document_edit": {
        "save_mode": "save",
        "destination": "",
        "overwrite": False,
        "expected_destination_sha256": "",
        "validation_profile": "default",
    },
    "get_document_lock": {
        "doc_name": "",
        "file_path": "",
        "session_id": "",
        "selector": None,
    },
    "heartbeat_document_lock": {
        "current_operation": "",
        "state": "",
        "document_dirty": None,
    },
    "lease_heartbeat_batch": {"client_monotonic_ns": ""},
    "release_document_lock": {
        "doc_key": "",
        "token": "",
        "selector": None,
        "disposition": "saved",
    },
    "run_legacy_save": {"validation_profile": "default"},
    "run_typed_save": {
        "destination": "",
        "overwrite": False,
        "expected_destination_sha256": "",
        "validation_profile": "default",
        "release": False,
    },
    "save_document": {"validation_profile": "default"},
    "save_document_as": {
        "overwrite": False,
        "expected_destination_sha256": "",
        "validation_profile": "default",
    },
    "update_document_lock": {
        "task_description": "",
        "progress_detail": "",
    },
}

EXPECTED_ANNOTATIONS = {
    "acquire_document_lock": {
        "doc_name": str,
        "file_path": str,
        "session_id": str,
        "task_description": str,
        "client": str,
        "selector": dict[str, Any] | None,
        "agent_id": str,
        "hash_policy": str,
        "return": dict[str, Any],
    },
    "adopt_dirty_document": {
        "selector": dict[str, Any] | None,
        "task_description": str,
        "client": str,
        "agent_id": str,
        "hash_policy": str,
        "return": dict[str, Any],
    },
    "force_release_stale_lock": {
        "doc_key": str,
        "return": dict[str, Any],
    },
    "get_document_lock": {
        "doc_name": str,
        "file_path": str,
        "session_id": str,
        "selector": dict[str, Any] | None,
        "return": dict[str, Any],
    },
    "heartbeat_document_lock": {
        "doc_key": str,
        "token": str,
        "current_operation": str,
        "state": str,
        "document_dirty": bool | None,
        "return": dict[str, Any],
    },
    "list_document_locks": {"return": dict[str, Any]},
    "release_document_lock": {
        "doc_key": str,
        "token": str,
        "selector": dict[str, Any] | None,
        "disposition": str,
        "return": dict[str, Any],
    },
}


def _lease_surface() -> dict[str, Any]:
    return next(
        surface
        for surface in load_manifest()["retained_compatibility_surfaces"]
        if surface["module"] == MODULE_NAME
    )


def _contract(value: object) -> list[dict[str, object]]:
    return [
        {
            "name": parameter.name,
            "kind": parameter.kind.name.lower(),
            "required": parameter.default is inspect.Parameter.empty,
        }
        for parameter in inspect.signature(value).parameters.values()
    ]


def _defaults(value: object) -> dict[str, object]:
    return {
        parameter.name: parameter.default
        for parameter in inspect.signature(value).parameters.values()
        if parameter.default is not inspect.Parameter.empty
    }


def _default_types(
    defaults: dict[str, dict[str, object]],
) -> dict[str, dict[str, type[object]]]:
    return {
        function: {
            parameter: type(value)
            for parameter, value in function_defaults.items()
        }
        for function, function_defaults in defaults.items()
    }


def _annotations(value: object) -> dict[str, object]:
    signature = inspect.signature(value)
    result = {
        parameter.name: parameter.annotation
        for parameter in signature.parameters.values()
        if parameter.annotation is not inspect.Parameter.empty
    }
    if signature.return_annotation is not inspect.Signature.empty:
        result["return"] = signature.return_annotation
    return result


def _representative_call(
    value: object,
    contract: list[dict[str, object]],
) -> dict[str, object]:
    args: list[object] = []
    kwargs: dict[str, object] = {}
    for parameter in contract:
        if not parameter["required"]:
            continue
        if parameter["kind"] == "positional_or_keyword":
            args.append(object())
        elif parameter["kind"] == "keyword_only":
            kwargs[str(parameter["name"])] = object()
        else:  # pragma: no cover - the frozen manifest contains neither kind
            raise AssertionError(f"unexpected parameter kind: {parameter['kind']}")
    return value(*args, **kwargs)


def _import_spellings():
    bootstrap_unit_test_runtime()
    installed_addon_root = str(ROOT / "addon" / "FreeCADMCP")
    if installed_addon_root not in sys.path:
        sys.path.insert(0, installed_addon_root)
    return importlib.import_module(MODULE_NAME), importlib.import_module(INSTALLED_NAME)


def test_manifest_names_and_exact_signatures_are_preserved():
    surface = _lease_surface()
    contracts = {
        item["symbol"]: item["parameter_contract"]
        for item in surface["post_cutover_deprecation_contracts"]
    }
    assert list(contracts) == surface["current_symbols"]
    assert surface["current_symbols"] == load_manifest()["public_lease_rpc_adapters"]

    for module in _import_spellings():
        assert module.__all__ == surface["current_symbols"]
        observed_defaults = {}
        observed_annotations = {}
        for name, expected_contract in contracts.items():
            value = getattr(module, name)
            assert _contract(value) == expected_contract
            if defaults := _defaults(value):
                observed_defaults[name] = defaults
            if annotations := _annotations(value):
                observed_annotations[name] = annotations
        assert observed_defaults == EXPECTED_DEFAULTS
        assert _default_types(observed_defaults) == _default_types(EXPECTED_DEFAULTS)
        assert observed_annotations == EXPECTED_ANNOTATIONS


def test_supported_import_spellings_retain_existing_identity_behavior():
    addon_module, installed_module = _import_spellings()
    assert addon_module.__file__ == installed_module.__file__
    assert addon_module is not installed_module
    for name in _lease_surface()["current_symbols"]:
        addon_callable = getattr(addon_module, name)
        installed_callable = getattr(installed_module, name)
        assert addon_callable is not installed_callable
        assert addon_callable.__name__ == installed_callable.__name__ == name


def test_every_frozen_lease_rpc_returns_a_fresh_deprecation_result():
    surface = _lease_surface()
    contracts = {
        item["symbol"]: item["parameter_contract"]
        for item in surface["post_cutover_deprecation_contracts"]
    }
    for module in _import_spellings():
        for name, contract in contracts.items():
            first = _representative_call(getattr(module, name), contract)
            second = _representative_call(getattr(module, name), contract)
            assert first == FROZEN_DEPRECATION_RESULT
            assert second == FROZEN_DEPRECATION_RESULT
            assert first is not second


def test_frozen_lease_rpc_module_has_no_live_authority_imports():
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    assert len(imports) == 1
    assert isinstance(imports[0], ast.ImportFrom)
    assert imports[0].module == "typing"
    assert "lease_methods_ops" not in source
