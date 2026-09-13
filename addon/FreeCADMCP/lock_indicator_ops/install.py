from __future__ import annotations

from typing import Any

from . import state
from .clickable_status_label import clickable_status_label_type
from .constants import _mcp_dock_features
from .document_changes_controls import refresh_document_changes_controls
from .install_dock_handlers import (
    InstallDockContext,
    on_keep_dirty,
    on_local_save_completed,
    on_save_and_clear,
    on_takeover,
)
from .install_dock_refresh import (
    build_refresh_from_leases,
    build_refresh_selected_detail,
)
from .install_dock_restore_handlers import (
    on_local_restore_completed,
    on_restore_baseline,
)
from .install_wire import (
    mount_dock_widget,
    wire_gui_update_callback,
    wire_refresh_timer,
    wire_status_details_click,
)
from .local_recovery import _connect_queued_qt_signal
from .refresh import _refresh_lock_indicator_now, _refresh_set_status_style
from .refresh_bridge import refresh_bridge_type
from .runtime_bindings import current_runtime_bindings

try:
    from automation_pause_ui_bridge import set_local_pause_refresh
except ImportError:  # pragma: no cover - package test layout
    from addon.FreeCADMCP.automation_pause_ui_bridge import set_local_pause_refresh

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


def install_lock_indicator() -> None:  # noqa: C901
    """Create the permanent status widget and closable detail dock."""

    if state._shared_state.installed:
        return
    bindings = current_runtime_bindings()
    if bindings is None:
        raise RuntimeError("lock indicator runtime bindings are not initialized")
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

    status = clickable_status_label_type(QtWidgets, QtCore)("No agent lock")
    status.setObjectName("McpDocumentLockStatus")
    status.setToolTip("No MCP document lease is active")
    try:
        main.statusBar().addPermanentWidget(status)
    except Exception:
        return
    state._shared_state.status_widget = status
    _refresh_set_status_style(None)

    bridge = refresh_bridge_type(QtCore)(main)
    bridge.refresh_requested.connect(bridge.refresh_now, QtCore.Qt.QueuedConnection)
    state._shared_state.refresh_bridge = bridge
    # Runtime pause admission reaches only this neutral callback.  Emitting the
    # Qt signal keeps UI work on the GUI queue and preserves the one-way local
    # control boundary.
    set_local_pause_refresh(bridge.refresh_requested.emit)

    dock = QtWidgets.QDockWidget("MCP Document Lock", main)
    dock.setObjectName("McpDocumentLockDock")
    dock.setFeatures(_mcp_dock_features(QtWidgets.QDockWidget))
    dock.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)
    dock._mcp_local_save_in_progress = False  # type: ignore[attr-defined]
    dock._mcp_local_restore_in_progress = False  # type: ignore[attr-defined]

    container = QtWidgets.QWidget(dock)
    layout = QtWidgets.QVBoxLayout(container)
    layout.addWidget(QtWidgets.QLabel("Document lease:", container))
    selector = QtWidgets.QComboBox(container)
    selector.setObjectName("McpDocumentLockSelector")
    layout.addWidget(selector)

    info = QtWidgets.QPlainTextEdit(container)
    info.setReadOnly(True)
    info.setMaximumBlockCount(200)
    layout.addWidget(info)

    takeover_btn = QtWidgets.QPushButton(
        "Take over / fence agent for selected document…", container
    )
    save_clear_btn = QtWidgets.QPushButton(
        "Save, verify, and clear selected document…", container
    )
    restore_btn = QtWidgets.QPushButton(
        "Restore baseline for selected document…", container
    )
    keep_dirty_btn = QtWidgets.QPushButton(
        "Keep dirty and acknowledge selected document…", container
    )
    pause_btn = QtWidgets.QPushButton("Pause agent writes", container)

    def toggle_agent_write_pause() -> None:
        if automation_pause_status()["paused"]:
            resume_local_agent_writes()
        else:
            request_local_pause_after_current()
        _refresh_lock_indicator_now()

    def selected_lease() -> dict[str, Any] | None:
        record_id = selector.currentData()
        records = getattr(dock, "_mcp_leases_by_id", {})
        return records.get(str(record_id))

    def local_recovery_busy() -> bool:
        return bool(
            getattr(dock, "_mcp_local_save_in_progress", False)
            or getattr(dock, "_mcp_local_restore_in_progress", False)
        )

    ctx = InstallDockContext(
        dock=dock,
        selector=selector,
        info=info,
        takeover_btn=takeover_btn,
        save_clear_btn=save_clear_btn,
        restore_btn=restore_btn,
        keep_dirty_btn=keep_dirty_btn,
        pause_btn=pause_btn,
        bridge=bridge,
        qt_widgets=QtWidgets,
        qt_core=QtCore,
        selected_lease=selected_lease,
        local_recovery_busy=local_recovery_busy,
        mark_compatibility_lease_user_intervened=(
            bindings.mark_compatibility_lease_user_intervened
        ),
    )

    takeover_btn.clicked.connect(lambda: on_takeover(ctx))
    save_clear_btn.clicked.connect(lambda: on_save_and_clear(ctx))
    restore_btn.clicked.connect(lambda: on_restore_baseline(ctx))
    keep_dirty_btn.clicked.connect(lambda: on_keep_dirty(ctx))
    pause_btn.clicked.connect(toggle_agent_write_pause)
    layout.addWidget(pause_btn)
    for button in (takeover_btn, save_clear_btn, restore_btn, keep_dirty_btn):
        layout.addWidget(button)

    dock.setWidget(container)
    _connect_queued_qt_signal(
        bridge.local_save_completed,
        lambda outcome: on_local_save_completed(ctx, outcome),
        QtCore,
    )
    _connect_queued_qt_signal(
        bridge.local_restore_completed,
        lambda outcome: on_local_restore_completed(ctx, outcome),
        QtCore,
    )

    dock.refresh_from_leases = build_refresh_from_leases(  # type: ignore[attr-defined]
        ctx,
        selected_lease=selected_lease,
        local_recovery_busy=local_recovery_busy,
    )
    selector.currentIndexChanged.connect(
        build_refresh_selected_detail(
            ctx,
            selected_lease=selected_lease,
            local_recovery_busy=local_recovery_busy,
        )
    )

    mount_dock_widget(main, dock, QtCore)
    wire_status_details_click(status)
    wire_refresh_timer(main, QtCore)
    wire_gui_update_callback(bindings.set_compatibility_gui_update_callback)

    state._shared_state.installed = True
    refresh_document_changes_controls()
    _refresh_lock_indicator_now()


__all__ = ["install_lock_indicator"]
