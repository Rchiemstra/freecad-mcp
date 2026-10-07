"""Turn an async mutation waiter into a terminal result off the GUI thread.

GUI-thread ``commit_native_mutation`` returns ``_AsyncMutationWaiter`` before
the owner thread has finished. Interpreting that object as a dict reports
``uncertain`` while the edit is still running (N6). ``dispatch_gui`` awaits
``await_result`` on the RPC thread; these helpers keep that wait off the GUI
thread and only then build the terminal result.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, Protocol, TypeVar, Union, cast

_T = TypeVar("_T")
_R = TypeVar("_R")
_T_co = TypeVar("_T_co", covariant=True)


class PendingNativeResult(Protocol[_T_co]):
    """A native commit still running on the document owner thread."""

    def await_result(self, timeout: float = 60.0) -> _T_co: ...


NativeOutcome = Union[_T, PendingNativeResult[_T]]
"""A terminal result, or one that ``dispatch_gui`` awaits off the GUI thread."""


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


def _pending_wait(result: object) -> Callable[[float], object] | None:
    if isinstance(result, dict):
        return None
    wait = getattr(result, "await_result", None)
    return cast("Callable[[float], object]", wait) if callable(wait) else None


def defer_native_result(
    native_result: object, interpret: Callable[[object], _T]
) -> NativeOutcome[_T]:
    """Interpret a commit dict now, or after ``await_result`` off the GUI thread."""

    wait = _pending_wait(native_result)
    if wait is None:
        return interpret(native_result)
    await_terminal = wait

    class _PendingNativeCommit:
        def await_result(self, timeout: float = 60.0) -> _T:
            if _on_gui_thread():
                raise RuntimeError(
                    "async mutation waiter must be awaited off the GUI thread"
                )
            return interpret(await_terminal(timeout))

    return _PendingNativeCommit()


def settle_native_commit(
    result: NativeOutcome[_R], finish: Callable[[_R], _T]
) -> NativeOutcome[_T]:
    """Call ``finish`` with the terminal commit value, after an off-GUI wait."""

    wait = _pending_wait(result)
    if wait is not None:
        await_terminal = wait

        class _Settled:
            def await_result(self, timeout: float = 60.0) -> _T:
                return finish(cast("_R", await_terminal(timeout)))

        return _Settled()
    return finish(cast("_R", result))


def continue_after_native_commit(
    result: NativeOutcome[Literal[True] | _T], finish: Callable[[], _T]
) -> NativeOutcome[_T]:
    """Apply ``finish`` once a deferred native commit has resolved to True."""

    wait = _pending_wait(result)
    if wait is not None:
        await_terminal = wait

        class _Continued:
            def await_result(self, timeout: float = 60.0) -> _T:
                resolved = await_terminal(timeout)
                if resolved is not True:
                    return cast("_T", resolved)
                return finish()

        return _Continued()
    if result is not True:
        return cast("_T", result)
    return finish()
