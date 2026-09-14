"""Phase 18 tombstones for orphaned lease bootstrap and sidecar helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.lease_runtime import LeaseRuntimeDependencies
from addon.FreeCADMCP.rpc_server.lease_runtime_ops import initialize as initialize_module
from addon.FreeCADMCP.rpc_server.rpc_helpers_ops import document_identity

pytestmark = pytest.mark.unit


class _AuthorityTrap:
    def __getattribute__(self, name: str):
        raise AssertionError(f"tombstone touched retired authority: {name}")


def test_initialize_module_has_no_live_sidecar_or_retention_bootstrap() -> None:
    source = initialize_module.__loader__.get_source(initialize_module.__name__)
    assert source is not None
    for forbidden in (
        "SidecarStore",
        "DocumentLeaseService",
        "bind_lease_retention_predicate",
        "SaveService",
        "import FreeCAD",
        "from FreeCAD",
        "_ensure_lease_watchdog_running",
    ):
        assert forbidden not in source


def test_initialize_document_lease_runtime_is_a_no_op_bootstrap() -> None:
    rpc_mod = LeaseRuntimeDependencies(
        document_identity_service=object(),
        document_lease_service=object(),
        document_lease_runtime_mode="enforce",
        document_lease_runtime_policy=(True, False, False),
        rpc_request_replay_cache=_AuthorityTrap(),
    )

    first = initialize_module.initialize_document_lease_runtime(
        {"document_lease_mode": "enforce"},
        rpc_mod=rpc_mod,
    )
    second = initialize_module.initialize_document_lease_runtime(
        {"document_lease_mode": "off"},
        rpc_mod=rpc_mod,
    )

    assert first is None
    assert second is None
    assert rpc_mod.document_lease_service is not None
    assert rpc_mod.document_lease_runtime_mode == "enforce"
    assert rpc_mod.document_lease_runtime_policy == (True, False, False)


def test_effective_sidecar_block_module_has_no_live_sidecar_store_path() -> None:
    source = document_identity.__loader__.get_source(document_identity.__name__)
    assert source is not None
    assert "SidecarStore" not in source
    assert "sidecar_store" not in source


def test_effective_sidecar_block_is_a_no_op() -> None:
    dependencies = SimpleNamespace(import_document_lease=_AuthorityTrap)

    first = document_identity._effective_sidecar_block(
        object(),
        {"request_id": "historic"},
        dependencies=dependencies,
    )
    second = document_identity._effective_sidecar_block(
        object(),
        {"request_id": "historic"},
        dependencies=dependencies,
    )

    assert first is None
    assert second is None
