"""JSON-RPC client connection to a FreeCAD add-on instance."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from .._shared.protocol.activate_document_contract import (
        DocumentName as ActivateDocumentName,
    )
    from .._shared.protocol.body_create_contract import BodyName
    from .._shared.protocol.body_create_contract import DocumentName as BodyDocumentName
    from .._shared.protocol.close_document_contract import DocumentName as CloseDocumentName
    from .._shared.protocol.create_document_contract import (
        DocumentName as CreateDocumentName,
    )
    from .._shared.protocol.create_object_contract import CreateObjectPayload
    from .._shared.protocol.create_object_contract import (
        DocumentName as CreateObjectDocumentName,
    )
    from .._shared.protocol.delete_object_contract import (
        DocumentName as DeleteObjectDocumentName,
    )
    from .._shared.protocol.delete_object_contract import ObjectName as DeleteObjectName
    from .._shared.protocol.edit_object_contract import DocumentName as EditObjectDocumentName
    from .._shared.protocol.edit_object_contract import EditObjectPayload
    from .._shared.protocol.edit_object_contract import ObjectName as EditObjectName
    from .._shared.protocol.insert_part_from_library_contract import (
        DocumentName as InsertPartDocumentName,
    )
    from .._shared.protocol.open_document_contract import PathName as OpenDocumentPath
    from .._shared.protocol.recompute_and_wait_contract import (
        DocumentName as RecomputeAndWaitDocumentName,
    )
    from .._shared.protocol.recompute_document_contract import (
        DocumentName as RecomputeDocumentName,
    )
    from .._shared.protocol.redo_contract import DocumentName as RedoDocumentName
    from .._shared.protocol.reload_document_contract import (
        DocumentName as ReloadDocumentName,
    )
    from .._shared.protocol.repair_references_contract import (
        DocumentName as RepairReferencesDocumentName,
    )
    from .._shared.protocol.repair_references_contract import RepairItemPayload
    from .._shared.protocol.undo_contract import DocumentName as UndoDocumentName


class FreeCADConnection:
    """Authenticated JSON-RPC client for one FreeCAD add-on RPC endpoint."""

    def close_document(self, doc_name: CloseDocumentName) -> object:
        routed = self._invoke_mutation_v2(
            "close_document",
            {"doc_name": doc_name},
            document_names=(doc_name,),
            operation_name="Close document",
        )
        if routed is not None:
            return routed
        return self.invoke_rpc("close_document", doc_name)

    if TYPE_CHECKING:

        def _invoke_mutation_v2(self, *args: object, **kwargs: object) -> object: ...

        def invoke_rpc(self, *args: object, **kwargs: object) -> object: ...

        def body_create(
            self, doc_name: BodyDocumentName, body_name: BodyName
        ) -> object: ...

        def create_document(self, name: CreateDocumentName) -> object: ...

        def create_object(
            self,
            doc_name: CreateObjectDocumentName,
            obj_data: CreateObjectPayload,
        ) -> object: ...

        def delete_object(
            self,
            doc_name: DeleteObjectDocumentName,
            obj_name: DeleteObjectName,
            recursive: bool = False,
            force: bool = False,
        ) -> object: ...

        def edit_object(
            self,
            doc_name: EditObjectDocumentName,
            obj_name: EditObjectName,
            properties: EditObjectPayload | Mapping[str, object],
        ) -> object: ...

        def repair_references(
            self,
            doc_name: RepairReferencesDocumentName,
            repairs: Sequence[RepairItemPayload],
            recompute: bool = False,
            validate: bool = False,
        ) -> object: ...

        def activate_document(self, doc_name: ActivateDocumentName) -> object: ...

        def insert_part_from_library(
            self, doc_name: InsertPartDocumentName, relative_path: str
        ) -> object: ...

        def open_document(self, path: OpenDocumentPath) -> object: ...

        def recompute_and_wait(
            self, doc_name: RecomputeAndWaitDocumentName
        ) -> object: ...

        def recompute_document(self, doc_name: RecomputeDocumentName) -> object: ...

        def redo(self, doc_name: RedoDocumentName) -> object: ...

        def reload_document(self, doc_name: ReloadDocumentName) -> object: ...

        def undo(self, doc_name: UndoDocumentName) -> object: ...
