"""Static contract examples for the body-create collaborator boundary."""

from __future__ import annotations

from collections.abc import Callable

from addon.FreeCADMCP._shared.protocol.body_create_contract import (
    BodyCreateRequest,
    BodyCreateSuccess,
    BodyDocument,
    BodyName,
    BodyReadDocument,
    DocumentName,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.body_create import (
    BodyCreateCollaborators,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)


class CompleteBodyCreateDouble:
    """A test double that satisfies every body-create dependency."""

    def validate_document_invariants(self, document: BodyReadDocument) -> object:
        return None

    def commit_body_create_mutation(
        self,
        document_name: DocumentName,
        callback: Callable[[BodyDocument], object],
        postcondition: Callable[[BodyReadDocument], object],
    ) -> object:
        return None


class MissingPostconditionDouble:
    """A stale double that cannot receive the native phase contract."""

    def validate_document_invariants(self, document: BodyReadDocument) -> object:
        return None

    def commit_body_create_mutation(
        self,
        document_name: DocumentName,
        callback: Callable[[BodyDocument], object],
    ) -> object:
        return None


complete: BodyCreateCollaborators = CompleteBodyCreateDouble()


def production_collaborators_are_compatible(
    collaborators: CadCollaborators,
) -> BodyCreateCollaborators:
    """Prove that the real dependency container satisfies the narrow protocol."""

    return collaborators


# With --warn-unused-ignores, mypy fails if the protocol becomes loose enough
# to accept a double that cannot receive the native postcondition contract.
missing_postcondition: BodyCreateCollaborators = MissingPostconditionDouble()  # type: ignore[assignment]

document_name = DocumentName("Model")
body_name = BodyName("MainBody")
valid_request = BodyCreateRequest(doc_name=document_name, body_name=body_name)
swapped_request = BodyCreateRequest(
    doc_name=body_name,  # type: ignore[arg-type]
    body_name=document_name,  # type: ignore[arg-type]
)

# A committed response cannot be constructed without its assigned Body name or
# the remaining required state fields.
incomplete_success: BodyCreateSuccess = {  # type: ignore[typeddict-item]
    "contract_version": 1,
    "success": True,
    "ok": True,
}
