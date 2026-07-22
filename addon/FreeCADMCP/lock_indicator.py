"""GUI indicators for per-document MCP agent leases.

Lazy PySide imports so the module can be imported without a FreeCAD GUI.
Closing the dock must not release the lock or hide the status-bar widget.
"""

from __future__ import annotations

import time
from typing import Any

_installed = False
_status_widget = None
_dock_widget = None
_refresh_timer = None


def _format_elapsed(seconds: float) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes, sec = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {sec}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def _lease_lines(lease: dict[str, Any]) -> tuple[str, str]:
    """Return (status_bar_text, tooltip)."""
    doc_key = lease.get("doc_key") or ""
    name = lease.get("doc_name") or ""
    filename = name
    if str(doc_key).lower().endswith(".fcstd"):
        from pathlib import Path

        filename = Path(doc_key).name
    op = lease.get("current_operation") or lease.get("state") or ""
    dirty = " — unsaved changes" if lease.get("document_dirty") else ""
    text = f"Agent editing {filename}"
    if op:
        text += f" — {op}"
    text += dirty

    acquired = float(lease.get("acquired_at") or time.time())
    heartbeat = float(lease.get("last_heartbeat") or acquired)
    now = time.time()
    tip_lines = [
        f"Document: {filename}",
        f"Doc name: {name}",
        f"State: {lease.get('state')}",
        f"Agent/client: {lease.get('client') or '(unknown)'}",
        f"Instance: {lease.get('instance_id')}",
        f"PID: {lease.get('pid')}  host: {lease.get('host')}",
        f"Operation: {lease.get('current_operation') or '(idle)'}",
        f"Task: {lease.get('task_description') or '(none)'}",
        f"Held for: {_format_elapsed(now - acquired)}",
        f"Last heartbeat: {_format_elapsed(now - heartbeat)} ago",
        f"Unsaved: {'yes' if lease.get('document_dirty') else 'no'}",
        f"Token: {(lease.get('token') or '')[:8]}…",
    ]
    return text, "\n".join(tip_lines)


def _active_leases() -> list[dict[str, Any]]:
    try:
        from document_lock import list_leases

        return [r.to_dict() for r in list_leases()]
    except Exception:
        return []


def refresh_lock_indicator() -> None:
    """Refresh status-bar text and dock contents from the lease registry."""
    global _status_widget, _dock_widget
    if _status_widget is None:
        return
    leases = _active_leases()
    if not leases:
        _status_widget.setText("No agent lock")
        _status_widget.setToolTip("No MCP document lease is active")
        _status_widget.setVisible(True)
    else:
        preferred = None
        for lease in leases:
            if lease.get("state") in ("USER_INTERVENED", "LOCKED_ERROR"):
                preferred = lease
                break
        preferred = preferred or leases[0]
        text, tip = _lease_lines(preferred)
        if len(leases) > 1:
            text += f" (+{len(leases) - 1} more)"
        _status_widget.setText(f"🔒 {text}")
        _status_widget.setToolTip(tip)
        _status_widget.setVisible(True)

    if _dock_widget is not None and hasattr(_dock_widget, "refresh_from_leases"):
        _dock_widget.refresh_from_leases(leases)


def install_lock_indicator() -> None:
    """Create status-bar permanent widget + closable dock (idempotent)."""
    global _installed, _status_widget, _dock_widget, _refresh_timer
    if _installed:
        return
    try:
        import FreeCADGui
        from PySide import QtCore, QtWidgets
    except ImportError:
        return

    try:
        main = FreeCADGui.getMainWindow()
    except Exception:
        return
    if main is None:
        return

    status = QtWidgets.QLabel("No agent lock")
    status.setObjectName("McpDocumentLockStatus")
    status.setToolTip("No MCP document lease is active")
    try:
        main.statusBar().addPermanentWidget(status)
    except Exception:
        return
    _status_widget = status

    dock = QtWidgets.QDockWidget("MCP Document Lock", main)
    dock.setObjectName("McpDocumentLockDock")
    dock.setFeatures(
        QtWidgets.QDockWidget.DockWidgetClosable
        | QtWidgets.QDockWidget.DockWidgetMovable
        | QtWidgets.QDockWidget.DockWidgetFloatable
    )
    # Closing the dock must NOT release the lock or hide the status-bar widget
    dock.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)

    container = QtWidgets.QWidget(dock)
    layout = QtWidgets.QVBoxLayout(container)
    info = QtWidgets.QPlainTextEdit(container)
    info.setReadOnly(True)
    info.setMaximumBlockCount(200)
    layout.addWidget(info)

    takeover_btn = QtWidgets.QPushButton(
        "Request takeover (mark USER_INTERVENED)", container
    )

    def _on_takeover() -> None:
        leases = _active_leases()
        if not leases:
            return
        try:
            from document_lock import mark_user_intervened

            for lease in leases:
                key = lease.get("doc_key")
                if key:
                    mark_user_intervened(key)
            refresh_lock_indicator()
        except Exception as exc:
            info.appendPlainText(f"Takeover failed: {exc}")

    takeover_btn.clicked.connect(_on_takeover)
    layout.addWidget(takeover_btn)
    dock.setWidget(container)

    def refresh_from_leases(leases: list[dict]) -> None:
        if not leases:
            info.setPlainText("No active MCP document leases.")
            return
        blocks = []
        for lease in leases:
            _text, tip = _lease_lines(lease)
            blocks.append(tip)
            blocks.append("-" * 40)
        info.setPlainText("\n".join(blocks))

    dock.refresh_from_leases = refresh_from_leases  # type: ignore[attr-defined]

    try:
        main.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)
        _dock_widget = dock
    except Exception:
        _dock_widget = None

    timer = QtCore.QTimer(main)
    timer.setInterval(1000)
    timer.timeout.connect(refresh_lock_indicator)
    timer.start()
    _refresh_timer = timer

    try:
        from document_lock import set_gui_update_callback

        def _on_gui_thread() -> None:
            QtCore.QTimer.singleShot(0, refresh_lock_indicator)

        set_gui_update_callback(_on_gui_thread)
    except Exception:
        pass

    _installed = True
    refresh_lock_indicator()
