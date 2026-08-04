from __future__ import annotations

# ruff: noqa: F403, F405
from ._support import *

"""Lease-service GUI task execution path."""


def _mutation_capability_context(captured, credentials, documents, spec):
    try:
        from document_lease import core_authority

        generations = {
            name: int(getattr(credential, "generation", 0) or 0)
            for name, credential, _state in credentials
        }
        kind_names = core_authority.kinds_for_rpc_method(
            captured["method"],
            getattr(spec.kind, "value", str(spec.kind)),
        )
        return core_authority.open_documents_mutation_capability(
            documents,
            generations=generations,
            kinds=kind_names,
        )
    except Exception:
        from contextlib import nullcontext

        return nullcontext([])


def _authorize_gui_credentials(self, collaborators, captured, inflight, lease):
    credentials = []
    marker_keys = list(captured["doc_keys"]) + list(captured["doc_names"])
    for name in captured["doc_names"]:
        credential, document_identity = collaborators.credential_for_document(
            name, captured["identity"]
        )
        allowed_states = {lease.LeaseState.LOCKED_IDLE}
        if captured["method_spec"].allowed_during_recovery:
            allowed_states.add(lease.LeaseState.LOCKED_ERROR)
        record = collaborators.document_lease_service.authorize(
            credential,
            selector={
                "document_session_uuid": document_identity.session_uuid,
                "document_name": name,
            },
            allowed_states=allowed_states,
        )
        self._touch_inflight_credential(credential, inflight)
        credentials.append((name, credential, record.state))
        marker_keys.extend(
            value
            for value in (
                getattr(credential, "document_session_uuid", None),
                getattr(record.document, "canonical_path", None),
                getattr(record.document, "comparison_key", None),
            )
            if value
        )
        collaborators.assert_mutation_file_metadata_unchanged(record)
    return credentials, tuple(sorted(set(marker_keys)))


def _begin_gui_lease_operations(
    collaborators, captured, inflight, credentials, lease
):
    operation = captured["method"]
    if inflight is not None:
        inflight.token.begin_mutation("gui_mutation_authorized")
    for _name, credential, initial_state in credentials:
        if "recompute" in operation:
            collaborators.document_lease_service.begin_recompute(credential)
        elif initial_state == lease.LeaseState.LOCKED_ERROR:
            collaborators.document_lease_service.begin_recovery(
                credential, operation=operation
            )
        else:
            collaborators.document_lease_service.begin_mutation(
                credential, operation=operation
            )


def _complete_gui_lease_operations(
    collaborators, captured, inflight, credentials, operation, result, failed
):
    for name, credential, _state in credentials:
        document = collaborators.freecad.getDocument(name)
        dirty = require_document_modified(document) if document is not None else True
        if failed:
            collaborators.document_lease_service.record_error(
                credential,
                code=str(result.get("error_code") or "OPERATION_FAILED"),
                message=collaborators.redact_rpc_diagnostic(
                    result.get("error") or result.get("message") or operation,
                    identity=captured["identity"],
                    inflight=inflight,
                ),
                request_id=captured["request_id"],
                dirty=dirty,
            )
        else:
            collaborators.document_lease_service.complete_operation(
                credential, dirty=dirty
            )


def _record_gui_lease_errors(collaborators, captured, inflight, credentials, exc):
    for name, credential, _state in credentials:
        try:
            document = collaborators.freecad.getDocument(name)
            collaborators.document_lease_service.record_error(
                credential,
                code=getattr(exc, "code", type(exc).__name__.upper()),
                message=collaborators.redact_rpc_diagnostic(
                    exc,
                    identity=captured["identity"],
                    inflight=inflight,
                ),
                request_id=captured["request_id"],
                dirty=(
                    document_modified_or_dirty(document) if document is not None else True
                ),
            )
        except Exception:
            pass


def run_enforced_lease_service_task(
    self, collaborators, original_task, captured, inflight
):
    dl = collaborators.import_document_lock()
    lease = collaborators.import_document_lease()
    credentials, marker_keys = _authorize_gui_credentials(
        self, collaborators, captured, inflight, lease
    )
    attribution_started = False
    operation = captured["method"]
    try:
        _begin_gui_lease_operations(
            collaborators, captured, inflight, credentials, lease
        )
        dl.begin_agent_mutation_scope(captured["request_id"], marker_keys)
        attribution_started = True
        documents = [
            collaborators.freecad.getDocument(name)
            for name, _credential, _state in credentials
        ]
        if any(document is None for document in documents):
            raise RuntimeError("A declared document closed before mutation execution")
        spec = captured["method_spec"]

        def begin_recompute():
            for _name, credential, _state in credentials:
                collaborators.document_lease_service.begin_recompute(credential)

        with _mutation_capability_context(captured, credentials, documents, spec):
            result, failed = self._execute_mutation_with_health(
                original_task,
                documents,
                spec,
                expected_objects=captured["expected_objects"],
                inflight=inflight,
                recompute_callback=begin_recompute,
                request_id=captured["request_id"],
            )
        _complete_gui_lease_operations(
            collaborators, captured, inflight, credentials, operation, result, failed
        )
        return result
    except Exception as exc:
        _record_gui_lease_errors(
            collaborators, captured, inflight, credentials, exc
        )
        raise
    finally:
        if attribution_started:
            dl.end_agent_mutation_scope(captured["request_id"], marker_keys)
