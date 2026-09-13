from __future__ import annotations

import logging

from ...freecad_client import FreeCADConnection
from ...responses.constants import ToolResponse
from ...responses.tool_results import json_response, tool_fail, tool_ok

logger = logging.getLogger("FreeCADMCPserver")

def create_document_operation(
    freecad: FreeCADConnection,
    name: str,
) -> ToolResponse:
    try:
        res = freecad.create_document(name)
        if res["success"]:
            public_res = dict(res)
            # Historic add-ons could still return an acquisition credential.
            # It is a deprecated wire artifact: MCP neither stores nor
            # acknowledges it, and it must never cross the public tool result.
            public_res.pop("credential", None)
            public_res["credential_stored"] = False
            if "credential" in res:
                public_res["token_exported"] = False
            return tool_ok(
                f"Document '{res['document_name']}' created successfully",
                structured=public_res,
            )
        return tool_fail(
            f"Failed to create document: {res['error']}",
            structured=res,
            error_code=res.get("error_code"),
        )
    except Exception as e:
        logger.error(f"Failed to create document: {e!s}")
        return tool_fail(f"Failed to create document: {e!s}")

def list_documents_operation(freecad: FreeCADConnection) -> ToolResponse:
    return json_response(freecad.list_documents())

def close_document_operation(freecad: FreeCADConnection, doc_name: str) -> ToolResponse:
    """Use the typed close gate; never hide closeDocument inside generated code."""

    try:
        result = None
        if isinstance(freecad, FreeCADConnection):
            result = freecad._invoke_mutation_v2(
                "close_document",
                {"doc_name": doc_name},
                document_names=(doc_name,),
                operation_name="Close document",
            )
        if result is None:
            result = freecad.invoke_rpc("close_document", doc_name)
        if isinstance(result, dict) and result.get("success"):
            backend_result = result.get("result", True)
            if backend_result is True:
                return tool_ok(f"Document '{doc_name}' closed", structured=result)
            failure = {
                **result,
                "success": False,
                "error_code": result.get(
                    "error_code", "DOCUMENT_CLOSE_NOT_CONFIRMED"
                ),
                "error": result.get("error") or str(backend_result),
            }
            return tool_fail(
                f"Failed to close document: {failure['error']}",
                structured=failure,
            )
        error = result.get("error") if isinstance(result, dict) else result
        return tool_fail(
            f"Failed to close document: {error}",
            structured=result if isinstance(result, dict) else None,
        )
    except Exception as exc:
        logger.error("Failed to close document: %s", exc)
        return tool_fail(
            f"Failed to close document: {exc}",
            error_code=type(exc).__name__.upper(),
        )

def reload_document_operation(
    freecad: FreeCADConnection,
    doc_name: str,
) -> ToolResponse:
    """Close and re-open a document so the GUI picks up external file
    changes (e.g. headless edits via `freecadcmd`).
    """
    try:
        res = freecad.reload_document(doc_name)
        if res.get("success"):
            return tool_ok(
                f"Document '{res['document_name']}' reloaded from disk.",
                structured=res,
            )
        return tool_fail(
            f"Failed to reload document: {res.get('error')}",
            structured=res,
            error_code=res.get("error_code"),
        )
    except Exception as e:
        logger.error(f"Failed to reload document: {e!s}")
        return tool_fail(
            f"Failed to reload document: {e!s}",
            error_code=type(e).__name__.upper(),
        )

def recompute_document_operation(freecad: FreeCADConnection, doc_name: str) -> ToolResponse:
    """Use the typed readiness-gated recompute RPC exactly once."""

    try:
        result = freecad.recompute_document(doc_name)
    except Exception as exc:
        logger.error("Failed to recompute document: %s", exc)
        return tool_fail(
            f"Failed to recompute document: {exc}",
            error_code=type(exc).__name__.upper(),
        )
    if not isinstance(result, dict):
        return tool_fail(
            "Failed to recompute document: invalid RPC response",
            error_code="INVALID_RPC_RESPONSE",
        )
    if result.get("success") is False or result.get("ok") is False:
        error = result.get("error", result.get("message", "unknown error"))
        return tool_fail(
            f"Failed to recompute document: {error}",
            structured=result,
            error_code=result.get("error_code"),
        )
    return tool_ok(
        f"Document '{doc_name}' recomputed",
        structured=result,
    )
