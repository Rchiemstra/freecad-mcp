"""Phase 13 contracts for explicit save lifecycle collaborators."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.lease_methods_ops.lifecycle_dependencies import (
    LifecycleCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.lease_methods_ops.save_public import (
    finalize_document_edit,
    save_document,
)
from addon.FreeCADMCP.rpc_server.methods.lease_methods_ops.save_typed_invoke_helpers import (
    invoke_save_with_capability,
)

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "addon" / "FreeCADMCP" / "rpc_server" / "methods" / "lease_methods_ops"
ASSIGNED = tuple(sorted(OPS.glob("save*.py")))


class _DocumentLock:
    def __init__(self, identity: dict[str, str]) -> None:
        self.identity = identity
        self.release_calls: list[tuple[str, str]] = []

    def get_request_identity(self) -> dict[str, str]:
        return self.identity

    def release_lease(self, doc_key: str, token: str) -> dict[str, object]:
        self.release_calls.append((doc_key, token))
        return {"success": True, "doc_key": doc_key}


def _callable(*_args, **_kwargs):
    return None


def _collaborators(lock: _DocumentLock, **overrides) -> LifecycleCollaborators:
    values = {
        "freecad": object(),
        "import_document_lock": lambda: lock,
        "import_document_lease": _callable,
        "import_core_authority": _callable,
        "document_lease_service": object(),
        "document_identity_service": object(),
        "save_service": object(),
        "credential_for_selector": _callable,
        "live_document_from_selector": _callable,
        "ensure_v2_document": _callable,
        "live_validation_evidence": _callable,
        "discard_terminal_snapshot": _callable,
        "saved_document_expectations": _callable,
        "validate_saved_document_worker": _callable,
        "inspect_references_gui": _callable,
        "redact_rpc_diagnostic": lambda value, **_kwargs: str(value),
        "lease_service_error": lambda exc, **_kwargs: {"success": False, "error": str(exc)},
        "deprecated_force_release_result": _callable,
        "refresh_lock_indicator": _callable,
    }
    values.update(overrides)
    return LifecycleCollaborators(**values)


def test_save_modules_have_no_runtime_locator_or_module_lifecycle_state() -> None:
    assert ASSIGNED
    for path in ASSIGNED:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        assert "_rpc_mod" not in source, path.name
        assert "from document_lease import core_authority" not in source, path.name
        assert "from lock_indicator" not in source, path.name
        assert not any(
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.endswith("_common")
            for node in ast.walk(tree)
        ), path.name
        assert not any(
            isinstance(node, (ast.Assign, ast.AnnAssign)) for node in tree.body
        ), path.name


def test_public_save_and_finalize_use_the_exact_injected_lock_and_indicator() -> None:
    lock = _DocumentLock({"lease_token": "v1-token", "request_id": "request-13"})
    refreshed: list[str] = []
    collaborators = _collaborators(
        lock,
        refresh_lock_indicator=lambda: refreshed.append("refresh"),
    )
    legacy_calls: list[tuple[object, str]] = []
    facade = SimpleNamespace(
        _lifecycle_collaborators=collaborators,
        _run_legacy_save=lambda selector, *, validation_profile: (
            legacy_calls.append((selector, validation_profile))
            or {"success": True, "lease": {"doc_key": "document-13"}}
        ),
        _run_typed_save=lambda *_args, **_kwargs: pytest.fail(
            "v1 identity must not enter typed save"
        ),
    )

    assert save_document(facade, {"document_name": "Doc"})["success"] is True
    finalized = finalize_document_edit(facade, {"document_name": "Doc"})

    assert finalized["released"] is True
    assert legacy_calls == [
        ({"document_name": "Doc"}, "default"),
        ({"document_name": "Doc"}, "default"),
    ]
    assert lock.release_calls == [("document-13", "v1-token")]
    assert refreshed == ["refresh"]
    assert facade._lifecycle_collaborators is collaborators


def test_save_invocation_uses_only_injected_native_capability_and_save_service() -> None:
    calls: list[tuple[str, object]] = []

    class _Capability:
        def __enter__(self):
            calls.append(("enter", None))

        def __exit__(self, *_args):
            calls.append(("exit", None))

    core = SimpleNamespace(
        kinds_for_rpc_method=lambda method, kind: calls.append((method, kind)) or {kind},
        open_mutation_capability=lambda document, **kwargs: (
            calls.append(("capability", (document, kwargs))) or _Capability()
        ),
    )
    save_service = SimpleNamespace(
        invoke_save_gui=lambda document, preflight: calls.append(
            ("save", (document, preflight))
        )
        or "native-save-result"
    )
    collaborators = _collaborators(
        _DocumentLock({}),
        import_core_authority=lambda: core,
        save_service=save_service,
    )
    document = object()
    phase = {"credential": SimpleNamespace(generation=9), "preflight": object()}

    result = invoke_save_with_capability(
        SimpleNamespace(), document, phase, "save", collaborators
    )

    assert result == "native-save-result"
    assert calls == [
        ("save_document", "save"),
        ("capability", (document, {"generation": 9, "kinds": {"save"}})),
        ("enter", None),
        ("save", (document, phase["preflight"])),
        ("exit", None),
    ]
