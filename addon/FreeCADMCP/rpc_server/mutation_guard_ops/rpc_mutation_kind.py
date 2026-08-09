"""RPC mutation kind classification."""

from __future__ import annotations

from enum import StrEnum


class RpcMutationKind(StrEnum):
    READ_ONLY = "read_only"
    LIVE_MUTATION = "live_mutation"
    SAVE = "save"
    RESTORE = "restore"
    CLOSE = "close"
    CONTROL = "control"
