"""Explicit document open and reload collaborators for GUI adapters."""

from __future__ import annotations

import os
from contextlib import suppress


def _active_document_name(freecad):
    document = getattr(freecad, "ActiveDocument", None)
    return str(getattr(document, "Name", "") or "")


def _restore_active_document(freecad, gui_module, document_name):
    if document_name and freecad.getDocument(document_name) is not None:
        freecad.setActiveDocument(document_name)
        gui_module.ActiveDocument = gui_module.getDocument(document_name)
        return
    freecad.setActiveDocument("")
    gui_module.ActiveDocument = None


def _report_sentinel_restore_failure(freecad):
    with suppress(Exception):
        freecad.Console.PrintError(
            "Human active-document restore failed after a document operation failure.\n"
        )


def _restore_with_primary(
    freecad,
    gui_module,
    document_name,
    primary_error,
    *,
    preserve_failure=False,
):
    try:
        _restore_active_document(freecad, gui_module, document_name)
    except Exception as restore_error:
        if primary_error is not None:
            primary_error.add_note(
                f"human active-document restore also failed: {restore_error}"
            )
            return
        if preserve_failure:
            _report_sentinel_restore_failure(freecad)
            return
        raise


def open_document(freecad, gui_module, path):
    path = str(path)
    if not path:
        return {"ok": False, "error": "path is required"}
    human_document = _active_document_name(freecad)
    primary_error = None
    result = None
    try:
        document = freecad.openDocument(path)
        if document is None:
            result = {"ok": False, "error": f"Failed to open: {path}"}
        else:
            result = {
                "ok": True,
                "document": str(document.Name),
                "label": str(document.Label),
                "path": path,
            }
    except Exception as exc:
        primary_error = exc
        raise
    finally:
        _restore_with_primary(
            freecad,
            gui_module,
            human_document,
            primary_error,
            preserve_failure=isinstance(result, dict) and not result.get("ok"),
        )
    return result


def _reload_preflight(
    freecad,
    identity_service,
    lease_service,
    compare_baseline,
    document_name,
):
    if document_name not in freecad.listDocuments():
        return f"Document '{document_name}' is not loaded.", None, None
    document = freecad.getDocument(document_name)
    file_path = str(getattr(document, "FileName", "") or "")
    if not file_path:
        return (
            (
                f"Document '{document_name}' has no file on disk "
                "(unsaved scratch document); nothing to reload from."
            ),
            None,
            None,
        )
    if not os.path.exists(file_path):
        return f"File for '{document_name}' not found at {file_path!r}.", None, None

    identity = None
    if lease_service is not None:
        identity = identity_service.resolve({"document_name": document_name})
        status = lease_service.get({"document_session_uuid": identity.session_uuid})
        if status is not None:
            baseline_data = status.get("document_state", {}).get("baseline")
            if baseline_data is None:
                return "Reload requires a verified saved baseline.", None, None
            compare_baseline(
                file_path,
                baseline_data,
                platform=identity_service.platform,
            )
    return None, file_path, identity


def reload_document(
    freecad,
    gui_module,
    identity_service,
    lease_service,
    compare_baseline,
    document_name,
):
    error, file_path, identity = _reload_preflight(
        freecad,
        identity_service,
        lease_service,
        compare_baseline,
        document_name,
    )
    if error is not None:
        return error

    human_document = _active_document_name(freecad)
    primary_error = None
    result = None
    try:
        freecad.closeDocument(document_name)
        reopened = freecad.openDocument(file_path)
        if reopened is None:
            result = f"FreeCAD did not reopen '{file_path}'."
        elif identity is not None:
            rebound = identity_service.rebind_document(identity.session_uuid, reopened)
            if rebound.comparison_key != identity.comparison_key:
                result = "Reload rebound the document to an unexpected file."
        if result is None:
            with suppress(Exception):
                freecad.Console.PrintMessage(
                    f"Document '{document_name}' reloaded from '{file_path}' via RPC.\n"
                )
            result = True
    except Exception as exc:
        primary_error = exc
        raise
    finally:
        _restore_with_primary(
            freecad,
            gui_module,
            human_document,
            primary_error,
            preserve_failure=result is not True,
        )
    return result


__all__ = ["open_document", "reload_document"]
