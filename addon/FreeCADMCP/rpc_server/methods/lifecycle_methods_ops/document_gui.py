"""Document create/close/reload GUI helpers."""

import FreeCAD

from ._common import _rpc_mod
from .document_gui_reload import reload_preflight


def close_document(self, doc_name: str) -> dict:
    res = self._dispatch_gui(lambda: self._close_document_gui(doc_name))
    return self._adapt_gui_mutation_result(res)


def create_document_gui(self, name):
    doc = FreeCAD.newDocument(name)
    doc.recompute()
    FreeCAD.Console.PrintMessage(f"Document '{name}' created via RPC.\n")
    return True


def reload_document_gui(self, doc_name: str):
    error, file_path, identity = reload_preflight(doc_name)
    if error is not None:
        return error
    session_uuid = identity.session_uuid if identity is not None else None
    FreeCAD.closeDocument(doc_name)
    reopened = FreeCAD.openDocument(file_path)
    if reopened is None:
        return f"FreeCAD did not reopen '{file_path}'."
    if session_uuid is not None:
        rebound = _rpc_mod().document_identity_service.rebind_document(session_uuid, reopened)
        if rebound.comparison_key != identity.comparison_key:
            return "Reload rebound the document to an unexpected file."
    FreeCAD.Console.PrintMessage(
        f"Document '{doc_name}' reloaded from '{file_path}' via RPC.\n"
    )
    return True


def close_document_gui(self, doc_name: str):
    try:
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return {
                "success": False,
                "error_code": "DOCUMENT_NOT_FOUND",
                "error": f"Document '{doc_name}' not found.",
            }
        if _rpc_mod().document_lease_service is not None:
            try:
                identity = _rpc_mod().document_identity_service.resolve(
                    {"document_name": doc_name}
                )
                active = _rpc_mod().document_lease_service.get(
                    {"document_session_uuid": identity.session_uuid}
                )
            except Exception:
                active = None
            if active is not None:
                return {
                    "success": False,
                    "error_code": "DOCUMENT_LEASE_ACTIVE",
                    "error": (
                        "A leased document cannot be closed by the generic RPC. "
                        "Finalize and verify the save first, then close the "
                        "released document."
                    ),
                }
        FreeCAD.closeDocument(doc_name)
        if FreeCAD.getDocument(doc_name):
            return {
                "success": False,
                "error_code": "DOCUMENT_CLOSE_REJECTED",
                "error": (
                    f"FreeCAD did not close document '{doc_name}'; "
                    "the application remains running."
                ),
            }
        FreeCAD.Console.PrintMessage(f"Document '{doc_name}' closed via RPC.\n")
        return {
            "success": True,
            "document_name": doc_name,
            "result": True,
        }
    except Exception as e:
        return {
            "success": False,
            "error_code": type(e).__name__.upper(),
            "error": str(e),
        }
