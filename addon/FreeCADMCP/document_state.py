"""Version-tolerant access to FreeCAD's authoritative modified flag.

``App::Document`` does not expose ``Modified`` in current FreeCAD builds; the
flag belongs to ``Gui::Document``.  Tests and some older bindings expose it on
the App proxy, so callers use these helpers instead of assuming either shape.
"""

from __future__ import annotations

from typing import Any


class DocumentDirtyStateUnavailable(RuntimeError):
    """FreeCAD's authoritative GUI modified flag cannot be read or written."""

    code = "DOCUMENT_DIRTY_STATE_UNAVAILABLE"


def _modified_attribute(target: Any) -> bool | None:
    if target is None:
        return None
    try:
        return bool(getattr(target, "Modified"))
    except (AttributeError, RuntimeError, TypeError):
        return None


def _gui_document_lookup(document: Any) -> tuple[bool, Any | None]:
    """Return ``(GUI API available, matching Gui::Document)``."""

    name = str(getattr(document, "Name", "") or "")
    if not name:
        return False, None
    try:
        import FreeCADGui

        getter = getattr(FreeCADGui, "getDocument", None)
        if not callable(getter):
            return False, None
        try:
            return True, getter(name)
        except Exception:
            return True, None
    except ImportError:
        return False, None


def gui_document_for(document: Any) -> Any | None:
    """Return the matching Gui::Document proxy when a GUI is available."""

    return _gui_document_lookup(document)[1]


def document_modified_state(document: Any) -> bool | None:
    """Return the authoritative dirty flag, or ``None`` when unavailable.

    ``isTouched()`` is only a conservative positive fallback in headless
    FreeCADCmd: recompute can clear it even when an unsaved edit remains, so a
    false value must never be interpreted as authoritative cleanliness.
    """

    gui_available, gui_document = _gui_document_lookup(document)
    if gui_available:
        # A running GUI is authoritative.  Never let a compatibility-only App
        # attribute conceal a missing, stale, or unreadable GUI proxy.
        return _modified_attribute(gui_document)
    app_state = _modified_attribute(document)
    if app_state is not None:
        return app_state
    try:
        if bool(document.isTouched()):
            return True
    except (AttributeError, RuntimeError, TypeError):
        pass
    return None


def require_document_modified(document: Any) -> bool:
    """Read the authoritative state or fail closed when it is unavailable."""

    state = document_modified_state(document)
    if state is None:
        raise DocumentDirtyStateUnavailable(
            "FreeCAD did not expose authoritative Gui::Document.Modified state"
        )
    return state


def document_modified_or_dirty(document: Any) -> bool:
    """Return dirty for true or unknown state, suitable for error journaling."""

    return document_modified_state(document) is not False


def set_document_modified(document: Any, modified: bool) -> None:
    """Set and read back the authoritative modified flag."""

    gui_available, gui_document = _gui_document_lookup(document)
    if not gui_available:
        # Legacy test doubles and old bindings may put Modified on App.  A
        # save method is allowed to clear that flag itself, but this helper
        # must not overwrite a still-dirty App fake and conceal a failed save.
        if _modified_attribute(document) is bool(modified):
            return
        raise DocumentDirtyStateUnavailable(
            "FreeCAD did not expose writable Gui::Document.Modified state"
        )
    target = gui_document
    if target is None or _modified_attribute(target) is None:
        raise DocumentDirtyStateUnavailable(
            "FreeCAD did not expose writable Gui::Document.Modified state"
        )
    try:
        setattr(target, "Modified", bool(modified))
    except Exception as exc:
        raise DocumentDirtyStateUnavailable(
            "FreeCAD rejected the GUI document modified-state update"
        ) from exc
    observed = _modified_attribute(target)
    if observed != bool(modified):
        raise DocumentDirtyStateUnavailable(
            "FreeCAD did not retain the requested GUI document modified state"
        )


def mark_document_modified(document: Any) -> bool:
    """Mark a restored live document dirty and prove the mark when possible."""

    gui_available, _gui_document = _gui_document_lookup(document)
    try:
        set_document_modified(document, True)
        return True
    except DocumentDirtyStateUnavailable:
        if gui_available:
            raise

    app_state = _modified_attribute(document)
    if app_state is not None:
        try:
            setattr(document, "Modified", True)
        except Exception as exc:
            raise DocumentDirtyStateUnavailable(
                "legacy App document modified state could not be updated"
            ) from exc
        return _modified_attribute(document) is True

    # FreeCADCmd has no Gui::Document.  A touched object is the strongest live
    # dirty signal available there; lease mutation revisions remain the durable
    # authority and save/reopen verification is still required for release.
    for obj in tuple(getattr(document, "Objects", ()) or ()):
        touch = getattr(obj, "touch", None)
        if callable(touch):
            touch()
            try:
                if bool(document.isTouched()):
                    return True
            except (AttributeError, RuntimeError, TypeError):
                pass
            break
    return document_modified_state(document) is True
