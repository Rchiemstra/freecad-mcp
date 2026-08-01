"""Typed mutation descriptors and GUI-thread transaction/postflight helpers."""

from __future__ import annotations

# §3.3 compatibility shims — keep old import paths working.
from .mutation_guard_ops.document_health_capture import (
    calculate_document_health_delta,
    capture_document_health,
)
from .mutation_guard_ops.document_health_delta import DocumentHealthDelta
from .mutation_guard_ops.document_health_snapshot import DocumentHealthSnapshot
from .mutation_guard_ops.document_health_verdict import DocumentHealthVerdict
from .mutation_guard_ops.gui_mutation_transaction import GuiMutationTransaction
from .mutation_guard_ops.method_specs import build_method_specs, make_method_spec
from .mutation_guard_ops.rollback_coverage import RollbackCoverage
from .mutation_guard_ops.rpc_method_spec import RpcMethodSpec
from .mutation_guard_ops.rpc_mutation_kind import RpcMutationKind
from .mutation_guard_ops.validate_invariants import validate_document_invariants
from .mutation_guard_ops.validation_profile import ValidationProfile

__all__ = [
    "DocumentHealthDelta",
    "DocumentHealthSnapshot",
    "DocumentHealthVerdict",
    "GuiMutationTransaction",
    "RollbackCoverage",
    "RpcMethodSpec",
    "RpcMutationKind",
    "ValidationProfile",
    "build_method_specs",
    "calculate_document_health_delta",
    "capture_document_health",
    "make_method_spec",
    "validate_document_invariants",
]
