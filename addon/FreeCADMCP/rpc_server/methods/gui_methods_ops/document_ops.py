"""Document listing and open/reload RPC methods (Phase 4 slice 4G)."""

from __future__ import annotations

import logging
from typing import Any

import FreeCAD

from ._common import _rpc_mod

logger = logging.getLogger("FreeCADMCP.rpc_server")


def list_documents(self):
    res = self._dispatch_gui(lambda: list(FreeCAD.listDocuments().keys()))
    return res if isinstance(res, list) else []


def reload_document(self, doc_name: str) -> dict[str, Any]:
    res = self._dispatch_gui(lambda: self._reload_document_gui(doc_name))
    return self._adapt_gui_mutation_result(
        res, success_fields={"document_name": doc_name}
    )


def open_document(self, path: str) -> dict[str, Any]:
    from ...gui_tools import open_document as _open_document

    rpc = _rpc_mod()

    def open_checked():
        existing_names = set(FreeCAD.listDocuments())
        identity_service = rpc.document_identity_service
        if identity_service is not None:
            try:
                identity_service.assert_open_path_available(path)
            except Exception as exc:
                return {
                    "ok": False,
                    "success": False,
                    "error_code": "DUPLICATE_OR_INVALID_DOCUMENT_OPEN",
                    "error": rpc._redact_rpc_diagnostic(exc),
                }
        result = _open_document(path)
        if not isinstance(result, dict) or not result.get("ok"):
            return result
        document_name = str(result.get("document") or "")
        document = FreeCAD.getDocument(document_name)
        try:
            if document is None:
                raise RuntimeError("opened document proxy is unavailable")
            identity = rpc._ensure_v2_document(document)
            result["document_session_uuid"] = identity.session_uuid
            result["canonical_path"] = identity.canonical_path
            return result
        except Exception as exc:
            if document_name and document_name not in existing_names:
                try:
                    FreeCAD.closeDocument(document_name)
                except Exception:
                    logger.exception(
                        "Could not close a document rejected after open"
                    )
            return {
                "ok": False,
                "success": False,
                "error_code": "DOCUMENT_OPEN_IDENTITY_REJECTED",
                "error": rpc._redact_rpc_diagnostic(exc),
            }

    res = self._dispatch_gui(open_checked)
    if isinstance(res, dict):
        return res
    return {"ok": False, "error": str(res)}


__all__ = ["list_documents", "open_document", "reload_document"]
