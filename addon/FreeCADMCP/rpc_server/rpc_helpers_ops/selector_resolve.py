"""Open-document resolution helpers for selector-based RPC paths."""

from __future__ import annotations

import FreeCAD

from ._common import RpcHelperDependencies


def validate_selector_fields(selector):
    if not isinstance(selector, dict):
        raise ValueError("DocumentSelector must be an object")
    accepted_fields = {
        "document_name",
        "document_session_uuid",
        "canonical_path",
    }
    unexpected_fields = sorted(
        str(field) for field in selector if field not in accepted_fields
    )
    if unexpected_fields:
        raise ValueError(
            "Unsupported DocumentSelector field(s): "
            + ", ".join(unexpected_fields)
            + ". Accepted fields are document_name, document_session_uuid, "
            "and canonical_path"
        )
    return (
        selector.get("document_name") or "",
        selector.get("document_session_uuid") or "",
        selector.get("canonical_path") or "",
    )


def resolve_named_document(name, dependencies: RpcHelperDependencies):
    document = FreeCAD.getDocument(str(name))
    if document is None:
        raise ValueError(f"Document {name!r} is not open")
    identity = dependencies.ensure_v2_document(document)
    return document, identity


def scan_open_documents(
    selector,
    session_uuid,
    canonical_path,
    dependencies: RpcHelperDependencies,
):
    from .document_identity import _candidate_matches_selector_target

    lease = dependencies.import_document_lease()
    for candidate in FreeCAD.listDocuments().values():
        try:
            candidate_identity = dependencies.ensure_v2_document(candidate)
        except Exception as exc:
            if isinstance(exc, lease.DocumentIdentityError):
                if _candidate_matches_selector_target(
                    candidate, selector, dependencies
                ):
                    raise
                continue
            raise
        if session_uuid and candidate_identity.session_uuid == session_uuid:
            return candidate, candidate_identity
        if canonical_path:
            try:
                resolved = dependencies.document_identity_service.resolve(
                    {"canonical_path": canonical_path}
                )
            except Exception:
                continue
            if resolved.session_uuid == candidate_identity.session_uuid:
                return candidate, candidate_identity
    raise ValueError("DocumentSelector does not identify an open document")
