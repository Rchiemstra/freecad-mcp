"""Reload preflight helpers for leased documents."""

from __future__ import annotations

import os

import FreeCAD

from ...lease_runtime import _import_document_lease
from ...save_service_ops.baseline import compare_file_to_baseline
from ._common import _rpc_mod


def reload_preflight(doc_name: str):
    if doc_name not in FreeCAD.listDocuments():
        return f"Document '{doc_name}' is not loaded.", None, None
    doc = FreeCAD.getDocument(doc_name)
    file_path = doc.FileName
    if not file_path:
        return (
            f"Document '{doc_name}' has no file on disk "
            "(unsaved scratch document); nothing to reload from."
        ), None, None
    if not os.path.exists(file_path):
        return f"File for '{doc_name}' not found at {file_path!r}.", None, None
    rpc_mod = _rpc_mod()
    if rpc_mod.document_lease_service is None:
        return None, file_path, None
    try:
        identity = rpc_mod.document_identity_service.resolve({"document_name": doc_name})
        status = rpc_mod.document_lease_service.get(
            {"document_session_uuid": identity.session_uuid}
        )
        if status is None:
            return None, file_path, None
        baseline_data = status.get("document_state", {}).get("baseline")
        baseline = _import_document_lease().FileBaseline.from_dict(baseline_data)
        if baseline is None:
            return "Reload requires a verified saved baseline.", None, None
        compare_file_to_baseline(
            file_path,
            baseline,
            platform=rpc_mod.document_identity_service.platform,
        )
        return None, file_path, identity
    except Exception as exc:
        return f"Reload preflight rejected the document: {exc}", None, None
