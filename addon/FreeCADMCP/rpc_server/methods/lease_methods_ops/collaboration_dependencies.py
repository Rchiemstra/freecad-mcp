"""Native collaboration and authenticated-runtime dependencies."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any, Protocol


class CompatibilityMutationAPI(Protocol):
    """The narrow native compatibility-mutation bridge used by the add-on."""

    def commit_compatibility_mutation(
        self,
        document_name: str,
        callback: Callable[[], Any],
        *,
        structural: bool = False,
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class CollaborationCollaborators:
    """Policy-free native collaboration and authenticated replay dependencies."""

    compatibility_api: CompatibilityMutationAPI
    freecad: Any
    runtime_manifest: Any | None
    inflight_request_registry: Any | None
    request_replay_cache: Any | None
    rpc_server_runtime_id: str | None
    addon_loaded_at: Any

    def __post_init__(self) -> None:
        if self.freecad is None:
            raise ValueError("freecad collaborator is required")
        if not callable(
            getattr(self.compatibility_api, "commit_compatibility_mutation", None)
        ):
            raise TypeError(
                "compatibility_api.commit_compatibility_mutation must be callable"
            )

    def commit_compatibility_mutation(
        self,
        document_name: str,
        callback: Callable[[], Any],
        *,
        structural: bool = False,
    ) -> Any:
        return self.compatibility_api.commit_compatibility_mutation(
            document_name, callback, structural=structural
        )

    def with_runtime_manifest(self, runtime_manifest: Any) -> CollaborationCollaborators:
        if runtime_manifest is None:
            raise ValueError("runtime_manifest collaborator is required")
        if (
            self.runtime_manifest is not None
            and self.runtime_manifest is not runtime_manifest
        ):
            raise RuntimeError("runtime_manifest collaborator is already bound")
        if self.runtime_manifest is runtime_manifest:
            return self
        return replace(self, runtime_manifest=runtime_manifest)

    def _without_runtime_manifest(self) -> CollaborationCollaborators:
        if self.runtime_manifest is None:
            return self
        return replace(self, runtime_manifest=None)


__all__ = ["CollaborationCollaborators", "CompatibilityMutationAPI"]
