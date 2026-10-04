"""Turn an async mutation waiter into a terminal result off the GUI thread.

GUI-thread ``commit_native_mutation`` returns ``_AsyncMutationWaiter`` before
the owner thread has finished. Interpreting that object as a dict reports
``uncertain`` while the edit is still running (N6). ``dispatch_gui`` awaits
``await_result`` on the RPC thread; these helpers keep that wait off the GUI
thread and only then build the terminal result.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

_T = TypeVar("_T")


def _on_gui_thread() -> bool:
    try:
        from PySide import QtCore
    except ImportError:
        try:
            from PySide6 import QtCore
        except ImportError:
            return False
    app = QtCore.QCoreApplication.instance()
    if app is None:
        return False
    return QtCore.QThread.currentThread() is app.thread()


def defer_native_result(native_result: object, interpret: Callable[[object], _T]) -> object:
    """Interpret a commit dict now, or after ``await_result`` off the GUI thread."""

    wait = getattr(native_result, "await_result", None)
    if not callable(wait):
        return interpret(native_result)

    class _PendingNativeCommit:
        def await_result(self, timeout: float = 60.0) -> _T:
            if _on_gui_thread():
                raise RuntimeError(
                    "async mutation waiter must be awaited off the GUI thread"
                )
            return interpret(wait(timeout))

    return _PendingNativeCommit()


def settle_native_commit(result: object, finish: Callable[[object], _T]) -> object:
    """Call ``finish`` with the terminal commit value, after an off-GUI wait."""

    wait = getattr(result, "await_result", None)
    if callable(wait) and not isinstance(result, dict):

        class _Settled:
            def await_result(self, timeout: float = 60.0) -> _T:
                return finish(wait(timeout))

        return _Settled()
    return finish(result)


def continue_after_native_commit(result: object, finish: Callable[[], _T]) -> object:
    """Apply ``finish`` once a deferred native commit has resolved to True."""

    wait = getattr(result, "await_result", None)
    if callable(wait) and not isinstance(result, dict):

        class _Continued:
            def await_result(self, timeout: float = 60.0) -> object:
                resolved = wait(timeout)
                if resolved is not True:
                    return resolved
                return finish()

        return _Continued()
    if result is not True:
        return result
    return finish()
