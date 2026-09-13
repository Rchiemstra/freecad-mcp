"""Optional local wiring for FreeCAD core's Document Changes controls."""

from __future__ import annotations

from typing import Any

try:
    from automation_pause import (
        request_local_pause_after_current,
        resume_local_agent_writes,
    )
    from automation_pause import (
        status as automation_pause_status,
    )
except ImportError:  # pragma: no cover - package test layout
    from addon.FreeCADMCP.automation_pause import (
        request_local_pause_after_current,
        resume_local_agent_writes,
    )
    from addon.FreeCADMCP.automation_pause import (
        status as automation_pause_status,
    )


def _current_operation_text(pause: dict[str, Any]) -> str:
    operation = pause.get("current_operation")
    if isinstance(operation, dict):
        method = str(operation.get("method") or "write")
        documents = [str(item) for item in operation.get("documents", ()) if item]
        target = f" ({', '.join(documents)})" if documents else ""
        if pause.get("paused"):
            text = f"Pausing after current MCP operation: {method}{target}"
        else:
            text = f"Active MCP operation: {method}{target}"
        return f"{text} — {_native_readiness_text()}"
    if pause.get("paused"):
        return (
            "MCP writes are paused locally; reads remain available. "
            f"— {_native_readiness_text()}"
        )
    last_operation = pause.get("last_operation")
    if isinstance(last_operation, dict):
        method = str(last_operation.get("method") or "write")
        documents = [str(item) for item in last_operation.get("documents", ()) if item]
        target = f" ({', '.join(documents)})" if documents else ""
        return f"Last MCP operation: {method}{target} — {_native_readiness_text()}"
    return f"No active agent operation reported — {_native_readiness_text()}"


def _native_readiness_text() -> str:
    """Read the core's already-public, GUI-thread readiness summary if present."""

    try:
        outcome = _native_readiness()
        if not isinstance(outcome, dict):
            return "mutation readiness unavailable"
        if outcome.get("ready"):
            return "mutation ready"
        active = [
            label
            for key, label in (
                ("pending_transaction", "transaction pending"),
                ("transaction_locked", "transaction locked"),
                ("recomputing", "recomputing"),
                ("must_execute", "recompute required"),
                ("pending_removal", "object removal pending"),
                ("commit_barrier", "commit barrier"),
                ("notification_replay", "notification replay"),
                ("poisoned", "commit poisoned"),
                ("quarantined", "quarantined"),
            )
            if outcome.get(key)
        ]
        return ", ".join(active) if active else "mutation not ready"
    except Exception:
        return "mutation readiness unavailable"


def _native_readiness() -> dict[str, Any] | None:
    """Return validated readiness without making a remote RPC call.

    Use the same fail-closed normalization as mutation admission so a broken
    advertised native getter becomes visible to the local operator instead of
    being mistaken for an older, clean runtime.
    """

    try:
        import FreeCAD

        try:
            from rpc_server.methods.cad_methods_ops.mutation_readiness import (
                document_readiness,
            )
        except ImportError:  # pragma: no cover - package test layout
            from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.mutation_readiness import (
                document_readiness,
            )

        document = FreeCAD.ActiveDocument
        return document_readiness(document) if document is not None else None
    except Exception:
        return None


def _requires_immediate_user_attention(readiness: dict[str, Any] | None) -> bool:
    """Only surface irrecoverable/ownership failures, never normal settling."""

    if readiness is None:
        return False
    reasons = set(readiness.get("reasons") or ())
    if (
        readiness.get("native_readiness_available") is False
        or "native_readiness_unavailable" in reasons
    ):
        return True
    unsafe = bool(
        readiness.get("quarantined")
        or readiness.get("poisoned")
        or readiness.get("collaboration_poisoned")
    )
    if unsafe:
        return True
    # A future/incompatible native runtime can say ``ready: false`` without a
    # recognized reason.  Surface that conservatively, while allowing the
    # ordinary transient settle states to remain non-interrupting.
    recognized_not_ready = (
        readiness.get("pending_transaction")
        or readiness.get("transaction_locked")
        or int(
            readiness.get("booked_transaction_id")
            or readiness.get("booked_transaction")
            or 0
        )
        != 0
        or readiness.get("recomputing")
        or readiness.get("must_execute")
        or readiness.get("pending_removal")
        or readiness.get("commit_barrier")
        or readiness.get("notification_replay")
        or readiness.get("automation_paused")
    )
    return readiness.get("ready") is False and not recognized_not_ready


def _show_document_changes_for_attention(main: Any, qt_widgets: Any) -> bool:
    """Reveal the core panel when it exists; the MCP dock remains a fallback."""

    dock = main.findChild(qt_widgets.QDockWidget, "Document Changes")
    if dock is None:
        return False
    dock.show()
    raise_panel = getattr(dock, "raise_", None)
    if callable(raise_panel):
        raise_panel()
    return True


def _on_pause_toggled(checked: bool) -> None:
    # This callback is attached solely from the local Qt widget.  No public
    # RPC method imports or exposes the resume function.
    if checked:
        request_local_pause_after_current()
    else:
        resume_local_agent_writes()
    try:
        from .refresh import refresh_lock_indicator

        refresh_lock_indicator()
    except Exception:
        pass


def refresh_document_changes_controls() -> bool:
    """Reveal and mirror core controls when this FreeCAD build provides them.

    The MCP Document Lock dock remains the fallback for older builds or when
    the core Document Changes panel has not been constructed.
    """

    try:
        import FreeCADGui
        from PySide import QtWidgets

        main = FreeCADGui.getMainWindow()
    except Exception:
        return False
    if main is None:
        return False
    checkbox = main.findChild(QtWidgets.QCheckBox, "pauseAgentWrites")
    operation_value = main.findChild(QtWidgets.QLabel, "agentOperationValue")
    if checkbox is None and operation_value is None:
        return False

    pause = automation_pause_status()
    if checkbox is not None:
        checkbox.show()
        if not bool(checkbox.property("mcpAutomationPauseConnected")):
            checkbox.toggled.connect(_on_pause_toggled)
            checkbox.setProperty("mcpAutomationPauseConnected", True)
        checkbox.blockSignals(True)
        try:
            checkbox.setChecked(bool(pause["paused"]))
        finally:
            checkbox.blockSignals(False)
        checkbox.setToolTip(
            "New MCP writes are blocked locally; reads remain available."
            if pause["paused"]
            else "Pause new MCP writes after any current operation finishes."
        )
    if operation_value is not None:
        operation_value.setText(_current_operation_text(pause))
        operation_value.setToolTip(
            "Local MCP admission status. This control is never changed by remote RPC."
        )
    if _requires_immediate_user_attention(_native_readiness()):
        _show_document_changes_for_attention(main, QtWidgets)
    return True


__all__ = [
    "_requires_immediate_user_attention",
    "_show_document_changes_for_attention",
    "refresh_document_changes_controls",
]
