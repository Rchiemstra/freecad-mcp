"""JSON-RPC client connection to a FreeCAD add-on instance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .typed_feature_rpc import attach_p3_feature_rpc

if TYPE_CHECKING:
    from .._shared.protocol.body_create_contract import BodyName, DocumentName
    from .._shared.protocol.boolean_difference_contract import (
        DocumentName as BooleanDifferenceDocumentName,
    )
    from .._shared.protocol.boolean_difference_contract import (
        FeatureName as BooleanDifferenceFeatureName,
    )
    from .._shared.protocol.boolean_intersection_contract import (
        DocumentName as BooleanIntersectionDocumentName,
    )
    from .._shared.protocol.boolean_intersection_contract import (
        FeatureName as BooleanIntersectionFeatureName,
    )
    from .._shared.protocol.boolean_union_contract import (
        DocumentName as BooleanUnionDocumentName,
    )
    from .._shared.protocol.boolean_union_contract import (
        FeatureName as BooleanUnionFeatureName,
    )
    from .._shared.protocol.chamfer_feature_contract import (
        DocumentName as ChamferFeatureDocumentName,
    )
    from .._shared.protocol.chamfer_feature_contract import (
        FeatureName as ChamferFeatureFeatureName,
    )
    from .._shared.protocol.fillet_feature_contract import (
        DocumentName as FilletFeatureDocumentName,
    )
    from .._shared.protocol.fillet_feature_contract import (
        FeatureName as FilletFeatureFeatureName,
    )
    from .._shared.protocol.helical_sweep_feature_contract import (
        DocumentName as HelicalSweepFeatureDocumentName,
    )
    from .._shared.protocol.helical_sweep_feature_contract import (
        FeatureName as HelicalSweepFeatureFeatureName,
    )
    from .._shared.protocol.linear_pattern_feature_contract import (
        DocumentName as LinearPatternFeatureDocumentName,
    )
    from .._shared.protocol.linear_pattern_feature_contract import (
        FeatureName as LinearPatternFeatureFeatureName,
    )
    from .._shared.protocol.loft_feature_contract import (
        DocumentName as LoftFeatureDocumentName,
    )
    from .._shared.protocol.loft_feature_contract import (
        FeatureName as LoftFeatureFeatureName,
    )
    from .._shared.protocol.mirror_feature_contract import (
        DocumentName as MirrorFeatureDocumentName,
    )
    from .._shared.protocol.mirror_feature_contract import (
        FeatureName as MirrorFeatureFeatureName,
    )
    from .._shared.protocol.polar_pattern_feature_contract import (
        DocumentName as PolarPatternFeatureDocumentName,
    )
    from .._shared.protocol.polar_pattern_feature_contract import (
        FeatureName as PolarPatternFeatureFeatureName,
    )
    from .._shared.protocol.revolve_feature_contract import (
        DocumentName as RevolveFeatureDocumentName,
    )
    from .._shared.protocol.revolve_feature_contract import (
        FeatureName as RevolveFeatureFeatureName,
    )
    from .._shared.protocol.sweep_feature_contract import (
        DocumentName as SweepFeatureDocumentName,
    )
    from .._shared.protocol.sweep_feature_contract import (
        FeatureName as SweepFeatureFeatureName,
    )


class FreeCADConnection:
    """Authenticated JSON-RPC client for one FreeCAD add-on RPC endpoint."""

    if TYPE_CHECKING:

        def body_create(
            self, doc_name: DocumentName, body_name: BodyName
        ) -> object: ...

        def boolean_difference(
            self,
            doc_name: BooleanDifferenceDocumentName,
            shape1: BooleanDifferenceFeatureName,
            shape2: BooleanDifferenceFeatureName,
            result_name: BooleanDifferenceFeatureName,
        ) -> object: ...

        def boolean_intersection(
            self,
            doc_name: BooleanIntersectionDocumentName,
            shape1: BooleanIntersectionFeatureName,
            shape2: BooleanIntersectionFeatureName,
            result_name: BooleanIntersectionFeatureName,
        ) -> object: ...

        def boolean_union(
            self,
            doc_name: BooleanUnionDocumentName,
            shape1: BooleanUnionFeatureName,
            shape2: BooleanUnionFeatureName,
            result_name: BooleanUnionFeatureName,
        ) -> object: ...

        def chamfer_feature(
            self,
            doc_name: ChamferFeatureDocumentName,
            base_feature: ChamferFeatureFeatureName,
            chamfer_name: ChamferFeatureFeatureName,
            size: float,
            edge_refs: list[str] | None = None,
            body_name: ChamferFeatureFeatureName | None = None,
        ) -> object: ...

        def fillet_feature(
            self,
            doc_name: FilletFeatureDocumentName,
            base_feature: FilletFeatureFeatureName,
            fillet_name: FilletFeatureFeatureName,
            radius: float,
            edge_refs: list[str] | None = None,
            body_name: FilletFeatureFeatureName | None = None,
        ) -> object: ...

        def helical_sweep_feature(
            self,
            doc_name: HelicalSweepFeatureDocumentName,
            profile_sketch: HelicalSweepFeatureFeatureName,
            helix_name: HelicalSweepFeatureFeatureName,
            pitch: float,
            height: float,
            radius: float,
            body_name: HelicalSweepFeatureFeatureName | None = None,
            left_handed: bool = False,
            reversed_dir: bool = False,
        ) -> object: ...

        def linear_pattern_feature(
            self,
            doc_name: LinearPatternFeatureDocumentName,
            feature_name: LinearPatternFeatureFeatureName,
            pattern_name: LinearPatternFeatureFeatureName,
            length: float,
            occurrences: int,
            direction: str = "X_Axis",
            body_name: LinearPatternFeatureFeatureName | None = None,
            reversed_dir: bool = False,
        ) -> object: ...

        def loft_feature(
            self,
            doc_name: LoftFeatureDocumentName,
            sketch_names: list[LoftFeatureFeatureName],
            loft_name: LoftFeatureFeatureName,
            body_name: LoftFeatureFeatureName | None = None,
            ruled: bool = False,
            closed: bool = False,
        ) -> object: ...

        def mirror_feature(
            self,
            doc_name: MirrorFeatureDocumentName,
            feature_name: MirrorFeatureFeatureName,
            mirror_name: MirrorFeatureFeatureName,
            plane: str = "YZ_Plane",
            body_name: MirrorFeatureFeatureName | None = None,
        ) -> object: ...

        def polar_pattern_feature(
            self,
            doc_name: PolarPatternFeatureDocumentName,
            feature_name: PolarPatternFeatureFeatureName,
            pattern_name: PolarPatternFeatureFeatureName,
            occurrences: int,
            angle: float = 360.0,
            axis: str = "Z_Axis",
            body_name: PolarPatternFeatureFeatureName | None = None,
            reversed_dir: bool = False,
        ) -> object: ...

        def revolve_feature(
            self,
            doc_name: RevolveFeatureDocumentName,
            sketch_name: RevolveFeatureFeatureName,
            revolve_name: RevolveFeatureFeatureName,
            angle: float = 360.0,
            axis: str = "Z_Axis",
            body_name: RevolveFeatureFeatureName | None = None,
            symmetric: bool = False,
            reversed_dir: bool = False,
        ) -> object: ...

        def sweep_feature(
            self,
            doc_name: SweepFeatureDocumentName,
            profile_sketch: SweepFeatureFeatureName,
            path_sketch: SweepFeatureFeatureName,
            sweep_name: SweepFeatureFeatureName,
            body_name: SweepFeatureFeatureName | None = None,
            frenet: bool = False,
        ) -> object: ...


attach_p3_feature_rpc(FreeCADConnection)
