"""JSON-RPC client connection to a FreeCAD add-on instance."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .._shared.protocol.body_create_contract import BodyName, DocumentName
    from .._shared.protocol.body_set_tip_contract import BodyName as TipBodyName
    from .._shared.protocol.body_set_tip_contract import DocumentName as TipDocumentName
    from .._shared.protocol.body_set_tip_contract import FeatureName as TipFeatureName
    from .._shared.protocol.pad_feature_contract import DocumentName as PadDocumentName
    from .._shared.protocol.pad_feature_contract import PadName
    from .._shared.protocol.pocket_feature_contract import DocumentName as PocketDocumentName
    from .._shared.protocol.pocket_feature_contract import PocketName
    from .._shared.protocol.sketch_add_constraint_contract import (
        DocumentName as AddConstraintDocumentName,
    )
    from .._shared.protocol.sketch_add_constraint_contract import SketchName as AddConstraintSketchName
    from .._shared.protocol.sketch_add_geometry_contract import (
        DocumentName as AddGeometryDocumentName,
    )
    from .._shared.protocol.sketch_add_geometry_contract import SketchName as AddGeometrySketchName
    from .._shared.protocol.sketch_attach_contract import DocumentName as AttachDocumentName
    from .._shared.protocol.sketch_attach_contract import SketchName as AttachSketchName
    from .._shared.protocol.sketch_create_contract import DocumentName as SketchCreateDocumentName
    from .._shared.protocol.sketch_create_contract import SketchName as SketchCreateName
    from .._shared.protocol.sketch_delete_constraint_contract import (
        DocumentName as DeleteConstraintDocumentName,
    )
    from .._shared.protocol.sketch_delete_constraint_contract import (
        SketchName as DeleteConstraintSketchName,
    )
    from .._shared.protocol.sketch_delete_geometry_contract import (
        DocumentName as DeleteGeometryDocumentName,
    )
    from .._shared.protocol.sketch_delete_geometry_contract import (
        SketchName as DeleteGeometrySketchName,
    )
    from .._shared.protocol.sketch_edit_constraint_contract import (
        DocumentName as EditConstraintDocumentName,
    )
    from .._shared.protocol.sketch_edit_constraint_contract import SketchName as EditConstraintSketchName


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

        def sketch_create(
            self,
            doc_name: SketchCreateDocumentName,
            sketch_name: SketchCreateName,
            body_name: str | None = None,
            attach_to: str | None = None,
        ) -> object: ...

        def sketch_attach(
            self,
            doc_name: AttachDocumentName,
            sketch_name: AttachSketchName,
            support: object,
            attachment_offset: Mapping[str, object] | None = None,
        ) -> object: ...

        def pad_feature(
            self,
            doc_name: PadDocumentName,
            sketch_name: str,
            pad_name: PadName,
            length: float,
            body_name: str | None = None,
            symmetric: bool = False,
            reversed_dir: bool = False,
        ) -> object: ...

        def pocket_feature(
            self,
            doc_name: PocketDocumentName,
            sketch_name: str,
            pocket_name: PocketName,
            length: float,
            body_name: str | None = None,
            symmetric: bool = False,
            reversed_dir: bool = False,
        ) -> object: ...

        def sketch_add_geometry(
            self,
            doc_name: AddGeometryDocumentName,
            sketch_name: AddGeometrySketchName,
            geometry: Sequence[object],
        ) -> object: ...

        def sketch_add_constraint(
            self,
            doc_name: AddConstraintDocumentName,
            sketch_name: AddConstraintSketchName,
            constraints: Sequence[object],
        ) -> object: ...

        def sketch_delete_geometry(
            self,
            doc_name: DeleteGeometryDocumentName,
            sketch_name: DeleteGeometrySketchName,
            geometry_indices: Sequence[int],
        ) -> object: ...

        def sketch_delete_constraint(
            self,
            doc_name: DeleteConstraintDocumentName,
            sketch_name: DeleteConstraintSketchName,
            constraint_indices: Sequence[int] | None = None,
            constraint_names: Sequence[str] | None = None,
        ) -> object: ...

        def sketch_edit_constraint(
            self,
            doc_name: EditConstraintDocumentName,
            sketch_name: EditConstraintSketchName,
            value: float | None = None,
            name: str | None = None,
            index: int | None = None,
        ) -> object: ...
