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
    """Frozen compatibility seam; native collaboration owns sidecar authority."""

    del document, request_identity, dependencies
    return None
