"""Version-tolerant access to FreeCAD's authoritative file-change state.

Current FreeCAD builds expose that state on ``App::Document`` through
``getFileChangeState()``/``hasPendingFileChanges()``.  Older builds expose only
the compatibility ``Gui::Document.Modified`` flag, so callers use these
helpers instead of assuming either runtime shape.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class DocumentDirtyStateUnavailable(RuntimeError):
    """FreeCAD's authoritative file-change state cannot be read or written."""

    code = "DOCUMENT_DIRTY_STATE_UNAVAILABLE"


def _modified_attribute(target: Any) -> bool | None:
    if target is None:
        return None
    try:
        return bool(target.Modified)
    except (AttributeError, RuntimeError, TypeError):
        return None


def _app_document_modified_state(document: Any) -> tuple[bool, bool | None]:
    """Return ``(native App API available, modified state)``.

    The structured getter is preferred because its save-failure overlay is
    part of the compatibility modified state.  Once either native App getter
    is advertised, a malformed/raising result is an unavailable authoritative
    state, not permission to fall back to a potentially stale GUI proxy.
    """

    state_getter = getattr(document, "getFileChangeState", None)
    if callable(state_getter):
        try:
            state = state_getter()
        except Exception:
            return True, None
        if not isinstance(state, Mapping):
            return True, None

        pending = state.get("has_pending_file_changes")
        failed = state.get("last_canonical_save_failed", False)
        if not isinstance(failed, bool):
            return True, None
        if isinstance(pending, bool):
            return True, pending or failed

        base_state = state.get("state")
        if isinstance(base_state, str):
            normalized = base_state.strip().lower()
            if normalized in {"not_saved", "clean", "modified"}:
                return True, normalized == "modified" or failed
        return True, None

    pending_getter = getattr(document, "hasPendingFileChanges", None)
    if callable(pending_getter):
        try:
            pending = pending_getter()
        except Exception:
            return True, None
        return (True, pending) if isinstance(pending, bool) else (True, None)

    return False, None


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

    Native ``App::Document`` state works in both GUI FreeCAD and headless
    FreeCADCmd.  ``isTouched()`` is only a conservative positive fallback for
    older headless builds: recompute can clear it even when an unsaved edit
    remains, so a false value must never imply authoritative cleanliness.
    """

    app_available, app_state = _app_document_modified_state(document)
    if app_available:
        return app_state

    gui_available, gui_document = _gui_document_lookup(document)
    if gui_available:
        # Legacy GUI builds own the compatibility flag.  Never let an App test
        # double conceal a missing, stale, or unreadable GUI proxy there.
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
            "FreeCAD did not expose authoritative App::Document file-change state"
        )
    return state


def document_modified_or_dirty(document: Any) -> bool:
    """Return dirty for true or unknown state, suitable for error journaling."""

    return document_modified_state(document) is not False


def set_document_modified(document: Any, modified: bool) -> None:
    """Set and read back the authoritative modified flag."""

    app_available, app_state = _app_document_modified_state(document)
    if app_available:
        if app_state is None:
            raise DocumentDirtyStateUnavailable(
                "FreeCAD exposed unreadable App::Document file-change state"
            )
        if app_state is bool(modified):
            return
        if not modified:
            # A native save owns its savepoint.  Clearing through the legacy
            # GUI compatibility setter could hide a re-entrant post-save edit.
            raise DocumentDirtyStateUnavailable(
                "FreeCAD's authoritative App::Document remains modified"
            )

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
        target.Modified = bool(modified)
    except Exception as exc:
        raise DocumentDirtyStateUnavailable(
            "FreeCAD rejected the GUI document modified-state update"
        ) from exc
    observed = (
        document_modified_state(document)
        if app_available
        else _modified_attribute(target)
    )
    if observed != bool(modified):
        raise DocumentDirtyStateUnavailable(
            "FreeCAD did not retain the requested GUI document modified state"
        )


def mark_document_modified(document: Any) -> bool:
    """Mark a restored live document dirty and prove the mark when possible."""

    app_available, _app_state = _app_document_modified_state(document)
    gui_available, _gui_document = _gui_document_lookup(document)
    try:
        set_document_modified(document, True)
        return True
    except DocumentDirtyStateUnavailable:
        if gui_available and not app_available:
            raise

    app_state = _modified_attribute(document)
    if app_state is not None:
        try:
            document.Modified = True
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
            if not app_available:
                try:
                    if bool(document.isTouched()):
                        return True
                except (AttributeError, RuntimeError, TypeError):
                    pass
            break
    return document_modified_state(document) is True
