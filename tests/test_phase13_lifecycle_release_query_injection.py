"""Phase 13 contracts for explicit release and lifecycle-query collaborators."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.lease_methods_ops.lifecycle_dependencies import (
    LifecycleCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.lease_methods_ops.lock_query import (
    get_document_lock,
    heartbeat_document_lock,
)
from addon.FreeCADMCP.rpc_server.methods.lease_methods_ops.release import (
    force_release_stale_lock,
    release_document_lock,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "addon" / "FreeCADMCP" / "rpc_server" / "methods" / "lease_methods_ops"
ASSIGNED = (
    OPS / "release.py",
    OPS / "release_gui.py",
    OPS / "lock_query.py",
    OPS / "lock_query_helpers.py",
)


class _DocumentLock:
    def __init__(self) -> None:
        self.release_calls: list[tuple[str, str]] = []
        self.heartbeat_calls: list[tuple[str, str, dict[str, object]]] = []

    def is_enabled(self) -> bool:
        return True

    def get_request_identity(self) -> dict[str, str]:
        return {"request_id": "request-13"}

    def release_lease(self, doc_key: str, token: str) -> dict[str, object]:
        self.release_calls.append((doc_key, token))
        return {"success": True, "doc_key": doc_key}

    def heartbeat_lease(self, doc_key, token, **kwargs):
        self.heartbeat_calls.append((doc_key, token, kwargs))
        return {"success": True}


class _LeaseService:
    def __init__(self) -> None:
        self.authorize_calls: list[tuple[object, dict[str, str], set[object]]] = []
        self.release_calls: list[tuple[object, object]] = []
        self.get_effective_calls: list[dict[str, str]] = []
        self.record = {"source": "local", "state": "LOCKED_IDLE"}

    def authorize(self, credential, *, selector, allowed_states):
        self.authorize_calls.append((credential, selector, allowed_states))
        return self.record

    def release_clean(self, credential, *, validation):
        self.release_calls.append((credential, validation))
        return {"terminal": "released"}

    def get_effective(self, selector):
        self.get_effective_calls.append(selector)
        return self.record


class _CoreAuthority:
    def __init__(self) -> None:
        self.documents: list[object] = []

    def sync_clear_from_release(self, document) -> None:
        self.documents.append(document)


def _collaborators(**overrides) -> LifecycleCollaborators:
    lock = overrides.pop("lock", _DocumentLock())
    service = overrides.pop("service", _LeaseService())
    identity = overrides.pop(
        "identity",
        SimpleNamespace(
            session_uuid="session-13",
            canonical_path="C:/model.FCStd",
            to_dict=lambda: {"document_session_uuid": "session-13"},
        ),
    )
    document = overrides.pop("document", object())
    core_authority = overrides.pop("core_authority", _CoreAuthority())
    refreshed: list[str] = overrides.pop("refreshed", [])
    freecad = overrides.pop(
        "freecad",
        SimpleNamespace(
            listDocuments=dict,
            Console=SimpleNamespace(PrintWarning=lambda _message: None),
        ),
    )
    values = {
        "freecad": freecad,
        "import_document_lock": lambda: lock,
        "import_document_lease": lambda: SimpleNamespace(
            LeaseState=SimpleNamespace(LOCKED_IDLE="LOCKED_IDLE"),
            sidecar_path_for=lambda path: f"{path}.lease",
        ),
        "import_core_authority": lambda: core_authority,
        "document_lease_service": service,
        "document_identity_service": object(),
        "save_service": object(),
        "credential_for_selector": lambda *_args: (
            "credential-13",
            identity,
            document,
        ),
        "live_document_from_selector": lambda _selector: (document, identity),
        "ensure_v2_document": lambda _document: identity,
        "live_validation_evidence": lambda *_args: "evidence-13",
        "discard_terminal_snapshot": lambda _terminal: None,
        "saved_document_expectations": lambda *_args: None,
        "validate_saved_document_worker": lambda *_args: None,
        "inspect_references_gui": lambda *_args: None,
        "redact_rpc_diagnostic": lambda value, **_kwargs: str(value),
        "lease_service_error": lambda exc, **_kwargs: {
            "success": False,
            "error": str(exc),
        },
        "deprecated_force_release_result": lambda: {
            "success": False,
            "error_code": "LOCAL_RECOVERY_REQUIRED",
            "error": "local recovery only",
        },
        "refresh_lock_indicator": lambda: refreshed.append("refresh"),
    }
    values.update(overrides)
    collaborators = LifecycleCollaborators(**values)
    return collaborators


def _facade(collaborators: LifecycleCollaborators):
    checkpoints: list[str] = []
    touched: list[tuple[object, object]] = []
    return SimpleNamespace(
        _lifecycle_collaborators=collaborators,
        _current_inflight=lambda: None,
        _request_checkpoint=lambda name: checkpoints.append(name),
        _dispatch_gui=lambda task, **_kwargs: task(),
        _touch_inflight_credential=lambda credential, inflight: touched.append(
            (credential, inflight)
        ),
        EXECUTE_TIMEOUT=120,
        checkpoints=checkpoints,
        touched=touched,
    )


def test_assigned_modules_have_no_rpc_locator_or_top_level_runtime_state() -> None:
    for path in ASSIGNED:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        assert "_rpc_mod" not in source, path.name
        assert not any(
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.endswith("_common")
            for node in ast.walk(tree)
        ), path.name
        assert not any(isinstance(node, ast.Assign) for node in tree.body), path.name


def test_release_uses_exact_injected_lifecycle_identities() -> None:
    lock = _DocumentLock()
    service = _LeaseService()
    core_authority = _CoreAuthority()
    discarded: list[object] = []
    collaborators = _collaborators(
        lock=lock,
        service=service,
        core_authority=core_authority,
        discard_terminal_snapshot=discarded.append,
    )
    facade = _facade(collaborators)

    result = release_document_lock(
        facade,
        selector={"document_session_uuid": "session-13"},
    )

    assert result == {"success": True, "lease": {"terminal": "released"}}
    assert facade.checkpoints == ["release_start"]
    assert service.authorize_calls == [
        ("credential-13", {"document_session_uuid": "session-13"}, {"LOCKED_IDLE"})
    ]
    assert service.release_calls == [("credential-13", "evidence-13")]
    assert len(core_authority.documents) == 1
    assert discarded == [{"terminal": "released"}]
    assert facade.touched == [("credential-13", None)]


def test_query_and_v1_heartbeat_use_only_injected_routes() -> None:
    lock = _DocumentLock()
    service = _LeaseService()
    refreshed: list[str] = []
    collaborators = _collaborators(
        lock=lock,
        service=service,
        refreshed=refreshed,
    )
    facade = _facade(collaborators)

    queried = get_document_lock(facade, selector={"document_session_uuid": "session-13"})
    assert heartbeat_document_lock(
        facade,
        "legacy-key",
        "secret-token",
        current_operation="secret-token active",
    ) == {"success": True}

    assert queried == {
        "success": True,
        "locked": True,
        "source": "local",
        "lease": service.record,
    }
    assert service.get_effective_calls == [{"document_session_uuid": "session-13"}]
    assert lock.heartbeat_calls == [
        (
            "legacy-key",
            "secret-token",
            {
                "current_operation": "<redacted> active",
                "state": None,
                "document_dirty": None,
            },
        )
    ]
    assert refreshed == ["refresh"]


def test_v1_release_and_deprecation_tombstone_add_no_lifecycle_policy() -> None:
    lock = _DocumentLock()
    refreshed: list[str] = []
    tombstone = {
        "success": False,
        "error_code": "LOCAL_RECOVERY_REQUIRED",
        "error": "injected tombstone",
    }
    deprecation_calls: list[str] = []

    def deprecated_result():
        deprecation_calls.append("force_release")
        return tombstone

    collaborators = _collaborators(
        lock=lock,
        refreshed=refreshed,
        deprecated_force_release_result=deprecated_result,
    )
    facade = _facade(collaborators)

    released = release_document_lock(facade, "legacy-key", "legacy-token")
    deprecated = force_release_stale_lock(facade, "legacy-key")

    assert released == {"success": True, "doc_key": "legacy-key"}
    assert lock.release_calls == [("legacy-key", "legacy-token")]
    assert refreshed == ["refresh"]
    assert deprecated is tombstone
    assert deprecation_calls == ["force_release"]
