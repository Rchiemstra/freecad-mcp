"""JSON-RPC client connection to a FreeCAD add-on instance."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .._shared.protocol.body_create_contract import BodyName, DocumentName
    from .._shared.protocol.sketch_add_line_contract import DocumentName as SketchAddLineDocumentName
    from .._shared.protocol.sketch_add_line_contract import SketchName as SketchAddLineSketchName
    from .._shared.protocol.sketch_add_circle_contract import DocumentName as SketchAddCircleDocumentName
    from .._shared.protocol.sketch_add_circle_contract import SketchName as SketchAddCircleSketchName
    from .._shared.protocol.sketch_add_arc_contract import DocumentName as SketchAddArcDocumentName
    from .._shared.protocol.sketch_add_arc_contract import SketchName as SketchAddArcSketchName
    from .._shared.protocol.sketch_add_rectangle_contract import DocumentName as SketchAddRectangleDocumentName
    from .._shared.protocol.sketch_add_rectangle_contract import SketchName as SketchAddRectangleSketchName
    from .._shared.protocol.sketch_add_ellipse_contract import DocumentName as SketchAddEllipseDocumentName
    from .._shared.protocol.sketch_add_ellipse_contract import SketchName as SketchAddEllipseSketchName
    from .._shared.protocol.sketch_add_arc_of_ellipse_contract import DocumentName as SketchAddArcOfEllipseDocumentName
    from .._shared.protocol.sketch_add_arc_of_ellipse_contract import SketchName as SketchAddArcOfEllipseSketchName
    from .._shared.protocol.sketch_add_slot_contract import DocumentName as SketchAddSlotDocumentName
    from .._shared.protocol.sketch_add_slot_contract import SketchName as SketchAddSlotSketchName
    from .._shared.protocol.sketch_add_polyline_contract import DocumentName as SketchAddPolylineDocumentName
    from .._shared.protocol.sketch_add_polyline_contract import SketchName as SketchAddPolylineSketchName
    from .._shared.protocol.sketch_add_bspline_contract import DocumentName as SketchAddBsplineDocumentName
    from .._shared.protocol.sketch_add_bspline_contract import SketchName as SketchAddBsplineSketchName
    from .._shared.protocol.sketch_add_bspline_through_points_contract import DocumentName as SketchAddBsplineThroughPointsDocumentName
    from .._shared.protocol.sketch_add_bspline_through_points_contract import SketchName as SketchAddBsplineThroughPointsSketchName
    from .._shared.protocol.sketch_add_bezier_contract import DocumentName as SketchAddBezierDocumentName
    from .._shared.protocol.sketch_add_bezier_contract import SketchName as SketchAddBezierSketchName
    from .._shared.protocol.sketch_add_regular_polygon_contract import DocumentName as SketchAddRegularPolygonDocumentName
    from .._shared.protocol.sketch_add_regular_polygon_contract import SketchName as SketchAddRegularPolygonSketchName
    from .._shared.protocol.sketch_add_parametric_curve_contract import DocumentName as SketchAddParametricCurveDocumentName
    from .._shared.protocol.sketch_add_parametric_curve_contract import SketchName as SketchAddParametricCurveSketchName
    from .._shared.protocol.sketch_import_points_contract import DocumentName as SketchImportPointsDocumentName
    from .._shared.protocol.sketch_import_points_contract import SketchName as SketchImportPointsSketchName
    from .._shared.protocol.sketch_toggle_construction_contract import DocumentName as SketchToggleConstructionDocumentName
    from .._shared.protocol.sketch_toggle_construction_contract import SketchName as SketchToggleConstructionSketchName
    from .._shared.protocol.sketch_constrain_coincident_contract import DocumentName as SketchConstrainCoincidentDocumentName
    from .._shared.protocol.sketch_constrain_coincident_contract import SketchName as SketchConstrainCoincidentSketchName
    from .._shared.protocol.sketch_constrain_horizontal_contract import DocumentName as SketchConstrainHorizontalDocumentName
    from .._shared.protocol.sketch_constrain_horizontal_contract import SketchName as SketchConstrainHorizontalSketchName
    from .._shared.protocol.sketch_constrain_vertical_contract import DocumentName as SketchConstrainVerticalDocumentName
    from .._shared.protocol.sketch_constrain_vertical_contract import SketchName as SketchConstrainVerticalSketchName
    from .._shared.protocol.sketch_constrain_distance_contract import DocumentName as SketchConstrainDistanceDocumentName
    from .._shared.protocol.sketch_constrain_distance_contract import SketchName as SketchConstrainDistanceSketchName
    from .._shared.protocol.sketch_constrain_radius_contract import DocumentName as SketchConstrainRadiusDocumentName
    from .._shared.protocol.sketch_constrain_radius_contract import SketchName as SketchConstrainRadiusSketchName
    from .._shared.protocol.sketch_constrain_equal_contract import DocumentName as SketchConstrainEqualDocumentName
    from .._shared.protocol.sketch_constrain_equal_contract import SketchName as SketchConstrainEqualSketchName
    from .._shared.protocol.sketch_constrain_parallel_contract import DocumentName as SketchConstrainParallelDocumentName
    from .._shared.protocol.sketch_constrain_parallel_contract import SketchName as SketchConstrainParallelSketchName
    from .._shared.protocol.sketch_constrain_perpendicular_contract import DocumentName as SketchConstrainPerpendicularDocumentName
    from .._shared.protocol.sketch_constrain_perpendicular_contract import SketchName as SketchConstrainPerpendicularSketchName
    from .._shared.protocol.sketch_constrain_tangent_contract import DocumentName as SketchConstrainTangentDocumentName
    from .._shared.protocol.sketch_constrain_tangent_contract import SketchName as SketchConstrainTangentSketchName
    from .._shared.protocol.sketch_trim_contract import DocumentName as SketchTrimDocumentName
    from .._shared.protocol.sketch_trim_contract import SketchName as SketchTrimSketchName
    from .._shared.protocol.sketch_extend_contract import DocumentName as SketchExtendDocumentName
    from .._shared.protocol.sketch_extend_contract import SketchName as SketchExtendSketchName
    from .._shared.protocol.sketch_split_contract import DocumentName as SketchSplitDocumentName
    from .._shared.protocol.sketch_split_contract import SketchName as SketchSplitSketchName
    from .._shared.protocol.sketch_fillet_contract import DocumentName as SketchFilletDocumentName
    from .._shared.protocol.sketch_fillet_contract import SketchName as SketchFilletSketchName
    from .._shared.protocol.sketch_symmetry_contract import DocumentName as SketchSymmetryDocumentName
    from .._shared.protocol.sketch_symmetry_contract import SketchName as SketchSymmetrySketchName


class FreeCADConnection:
    """Authenticated JSON-RPC client for one FreeCAD add-on RPC endpoint."""

    if TYPE_CHECKING:

        def body_create(
            self, doc_name: DocumentName, body_name: BodyName
        ) -> object: ...

    def _invoke_mutation_v2(
        self,
        method: str,
        params: dict[str, object],
        *,
        document_names: tuple[str, ...] = (),
        operation_name: str | None = None,
    ) -> object | None:
        raise NotImplementedError

    def sketch_add_line(
        self, doc_name: SketchAddLineDocumentName, sketch_name: SketchAddLineSketchName, x1: float, y1: float, x2: float, y2: float, construction: bool = False,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "construction": construction,
        }
        routed = self._invoke_mutation_v2(
            "sketch_add_line",
            params,
            document_names=(doc_name,),
            operation_name='Add sketch line',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_add_circle(
        self, doc_name: SketchAddCircleDocumentName, sketch_name: SketchAddCircleSketchName, cx: float, cy: float, radius: float, construction: bool = False,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "cx": cx,
            "cy": cy,
            "radius": radius,
            "construction": construction,
        }
        routed = self._invoke_mutation_v2(
            "sketch_add_circle",
            params,
            document_names=(doc_name,),
            operation_name='Add sketch circle',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_add_arc(
        self, doc_name: SketchAddArcDocumentName, sketch_name: SketchAddArcSketchName, cx: float, cy: float, radius: float, start_angle: float, end_angle: float, construction: bool = False,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "cx": cx,
            "cy": cy,
            "radius": radius,
            "start_angle": start_angle,
            "end_angle": end_angle,
            "construction": construction,
        }
        routed = self._invoke_mutation_v2(
            "sketch_add_arc",
            params,
            document_names=(doc_name,),
            operation_name='Add sketch arc',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_add_rectangle(
        self, doc_name: SketchAddRectangleDocumentName, sketch_name: SketchAddRectangleSketchName, x1: float, y1: float, x2: float, y2: float, construction: bool = False,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "construction": construction,
        }
        routed = self._invoke_mutation_v2(
            "sketch_add_rectangle",
            params,
            document_names=(doc_name,),
            operation_name='Add sketch rectangle',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_add_ellipse(
        self, doc_name: SketchAddEllipseDocumentName, sketch_name: SketchAddEllipseSketchName, cx: float, cy: float, major_radius: float, minor_radius: float, angle: float = 0.0, construction: bool = False,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "cx": cx,
            "cy": cy,
            "major_radius": major_radius,
            "minor_radius": minor_radius,
            "angle": angle,
            "construction": construction,
        }
        routed = self._invoke_mutation_v2(
            "sketch_add_ellipse",
            params,
            document_names=(doc_name,),
            operation_name='Add sketch ellipse',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_add_arc_of_ellipse(
        self, doc_name: SketchAddArcOfEllipseDocumentName, sketch_name: SketchAddArcOfEllipseSketchName, cx: float, cy: float, major_radius: float, minor_radius: float, start_angle: float, end_angle: float, angle: float = 0.0, construction: bool = False,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "cx": cx,
            "cy": cy,
            "major_radius": major_radius,
            "minor_radius": minor_radius,
            "start_angle": start_angle,
            "end_angle": end_angle,
            "angle": angle,
            "construction": construction,
        }
        routed = self._invoke_mutation_v2(
            "sketch_add_arc_of_ellipse",
            params,
            document_names=(doc_name,),
            operation_name='Add sketch arc of ellipse',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_add_slot(
        self, doc_name: SketchAddSlotDocumentName, sketch_name: SketchAddSlotSketchName, x1: float, y1: float, x2: float, y2: float, width: float, construction: bool = False,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "width": width,
            "construction": construction,
        }
        routed = self._invoke_mutation_v2(
            "sketch_add_slot",
            params,
            document_names=(doc_name,),
            operation_name='Add sketch slot',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_add_polyline(
        self, doc_name: SketchAddPolylineDocumentName, sketch_name: SketchAddPolylineSketchName, points: list[dict[str, float]], closed: bool = False, construction: bool = False,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "points": points,
            "closed": closed,
            "construction": construction,
        }
        routed = self._invoke_mutation_v2(
            "sketch_add_polyline",
            params,
            document_names=(doc_name,),
            operation_name='Add sketch polyline',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_add_bspline(
        self, doc_name: SketchAddBsplineDocumentName, sketch_name: SketchAddBsplineSketchName, poles: list[dict[str, float]], degree: int = 3, weights: list[float] | None = None, knots: list[float] | None = None, multiplicities: list[int] | None = None, periodic: bool = False, construction: bool = False,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "poles": poles,
            "degree": degree,
            "weights": weights,
            "knots": knots,
            "multiplicities": multiplicities,
            "periodic": periodic,
            "construction": construction,
        }
        routed = self._invoke_mutation_v2(
            "sketch_add_bspline",
            params,
            document_names=(doc_name,),
            operation_name='Add sketch BSpline',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_add_bspline_through_points(
        self, doc_name: SketchAddBsplineThroughPointsDocumentName, sketch_name: SketchAddBsplineThroughPointsSketchName, points: list[dict[str, float]], degree: int = 3, periodic: bool = False, construction: bool = False,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "points": points,
            "degree": degree,
            "periodic": periodic,
            "construction": construction,
        }
        routed = self._invoke_mutation_v2(
            "sketch_add_bspline_through_points",
            params,
            document_names=(doc_name,),
            operation_name='Add interpolating sketch BSpline',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_add_bezier(
        self, doc_name: SketchAddBezierDocumentName, sketch_name: SketchAddBezierSketchName, poles: list[dict[str, float]], construction: bool = False,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "poles": poles,
            "construction": construction,
        }
        routed = self._invoke_mutation_v2(
            "sketch_add_bezier",
            params,
            document_names=(doc_name,),
            operation_name='Add sketch Bezier',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_add_regular_polygon(
        self, doc_name: SketchAddRegularPolygonDocumentName, sketch_name: SketchAddRegularPolygonSketchName, cx: float, cy: float, radius: float, sides: int, angle: float = 0.0, construction: bool = False,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "cx": cx,
            "cy": cy,
            "radius": radius,
            "sides": sides,
            "angle": angle,
            "construction": construction,
        }
        routed = self._invoke_mutation_v2(
            "sketch_add_regular_polygon",
            params,
            document_names=(doc_name,),
            operation_name='Add sketch regular polygon',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_add_parametric_curve(
        self, doc_name: SketchAddParametricCurveDocumentName, sketch_name: SketchAddParametricCurveSketchName, x_expr: str, y_expr: str, t_start: float, t_end: float, samples: int = 100, construction: bool = False,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "x_expr": x_expr,
            "y_expr": y_expr,
            "t_start": t_start,
            "t_end": t_end,
            "samples": samples,
            "construction": construction,
        }
        routed = self._invoke_mutation_v2(
            "sketch_add_parametric_curve",
            params,
            document_names=(doc_name,),
            operation_name='Add sketch parametric curve',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_import_points(
        self, doc_name: SketchImportPointsDocumentName, sketch_name: SketchImportPointsSketchName, points: list[dict[str, float]], construction: bool = False,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "points": points,
            "construction": construction,
        }
        routed = self._invoke_mutation_v2(
            "sketch_import_points",
            params,
            document_names=(doc_name,),
            operation_name='Import sketch points',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_toggle_construction(
        self, doc_name: SketchToggleConstructionDocumentName, sketch_name: SketchToggleConstructionSketchName, geo_indices: list[int], construction: bool = False,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "geo_indices": geo_indices,
            "construction": construction,
        }
        routed = self._invoke_mutation_v2(
            "sketch_toggle_construction",
            params,
            document_names=(doc_name,),
            operation_name='Toggle sketch construction',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_constrain_coincident(
        self, doc_name: SketchConstrainCoincidentDocumentName, sketch_name: SketchConstrainCoincidentSketchName, geo1: int, pos1: int, geo2: int, pos2: int,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "geo1": geo1,
            "pos1": pos1,
            "geo2": geo2,
            "pos2": pos2,
        }
        routed = self._invoke_mutation_v2(
            "sketch_constrain_coincident",
            params,
            document_names=(doc_name,),
            operation_name='Add coincident constraint',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_constrain_horizontal(
        self, doc_name: SketchConstrainHorizontalDocumentName, sketch_name: SketchConstrainHorizontalSketchName, geo: int,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "geo": geo,
        }
        routed = self._invoke_mutation_v2(
            "sketch_constrain_horizontal",
            params,
            document_names=(doc_name,),
            operation_name='Add horizontal constraint',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_constrain_vertical(
        self, doc_name: SketchConstrainVerticalDocumentName, sketch_name: SketchConstrainVerticalSketchName, geo: int,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "geo": geo,
        }
        routed = self._invoke_mutation_v2(
            "sketch_constrain_vertical",
            params,
            document_names=(doc_name,),
            operation_name='Add vertical constraint',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_constrain_distance(
        self, doc_name: SketchConstrainDistanceDocumentName, sketch_name: SketchConstrainDistanceSketchName, geo: int, value: float, pos: int | None = None, name: str | None = None,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "geo": geo,
            "value": value,
            "pos": pos,
            "name": name,
        }
        routed = self._invoke_mutation_v2(
            "sketch_constrain_distance",
            params,
            document_names=(doc_name,),
            operation_name='Add distance constraint',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_constrain_radius(
        self, doc_name: SketchConstrainRadiusDocumentName, sketch_name: SketchConstrainRadiusSketchName, geo: int, value: float, name: str | None = None,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "geo": geo,
            "value": value,
            "name": name,
        }
        routed = self._invoke_mutation_v2(
            "sketch_constrain_radius",
            params,
            document_names=(doc_name,),
            operation_name='Add radius constraint',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_constrain_equal(
        self, doc_name: SketchConstrainEqualDocumentName, sketch_name: SketchConstrainEqualSketchName, geo1: int, geo2: int,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "geo1": geo1,
            "geo2": geo2,
        }
        routed = self._invoke_mutation_v2(
            "sketch_constrain_equal",
            params,
            document_names=(doc_name,),
            operation_name='Add equal constraint',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_constrain_parallel(
        self, doc_name: SketchConstrainParallelDocumentName, sketch_name: SketchConstrainParallelSketchName, geo1: int, geo2: int,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "geo1": geo1,
            "geo2": geo2,
        }
        routed = self._invoke_mutation_v2(
            "sketch_constrain_parallel",
            params,
            document_names=(doc_name,),
            operation_name='Add parallel constraint',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_constrain_perpendicular(
        self, doc_name: SketchConstrainPerpendicularDocumentName, sketch_name: SketchConstrainPerpendicularSketchName, geo1: int, geo2: int,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "geo1": geo1,
            "geo2": geo2,
        }
        routed = self._invoke_mutation_v2(
            "sketch_constrain_perpendicular",
            params,
            document_names=(doc_name,),
            operation_name='Add perpendicular constraint',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_constrain_tangent(
        self, doc_name: SketchConstrainTangentDocumentName, sketch_name: SketchConstrainTangentSketchName, geo1: int, geo2: int,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "geo1": geo1,
            "geo2": geo2,
        }
        routed = self._invoke_mutation_v2(
            "sketch_constrain_tangent",
            params,
            document_names=(doc_name,),
            operation_name='Add tangent constraint',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_trim(
        self, doc_name: SketchTrimDocumentName, sketch_name: SketchTrimSketchName, geo_index: int, point_x: float, point_y: float,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "geo_index": geo_index,
            "point_x": point_x,
            "point_y": point_y,
        }
        routed = self._invoke_mutation_v2(
            "sketch_trim",
            params,
            document_names=(doc_name,),
            operation_name='Trim sketch geometry',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_extend(
        self, doc_name: SketchExtendDocumentName, sketch_name: SketchExtendSketchName, geo_index: int, increment: float, end_point: int = 2,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "geo_index": geo_index,
            "increment": increment,
            "end_point": end_point,
        }
        routed = self._invoke_mutation_v2(
            "sketch_extend",
            params,
            document_names=(doc_name,),
            operation_name='Extend sketch geometry',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_split(
        self, doc_name: SketchSplitDocumentName, sketch_name: SketchSplitSketchName, geo_index: int, point_x: float, point_y: float,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "geo_index": geo_index,
            "point_x": point_x,
            "point_y": point_y,
        }
        routed = self._invoke_mutation_v2(
            "sketch_split",
            params,
            document_names=(doc_name,),
            operation_name='Split sketch geometry',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_fillet(
        self, doc_name: SketchFilletDocumentName, sketch_name: SketchFilletSketchName, geo1: int, geo2: int, radius: float,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "geo1": geo1,
            "geo2": geo2,
            "radius": radius,
        }
        routed = self._invoke_mutation_v2(
            "sketch_fillet",
            params,
            document_names=(doc_name,),
            operation_name='Fillet sketch geometry',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }

    def sketch_symmetry(
        self, doc_name: SketchSymmetryDocumentName, sketch_name: SketchSymmetrySketchName, geo_indices: list[int], symmetry_geo: int, copy: bool = True,
    ) -> object:
        params: dict[str, object] = {
            "doc_name": doc_name,
            "sketch_name": sketch_name,
            "geo_indices": geo_indices,
            "symmetry_geo": symmetry_geo,
            "copy": copy,
        }
        routed = self._invoke_mutation_v2(
            "sketch_symmetry",
            params,
            document_names=(doc_name,),
            operation_name='Apply sketch symmetry',
        )
        if routed is not None:
            return routed
        return {
            "contract_version": 1,
            "success": False,
            "ok": False,
            "outcome": "uncertain",
            "committed": None,
            "retry_safe": False,
            "error_code": "INVALID_RPC_RESPONSE",
            "error": "typed RPC v2 context is unavailable",
        }
