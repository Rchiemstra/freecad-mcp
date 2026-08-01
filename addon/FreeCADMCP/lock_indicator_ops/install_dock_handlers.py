from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .formatting import _bounded_text
from .lease_view import _lease_view
from .local_recovery import (
    _acknowledge_selected_dirty,
    _confirmed_foreign_takeover,
    _live_document_for_view,
    _local_recovery_capabilities,
    _v2_lease_service,
)
from .local_save import _runtime_save_components, _start_verified_local_save_and_clear_async
from .refresh import refresh_lock_indicator


@dataclass
class InstallDockContext:
    dock: Any
    selector: Any
    info: Any
    takeover_btn: Any
    save_clear_btn: Any
    restore_btn: Any
    keep_dirty_btn: Any
    bridge: Any
    qt_widgets: Any
    qt_core: Any
    selected_lease: Callable[[], dict[str, Any] | None]
    local_recovery_busy: Callable[[], bool]


def _selected_v2_context(ctx: InstallDockContext) -> tuple[dict[str, Any], Any, Any]:
    lease = ctx.selected_lease()
    if lease is None:
        raise RuntimeError("no document lease is selected")
    view = _lease_view(lease)
    service = _v2_lease_service()
    if service is None or not view["is_v2"] or view["source"] != "local":
        raise RuntimeError("the selected lease is not a local v2 recovery record")
    document = _live_document_for_view(view, service)
    if document is None:
        raise RuntimeError("the selected v2 document is no longer open")
    return lease, service, document


def _execute_v2_takeover(
    ctx: InstallDockContext,
    lease: Mapping[str, Any],
    view: Mapping[str, Any],
    service: Any,
    document: Any,
) -> None:
    if view["source"] == "foreign_recovery":
        _confirmed_foreign_takeover(
            lease,
            service,
            document,
            reason="Confirmed local GUI takeover of dead foreign owner",
        )
        return
    try:
        from document_lease.observer import take_over_selected_document
    except ImportError:
        from addon.FreeCADMCP.document_lease.observer import take_over_selected_document

    result = take_over_selected_document(
        service_provider=lambda: service,
        selected_document_provider=lambda: document,
        reason="Confirmed local GUI takeover",
    )
    if result is None:
        raise RuntimeError("the selected v2 lease is no longer active")


def on_takeover(ctx: InstallDockContext) -> None:
    lease = ctx.selected_lease()
    if lease is None:
        return
    view = _lease_view(lease)
    target = view["doc_key"] or view["document_session_uuid"]
    if not target:
        ctx.info.appendPlainText(
            "Takeover failed: selected record has no document identity"
        )
        return

    dirty_text = "has unsaved changes" if view["dirty"] else "is currently clean"
    baseline_text = (
        "a recovery baseline is available"
        if view["baseline_available"]
        else "no recovery baseline is available"
    )
    owner = _bounded_text(view["agent_id"] or view["client"])
    message = (
        f"Take over {view['filename']} from {owner or 'the current agent'}?\n\n"
        f"The document {dirty_text}, and {baseline_text}.\n"
        "This revokes the current agent credential and requires you to "
        "resolve the document by saving, restoring, or acknowledging dirty state."
    )
    answer = ctx.qt_widgets.QMessageBox.warning(
        ctx.dock,
        "Confirm document takeover",
        message,
        ctx.qt_widgets.QMessageBox.Yes | ctx.qt_widgets.QMessageBox.Cancel,
        ctx.qt_widgets.QMessageBox.Cancel,
    )
    if answer != ctx.qt_widgets.QMessageBox.Yes:
        return
    try:
        service = _v2_lease_service()
        session_uuid = view["document_session_uuid"]
        if service is not None and session_uuid and view["is_v2"]:
            document = _live_document_for_view(view, service)
            if document is None:
                raise RuntimeError("the selected v2 document is no longer open")
            _execute_v2_takeover(ctx, lease, view, service, document)
        else:
            from document_lock import mark_user_intervened

            result = mark_user_intervened(str(target))
            if result is None:
                raise RuntimeError("the selected lease is no longer active")
        refresh_lock_indicator()
    except Exception as exc:
        ctx.info.appendPlainText(f"Takeover failed: {_bounded_text(exc, limit=300)}")


def on_keep_dirty(ctx: InstallDockContext) -> None:
    try:
        if ctx.local_recovery_busy():
            raise RuntimeError("another local recovery action is still running")
        lease, service, document = _selected_v2_context(ctx)
        view = _lease_view(lease)
        if not _local_recovery_capabilities(lease, document)["keep_dirty"]:
            raise RuntimeError(
                "take over the document and leave it dirty before acknowledging it"
            )
        answer = ctx.qt_widgets.QMessageBox.warning(
            ctx.dock,
            "Confirm dirty document acknowledgement",
            (
                f"Keep {view['filename']} open with unsaved changes?\n\n"
                "The agent credential is already revoked. A persistent "
                "UNLOCKED_DIRTY recovery record will continue to block new "
                "agent acquisitions until you save and clear it."
            ),
            ctx.qt_widgets.QMessageBox.Yes | ctx.qt_widgets.QMessageBox.Cancel,
            ctx.qt_widgets.QMessageBox.Cancel,
        )
        if answer != ctx.qt_widgets.QMessageBox.Yes:
            return
        _acknowledge_selected_dirty(lease, service, document)
        refresh_lock_indicator()
    except Exception as exc:
        ctx.info.appendPlainText(
            f"Keep-dirty acknowledgement failed: {_bounded_text(exc, limit=300)}"
        )


def on_save_and_clear(ctx: InstallDockContext) -> None:
    try:
        if ctx.local_recovery_busy():
            raise RuntimeError(
                "another local recovery action is already running for this dock"
            )
        lease, service, document = _selected_v2_context(ctx)
        view = _lease_view(lease)
        if not _local_recovery_capabilities(lease, document)["save_and_clear"]:
            raise RuntimeError(
                "save-and-clear requires a taken-over saved document with a baseline"
            )
        answer = ctx.qt_widgets.QMessageBox.warning(
            ctx.dock,
            "Confirm verified local save",
            (
                f"Save {view['filename']} to its current path, reopen-verify it "
                "with the matching FreeCADCmd worker, and clear its lease?\n\n"
                "The file is compared with the recorded baseline before FreeCAD "
                "writes it. Any conflict, validation error, or sidecar failure "
                "leaves the recovery record in place."
            ),
            ctx.qt_widgets.QMessageBox.Yes | ctx.qt_widgets.QMessageBox.Cancel,
            ctx.qt_widgets.QMessageBox.Cancel,
        )
        if answer != ctx.qt_widgets.QMessageBox.Yes:
            return
        (
            local_save_service,
            expectation_builder,
            worker_validator,
            snapshot_discarder,
            local_gui_dispatcher,
        ) = _runtime_save_components()
        ctx.dock._mcp_local_save_in_progress = True  # type: ignore[attr-defined]
        ctx.save_clear_btn.setEnabled(False)
        ctx.restore_btn.setEnabled(False)
        ctx.keep_dirty_btn.setEnabled(False)
        _start_verified_local_save_and_clear_async(
            lease,
            service,
            document,
            completion_emit=ctx.bridge.local_save_completed.emit,
            save_service=local_save_service,
            expectation_builder=expectation_builder,
            worker_validator=worker_validator,
            snapshot_discarder=snapshot_discarder,
            gui_dispatcher=local_gui_dispatcher,
        )
        ctx.info.appendPlainText(
            "Verified local save started; hashing and reopen validation "
            "are running in the background."
        )
    except Exception as exc:
        ctx.dock._mcp_local_save_in_progress = False  # type: ignore[attr-defined]
        ctx.info.appendPlainText(
            f"Verified save-and-clear failed: {_bounded_text(exc, limit=300)}"
        )
        refresh_lock_indicator()


def on_local_save_completed(ctx: InstallDockContext, outcome: Any) -> None:
    ctx.dock._mcp_local_save_in_progress = False  # type: ignore[attr-defined]
    payload = outcome if isinstance(outcome, Mapping) else {}
    if payload.get("ok"):
        result = payload.get("result", {})
        result = result if isinstance(result, Mapping) else {}
        saved = result.get("save", {})
        saved = saved if isinstance(saved, Mapping) else {}
        ctx.info.appendPlainText(
            "Verified local save completed and the document lease was cleared: "
            + _bounded_text(saved.get("path", "selected document"), limit=260)
        )
    else:
        ctx.info.appendPlainText(
            "Verified save-and-clear failed: "
            + _bounded_text(payload.get("error", "unknown error"), limit=300)
        )
    refresh_lock_indicator()

