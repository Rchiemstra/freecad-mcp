from __future__ import annotations

import contextlib
import sys
import threading
import uuid
from collections.abc import Callable, Mapping
from typing import Any

from .constants import _LOCAL_SAVE_GUI_TIMEOUT
from .facade_bindings import facade_callable
from .lease_view import _lease_view
from .local_restore_gui import _run_restore_gui_phase


def _runtime_restore_components() -> tuple[Any, Any, Any, Any]:
    """Resolve the bounded in-place restore implementation from the live addon."""

    for module_name in (
        "rpc_server.rpc_server",
        "addon.FreeCADMCP.rpc_server.rpc_server",
    ):
        module = sys.modules.get(module_name)
        if module is None:
            continue
        dispatcher = getattr(module, "gui_dispatcher", None)
        path_resolver = getattr(module, "recovery_snapshot_path", None)
        restore = getattr(module, "restore_snapshot_in_place_gui", None)
        validator = getattr(module, "validate_document_invariants", None)
        if (
            callable(getattr(dispatcher, "submit", None))
            and callable(path_resolver)
            and callable(restore)
            and callable(validator)
        ):
            return dispatcher, path_resolver, restore, validator
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
    """Restore one opaque baseline snapshot without closing the leased proxy."""

    session_uuid, current_view, snapshot_id = _validate_restore_prerequisites(
        lease, service
    )

    if gui_dispatcher is None:
        (
            gui_dispatcher,
            snapshot_path_resolver,
            snapshot_restorer,
            document_validator,
        ) = _runtime_restore_components()
    if not callable(snapshot_path_resolver) or not callable(snapshot_restorer):
        raise RuntimeError("lease baseline snapshot restore is unavailable")
    if not callable(document_validator):
        raise RuntimeError("snapshot post-restore validation is unavailable")
    if not callable(getattr(gui_dispatcher, "submit", None)):
        raise RuntimeError("the FreeCAD GUI dispatcher is not running")

    def restore_gui() -> Mapping[str, Any]:
        return _run_restore_gui_phase(
            service=service,
            document=document,
            session_uuid=session_uuid,
            current_view=current_view,
            snapshot_id=snapshot_id,
            snapshot_path_resolver=snapshot_path_resolver,
            snapshot_restorer=snapshot_restorer,
            document_validator=document_validator,
        )

    submit = gui_dispatcher.submit
    return submit(
        restore_gui,
        timeout=_LOCAL_SAVE_GUI_TIMEOUT,
        request_id=f"local-restore-{uuid.uuid4()}",
    )


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
