"""Internal dispatch helpers bound on ``FreeCADRPC``."""

from .dispatch_helpers_ops.cancellation import (
    begin_request_cancellation,
    complete_request_cancellation,
    finish_cancellation_resolution,
    wait_for_cancellation_resolution,
)
from .dispatch_helpers_ops.credential_inflight import (
    model_credential,
    retain_inflight_credential,
    touch_inflight_credential,
)
from .dispatch_helpers_ops.dispatch_core import dispatch
from .dispatch_helpers_ops.dispatch_gui import dispatch_gui, dispatch_snapshot_gui
from .dispatch_helpers_ops.inflight_context import current_inflight, request_checkpoint
from .dispatch_helpers_ops.mutation_context import call_with_mutation_context
from .dispatch_helpers_ops.mutation_execute import execute_mutation_with_health
from .dispatch_helpers_ops.mutation_health import (
    adapt_gui_mutation_result,
    aggregate_document_health,
    expected_object_names,
    observed_document_evidence,
    unknown_mutation_evidence,
)

__all__ = [
    "adapt_gui_mutation_result",
    "aggregate_document_health",
    "begin_request_cancellation",
    "call_with_mutation_context",
    "complete_request_cancellation",
    "current_inflight",
    "dispatch",
    "dispatch_gui",
    "dispatch_snapshot_gui",
    "execute_mutation_with_health",
    "expected_object_names",
    "finish_cancellation_resolution",
    "model_credential",
    "observed_document_evidence",
    "request_checkpoint",
    "retain_inflight_credential",
    "touch_inflight_credential",
    "unknown_mutation_evidence",
    "wait_for_cancellation_resolution",
]


