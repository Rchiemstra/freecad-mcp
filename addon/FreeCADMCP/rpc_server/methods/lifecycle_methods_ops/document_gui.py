"""Document create/close/reload GUI helpers."""

import FreeCAD

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
    error, file_path, identity = reload_preflight(self, doc_name)
    if error is not None:
        return error
    del identity
    FreeCAD.closeDocument(doc_name)
    reopened = FreeCAD.openDocument(file_path)
    if reopened is None:
        return f"FreeCAD did not reopen '{file_path}'."
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
