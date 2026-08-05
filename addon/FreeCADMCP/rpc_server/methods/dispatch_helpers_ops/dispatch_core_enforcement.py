from __future__ import annotations

# ruff: noqa: F403
from ._support import *
from .dispatch_core_enforcement_auth import (
    authenticate_session_or_error,
    is_read_only_execute,
    make_authorize_document,
    requires_authenticated_session,
)
from .dispatch_core_enforcement_routes import dispatch_enforced_verb
from .dispatch_core_execute import dispatch_execute_code


def dispatch_enforcement(
    self,
    method,
    params,
    func,
    kind,
    extractor,
    method_spec,
    dl,
    VerbKind,
    annotate_read_result,
    check_mutation_allowed,
    resolve_doc_key,
    extract_referenced_documents_from_code,
    validate_unsafe_execute_scope,
    collaborators,
    *,
    session_authenticated=False,
):
    identity = dl.get_request_identity()
    read_only_execute = is_read_only_execute(method, params)
    if not session_authenticated and requires_authenticated_session(
        method, kind, VerbKind, read_only_execute
    ):
        auth_error = authenticate_session_or_error(collaborators, dl, identity)
        if auth_error is not None:
            return auth_error

    doc_name = None
    try:
        doc_name = extractor(params if isinstance(params, tuple) else tuple(params))
    except Exception:
        doc_name = None

    authorize_document = make_authorize_document(
        self,
        collaborators,
        method_spec,
        dl,
        resolve_doc_key,
        check_mutation_allowed,
    )

    if method == "execute_code":
        return dispatch_execute_code(
            self,
            method,
            params,
            func,
            method_spec,
            dl,
            identity,
            authorize_document,
            resolve_doc_key,
            annotate_read_result,
            extract_referenced_documents_from_code,
            validate_unsafe_execute_scope,
            collaborators,
        )

    return dispatch_enforced_verb(
        self,
        method,
        params,
        func,
        kind,
        doc_name,
        method_spec,
        dl,
        VerbKind,
        authorize_document,
        resolve_doc_key,
        annotate_read_result,
    )
