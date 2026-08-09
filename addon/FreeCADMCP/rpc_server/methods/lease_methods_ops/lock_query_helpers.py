"""Lease query helpers for v2 document lease service."""

import os
from typing import Any

from .lifecycle_dependencies import LifecycleCollaborators


def lease_service_get_lock(
    *,
    doc_name,
    file_path,
    session_id,
    selector,
    dl,
    collaborators: LifecycleCollaborators,
) -> dict[str, Any]:
    requested_selector = dict(selector or {})
    if doc_name:
        requested_selector.setdefault("document_name", doc_name)
    if file_path:
        requested_selector.setdefault("canonical_path", file_path)
    if session_id:
        requested_selector.setdefault("document_session_uuid", session_id)
    _document, document_identity = collaborators.live_document_from_selector(
        requested_selector
    )
    record = collaborators.document_lease_service.get_effective(
        {"document_session_uuid": document_identity.session_uuid}
    )
    if record is not None:
        return {
            "success": True,
            "locked": True,
            "source": record.get("source", "local"),
            "lease": record,
        }
    if not document_identity.canonical_path:
        return {
            "success": True,
            "locked": False,
            "document": document_identity.to_dict(),
            "lease": None,
        }
    compatibility = dl.inspect_persisted_compatibility_lease(
        document_identity.canonical_path
    )
    if compatibility is not None:
        return {
            "success": True,
            "locked": True,
            "source": "local_compatibility_v1",
            "lease": compatibility,
        }
    lease = collaborators.import_document_lease()
    sidecar = lease.sidecar_path_for(document_identity.canonical_path)
    if not os.path.lexists(sidecar):
        return {
            "success": True,
            "locked": False,
            "document": document_identity.to_dict(),
            "lease": None,
        }
    try:
        shadow = collaborators.document_lease_service.sidecar_store.read(sidecar)
        return {
            "success": True,
            "locked": True,
            "source": "foreign_sidecar",
            "lease": shadow.to_public_dict(),
        }
    except Exception as exc:
        return {
            "success": True,
            "locked": True,
            "source": "unknown_sidecar",
            "error_code": "SIDECAR_UNKNOWN",
            "error": str(exc)[:2048],
        }


def list_v2_locks(dl, *, collaborators: LifecycleCollaborators):
    lease = collaborators.import_document_lease()
    local = collaborators.document_lease_service.list_effective_records()
    local_ids = {item.get("document", {}).get("session_uuid") for item in local}
    shadows = []
    for document in collaborators.freecad.listDocuments().values():
        try:
            document_identity = collaborators.ensure_v2_document(document)
            if (
                document_identity.session_uuid in local_ids
                or not document_identity.canonical_path
            ):
                continue
            compatibility = dl.inspect_persisted_compatibility_lease(
                document_identity.canonical_path
            )
            if compatibility is not None:
                compatibility["source"] = "local_compatibility_v1"
                local.append(compatibility)
                local_ids.add(document_identity.session_uuid)
                continue
            sidecar = lease.sidecar_path_for(document_identity.canonical_path)
            if not os.path.lexists(sidecar):
                continue
            try:
                record = collaborators.document_lease_service.sidecar_store.read(sidecar)
                shadows.append(
                    {
                        "source": "foreign_sidecar",
                        "lease": record.to_public_dict(),
                    }
                )
            except Exception as exc:
                shadows.append(
                    {
                        "source": "unknown_sidecar",
                        "document": document_identity.to_dict(),
                        "error_code": "SIDECAR_UNKNOWN",
                        "error": str(exc)[:2048],
                    }
                )
        except Exception as exc:
            shadows.append(
                {
                    "source": "identity_error",
                    "error_code": "DOCUMENT_IDENTITY_ERROR",
                    "error": str(exc)[:2048],
                }
            )
    return {
        "success": True,
        "leases": local,
        "sidecars": shadows,
    }


def list_v1_locks(dl, *, collaborators: LifecycleCollaborators):
    registry = [r.to_dict() for r in dl.list_leases()]
    paths = []
    for doc in collaborators.freecad.listDocuments().values():
        fname = getattr(doc, "FileName", None) or ""
        if fname:
            paths.append(fname)
    discovered = [r.to_dict() for r in dl.discover_sidecar_leases(paths)]
    return {
        "success": True,
        "leases": registry,
        "sidecars": discovered,
    }
