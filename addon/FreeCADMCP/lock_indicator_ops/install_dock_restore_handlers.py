from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .formatting import _bounded_text
from .install_dock_handlers import InstallDockContext, _selected_v2_context
from .lease_view import _lease_view
from .local_recovery import _local_recovery_capabilities
from .local_restore import _runtime_restore_components, _start_local_baseline_restore_async
from .refresh import refresh_lock_indicator

try:
    from document_state import document_modified_state
except ImportError:
    from addon.FreeCADMCP.document_state import document_modified_state


def on_restore_baseline(ctx: InstallDockContext) -> None:
    try:
        if ctx.local_recovery_busy():
            raise RuntimeError(
                "another local recovery action is already running for this dock"
            )
        lease, service, document = _selected_v2_context(ctx)
        view = _lease_view(lease)
        if not _local_recovery_capabilities(lease, document)["restore_baseline"]:
            raise RuntimeError(
                "restore requires a taken-over document with a lease snapshot"
            )
        modified_state = document_modified_state(document)
        if modified_state is True:
            dirty_text = "currently has unsaved changes"
        elif modified_state is False:
            dirty_text = "is currently clean"
        else:
            dirty_text = "has an unknown modified state"
        answer = ctx.qt_widgets.QMessageBox.warning(
            ctx.dock,
            "Confirm baseline restore",
            (
                f"Replace the in-memory contents of {view['filename']} with "
                f"its lease baseline?\n\nThe document {dirty_text}. This action "
                "does not overwrite the source FCStd or close/reopen the document. "
                "The same session UUID and recovery lease remain active, and the "
                "restored document stays dirty until a verified save-and-clear."
            ),
            ctx.qt_widgets.QMessageBox.Yes | ctx.qt_widgets.QMessageBox.Cancel,
            ctx.qt_widgets.QMessageBox.Cancel,
        )
        if answer != ctx.qt_widgets.QMessageBox.Yes:
            return
        (
            restore_dispatcher,
            snapshot_path_resolver,
            snapshot_restorer,
            document_validator,
        ) = _runtime_restore_components()
        ctx.dock._mcp_local_restore_in_progress = True  # type: ignore[attr-defined]
        ctx.save_clear_btn.setEnabled(False)
        ctx.restore_btn.setEnabled(False)
        ctx.keep_dirty_btn.setEnabled(False)
        _start_local_baseline_restore_async(
            lease,
            service,
            document,
            completion_emit=ctx.bridge.local_restore_completed.emit,
            gui_dispatcher=restore_dispatcher,
            snapshot_path_resolver=snapshot_path_resolver,
            snapshot_restorer=snapshot_restorer,
            document_validator=document_validator,
        )
        ctx.info.appendPlainText(
            "Lease baseline restore started; the source file remains untouched."
        )
    except Exception as exc:
        ctx.dock._mcp_local_restore_in_progress = False  # type: ignore[attr-defined]
        ctx.info.appendPlainText(
            f"Baseline restore failed: {_bounded_text(exc, limit=300)}"
        )
        refresh_lock_indicator()


def on_local_restore_completed(ctx: InstallDockContext, outcome: Any) -> None:
    ctx.dock._mcp_local_restore_in_progress = False  # type: ignore[attr-defined]
    payload = outcome if isinstance(outcome, Mapping) else {}
    if payload.get("ok"):
        result = payload.get("result", {})
        result = result if isinstance(result, Mapping) else {}
        ctx.info.appendPlainText(
            "Lease baseline restored in place; session and lease preserved: "
            + _bounded_text(
                result.get("document_session_uuid", "selected document"),
                limit=100,
            )
        )
    else:
        ctx.info.appendPlainText(
            "Baseline restore failed: "
            + _bounded_text(payload.get("error", "unknown error"), limit=300)
        )
    refresh_lock_indicator()
