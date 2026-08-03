from __future__ import annotations

# ruff: noqa: F403, F405
from ._support import *
from .dispatch_core_enforcement import dispatch_enforcement
from .dispatch_core_unenforced import dispatch_unenforced_mutation, import_document_lock_or_none

"""RPC dispatch chokepoint with lease enforcement."""


def dispatch(self, method, params):
    """RPC chokepoint: enforce document leases when configured.

    When ``document_lock_enforcement`` is off, behaviour is identical to
    the default SimpleXMLRPCDispatcher instance dispatch.
    """
    dl = import_document_lock_or_none()
    if dl is None:
        func = getattr(self, method, None)
        if func is None or method.startswith("_"):
            raise Exception(f'method "{method}" is not supported')
        return func(*params)

    kind, extractor = dl.classify_verb(method)
    method_spec = make_method_spec(method, kind.value)
    enforce = dl.is_enforcement_enabled()

    func = getattr(self, method, None)
    if func is None or method.startswith("_"):
        raise Exception(f'method "{method}" is not supported')

    if not enforce:
        read_only_execute = (
            method == "execute_code"
            and len(params) > 1
            and isinstance(params[1], dict)
            and bool(params[1].get("read_only", False))
        )
        if (
            method_spec.mutates_live_document
            and not read_only_execute
            and method != "create_document"
        ):
            return dispatch_unenforced_mutation(
                self, method, params, func, method_spec, extractor, dl
            )
        return func(*params)
    return dispatch_enforcement(
        self,
        method,
        params,
        func,
        kind,
        extractor,
        method_spec,
        dl,
        dl.VerbKind,
        dl.annotate_read_result,
        dl.check_mutation_allowed,
        dl.resolve_doc_key,
        dl.extract_referenced_documents_from_code,
        dl.validate_unsafe_execute_scope,
    )
