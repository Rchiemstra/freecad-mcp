"""Static contract examples for the body-create collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.body_create import (
    BodyCreateCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)


class CompleteBodyCreateDouble:
    """A test double that satisfies every body-create dependency."""

    freecad: Any

    def validate_document_invariants(self, document: Any) -> None:
        pass

    def commit_compatibility_mutation(
        self,
        document_name: str,
        callback: Callable[[], Any],
        *,
        structural: bool = False,
    ) -> Any:
        return None


class MissingStructuralScopeDouble:
    """A stale double that cannot receive the structural mutation scope."""

    freecad: Any

    def validate_document_invariants(self, document: Any) -> None:
        pass

    def commit_compatibility_mutation(
        self,
        document_name: str,
        callback: Callable[[], Any],
    ) -> Any:
        return None


complete: BodyCreateCollaborators = CompleteBodyCreateDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> BodyCreateCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


# With --warn-unused-ignores, mypy fails if the protocol becomes loose enough
# to accept a double that cannot receive structural=True.
missing_scope: BodyCreateCollaborators = MissingStructuralScopeDouble()  # type: ignore[assignment]
