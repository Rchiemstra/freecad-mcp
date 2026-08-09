"""RPC method spec construction from legacy verb registry."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .method_spec_constants import (
    FULL_VALIDATION_METHODS,
    LEASE_LIFETIME_IDEMPOTENCY_METHODS,
    NATIVE_COMPATIBILITY_METHODS,
    NO_OUTER_TRANSACTION,
    PARTDESIGN_METHODS,
    PARTIAL_ROLLBACK_METHODS,
    REBIND_DOCUMENT_METHODS,
    SAVE_LIFECYCLE_METHODS,
)
from .rollback_coverage import RollbackCoverage
from .rpc_method_spec import RpcMethodSpec
from .rpc_mutation_kind import RpcMutationKind
from .validate_invariants import validate_document_invariants
from .validation_profile import ValidationProfile


def make_method_spec(name: str, kind: str) -> RpcMethodSpec:
    """Translate the exhaustive legacy verb registry into a richer descriptor."""

    normalized = str(kind).upper()
    if normalized == "READ_ONLY":
        return RpcMethodSpec(name, RpcMutationKind.READ_ONLY)
    if normalized == "LIFECYCLE":
        lifecycle_kind = (
            RpcMutationKind.SAVE
            if name in SAVE_LIFECYCLE_METHODS
            else RpcMutationKind.CONTROL
        )
        return RpcMethodSpec(
            name,
            lifecycle_kind,
            may_rebind_document=name in {"save_document_as", "finalize_document_edit"},
            pin_replay_for_lease_lifetime=(
                name in LEASE_LIFETIME_IDEMPOTENCY_METHODS
            ),
        )
    mutation_kind = (
        RpcMutationKind.RESTORE
        if name in {"restore", "reload_document"}
        else RpcMutationKind.CLOSE
        if name == "close_document"
        else RpcMutationKind.LIVE_MUTATION
    )
    return RpcMethodSpec(
        name,
        mutation_kind,
        transaction=name not in NO_OUTER_TRANSACTION,
        recompute=(
            name in PARTDESIGN_METHODS
            and name not in NATIVE_COMPATIBILITY_METHODS
        ),
        validator=(
            validate_document_invariants
            if (
                name in PARTDESIGN_METHODS
                and name not in NATIVE_COMPATIBILITY_METHODS
            )
            else None
        ),
        may_rebind_document=name in REBIND_DOCUMENT_METHODS,
        # A failed typed mutation rolls the document transaction back but leaves
        # the lease in LOCKED_ERROR as a visible fence. The credential owner
        # must be able to correct or retry through another typed, health-checked
        # mutation. Keep arbitrary-code and legacy nested-code escape hatches
        # blocked; local restore/reload remains an explicit recovery path.
        allowed_during_recovery=(
            mutation_kind == RpcMutationKind.RESTORE
            or (
                mutation_kind == RpcMutationKind.LIVE_MUTATION
                and name not in {"execute_code", "run_transaction"}
            )
        ),
        pin_replay_for_lease_lifetime=True,
        validation_profile=(
            ValidationProfile.FULL
            if name in FULL_VALIDATION_METHODS
            else ValidationProfile.DEFAULT
        ),
        rollback_coverage=(
            RollbackCoverage.PARTIAL
            if name in PARTIAL_ROLLBACK_METHODS
            else RollbackCoverage.UNAVAILABLE
            if name == "execute_code"
            else RollbackCoverage.DOCUMENT_ONLY
        ),
    )


def build_method_specs(
    classifications: Mapping[str, tuple[Any, Any]],
) -> dict[str, RpcMethodSpec]:
    return {
        name: make_method_spec(name, getattr(kind, "value", str(kind)))
        for name, (kind, _resolver) in classifications.items()
    }
