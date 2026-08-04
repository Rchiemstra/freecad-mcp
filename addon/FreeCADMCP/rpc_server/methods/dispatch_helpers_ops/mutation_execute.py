from __future__ import annotations

# ruff: noqa: F403, F405
from ._support import *
from .mutation_execute_body import (
    mutation_failure_result,
    run_mutation_transaction_body,
)
from .mutation_execute_close import finalize_close_mutation
from .mutation_execute_finalize import finalize_mutation_health

"""Execute typed GUI mutations with health postflight."""


def _capture_mutation_baselines(freecad, documents, spec, expected):
    all_before = {
        str(getattr(document, "Name", "") or ""): capture_document_health(
            document,
            profile=(
                spec.validation_profile
                if document in documents
                else ValidationProfile.MINIMAL
            ),
            affected_objects=expected,
        )
        for document in tuple(freecad.listDocuments().values())
    }
    before = {
        str(getattr(document, "Name", "") or ""): all_before[
            str(getattr(document, "Name", "") or "")
        ]
        for document in documents
    }
    return all_before, before


def execute_mutation_with_health(
    self,
    task,
    documents,
    spec,
    *,
    expected_objects=(),
    inflight=None,
    recompute_callback=None,
    request_id=None,
):
    """Run, validate, then commit a typed GUI mutation."""

    documents = tuple(documents)
    freecad = self._execution_collaborators.freecad
    expected = set(expected_objects)
    declared_names = {
        str(getattr(document, "Name", "") or "") for document in documents
    }
    all_before, before = _capture_mutation_baselines(
        freecad, documents, spec, expected
    )
    transaction = GuiMutationTransaction(
        documents,
        f"MCP: {spec.name}",
        enabled=spec.transaction,
    )
    result = None
    failed = False
    attempted_deltas = []
    unexpected_documents = []
    validation_error = None
    transaction.__enter__()
    try:
        if inflight is not None:
            inflight.token.checkpoint("gui_mutation_invocation")
        result = task()
        failed = isinstance(result, dict) and (
            result.get("success") is False or result.get("ok") is False
        )
        if spec.kind == RpcMutationKind.CLOSE:
            return finalize_close_mutation(
                self,
                transaction,
                spec,
                result,
                failed,
                declared_names=declared_names,
                request_id=request_id,
            )
        (
            result,
            failed,
            attempted_deltas,
            unexpected_documents,
            validation_error,
        ) = run_mutation_transaction_body(
            self,
            documents=documents,
            spec=spec,
            before=before,
            all_before=all_before,
            declared_names=declared_names,
            expected=expected,
            inflight=inflight,
            recompute_callback=recompute_callback,
            result=result,
            failed=failed,
            transaction=transaction,
            freecad=freecad,
        )
    except RequestCancellationError:
        transaction.abort()
        raise
    except Exception as exc:
        transaction.abort()
        result, failed, validation_error = mutation_failure_result(result, exc)
    finally:
        transaction.__exit__(None, None, None)

    return finalize_mutation_health(
        self,
        transaction=transaction,
        spec=spec,
        result=result,
        failed=failed,
        before=before,
        documents=documents,
        expected=expected,
        declared_names=declared_names,
        attempted_deltas=attempted_deltas,
        unexpected_documents=unexpected_documents,
        validation_error=validation_error,
        request_id=request_id,
    )
