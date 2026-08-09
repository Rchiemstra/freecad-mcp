"""RPC method mutation descriptor."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .rollback_coverage import RollbackCoverage
from .rpc_mutation_kind import RpcMutationKind
from .validation_profile import ValidationProfile


@dataclass(frozen=True)
class RpcMethodSpec:
    name: str
    kind: RpcMutationKind
    transaction: bool = False
    recompute: bool = False
    validator: Callable[[Any], Mapping[str, Any]] | None = None
    may_rebind_document: bool = False
    allowed_during_recovery: bool = False
    pin_replay_for_lease_lifetime: bool = False
    validation_profile: ValidationProfile = ValidationProfile.DEFAULT
    rollback_coverage: RollbackCoverage = RollbackCoverage.DOCUMENT_ONLY

    @property
    def mutates_live_document(self) -> bool:
        return self.kind in {
            RpcMutationKind.LIVE_MUTATION,
            RpcMutationKind.SAVE,
            RpcMutationKind.RESTORE,
            RpcMutationKind.CLOSE,
        }
