from __future__ import annotations

# ruff: noqa: F403, F405
from ._support import *

"""Non-enforcement dispatch path extracted from ``dispatch``."""


def import_document_lock_or_none(collaborators):
    try:
        return collaborators.import_document_lock()
    except ImportError:
        return None


def collect_execute_scope_names(method, params, extractor):
    names = []
    scope_resolution_failed = False
    try:
        extracted = extractor(params if isinstance(params, tuple) else tuple(params))
        if extracted:
            names.append(str(extracted))
    except Exception:
        scope_resolution_failed = True

    execute_options = {}
    affected_documents_declared = False
    if method == "execute_code" and len(params) > 1 and isinstance(params[1], dict):
        execute_options = params[1]
        affected = execute_options.get("affected_documents")
        if isinstance(affected, (list, tuple)):
            affected_documents_declared = bool(affected) and all(
                isinstance(name, str) and bool(name.strip()) for name in affected
            )
            affected_names = affected if affected_documents_declared else ()
            if affected and not affected_documents_declared:
                scope_resolution_failed = True
        else:
            affected_names = ()
            if affected is not None:
                scope_resolution_failed = True
        for name in (execute_options.get("document"), *affected_names):
            if isinstance(name, str) and name and name not in names:
                names.append(name)
            elif name is not None and not isinstance(name, str):
                scope_resolution_failed = True
    return names, execute_options, affected_documents_declared, scope_resolution_failed


def resolve_mutation_documents(collaborators, names, params, scope_resolution_failed):
    selector = params[0] if params and isinstance(params[0], dict) else {}
    selected_name = selector.get("document_name")
    if selected_name and selected_name not in names:
        names.append(str(selected_name))
    selected_path = str(selector.get("canonical_path") or "")
    documents = []
    for name in names:
        document = collaborators.freecad.getDocument(name)
        if document is not None and document not in documents:
            documents.append(document)
        elif document is None:
            scope_resolution_failed = True
    selected_path_resolved = not selected_path
    open_documents = tuple(collaborators.freecad.listDocuments().values())
    if selected_path:
        wanted = os.path.normcase(os.path.realpath(selected_path))
        for document in open_documents:
            live_path = str(getattr(document, "FileName", "") or "")
            if live_path and os.path.normcase(os.path.realpath(live_path)) == wanted:
                selected_path_resolved = True
                if document not in documents:
                    documents.append(document)
    if not selected_path_resolved:
        scope_resolution_failed = True
    return documents, open_documents, scope_resolution_failed


def sidecar_scope_required_error(method, sidecar_blocks, affected_documents_declared):
    if (
        sidecar_blocks
        and method == "execute_code"
        and not affected_documents_declared
    ):
        return {
            "success": False,
            "error_code": "FOREIGN_LEASE_SCOPE_REQUIRED",
            "error": (
                "Live mutating execute_code requires a non-empty "
                "affected_documents list while an open document has "
                "an active or unreadable v2 sidecar"
            ),
            "blocked_documents": _blocked_documents_payload(sidecar_blocks),
        }
    return None


def sidecar_scope_unresolved_error(sidecar_blocks, scope_resolved):
    if sidecar_blocks and not scope_resolved:
        return {
            "success": False,
            "error_code": "FOREIGN_LEASE_SCOPE_UNRESOLVED",
            "error": (
                "Mutation scope could not be resolved while an open "
                "document has an active or unreadable v2 sidecar"
            ),
            "blocked_documents": _blocked_documents_payload(sidecar_blocks),
        }
    return None


def _blocked_documents_payload(sidecar_blocks):
    return [
        {
            "document_name": str(getattr(document, "Name", "") or ""),
            "error_code": blocked.get("error_code", "DOCUMENT_LEASE_CONFLICT"),
        }
        for document, blocked in sidecar_blocks
    ]


def collect_sidecar_blocks(collaborators, open_documents, request_identity):
    sidecar_blocks = []
    for document in open_documents:
        blocked = collaborators.external_scope_block(document, request_identity)
        if blocked is not None:
            sidecar_blocks.append((document, blocked))
    return sidecar_blocks


def document_sidecar_block(documents, sidecar_blocks):
    for document in documents:
        blocked = next(
            (result for candidate, result in sidecar_blocks if candidate is document),
            None,
        )
        if blocked is not None:
            return blocked
    return None


def dispatch_unenforced_mutation(self, method, params, func, method_spec, extractor, dl):
    collaborators = self._execution_collaborators
    names, _execute_options, affected_documents_declared, scope_resolution_failed = (
        collect_execute_scope_names(method, params, extractor)
    )
    documents, open_documents, scope_resolution_failed = resolve_mutation_documents(
        collaborators, names, params, scope_resolution_failed
    )
    request_identity = dl.get_request_identity()
    sidecar_blocks = collect_sidecar_blocks(
        collaborators, open_documents, request_identity
    )

    scope_required_error = sidecar_scope_required_error(
        method, sidecar_blocks, affected_documents_declared
    )
    if scope_required_error is not None:
        return scope_required_error

    scope_resolved = bool(documents) and not scope_resolution_failed
    unresolved_error = sidecar_scope_unresolved_error(sidecar_blocks, scope_resolved)
    if unresolved_error is not None:
        return unresolved_error

    blocked = document_sidecar_block(documents, sidecar_blocks)
    if blocked is not None:
        return blocked
    if not documents:
        return func(*params)
    return self._call_with_mutation_context(
        func,
        params,
        {
            "request_id": dl.get_request_identity().get("request_id") or str(uuid.uuid4()),
            "method": method_spec.name,
            "doc_keys": (),
            "doc_names": tuple(
                str(getattr(document, "Name", "") or "") for document in documents
            ),
            "identity": dict(dl.get_request_identity()),
            "method_spec": method_spec,
            "expected_objects": self._expected_object_names(params),
            "lease_enforced": False,
        },
    )
