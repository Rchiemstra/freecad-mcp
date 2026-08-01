from __future__ import annotations

# ruff: noqa: F403, F405
from ._support import *

"""Mutating execute_code path for enforced dispatch."""


def validate_generated_execute(identity, code, options, method_spec):
    operation_id = str(options.get("operation_id") or "")
    supplied_signature = str(options.get("operation_signature") or "")
    expected_signature = _rpc_mod()._generated_execute_signature(
        session_token=identity.get("rpc_session_token") or "",
        request_id=identity.get("request_id") or "",
        code=code,
        options=options,
    )
    if not operation_id or not hmac.compare_digest(supplied_signature, expected_signature):
        return {
            "success": False,
            "error_code": "GENERATED_OPERATION_SIGNATURE_INVALID",
            "error": (
                "The internal generated-operation capability "
                "signature is missing or invalid"
            ),
        }
    return _rpc_mod()._generated_operation_method_spec(method_spec, operation_id)


def validate_mutating_execute_scope(
    code, options, generated_operation, validate_unsafe_execute_scope
):
    primary = options["document"]
    additional = [
        name for name in (options.get("affected_documents") or []) if name != primary
    ]
    declared = {primary, *additional}
    if generated_operation:
        return declared, None
    scope_validation = validate_unsafe_execute_scope(code, declared)
    if not scope_validation["ok"]:
        return declared, {
            "success": False,
            "error_code": "UNSAFE_EXECUTE_SCOPE_REJECTED",
            "error": (
                "Unsafe live Python contains document access that "
                "cannot be proven to match its declared lease scope"
            ),
            "violations": scope_validation["violations"],
        }
    return declared, None


def dispatch_mutating_execute_code(
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
):
    generated_operation = bool(options.get("generated_operation"))
    if generated_operation:
        signature_result = validate_generated_execute(identity, code, options, method_spec)
        if isinstance(signature_result, dict):
            return signature_result
        method_spec = signature_result
    settings = load_settings()
    if not generated_operation and not settings.get("allow_unsafe_mutating_execute_code", False):
        return {
            "success": False,
            "error_code": "unsafe_mutating_execute_code_disabled",
            "error": (
                "Arbitrary mutating execute_code is disabled in document "
                "lease enforce mode. Use a typed MCP operation or explicitly "
                "enable allow_unsafe_mutating_execute_code."
            ),
        }
    if not options.get("document"):
        return {
            "success": False,
            "error_code": "document_not_locked",
            "error": (
                "execute_code mutations require options.document "
                "(explicit document identity) and an owned lease. "
                "Call acquire_document_lock first."
            ),
        }
    declared, scope_error = validate_mutating_execute_scope(
        code, options, generated_operation, validate_unsafe_execute_scope
    )
    if scope_error is not None:
        return scope_error
    referenced = extract_referenced_documents_from_code(code)
    undeclared = referenced - declared
    if undeclared:
        return {
            "success": False,
            "error_code": "multi_document_undeclared",
            "error": (
                "execute_code references documents not declared in "
                f"options.document / affected_documents: {sorted(undeclared)}. "
                "Declare and lock every affected document."
            ),
            "undeclared": sorted(undeclared),
        }
    for name in declared:
        allowed = authorize_document(name)
        if not allowed.get("success"):
            return allowed
    keys = []
    for name in declared:
        with contextlib.suppress(Exception):
            keys.append(resolve_doc_key(doc_name=name))
    return self._call_with_mutation_context(
        func,
        params,
        {
            "request_id": dl.get_request_identity().get("request_id") or str(uuid.uuid4()),
            "method": method_spec.name,
            "doc_keys": tuple(keys),
            "doc_names": tuple(declared),
            "identity": dict(dl.get_request_identity()),
            "method_spec": method_spec,
            "expected_objects": self._expected_object_names(params),
            "lease_enforced": True,
        },
    )
