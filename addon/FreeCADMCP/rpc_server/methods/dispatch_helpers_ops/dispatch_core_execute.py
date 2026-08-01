from __future__ import annotations

# ruff: noqa: F403
from ._support import *
from .dispatch_core_execute_mutating import dispatch_mutating_execute_code


def dispatch_execute_code(
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
):
    options = params[1] if len(params) > 1 and isinstance(params[1], dict) else {}
    read_only = bool(options.get("read_only", False))
    code = params[0] if params else ""
    if not read_only:
        return dispatch_mutating_execute_code(
            self,
            method,
            params,
            func,
            method_spec,
            dl,
            identity,
            authorize_document,
            resolve_doc_key,
            code,
            options,
            extract_referenced_documents_from_code,
            validate_unsafe_execute_scope,
        )

    safe_options = dict(options)
    safe_options["execution_mode"] = "worker"
    if len(params) > 1:
        params = (params[0], safe_options, *params[2:])
    else:
        params = (params[0], safe_options)
    result = func(*params)
    if options.get("document"):
        try:
            key = resolve_doc_key(doc_name=options["document"])
            return annotate_read_result(result, key)
        except Exception:
            return result
    return result
