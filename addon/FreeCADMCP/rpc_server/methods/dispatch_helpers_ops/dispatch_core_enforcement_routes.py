from __future__ import annotations

# ruff: noqa: F403, F405
from ._support import *

"""Verb routing for enforced dispatch."""


def dispatch_enforced_verb(
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
):
    if method == "execute_code_async":
        return {
            "success": False,
            "error_code": "document_not_locked",
            "error": (
                "execute_code_async is blocked while document lock enforcement "
                "is enabled (no explicit document / lease). Use execute_code "
                "with options.document and an owned lease instead."
            ),
        }

    if method == "create_document":
        return func(*params)

    if kind == VerbKind.LIFECYCLE:
        return func(*params)

    if kind == VerbKind.READ_ONLY:
        result = func(*params)
        if doc_name:
            try:
                key = resolve_doc_key(doc_name=doc_name)
                return annotate_read_result(result, key)
            except Exception:
                return result
        return result

    if not doc_name:
        return {
            "success": False,
            "error_code": "document_not_locked",
            "error": (
                f"{method} requires an explicit document identity and an owned "
                "lease while document lock enforcement is enabled. "
                "Call acquire_document_lock first."
            ),
        }
    try:
        doc_key = resolve_doc_key(doc_name=doc_name)
    except Exception as exc:
        return {
            "success": False,
            "error_code": "document_not_locked",
            "error": f"Cannot resolve document {doc_name!r}: {exc}",
        }
    allowed = authorize_document(doc_name)
    if not allowed.get("success"):
        return allowed

    return self._call_with_mutation_context(
        func,
        params,
        {
            "request_id": dl.get_request_identity().get("request_id") or str(uuid.uuid4()),
            "method": method,
            "doc_keys": (doc_key,),
            "doc_names": (doc_name,),
            "identity": dict(dl.get_request_identity()),
            "method_spec": method_spec,
            "expected_objects": self._expected_object_names(params),
            "lease_enforced": True,
        },
    )
