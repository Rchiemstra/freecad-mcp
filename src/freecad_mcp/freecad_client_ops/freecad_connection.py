"""JSON-RPC client connection to a FreeCAD add-on instance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .typed_feature_rpc import attach_p3_feature_rpc
from .._shared.protocol.create_assembly_contract import AssemblyName as CreateAssemblyName
from .._shared.protocol.create_assembly_contract import DocumentName as CreateAssemblyDocumentName
from .._shared.protocol.create_assembly_grounded_joint_contract import ComponentName
from .._shared.protocol.create_assembly_grounded_joint_contract import (
    AssemblyName as str,
)
from .._shared.protocol.create_assembly_grounded_joint_contract import (
    str as str,
)
from .._shared.protocol.create_assembly_joint_contract import AssemblyName as JointAssemblyName
from .._shared.protocol.create_assembly_joint_contract import DocumentName as JointDocumentName
from .._shared.protocol.solve_assembly_contract import AssemblyName as SolveAssemblyName
from .._shared.protocol.solve_assembly_contract import DocumentName as SolveDocumentName
from .._shared.protocol.create_helical_gear_contract import DocumentName as HelicalDocumentName
from .._shared.protocol.create_helical_gear_contract import GearName as HelicalGearName
from .._shared.protocol.create_involute_gear_contract import DocumentName as InvoluteDocumentName
from .._shared.protocol.create_involute_gear_contract import GearName as InvoluteGearName
from .._shared.protocol.create_spur_gear_contract import DocumentName as SpurDocumentName
from .._shared.protocol.create_spur_gear_contract import GearName as SpurGearName
from .._shared.protocol.export_brep_contract import DocumentName as ExportBrepDocumentName
from .._shared.protocol.export_brep_contract import ObjectName as ExportBrepObjectName
from .._shared.protocol.export_step_contract import DocumentName as ExportStepDocumentName
from .._shared.protocol.export_stl_contract import DocumentName as ExportStlDocumentName
from .._shared.protocol.import_brep_contract import DocumentName as ImportBrepDocumentName
from .._shared.protocol.import_brep_contract import ObjectName as ImportBrepObjectName
from .._shared.protocol.import_step_contract import DocumentName as ImportStepDocumentName
from .._shared.protocol.bounding_box_contract import DocumentName as BoundingBoxDocumentName
from .._shared.protocol.bounding_box_contract import ObjectName as BoundingBoxObjectName
from .._shared.protocol.center_of_mass_contract import DocumentName as CenterOfMassDocumentName
from .._shared.protocol.center_of_mass_contract import ObjectName as CenterOfMassObjectName
from .._shared.protocol.common_volume_along_path_contract import (
    str as str,
)
from .._shared.protocol.rotate_contract import DocumentName as RotateDocumentName
from .._shared.protocol.rotate_contract import ObjectName as RotateObjectName
from .._shared.protocol.scale_contract import DocumentName as ScaleDocumentName
from .._shared.protocol.scale_contract import ObjectName as ScaleObjectName
from .._shared.protocol.translate_contract import DocumentName as TranslateDocumentName
from .._shared.protocol.translate_contract import ObjectName as TranslateObjectName

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
        str as str,
    )
    from .._shared.protocol.sketch_add_constraint_contract import SketchName as AddConstraintSketchName
    from .._shared.protocol.sketch_add_geometry_contract import (
        str as str,
    )
    from .._shared.protocol.sketch_add_geometry_contract import SketchName as AddGeometrySketchName
    from .._shared.protocol.sketch_attach_contract import DocumentName as AttachDocumentName
    from .._shared.protocol.sketch_attach_contract import SketchName as AttachSketchName
    from .._shared.protocol.sketch_create_contract import DocumentName as SketchCreateDocumentName
    from .._shared.protocol.sketch_create_contract import SketchName as SketchCreateName
    from .._shared.protocol.sketch_delete_constraint_contract import (
        str as str,
    )
    from .._shared.protocol.sketch_delete_constraint_contract import (
        str as str,
    )
    from .._shared.protocol.sketch_delete_geometry_contract import (
        str as str,
    )
    from .._shared.protocol.sketch_delete_geometry_contract import (
        str as str,
    )
    from .._shared.protocol.sketch_edit_constraint_contract import (
        str as str,
    )
    from .._shared.protocol.sketch_edit_constraint_contract import SketchName as EditConstraintSketchName

    from collections.abc import Mapping, Sequence

    from .._shared.protocol.activate_document_contract import (
        str as str,
    )
    from .._shared.protocol.body_create_contract import BodyName
    from .._shared.protocol.body_create_contract import DocumentName as BodyDocumentName
    from .._shared.protocol.close_document_contract import DocumentName as CloseDocumentName
    from .._shared.protocol.create_document_contract import (
        str as str,
    )
    from .._shared.protocol.create_object_contract import CreateObjectPayload
    from .._shared.protocol.create_object_contract import (
        str as str,
    )
    from .._shared.protocol.delete_object_contract import (
        str as str,
    )
    from .._shared.protocol.delete_object_contract import ObjectName as DeleteObjectName
    from .._shared.protocol.edit_object_contract import DocumentName as EditObjectDocumentName
    from .._shared.protocol.edit_object_contract import EditObjectPayload
    from .._shared.protocol.edit_object_contract import ObjectName as EditObjectName
    from .._shared.protocol.insert_part_from_library_contract import (
        str as str,
    )
    from .._shared.protocol.open_document_contract import PathName as OpenDocumentPath
    from .._shared.protocol.recompute_and_wait_contract import (
        str as str,
    )
    from .._shared.protocol.recompute_document_contract import (
        str as str,
    )
    from .._shared.protocol.redo_contract import DocumentName as RedoDocumentName
    from .._shared.protocol.reload_document_contract import (
        str as str,
    )
    from .._shared.protocol.repair_references_contract import (
        str as str,
    )
    from .._shared.protocol.repair_references_contract import RepairItemPayload
    from .._shared.protocol.undo_contract import DocumentName as UndoDocumentName

    from .._shared.protocol.body_create_contract import BodyName, DocumentName
    from .._shared.protocol.boolean_difference_contract import (
        str as str,
    )
    from .._shared.protocol.boolean_difference_contract import (
        str as str,
    )
    from .._shared.protocol.boolean_intersection_contract import (
        str as str,
    )
    from .._shared.protocol.boolean_intersection_contract import (
        str as str,
    )
    from .._shared.protocol.boolean_union_contract import (
        str as str,
    )
    from .._shared.protocol.boolean_union_contract import (
        str as str,
    )
    from .._shared.protocol.chamfer_feature_contract import (
        str as str,
    )
    from .._shared.protocol.chamfer_feature_contract import (
        str as str,
    )
    from .._shared.protocol.fillet_feature_contract import (
        str as str,
    )
    from .._shared.protocol.fillet_feature_contract import (
        str as str,
    )
    from .._shared.protocol.helical_sweep_feature_contract import (
        str as str,
    )
    from .._shared.protocol.helical_sweep_feature_contract import (
        str as str,
    )
    from .._shared.protocol.linear_pattern_feature_contract import (
        str as str,
    )
    from .._shared.protocol.linear_pattern_feature_contract import (
        str as str,
    )
    from .._shared.protocol.loft_feature_contract import (
        str as str,
    )
    from .._shared.protocol.loft_feature_contract import (
        str as str,
    )
    from .._shared.protocol.mirror_feature_contract import (
        str as str,
    )
    from .._shared.protocol.mirror_feature_contract import (
        str as str,
    )
    from .._shared.protocol.polar_pattern_feature_contract import (
        str as str,
    )
    from .._shared.protocol.polar_pattern_feature_contract import (
        str as str,
    )
    from .._shared.protocol.revolve_feature_contract import (
        str as str,
    )
    from .._shared.protocol.revolve_feature_contract import (
        str as str,
    )
    from .._shared.protocol.sweep_feature_contract import (
        str as str,
    )
    from .._shared.protocol.sweep_feature_contract import (
        str as str,
    )

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

    def close_document(self, doc_name: str) -> object:
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

        def get_active_screenshot(self) -> str | None: ...

        def invoke_rpc(self, *args: object, **kwargs: object) -> object: ...

        def body_create(
            self, doc_name: str, body_name: str
        ) -> object: ...

        def create_document(self, name: str) -> object: ...

        def create_object(
            self,
            doc_name: str,
            obj_data: CreateObjectPayload,
        ) -> object: ...

        def delete_object(
            self,
            doc_name: str,
            obj_name: str,
            recursive: bool = False,
            force: bool = False,
        ) -> object: ...

        def edit_object(
            self,
            doc_name: str,
            obj_name: str,
            properties: EditObjectPayload | Mapping[str, object],
        ) -> object: ...

        def repair_references(
            self,
            doc_name: str,
            repairs: Sequence[Mapping[str, object]],
            recompute: bool = False,
            validate: bool = False,
        ) -> object: ...

        def activate_document(self, doc_name: str) -> object: ...

        def insert_part_from_library(
            self, doc_name: str, relative_path: str
        ) -> object: ...

        def open_document(self, path: str) -> object: ...

        def recompute_and_wait(
            self, doc_name: str
        ) -> object: ...

        def recompute_document(self, doc_name: str) -> object: ...

        def redo(self, doc_name: str) -> object: ...

        def reload_document(self, doc_name: str) -> object: ...

        def undo(self, doc_name: str) -> object: ...

    def create_assembly(self, doc_name: str, assembly_name: str = "Assembly", create_joint_group: object = True, recompute: object = False, if_exists: object = "error") -> object:
        params = {
            "doc_name": doc_name,
            "assembly_name": assembly_name,
            "create_joint_group": create_joint_group,
            "recompute": recompute,
            "if_exists": if_exists,
        }
        invoke = getattr(self, "_invoke_mutation_v2")
        routed = invoke(
            "create_assembly",
            params,
            document_names=(str(doc_name),) if isinstance(doc_name, str) else (),
            operation_name="Create Assembly",
        )
        if routed is not None:
            return routed
        server = getattr(self, "server")
        return getattr(server, "create_assembly")(*[params[name] for name in params])

    def create_assembly_grounded_joint(self, doc_name: str, assembly_name: str, component_name: str, label: object = None, recompute: object = True) -> object:
        params = {
            "doc_name": doc_name,
            "assembly_name": assembly_name,
            "component_name": component_name,
            "label": label,
            "recompute": recompute,
        }
        invoke = getattr(self, "_invoke_mutation_v2")
        routed = invoke(
            "create_assembly_grounded_joint",
            params,
            document_names=(str(doc_name),) if isinstance(doc_name, str) else (),
            operation_name="Create Grounded Joint",
        )
        if routed is not None:
            return routed
        server = getattr(self, "server")
        return getattr(server, "create_assembly_grounded_joint")(*[params[name] for name in params])

    def create_assembly_joint(self, doc_name: str, assembly_name: str, joint_type: object, ref1_component: object, ref2_component: object, ref1_element: object = "", ref2_element: object = "", ref1_vertex: object = None, ref2_vertex: object = None, label: object = None, solve: object = True, presolve: object = True, recompute: object = True, properties: object = None) -> object:
        params = {
            "doc_name": doc_name,
            "assembly_name": assembly_name,
            "joint_type": joint_type,
            "ref1_component": ref1_component,
            "ref2_component": ref2_component,
            "ref1_element": ref1_element,
            "ref2_element": ref2_element,
            "ref1_vertex": ref1_vertex,
            "ref2_vertex": ref2_vertex,
            "label": label,
            "solve": solve,
            "presolve": presolve,
            "recompute": recompute,
            "properties": properties,
        }
        invoke = getattr(self, "_invoke_mutation_v2")
        routed = invoke(
            "create_assembly_joint",
            params,
            document_names=(str(doc_name),) if isinstance(doc_name, str) else (),
            operation_name="Create Assembly Joint",
        )
        if routed is not None:
            return routed
        server = getattr(self, "server")
        return getattr(server, "create_assembly_joint")(*[params[name] for name in params])

    def solve_assembly(self, doc_name: str, assembly_name: str) -> object:
        params = {
            "doc_name": doc_name,
            "assembly_name": assembly_name,
        }
        invoke = getattr(self, "_invoke_mutation_v2")
        routed = invoke(
            "solve_assembly",
            params,
            document_names=(str(doc_name),) if isinstance(doc_name, str) else (),
            operation_name="Solve Assembly",
        )
        if routed is not None:
            return routed
        server = getattr(self, "server")
        return getattr(server, "solve_assembly")(*[params[name] for name in params])

    def create_helical_gear(self, doc_name: str, gear_name: str, teeth: object, module: object, width: object, helix_angle: object = 15.0, pressure_angle: object = 20.0, bore_diameter: object = 0.0, clearance: object = 0.0, backlash: object = 0.0, samples_per_flank: object = 12, body_name: object = None) -> object:
        params = {
            "doc_name": doc_name,
            "gear_name": gear_name,
            "teeth": teeth,
            "module": module,
            "width": width,
            "helix_angle": helix_angle,
            "pressure_angle": pressure_angle,
            "bore_diameter": bore_diameter,
            "clearance": clearance,
            "backlash": backlash,
            "samples_per_flank": samples_per_flank,
            "body_name": body_name,
        }
        invoke = getattr(self, "_invoke_mutation_v2")
        routed = invoke(
            "create_helical_gear",
            params,
            document_names=(str(doc_name),) if isinstance(doc_name, str) else (),
            operation_name="Create Helical Gear",
        )
        if routed is not None:
            return routed
        server = getattr(self, "server")
        return getattr(server, "create_helical_gear")(*[params[name] for name in params])

    def create_involute_gear(self, doc_name: str, gear_name: str, teeth: object, module: object, width: object, pressure_angle: object = 20.0, bore_diameter: object = 0.0, clearance: object = 0.0, backlash: object = 0.0, samples_per_flank: object = 12, body_name: object = None, sketch_name: object = None) -> object:
        params = {
            "doc_name": doc_name,
            "gear_name": gear_name,
            "teeth": teeth,
            "module": module,
            "width": width,
            "pressure_angle": pressure_angle,
            "bore_diameter": bore_diameter,
            "clearance": clearance,
            "backlash": backlash,
            "samples_per_flank": samples_per_flank,
            "body_name": body_name,
            "sketch_name": sketch_name,
        }
        invoke = getattr(self, "_invoke_mutation_v2")
        routed = invoke(
            "create_involute_gear",
            params,
            document_names=(str(doc_name),) if isinstance(doc_name, str) else (),
            operation_name="Create Involute Gear",
        )
        if routed is not None:
            return routed
        server = getattr(self, "server")
        return getattr(server, "create_involute_gear")(*[params[name] for name in params])

    def create_spur_gear(self, doc_name: str, gear_name: str, teeth: object, module: object, width: object, pressure_angle: object = 20.0, bore_diameter: object = 0.0, clearance: object = 0.0, backlash: object = 0.0, samples_per_flank: object = 8, body_name: object = None, sketch_name: object = None, tooth_profile: object = "involute") -> object:
        params = {
            "doc_name": doc_name,
            "gear_name": gear_name,
            "teeth": teeth,
            "module": module,
            "width": width,
            "pressure_angle": pressure_angle,
            "bore_diameter": bore_diameter,
            "clearance": clearance,
            "backlash": backlash,
            "samples_per_flank": samples_per_flank,
            "body_name": body_name,
            "sketch_name": sketch_name,
            "tooth_profile": tooth_profile,
        }
        invoke = getattr(self, "_invoke_mutation_v2")
        routed = invoke(
            "create_spur_gear",
            params,
            document_names=(str(doc_name),) if isinstance(doc_name, str) else (),
            operation_name="Create Spur Gear",
        )
        if routed is not None:
            return routed
        server = getattr(self, "server")
        return getattr(server, "create_spur_gear")(*[params[name] for name in params])

    def export_brep(self, doc_name: str, obj_name: str, file_path: object) -> object:
        params = {
            "doc_name": doc_name,
            "obj_name": obj_name,
            "file_path": file_path,
        }
        invoke = getattr(self, "_invoke_mutation_v2")
        routed = invoke(
            "export_brep",
            params,
            document_names=(str(doc_name),) if isinstance(doc_name, str) else (),
            operation_name="Export BREP",
        )
        if routed is not None:
            return routed
        server = getattr(self, "server")
        return getattr(server, "export_brep")(*[params[name] for name in params])

    def export_step(self, doc_name: str, file_path: object, obj_names: object = None) -> object:
        params = {
            "doc_name": doc_name,
            "file_path": file_path,
            "obj_names": obj_names,
        }
        invoke = getattr(self, "_invoke_mutation_v2")
        routed = invoke(
            "export_step",
            params,
            document_names=(str(doc_name),) if isinstance(doc_name, str) else (),
            operation_name="Export STEP",
        )
        if routed is not None:
            return routed
        server = getattr(self, "server")
        return getattr(server, "export_step")(*[params[name] for name in params])

    def export_stl(self, doc_name: str, file_path: object, obj_names: object = None, mesh_deviation: object = 0.1) -> object:
        params = {
            "doc_name": doc_name,
            "file_path": file_path,
            "obj_names": obj_names,
            "mesh_deviation": mesh_deviation,
        }
        invoke = getattr(self, "_invoke_mutation_v2")
        routed = invoke(
            "export_stl",
            params,
            document_names=(str(doc_name),) if isinstance(doc_name, str) else (),
            operation_name="Export STL",
        )
        if routed is not None:
            return routed
        server = getattr(self, "server")
        return getattr(server, "export_stl")(*[params[name] for name in params])

    def import_brep(self, doc_name: str, file_path: object, obj_name: str = "BRepImport") -> object:
        params = {
            "doc_name": doc_name,
            "file_path": file_path,
            "obj_name": obj_name,
        }
        invoke = getattr(self, "_invoke_mutation_v2")
        routed = invoke(
            "import_brep",
            params,
            document_names=(str(doc_name),) if isinstance(doc_name, str) else (),
            operation_name="Import BREP",
        )
        if routed is not None:
            return routed
        server = getattr(self, "server")
        return getattr(server, "import_brep")(*[params[name] for name in params])

    def import_step(self, doc_name: str, file_path: object) -> object:
        params = {
            "doc_name": doc_name,
            "file_path": file_path,
        }
        invoke = getattr(self, "_invoke_mutation_v2")
        routed = invoke(
            "import_step",
            params,
            document_names=(str(doc_name),) if isinstance(doc_name, str) else (),
            operation_name="Import STEP",
        )
        if routed is not None:
            return routed
        server = getattr(self, "server")
        return getattr(server, "import_step")(*[params[name] for name in params])

    def bounding_box(self, doc_name: str, obj_name: str) -> object:
        params = {
            "doc_name": doc_name,
            "obj_name": obj_name,
        }
        invoke = getattr(self, "_invoke_mutation_v2")
        routed = invoke(
            "bounding_box",
            params,
            document_names=(str(doc_name),) if isinstance(doc_name, str) else (),
            operation_name="Bounding Box",
        )
        if routed is not None:
            return routed
        server = getattr(self, "server")
        return getattr(server, "bounding_box")(*[params[name] for name in params])

    def center_of_mass(self, doc_name: str, obj_name: str) -> object:
        params = {
            "doc_name": doc_name,
            "obj_name": obj_name,
        }
        invoke = getattr(self, "_invoke_mutation_v2")
        routed = invoke(
            "center_of_mass",
            params,
            document_names=(str(doc_name),) if isinstance(doc_name, str) else (),
            operation_name="Center of Mass",
        )
        if routed is not None:
            return routed
        server = getattr(self, "server")
        return getattr(server, "center_of_mass")(*[params[name] for name in params])

    def common_volume_along_path(self, doc_name: str, moving_object: object, obstacle_objects: object, path_object: object = None, sample_count: object = 12, samples: object = None, volume_threshold_mm3: object = 1e-6, stop_on_first_hit: object = False) -> object:
        params = {
            "doc_name": doc_name,
            "moving_object": moving_object,
            "obstacle_objects": obstacle_objects,
            "path_object": path_object,
            "sample_count": sample_count,
            "samples": samples,
            "volume_threshold_mm3": volume_threshold_mm3,
            "stop_on_first_hit": stop_on_first_hit,
        }
        invoke = getattr(self, "_invoke_mutation_v2")
        routed = invoke(
            "common_volume_along_path",
            params,
            document_names=(str(doc_name),) if isinstance(doc_name, str) else (),
            operation_name="Common Volume Along Path",
        )
        if routed is not None:
            return routed
        server = getattr(self, "server")
        return getattr(server, "common_volume_along_path")(*[params[name] for name in params])

    def rotate(self, doc_name: str, obj_name: str, axis_x: object, axis_y: object, axis_z: object, angle_deg: object, center_x: object = 0.0, center_y: object = 0.0, center_z: object = 0.0) -> object:
        params = {
            "doc_name": doc_name,
            "obj_name": obj_name,
            "axis_x": axis_x,
            "axis_y": axis_y,
            "axis_z": axis_z,
            "angle_deg": angle_deg,
            "center_x": center_x,
            "center_y": center_y,
            "center_z": center_z,
        }
        invoke = getattr(self, "_invoke_mutation_v2")
        routed = invoke(
            "rotate",
            params,
            document_names=(str(doc_name),) if isinstance(doc_name, str) else (),
            operation_name="Rotate",
        )
        if routed is not None:
            return routed
        server = getattr(self, "server")
        return getattr(server, "rotate")(*[params[name] for name in params])

    def scale(self, doc_name: str, obj_name: str, sx: object, sy: object, sz: object) -> object:
        params = {
            "doc_name": doc_name,
            "obj_name": obj_name,
            "sx": sx,
            "sy": sy,
            "sz": sz,
        }
        invoke = getattr(self, "_invoke_mutation_v2")
        routed = invoke(
            "scale",
            params,
            document_names=(str(doc_name),) if isinstance(doc_name, str) else (),
            operation_name="Scale",
        )
        if routed is not None:
            return routed
        server = getattr(self, "server")
        return getattr(server, "scale")(*[params[name] for name in params])

    def translate(self, doc_name: str, obj_name: str, dx: object, dy: object, dz: object) -> object:
        params = {
            "doc_name": doc_name,
            "obj_name": obj_name,
            "dx": dx,
            "dy": dy,
            "dz": dz,
        }
        invoke = getattr(self, "_invoke_mutation_v2")
        routed = invoke(
            "translate",
            params,
            document_names=(str(doc_name),) if isinstance(doc_name, str) else (),
            operation_name="Translate",
        )
        if routed is not None:
            return routed
        server = getattr(self, "server")
        return getattr(server, "translate")(*[params[name] for name in params])

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

    if TYPE_CHECKING:

        def _invoke_mutation_v2(self, *args: object, **kwargs: object) -> object: ...

        def activate_document(self, doc_name: str) -> object: ...

        def body_create(
            self, doc_name: str, body_name: str
        ) -> object: ...

        def body_set_tip(
            self,
            doc_name: str,
            body_name: str,
            feature_name: str,
        ) -> object: ...

        def boolean_difference(
            self,
            doc_name: str,
            shape1: str,
            shape2: str,
            result_name: str,
        ) -> object: ...

        def boolean_intersection(
            self,
            doc_name: str,
            shape1: str,
            shape2: str,
            result_name: str,
        ) -> object: ...

        def boolean_union(
            self,
            doc_name: str,
            shape1: str,
            shape2: str,
            result_name: str,
        ) -> object: ...

        def build_path_wire(self, doc_name: str, wire_name: str, segments: object, tolerance_mm: float = 0.5, container: str | None = None, if_exists: str = "error") -> object: ...

        def capture_state(self, doc_name: str, object_names: object = None) -> object: ...

        def chamfer_feature(
            self,
            doc_name: str,
            base_feature: str,
            chamfer_name: str,
            size: float,
            edge_refs: list[str] | None = None,
            body_name: str | None = None,
        ) -> object: ...

        def clear_expression(self, doc_name: str, object_name: str, prop_path: str) -> object: ...

        def create_datum_plane(self, doc_name: str, plane_name: str, body_name: str, mode: str, source_ref: str | None = None, face_a: str | None = None, face_b: str | None = None, offset_along_normal: object = None, map_mode: str = "FlatFace", if_exists: str = "error") -> object: ...

        def create_document(self, name: str) -> object: ...

        def create_object(
            self,
            doc_name: str,
            obj_data: CreateObjectPayload,
        ) -> object: ...

        def create_part_container(self, doc_name: str, part_name: str, parent_container: str | None = None, if_exists: str = "error") -> object: ...

        def create_placement_binder(self, doc_name: str, owner_body: str, name: str, source: str, relative: bool = True, bind_mode: str = "Synchronized") -> object: ...

        def create_placement_datum(self, doc_name: str, owner_body: str, name: str, source: str, relative: bool = True, offset: object = None) -> object: ...

        def create_subshape_binder(self, doc_name: str, binder_name: str, source_object: str, sub_elements: object = None, target_body: str | None = None, target_container: str | None = None, relative: bool = False, sync_placement: bool = True, if_exists: str = "error") -> object: ...

        def delete_object(
            self,
            doc_name: str,
            obj_name: str,
            recursive: bool = False,
            force: bool = False,
        ) -> object: ...

        def edit_object(
            self,
            doc_name: str,
            obj_name: str,
            properties: EditObjectPayload | Mapping[str, object],
        ) -> object: ...

        def fillet_feature(
            self,
            doc_name: str,
            base_feature: str,
            fillet_name: str,
            radius: float,
            edge_refs: list[str] | None = None,
            body_name: str | None = None,
        ) -> object: ...

        def helical_sweep_feature(
            self,
            doc_name: str,
            profile_sketch: str,
            helix_name: str,
            pitch: float,
            height: float,
            radius: float,
            body_name: str | None = None,
            left_handed: bool = False,
            reversed_dir: bool = False,
        ) -> object: ...

        def insert_part_from_library(
            self, doc_name: str, relative_path: str
        ) -> object: ...

        def invoke_rpc(self, *args: object, **kwargs: object) -> object: ...

        def linear_pattern_feature(
            self,
            doc_name: str,
            feature_name: str,
            pattern_name: str,
            length: float,
            occurrences: int,
            direction: str = "X_Axis",
            body_name: str | None = None,
            reversed_dir: bool = False,
        ) -> object: ...

        def loft_feature(
            self,
            doc_name: str,
            sketch_names: list[str],
            loft_name: str,
            body_name: str | None = None,
            ruled: bool = False,
            closed: bool = False,
        ) -> object: ...

        def mirror_feature(
            self,
            doc_name: str,
            feature_name: str,
            mirror_name: str,
            plane: str = "YZ_Plane",
            body_name: str | None = None,
        ) -> object: ...

        def move_object(self, doc_name: str, obj_name: str, target_container: str, remove_from_old_parent: bool = True) -> object: ...

        def open_document(self, path: str) -> object: ...

        def pad_feature(
            self,
            doc_name: str,
            sketch_name: str,
            pad_name: str,
            length: float,
            body_name: str | None = None,
            symmetric: bool = False,
            reversed_dir: bool = False,
        ) -> object: ...

        def pocket_feature(
            self,
            doc_name: str,
            sketch_name: str,
            pocket_name: str,
            length: float,
            body_name: str | None = None,
            symmetric: bool = False,
            reversed_dir: bool = False,
        ) -> object: ...

        def polar_pattern_feature(
            self,
            doc_name: str,
            feature_name: str,
            pattern_name: str,
            occurrences: int,
            angle: float = 360.0,
            axis: str = "Z_Axis",
            body_name: str | None = None,
            reversed_dir: bool = False,
        ) -> object: ...

        def preview_attachment(self, doc_name: str, datum_name: str) -> object: ...

        def recompute_and_wait(
            self, doc_name: str
        ) -> object: ...

        def recompute_document(self, doc_name: str) -> object: ...

        def redo(self, doc_name: str) -> object: ...

        def relink_references(self, doc_name: str, from_obj: str, to_obj: str) -> object: ...

        def reload_document(self, doc_name: str) -> object: ...

        def repair_references(
            self,
            doc_name: str,
            repairs: Sequence[Mapping[str, object]],
            recompute: bool = False,
            validate: bool = False,
        ) -> object: ...

        def restore(self, doc_name: str, snapshot_id: str | None = None) -> object: ...

        def revolve_feature(
            self,
            doc_name: str,
            sketch_name: str,
            revolve_name: str,
            angle: float = 360.0,
            axis: str = "Z_Axis",
            body_name: str | None = None,
            symmetric: bool = False,
            reversed_dir: bool = False,
        ) -> object: ...

        def run_fem_analysis(self, doc_name: str, analysis_name: str, timeout: int = 600) -> object: ...

        def set_expression(self, doc_name: str, object_name: str, prop_path: str, expression: str) -> object: ...

        def sketch_add_constraint(
            self,
            doc_name: str,
            sketch_name: str,
            constraints: Sequence[object],
        ) -> object: ...

        def sketch_add_external_projection(self, doc_name: str, sketch_name: str, source_ref: str, projection_mode: str = "auto", defining: bool = False, allow_gui_geometry_loop: bool = False) -> object: ...

        def sketch_add_geometry(
            self,
            doc_name: str,
            sketch_name: str,
            geometry: Sequence[object],
        ) -> object: ...

        def sketch_attach(
            self,
            doc_name: str,
            sketch_name: str,
            support: object,
            attachment_offset: Mapping[str, object] | None = None,
        ) -> object: ...

        def sketch_create(
            self,
            doc_name: str,
            sketch_name: str,
            body_name: str | None = None,
            attach_to: str | None = None,
        ) -> object: ...

        def sketch_delete_constraint(
            self,
            doc_name: str,
            sketch_name: str,
            constraint_indices: Sequence[int] | None = None,
            constraint_names: Sequence[str] | None = None,
        ) -> object: ...

        def sketch_delete_geometry(
            self,
            doc_name: str,
            sketch_name: str,
            geometry_indices: Sequence[int],
        ) -> object: ...

        def sketch_edit_constraint(
            self,
            doc_name: str,
            sketch_name: str,
            value: float | None = None,
            name: str | None = None,
            index: int | None = None,
        ) -> object: ...

        def snapshot(self, doc_name: str) -> object: ...

        def spreadsheet_create(self, doc_name: str, sheet_name: str) -> object: ...

        def spreadsheet_get_cells(self, doc_name: str, sheet_name: str, addresses: object) -> object: ...

        def spreadsheet_list_aliases(self, doc_name: str, sheet_name: str) -> object: ...

        def spreadsheet_set_alias(self, doc_name: str, sheet_name: str, address: str, alias: str) -> object: ...

        def spreadsheet_set_cells(self, doc_name: str, sheet_name: str, cells: object) -> object: ...

        def sweep_feature(
            self,
            doc_name: str,
            profile_sketch: str,
            path_sketch: str,
            sweep_name: str,
            body_name: str | None = None,
            frenet: bool = False,
        ) -> object: ...

        def sweep_pipe(self, doc_name: str, path_wire: str, diameter_mm: float, solid_name: str, profile_mode: str = "frenet", color: object = None, container: str | None = None, if_exists: str = "error") -> object: ...

        def undo(self, doc_name: str) -> object: ...

        def validate_movement_follow(self, doc_name: str, source: str, dependents: object, translation: object, axis: object, angle_deg: float, restore: bool = True, tolerance: float = 1e-07) -> object: ...


attach_p3_feature_rpc(FreeCADConnection)
