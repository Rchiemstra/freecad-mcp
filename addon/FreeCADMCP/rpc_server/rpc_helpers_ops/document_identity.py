import os

import FreeCAD

try:
    from document_lease.observer import register_live_document_recovery
except ImportError:
    from addon.FreeCADMCP.document_lease.observer import (
        register_live_document_recovery,
    )

from ._common import RpcHelperDependencies
from .diagnostics import _format_identity_registration_error
from .selector_resolve import (
    resolve_named_document,
    scan_open_documents,
    validate_selector_fields,
)

"""Document identity, selector, and credential helpers."""


def _freecad_version_parts():
    value = getattr(FreeCAD, "Version", ())
    value = value() if callable(value) else value
    return tuple(str(part) for part in (value or ()))

def _ensure_v2_document(document, dependencies: RpcHelperDependencies):
    if dependencies.document_identity_service is None:
        raise RuntimeError("document lease service is not initialized")
    if dependencies.document_lease_service is None:
        return dependencies.document_identity_service.register_document(document)
    identity, imported, failure = register_live_document_recovery(
        dependencies.document_lease_service, document
    )
    if identity is None:
        lease = dependencies.import_document_lease()
        details = failure.to_details() if failure is not None else {}
        raise lease.DocumentIdentityError(
            _format_identity_registration_error(failure)
            if failure is not None
            else "live document identity could not be registered",
            details=details,
        )
    if imported is not None:
        try:
            dependencies.refresh_lock_indicator()
        except Exception:
            dependencies.logger.debug(
                "Could not queue foreign recovery status refresh", exc_info=True
            )
    return identity


def _candidate_matches_selector_target(
    candidate, selector, dependencies: RpcHelperDependencies
):
    """Return True when an open document is the selector's intended target."""
    if dependencies.document_identity_service is None:
        return False
    lease = dependencies.import_document_lease()
    session_uuid = str(selector.get("document_session_uuid") or "")
    if session_uuid:
        try:
            registered = dependencies.document_identity_service.registered_session_uuid(
                candidate
            )
        except (lease.UnknownDocumentError, lease.DocumentIdentityError):
            registered = None
        if registered == session_uuid:
            return True
    try:
        expected = dependencies.document_identity_service.resolve(selector)
    except (lease.UnknownDocumentError, lease.DocumentIdentityError):
        return False
    name = getattr(candidate, "Name", None) or getattr(candidate, "Label", None)
    if name and str(name) == expected.name:
        return True
    path = str(getattr(candidate, "FileName", "") or "").strip()
    if path and expected.comparison_key:
        _, comparison = lease.canonicalize_path(
            path, platform=dependencies.document_identity_service.platform
        )
        if comparison == expected.comparison_key:
            return True
    return False


def _live_document_from_selector(selector, dependencies: RpcHelperDependencies):
    """Resolve a selector only against currently open FreeCAD documents."""
    name, session_uuid, canonical_path = validate_selector_fields(selector)
    if name:
        document, identity = resolve_named_document(name, dependencies)
    else:
        document, identity = scan_open_documents(
            selector, session_uuid, canonical_path, dependencies
        )
    asserted = dependencies.document_identity_service.resolve(selector)
    if asserted.session_uuid != identity.session_uuid:
        raise ValueError("DocumentSelector fields identify different documents")
    return document, asserted


def _credential_from_wire(
    payload, identity=None, *, dependencies: RpcHelperDependencies
):
    lease = dependencies.import_document_lease()
    if not isinstance(payload, dict):
        raise lease.AuthorizationError("a complete LeaseCredential is required")
    try:
        request_identity = dict(
            identity or dependencies.import_document_lock().get_request_identity()
        )
        authenticated_runtime_id = str(
            request_identity.get("instance_id")
            if request_identity.get("authenticated_session_id")
            else ""
        )
        return lease.LeaseCredential(
            lease_id=str(payload["lease_id"]),
            document_session_uuid=str(payload["document_session_uuid"]),
            generation=int(payload["generation"]),
            token=str(payload["token"]),
            mcp_instance_id=authenticated_runtime_id,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise lease.AuthorizationError(
            "lease id, document, generation, token, and authenticated runtime are required"
        ) from exc


def _credential_for_document(
    document_name, identity=None, *, dependencies: RpcHelperDependencies
):
    identity = dict(
        identity or dependencies.import_document_lock().get_request_identity()
    )
    document = FreeCAD.getDocument(document_name)
    if document is None:
        raise ValueError(f"Document {document_name!r} is not open")
    document_identity = _ensure_v2_document(document, dependencies)
    matches = [
        item
        for item in identity.get("lease_credentials") or []
        if isinstance(item, dict)
        and item.get("document_session_uuid") == document_identity.session_uuid
    ]
    if len(matches) != 1:
        lease = dependencies.import_document_lease()
        raise lease.AuthorizationError(
            "request must contain exactly one credential for the selected document"
        )
    return (
        _credential_from_wire(matches[0], identity, dependencies=dependencies),
        document_identity,
    )


def _credential_for_selector(
    selector, identity=None, *, dependencies: RpcHelperDependencies
):
    identity = dict(
        identity or dependencies.import_document_lock().get_request_identity()
    )
    document, document_identity = _live_document_from_selector(
        selector, dependencies
    )
    matches = [
        item
        for item in identity.get("lease_credentials") or []
        if isinstance(item, dict)
        and item.get("document_session_uuid") == document_identity.session_uuid
    ]
    if len(matches) != 1:
        lease = dependencies.import_document_lease()
        raise lease.AuthorizationError(
            "request must contain exactly one credential for the selected document"
        )
    return (
        _credential_from_wire(matches[0], identity, dependencies=dependencies),
        document_identity,
        document,
    )


def _effective_sidecar_block(
    document, request_identity, *, dependencies: RpcHelperDependencies
):
    """Block foreign/unknown sidecars while honoring a proven live v1 lease."""

    path = str(getattr(document, "FileName", "") or "")
    if not path:
        return None
    lease = dependencies.import_document_lease()
    sidecar = lease.sidecar_path_for(path)
    if not os.path.lexists(sidecar):
        return None
    store = (
        dependencies.document_lease_service.sidecar_store
        if dependencies.document_lease_service is not None
        else lease.SidecarStore(strict_permissions=False, allow_network=True)
    )
    try:
        persisted = store.read(sidecar)
    except Exception as exc:
        # A v1 sidecar remains unknown when found on disk by itself. During the
        # documented off/observe migration window, however, the same addon
        # process can prove the flat record against its private live registry,
        # exact instance identity, bearer token, generation, and fingerprint.
        # This does not parse or migrate v1 data into the v2 authority.
        try:
            dl = dependencies.import_document_lock()
            doc_key = dl.resolve_doc_key(
                doc_name=str(getattr(document, "Name", "") or "") or None,
                file_path=path,
            )
            compatible = dl.check_persisted_mutation_allowed(
                doc_key,
                identity=request_identity,
                allowed_states={
                    dl.LeaseState.LOCKED_IDLE.value,
                    dl.LeaseState.LOCKED_ERROR.value,
                },
            )
            if compatible.get("success"):
                return None
        except Exception:
            pass
        return {
            "success": False,
            "error_code": "SIDECAR_UNKNOWN",
            "error": (
                "A document lease sidecar exists but cannot be validated; "
                f"writes remain blocked: {str(exc)[:1024]}"
            ),
        }

    if dependencies.document_lease_service is not None:
        try:
            identity = _ensure_v2_document(document, dependencies)
            local = dependencies.document_lease_service.get(
                {"document_session_uuid": identity.session_uuid}
            )
            if local is not None:
                credential, _identity = _credential_for_document(
                    document.Name,
                    request_identity,
                    dependencies=dependencies,
                )
                dependencies.document_lease_service.authorize(
                    credential,
                    selector={"document_session_uuid": identity.session_uuid},
                )
                return None
        except Exception:
            pass
    return {
        "success": False,
        "error_code": "DOCUMENT_LEASE_CONFLICT",
        "error": "A v2 document lease owns this file; this request is read-only",
        "lease": persisted.to_public_dict(),
    }
