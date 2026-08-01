from __future__ import annotations

from .document_lock_observer import DocumentLockObserver
from .settings import is_enabled

_observer_registered = False


def register_observer() -> None:
    """Register DocumentLockObserver when enable_document_lock is true."""
    global _observer_registered
    if _observer_registered:
        return
    if not is_enabled():
        return
    try:
        import FreeCAD

        observer = DocumentLockObserver()
        FreeCAD.addDocumentObserver(observer)
        FreeCAD._mcp_document_lock_observer = observer
        _observer_registered = True
    except ImportError:
        pass


def register_lock_feature() -> None:
    """InitGui entry: observer + GUI indicator when enabled."""
    if not is_enabled():
        return
    register_observer()
    try:
        from lock_indicator import install_lock_indicator

        install_lock_indicator()
    except Exception as exc:
        try:
            import FreeCAD

            FreeCAD.Console.PrintWarning(f"[MCP] Lock indicator not installed: {exc}\n")
        except ImportError:
            pass
