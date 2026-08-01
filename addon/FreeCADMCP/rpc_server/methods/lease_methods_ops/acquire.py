"""Lease RPC methods extracted from ``FreeCADRPC`` (Phase 4 slice 4E)."""

from typing import Any

from ._common import _rpc_mod


def acquire_document_lock(
    self,
    doc_name: str = "",
    file_path: str = "",
    session_id: str = "",
    task_description: str = "",
    client: str = "",
    selector: dict[str, Any] | None = None,
    agent_id: str = "",
    hash_policy: str = "sha256",
) -> dict[str, Any]:
    """Acquire an exclusive renewable write lease for a document."""
    try:
        dl = _rpc_mod()._import_document_lock()
    except ImportError as exc:
        return {"success": False, "error": str(exc)}
    if not dl.is_enabled():
        return {
            "success": False,
            "error_code": "document_lock_disabled",
            "error": "enable_document_lock is false in freecad_mcp_settings.json",
        }
    identity = dl.get_request_identity()
    instance_id = identity.get("instance_id") or ""
    if not instance_id:
        return {
            "success": False,
            "error_code": "missing_instance_id",
            "error": "X-MCP-Instance-Id header is required to acquire a lock",
        }
    if not (doc_name or file_path or session_id or selector):
        return {
            "success": False,
            "error_code": "document_identity_required",
            "error": (
                "Provide an explicit doc_name, file_path, or session_id "
                "(never implicitly locks ActiveDocument)"
            ),
        }

    if _rpc_mod().document_lease_service is None:
        return {
            "success": False,
            "error_code": "LEASE_PROTOCOL_UNAVAILABLE",
            "error": "Document lease v2 is unavailable",
        }
    if not identity.get("authenticated_session_id"):
        return {
            "success": False,
            "error_code": "LEASE_PROTOCOL_REQUIRED",
            "error": (
                "Document acquisition requires an authenticated protocol-v2 "
                "session; legacy identity arguments are selector aliases only"
            ),
        }
    requested_selector = dict(selector or {})
    selector_aliases = {
        "document_name": doc_name,
        "canonical_path": file_path,
        "document_session_uuid": session_id,
    }
    for selector_field, value in selector_aliases.items():
        if not value:
            continue
        existing = requested_selector.get(selector_field)
        if existing and str(existing) != str(value):
            return {
                "success": False,
                "error_code": "DOCUMENT_SELECTOR_CONFLICT",
                "error": (
                    f"{selector_field} was supplied with conflicting selector "
                    "and deprecated-alias values"
                ),
            }
        requested_selector[selector_field] = value
    return self._acquire_document_lock_v2(
        requested_selector,
        request_identity=identity,
        task_description=task_description,
        client=client,
        agent_id=agent_id,
        hash_policy=hash_policy,
    )

def adopt_dirty_document(
    self,
    selector: dict[str, Any] | None = None,
    task_description: str = "",
    client: str = "",
    agent_id: str = "",
    hash_policy: str = "sha256",
) -> dict[str, Any]:
    """Locally confirm and adopt an already-dirty document into lease v2."""

    try:
        dl = _rpc_mod()._import_document_lock()
    except ImportError as exc:
        return {"success": False, "error": str(exc)}
    if not dl.is_enabled():
        return {
            "success": False,
            "error_code": "document_lock_disabled",
            "error": "enable_document_lock is false in freecad_mcp_settings.json",
        }
    identity = dl.get_request_identity()
    if not identity.get("instance_id"):
        return {
            "success": False,
            "error_code": "missing_instance_id",
            "error": "X-MCP-Instance-Id header is required to adopt a document",
        }
    if not identity.get("authenticated_session_id"):
        return {
            "success": False,
            "error_code": "authenticated_session_required",
            "error": "Dirty-document adoption requires authenticated lease protocol v2",
        }
    requested_selector = dict(selector or {})
    if not requested_selector:
        return {
            "success": False,
            "error_code": "document_identity_required",
            "error": (
                "Provide selector.document_name, selector.document_session_uuid, "
                "or selector.canonical_path"
            ),
        }
    if _rpc_mod().document_lease_service is None:
        return {
            "success": False,
            "error_code": "LEASE_PROTOCOL_UNAVAILABLE",
            "error": "Document lease v2 is unavailable",
        }
    return self._acquire_document_lock_v2(
        requested_selector,
        request_identity=identity,
        task_description=task_description,
        client=client,
        agent_id=agent_id,
        hash_policy=hash_policy,
        adopt_dirty=True,
    )
