from __future__ import annotations

import contextlib
import threading
import uuid
from collections.abc import Callable, Mapping
from typing import Any

from .constants import _LOCAL_SAVE_GUI_TIMEOUT
from .facade_bindings import facade_callable
from .lease_view import _lease_view
from .runtime_bindings import current_runtime_bindings

_LEGACY_MESSAGE = (
    "Document authority is owned by native FreeCAD collaboration."
)


def _legacy_lease_authority_removed() -> dict[str, object]:
    return {
        "success": False,
        "ok": False,
        "error_code": "LEGACY_LEASE_AUTHORITY_REMOVED",
        "error": _LEGACY_MESSAGE,
    }


def _runtime_save_components() -> tuple[Any, Any, Any, Any, Any]:
    bindings = current_runtime_bindings()
    if bindings is not None:
        save = bindings.current_save_service()
        dispatcher = bindings.current_gui_dispatcher()
        if save is not None and callable(getattr(dispatcher, "submit", None)):
            return (
                save,
                bindings.saved_document_expectations,
                bindings.validate_saved_document_worker,
                bindings.discard_terminal_snapshot,
                dispatcher,
            )
    raise RuntimeError(
        "verified local save is unavailable because the typed save/worker service "
        "and GUI dispatcher are not running"
    )


def _submit_local_save_gui(dispatcher: Any, task: Callable[[], Any]) -> Any:
    """Submit one bounded save phase to the already-running GUI dispatcher."""

    submit = getattr(dispatcher, "submit", None)
    if not callable(submit):
        raise RuntimeError("the FreeCAD GUI dispatcher is not running")
    return submit(
        task,
        timeout=_LOCAL_SAVE_GUI_TIMEOUT,
        request_id=f"local-save-{uuid.uuid4()}",
    )


def _inspect_local_save_document_gui(
    service: Any,
    document: Any,
    *,
    session_uuid: str,
) -> Any:
    """Re-resolve the exact live proxy from inside a GUI-dispatched phase."""

    identity_service = getattr(service, "identity_service", None)
    inspect = getattr(identity_service, "inspect_registered_document", None)
    if not callable(inspect):
        raise RuntimeError("live document identity validation is unavailable")
    identity = inspect(session_uuid, document)
    if str(getattr(identity, "session_uuid", "") or "") != session_uuid:
        raise RuntimeError("the live document session identity changed")
    return identity


def _resolve_save_prerequisites(
    lease: Mapping[str, Any], service: Any
) -> tuple[Mapping[str, Any], Any, str, str, Mapping[str, Any]]:
    view = _lease_view(lease)
    session_uuid = view["document_session_uuid"]
    if not session_uuid or view["source"] != "local" or not view["is_v2"]:
        raise RuntimeError("save-and-clear is available only for a local v2 record")
    state = view["state"].upper()
    if state not in {"USER_INTERVENED", "UNLOCKED_DIRTY"}:
        raise RuntimeError("take over the selected document before saving and clearing")

    current = service.get({"document_session_uuid": session_uuid})
    baseline_payload = (
        current.get("document_state", {}).get("baseline")
        if isinstance(current, Mapping)
        else None
    )
    if not baseline_payload:
        raise RuntimeError(
            "the selected document has no saved baseline; guarded Save As recovery is required"
        )
    try:
        from document_lease.model import FileBaseline
    except ImportError:
        from addon.FreeCADMCP.document_lease.model import FileBaseline

    expected_baseline = FileBaseline.from_dict(baseline_payload)
    if expected_baseline is None:
        raise RuntimeError("the selected document baseline is invalid")
    current_document = current.get("document", {})
    expected_path = (
        current_document.get("canonical_path")
        if isinstance(current_document, Mapping)
        else None
    )
    if not expected_path:
        raise RuntimeError(
            "the selected document has no current saved path; guarded Save As recovery is required"
        )
    return current, expected_baseline, str(expected_path), session_uuid, view


def _capture_save_gui_context(
    *,
    service: Any,
    document: Any,
    session_uuid: str,
    view: Mapping[str, Any],
    expected_path: str,
    expected_comparison_key: str | None,
    gui_dispatcher: Any,
    expectation_builder: Any,
) -> Mapping[str, Any]:
    def capture_gui_context() -> Mapping[str, Any]:
        identity = _inspect_local_save_document_gui(
            service,
            document,
            session_uuid=session_uuid,
        )
        live_path = str(getattr(identity, "canonical_path", "") or "")
        live_comparison = str(getattr(identity, "comparison_key", "") or "")
        if not live_path:
            raise RuntimeError(
                "the live document no longer has a saved path; guarded Save As "
                "recovery is required"
            )
        if expected_comparison_key:
            if live_comparison != str(expected_comparison_key):
                raise RuntimeError("the live document path changed before save")
        elif live_path != str(expected_path):
            raise RuntimeError("the live document path changed before save")
        return {
            "source_path": live_path,
            "document_name": str(
                getattr(identity, "name", "")
                or getattr(document, "Name", "")
                or view["doc_name"]
            ),
            "validation_expectations": expectation_builder(document),
        }

    return _submit_local_save_gui(gui_dispatcher, capture_gui_context)


def _verified_local_save_and_clear(
    lease: Mapping[str, Any],
    service: Any,
    document: Any,
    *,
    save_service: Any | None = None,
    expectation_builder: Any | None = None,
    worker_validator: Any | None = None,
    snapshot_discarder: Any | None = None,
    gui_dispatcher: Any | None = None,
) -> Mapping[str, Any]:
    """Return the frozen result for retired local save-and-clear authority."""

    del (
        lease,
        service,
        document,
        save_service,
        expectation_builder,
        worker_validator,
        snapshot_discarder,
        gui_dispatcher,
    )
    return _legacy_lease_authority_removed()


def _start_verified_local_save_and_clear_async(
    lease: Mapping[str, Any],
    service: Any,
    document: Any,
    *,
    completion_emit: Callable[[Mapping[str, Any]], None],
    thread_factory: Callable[..., Any] = threading.Thread,
    **pipeline_dependencies: Any,
) -> Any:
    if not callable(completion_emit):
        raise TypeError("completion_emit must be callable")

    def run() -> None:
        save_and_clear = facade_callable(
            "_verified_local_save_and_clear",
            _verified_local_save_and_clear,
        )
        try:
            result = save_and_clear(
                lease,
                service,
                document,
                **pipeline_dependencies,
            )
        except Exception as exc:
            outcome: Mapping[str, Any] = {
                "ok": False,
                "error": str(exc),
                "error_type": type(exc).__name__,
            }
        else:
            outcome = {"ok": True, "result": result}
        with contextlib.suppress(RuntimeError):
            completion_emit(outcome)

    worker = thread_factory(
        target=run,
        name="FreeCADMCP-local-save-recovery",
        daemon=True,
    )
    worker.start()
    return worker
