from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable, Mapping
from typing import Any

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


def _runtime_restore_components() -> tuple[Any, Any, Any, Any]:
    """Return the explicitly composed in-place restore implementation."""

    bindings = current_runtime_bindings()
    if bindings is not None:
        dispatcher = bindings.current_gui_dispatcher()
        if callable(getattr(dispatcher, "submit", None)):
            return (
                dispatcher,
                bindings.recovery_snapshot_path,
                bindings.restore_snapshot_in_place_gui,
                bindings.validate_document_invariants,
            )
    raise RuntimeError(
        "baseline restore is unavailable because the lease snapshot service "
        "and GUI dispatcher are not running"
    )


def _validate_restore_prerequisites(
    lease: Mapping[str, Any], service: Any
) -> tuple[str, Mapping[str, Any], str]:
    selected_view = _lease_view(lease)
    session_uuid = selected_view["document_session_uuid"]
    if (
        not session_uuid
        or selected_view["source"] != "local"
        or not selected_view["is_v2"]
    ):
        raise RuntimeError("baseline restore is available only for a local v2 record")
    if selected_view["state"].upper() not in {
        "USER_INTERVENED",
        "UNLOCKED_DIRTY",
    }:
        raise RuntimeError("take over the selected document before restoring it")

    current = service.get({"document_session_uuid": session_uuid})
    if not isinstance(current, Mapping):
        raise RuntimeError("the selected recovery record is no longer active")
    current_view = _lease_view(current)
    if current_view["lease_id"] != selected_view["lease_id"]:
        raise RuntimeError("the selected recovery record changed before restore")
    if current_view["state"].upper() not in {
        "USER_INTERVENED",
        "UNLOCKED_DIRTY",
    }:
        raise RuntimeError("the selected recovery record no longer permits restore")
    snapshot_id = current_view["snapshot_id"]
    if not snapshot_id:
        raise RuntimeError("the selected lease has no recovery baseline snapshot")
    return session_uuid, current_view, snapshot_id


def _restore_local_baseline(
    lease: Mapping[str, Any],
    service: Any,
    document: Any,
    *,
    gui_dispatcher: Any | None = None,
    snapshot_path_resolver: Any | None = None,
    snapshot_restorer: Any | None = None,
    document_validator: Any | None = None,
) -> Mapping[str, Any]:
    """Return the frozen result for retired baseline-restore authority."""

    del (
        lease,
        service,
        document,
        gui_dispatcher,
        snapshot_path_resolver,
        snapshot_restorer,
        document_validator,
    )
    return _legacy_lease_authority_removed()


def _start_local_baseline_restore_async(
    lease: Mapping[str, Any],
    service: Any,
    document: Any,
    *,
    completion_emit: Callable[[Mapping[str, Any]], None],
    thread_factory: Callable[..., Any] = threading.Thread,
    **restore_dependencies: Any,
) -> Any:
    """Run restore orchestration off Qt and queue its result through a signal."""

    if not callable(completion_emit):
        raise TypeError("completion_emit must be callable")

    def run() -> None:
        restore_baseline = facade_callable(
            "_restore_local_baseline",
            _restore_local_baseline,
        )
        try:
            result = restore_baseline(
                lease,
                service,
                document,
                **restore_dependencies,
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
        name="FreeCADMCP-local-baseline-restore",
        daemon=True,
    )
    worker.start()
    return worker
