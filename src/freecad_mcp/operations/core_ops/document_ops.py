from __future__ import annotations

import logging

from ...freecad_client import FreeCADConnection
from ...outcomes import OutcomeStatus
from ...responses import ToolResponse, json_response, tool_fail, tool_ok
from ...template_resources import render_template_text
from .run_code import _run_code

logger = logging.getLogger("FreeCADMCPserver")

def create_document_operation(
    freecad: FreeCADConnection,
    name: str,
    *,
    lease_manager=None,
    document_sessions: dict[str, str] | None = None,
) -> ToolResponse:
    try:
        res = freecad.create_document(name)
        if res["success"]:
            credential_data = res.get("credential") or {}
            public_res = dict(res)
            # The credential is a one-time bearer secret. It is retained only
            # in the private lease manager and must never cross the MCP tool
            # result boundary, including structuredContent.
            public_res.pop("credential", None)
            if credential_data and lease_manager is not None:
                from ...lease_manager import LeaseCredential

                try:
                    credential = LeaseCredential(
                        lease_id=str(credential_data["lease_id"]),
                        document_session_uuid=str(
                            credential_data["document_session_uuid"]
                        ),
                        generation=int(credential_data["generation"]),
                        token=str(credential_data["token"]),
                    )
                    lease_manager.store(credential)
                except Exception:
                    logger.exception(
                        "local create_document credential custody failed; "
                        "escrow left unacknowledged"
                    )
                    public_res["credential_stored"] = False
                    public_res["token_exported"] = False
                    return json_response(
                        public_res,
                        status=OutcomeStatus.WARNING,
                        message=(
                            f"Document '{res.get('document_name') or name}' created "
                            "but local credential custody failed; escrow remains "
                            "unacknowledged for retry"
                        ),
                    )
                if document_sessions is not None:
                    document_sessions[res["document_name"]] = (
                        credential.document_session_uuid
                    )
                cleanup_pending = False
                if res.get("request_id"):
                    try:
                        freecad.acknowledge_acquisition_claim(str(res["request_id"]))
                    except Exception:
                        logger.exception(
                            "acquisition claim acknowledgement after create failed; "
                            "cleanup pending"
                        )
                        cleanup_pending = True
                public_res["lease"] = {
                    "lease_id": credential.lease_id,
                    "document_session_uuid": credential.document_session_uuid,
                    "generation": credential.generation,
                    "credential_stored": True,
                }
                public_res["credential_stored"] = True
                public_res["token_exported"] = False
                if cleanup_pending:
                    public_res["cleanup_pending"] = True
                    return json_response(
                        public_res,
                        status=OutcomeStatus.WARNING,
                        message=(
                            f"Document '{res['document_name']}' created and leased; "
                            "escrow cleanup is pending"
                        ),
                    )
                return tool_ok(
                    f"Document '{res['document_name']}' created and leased successfully",
                    structured=public_res,
                )
            public_res["credential_stored"] = False
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
    code = render_template_text(
        "core/doc_action.py.txt",
        doc_name=repr(doc_name),
        action_line="_d.recompute()",
        message=repr("recomputed"),
    )
    return _run_code(freecad, True, code,
                     f"Document '{doc_name}' recomputed", "Failed to recompute",
                     document=doc_name)
