"""Phase 18 regressions for tombstoned addon lease-authority corpses."""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.helpers.architecture_baseline import FROZEN_DEPRECATION_RESULT
from tests.helpers.runtime_bootstrap import bootstrap_unit_test_runtime

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
ADDON = ROOT / "addon" / "FreeCADMCP"

CORE_AUTHORITY_OPS_ROOT = ADDON / "document_lease" / "core_authority_ops"
REMOVED_SIDECAR_WRITE_HELPERS = (
    ADDON / "document_lease" / "sidecar_ops" / "guard.py",
    ADDON / "document_lease" / "sidecar_ops" / "cas.py",
)

AUTHORITY_CORPSE_PATHS = (
    ADDON / "document_lease" / "core_authority.py",
    ADDON
    / "rpc_server"
    / "methods"
    / "dispatch_helpers_ops"
    / "dispatch_gui_lease_enforced.py",
    ADDON / "document_lease" / "observer_ops" / "registration.py",
    ADDON / "document_lease" / "observer_ops" / "app_observer.py",
    ADDON / "lock_indicator_ops" / "local_recovery.py",
    ADDON / "lock_indicator_ops" / "local_save.py",
    ADDON / "lock_indicator_ops" / "local_restore.py",
    ADDON / "lock_indicator_ops" / "local_restore_gui.py",
    ADDON / "document_lease" / "sidecar_ops" / "store_create.py",
    ADDON / "document_lease" / "sidecar_ops" / "store_replace.py",
    ADDON / "document_lease" / "sidecar_ops" / "store_delete.py",
)


def _assert_no_freecad_imports(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("FreeCAD")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not module.startswith("FreeCAD")


@pytest.fixture(autouse=True)
def _bootstrap_runtime() -> None:
    bootstrap_unit_test_runtime()


def test_core_authority_exports_are_frozen_and_do_not_touch_freecad():
    from addon.FreeCADMCP.document_lease import core_authority

    document = MagicMock()
    document.setMutationOwner = MagicMock()
    document.openMutationCapability = MagicMock()

    assert core_authority.set_mcp_owner(document, generation=3) is False
    assert core_authority.bump_takeover(document) is None
    assert core_authority.core_authority_available(document) is False
    assert core_authority.sync_gui_lease_takeover(document) is False
    with core_authority.open_mutation_capability(document, generation=1) as capsule:
        assert capsule is None
    document.setMutationOwner.assert_not_called()
    document.openMutationCapability.assert_not_called()
    _assert_no_freecad_imports(ADDON / "document_lease" / "core_authority.py")


def test_dispatch_gui_lease_enforced_returns_frozen_deprecation():
    from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops import (
        dispatch_gui_lease_enforced,
    )

    result = dispatch_gui_lease_enforced.run_enforced_lease_service_task(
        None,
        MagicMock(),
        lambda: "task",
        {"method": "mutate"},
        None,
        completion_lock=MagicMock(),
        completion_handoff={"held": False},
    )

    assert result == FROZEN_DEPRECATION_RESULT


def test_observer_takeover_paths_do_not_call_lease_service():
    from addon.FreeCADMCP.document_lease.observer import take_over_selected_document
    from addon.FreeCADMCP.document_lease.observer_ops.app_observer import (
        LeaseObserver,
    )

    service = MagicMock()
    document = MagicMock(Name="Doc")
    identity = MagicMock(session_uuid="uuid-1")

    assert (
        take_over_selected_document(
            service_provider=lambda: service,
            selected_document_provider=lambda: document,
        )
        is None
    )
    service.takeover.assert_not_called()

    observer = LeaseObserver(
        service_provider=lambda: service,
        selected_document_provider=lambda: document,
    )
    assert (
        observer._takeover_unscoped_change(
            service,
            identity,
            document,
            kind="manual",
            detail="test",
            dirty=False,
        )
        is None
    )
    service.takeover.assert_not_called()


@pytest.mark.parametrize(
    "module_name, callable_name, args, kwargs",
    (
        (
            "addon.FreeCADMCP.lock_indicator_ops.local_recovery",
            "_confirmed_foreign_takeover",
            ({"lease_id": "l1"}, MagicMock(), MagicMock()),
            {"reason": "test"},
        ),
        (
            "addon.FreeCADMCP.lock_indicator_ops.local_recovery",
            "_acknowledge_selected_dirty",
            ({"lease_id": "l1"}, MagicMock(), MagicMock()),
            {},
        ),
        (
            "addon.FreeCADMCP.lock_indicator_ops.local_save",
            "_verified_local_save_and_clear",
            ({"lease_id": "l1"}, MagicMock(), MagicMock()),
            {},
        ),
        (
            "addon.FreeCADMCP.lock_indicator_ops.local_restore",
            "_restore_local_baseline",
            ({"lease_id": "l1"}, MagicMock(), MagicMock()),
            {},
        ),
        (
            "addon.FreeCADMCP.lock_indicator_ops.local_restore_gui",
            "_run_restore_gui_phase",
            (),
            {
                "service": MagicMock(),
                "document": MagicMock(),
                "session_uuid": "uuid-1",
                "current_view": {"lease_id": "l1", "snapshot_id": "snap"},
                "snapshot_id": "snap",
                "snapshot_path_resolver": MagicMock(),
                "snapshot_restorer": MagicMock(),
                "document_validator": MagicMock(),
            },
        ),
    ),
)
def test_lock_indicator_recovery_paths_return_frozen_deprecation(
    module_name, callable_name, args, kwargs
):
    import importlib

    module = importlib.import_module(module_name)
    result = getattr(module, callable_name)(*args, **kwargs)
    assert result == FROZEN_DEPRECATION_RESULT


def test_sidecar_write_paths_raise_legacy_authority_error():
    from addon.FreeCADMCP.document_lease.model import LeaseRecord
    from addon.FreeCADMCP.document_lease.sidecar_ops import (
        store_create,
        store_delete,
        store_replace,
    )
    from addon.FreeCADMCP.document_lease.sidecar_ops.io import write_temp
    from addon.FreeCADMCP.document_lease.sidecar_types.sidecar_error import (
        SidecarError,
    )

    record = MagicMock(spec=LeaseRecord)
    sidecar = Path("/tmp/example.FCM.json")
    message = "LEGACY_LEASE_AUTHORITY_REMOVED"

    for writer in (
        lambda: store_create.create_sidecar(
            sidecar,
            record,
            max_bytes=1024,
            strict_permissions=True,
            persist_task_summary=False,
        ),
        lambda: store_replace.replace_sidecar(
            sidecar,
            record,
            expected=record,
            max_bytes=1024,
            strict_permissions=True,
            persist_task_summary=False,
        ),
        lambda: store_delete.delete_sidecar(
            sidecar,
            expected=record,
            max_bytes=1024,
            strict_permissions=True,
        ),
        lambda: write_temp(sidecar, b"{}", strict_permissions=True),
    ):
        with pytest.raises(SidecarError) as exc_info:
            writer()
        assert message in str(exc_info.value)


def test_authority_corpse_modules_avoid_live_freecad_imports():
    for path in AUTHORITY_CORPSE_PATHS:
        _assert_no_freecad_imports(path)


def test_core_authority_ops_package_is_removed():
    assert not CORE_AUTHORITY_OPS_ROOT.exists()


def test_core_authority_ops_cannot_be_imported():
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("addon.FreeCADMCP.document_lease.core_authority_ops")


@pytest.mark.parametrize(
    "module_suffix",
    (
        "owner",
        "capability",
        "lease_sync",
        "document",
        "kinds",
    ),
)
def test_core_authority_ops_submodules_cannot_be_imported(module_suffix: str):
    import importlib

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(
            f"addon.FreeCADMCP.document_lease.core_authority_ops.{module_suffix}"
        )


def test_sidecar_write_guard_and_cas_helpers_are_removed():
    for path in REMOVED_SIDECAR_WRITE_HELPERS:
        assert not path.exists()
