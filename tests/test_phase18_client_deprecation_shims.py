"""Phase 18 contracts for frozen client-side lease authority adapters."""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import pytest

from freecad_mcp.lease_manager_ops.lease_client_manager import LeaseClientManager
from freecad_mcp.lease_manager_ops.lease_client_manager import (
    bind_lease_client_manager,
)
from freecad_mcp.lease_manager_ops.stale_lease_recovery_orchestrator import (
    StaleLeaseRecoveryOrchestrator,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATHS = (
    ROOT / "src/freecad_mcp/lease_manager_ops/lease_client_manager.py",
    ROOT
    / "src/freecad_mcp/lease_manager_ops/stale_lease_recovery_orchestrator.py",
)
EXPECTED_RESULT = {
    "success": False,
    "ok": False,
    "error_code": "LEGACY_LEASE_AUTHORITY_REMOVED",
    "error": "Document authority is owned by native FreeCAD collaboration.",
}
COMPATIBILITY_MODULES = (
    "freecad_mcp.lease_manager_ops.lease_client_manager_init",
    "freecad_mcp.lease_manager_ops.lease_client_credential_ops",
    "freecad_mcp.lease_manager_ops.lease_client_heartbeat_ops",
    "freecad_mcp.lease_manager_ops.lease_client_status_ops",
    "freecad_mcp.lease_manager",
)


def _parameter_contract(callable_object):
    return tuple(
        (parameter.name, parameter.kind, parameter.default)
        for parameter in inspect.signature(callable_object).parameters.values()
    )


def test_deprecation_adapters_retain_exact_manifest_signatures():
    assert _parameter_contract(LeaseClientManager) == (
        ("args", inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.empty),
        ("kwargs", inspect.Parameter.VAR_KEYWORD, inspect.Parameter.empty),
    )
    assert _parameter_contract(StaleLeaseRecoveryOrchestrator) == (
        ("stale_after_seconds", inspect.Parameter.KEYWORD_ONLY, 90.0),
        ("blocking_timeout_s", inspect.Parameter.KEYWORD_ONLY, 120.0),
    )


def test_historic_binder_retains_signature_and_is_a_no_op():
    sentinel = object()

    assert _parameter_contract(bind_lease_client_manager) == (
        (
            "LeaseClientManager",
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.empty,
        ),
    )
    assert bind_lease_client_manager(sentinel) is None


def test_historic_compatibility_modules_remain_importable():
    imported = tuple(importlib.import_module(name) for name in COMPATIBILITY_MODULES)

    assert all(module is not None for module in imported)
    public_module = imported[-1]
    assert public_module.LeaseClientManager is LeaseClientManager
    assert (
        public_module.StaleLeaseRecoveryOrchestrator
        is StaleLeaseRecoveryOrchestrator
    )


@pytest.mark.parametrize(
    "adapter, args, kwargs",
    (
        (LeaseClientManager, ("ignored",), {"session_token": "not-retained"}),
        (StaleLeaseRecoveryOrchestrator, (), {}),
        (
            StaleLeaseRecoveryOrchestrator,
            (),
            {"stale_after_seconds": 1.0, "blocking_timeout_s": 2.0},
        ),
    ),
)
def test_deprecation_adapters_return_fresh_exact_results(adapter, args, kwargs):
    first = adapter(*args, **kwargs)
    second = adapter(*args, **kwargs)

    assert first == EXPECTED_RESULT
    assert second == EXPECTED_RESULT
    assert first is not second


def test_deprecation_modules_have_no_live_authority_imports_or_state():
    for path in MODULE_PATHS:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

        imports = tuple(
            node
            for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom))
        )
        assert all(
            isinstance(node, ast.ImportFrom) and node.module == "__future__"
            for node in imports
        )
        assert not any(isinstance(node, ast.ClassDef) for node in tree.body)
        assert not any(
            isinstance(node, (ast.AsyncFunctionDef, ast.Await, ast.With, ast.AsyncWith))
            for node in ast.walk(tree)
        )
