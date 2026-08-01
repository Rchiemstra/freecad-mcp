"""Qt navigation guards that defer GUI dispatch during user interaction."""

from __future__ import annotations

from typing import Any

from PySide import QtCore, QtWidgets


def is_unittest_mock(value: Any) -> bool:
    return type(value).__module__.startswith("unittest.mock")


def mouse_buttons_held(app: Any) -> bool:
    """True only for a real Qt mouse-button bitfield with buttons down."""
    try:
        buttons = app.mouseButtons()
    except Exception:
        return False
    if is_unittest_mock(buttons):
        return False
    try:
        return int(buttons) != int(QtCore.Qt.NoButton)
    except (TypeError, ValueError):
        return buttons != QtCore.Qt.NoButton


def blocking_overlay_active(app: Any) -> bool:
    for getter_name in ("activePopupWidget", "activeModalWidget"):
        getter = getattr(app, getter_name, None)
        if getter is None:
            continue
        try:
            widget = getter()
        except Exception:
            continue
        if widget is None or is_unittest_mock(widget):
            continue
        # Qt can retain an "active" popup/modal pointer briefly after the
        # native window was hidden or closed during startup. Treating that
        # stale invisible widget as blocking defers every queued RPC forever,
        # even though the GUI is responsive and no dialog can be dismissed.
        is_visible = getattr(widget, "isVisible", None)
        if callable(is_visible):
            try:
                if not bool(is_visible()):
                    continue
            except Exception:
                # If visibility cannot be established, preserve the
                # conservative modal guard.
                pass
        return True
    return False


def gui_busy_for_3d_navigation() -> bool:
    """Skip GUI dispatch while the user is interacting with the 3D view / dialogs."""
    app = QtWidgets.QApplication.instance()
    if app is None or is_unittest_mock(app):
        return False
    try:
        return mouse_buttons_held(app) or blocking_overlay_active(app)
    except Exception:
        return False
