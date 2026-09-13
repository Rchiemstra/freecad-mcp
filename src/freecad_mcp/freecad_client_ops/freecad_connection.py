"""JSON-RPC client connection to a FreeCAD add-on instance."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .._shared.protocol.body_create_contract import BodyName, DocumentName
    from .._shared.protocol.body_set_tip_contract import BodyName as TipBodyName
    from .._shared.protocol.body_set_tip_contract import DocumentName as TipDocumentName
    from .._shared.protocol.body_set_tip_contract import FeatureName as TipFeatureName


class FreeCADConnection:
    """Authenticated JSON-RPC client for one FreeCAD add-on RPC endpoint."""

    if TYPE_CHECKING:

        def body_create(
            self, doc_name: DocumentName, body_name: BodyName
        ) -> object: ...

        def body_set_tip(
            self,
            doc_name: TipDocumentName,
            body_name: TipBodyName,
            feature_name: TipFeatureName,
        ) -> object: ...
