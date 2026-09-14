"""JSON-RPC client connection to a FreeCAD add-on instance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._shared.protocol.create_assembly_contract import AssemblyName as CreateAssemblyName
from .._shared.protocol.create_assembly_contract import DocumentName as CreateAssemblyDocumentName
from .._shared.protocol.create_assembly_grounded_joint_contract import ComponentName
from .._shared.protocol.create_assembly_grounded_joint_contract import (
    AssemblyName as GroundedAssemblyName,
)
from .._shared.protocol.create_assembly_grounded_joint_contract import (
    DocumentName as GroundedDocumentName,
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
    DocumentName as CommonVolumeDocumentName,
)
from .._shared.protocol.rotate_contract import DocumentName as RotateDocumentName
from .._shared.protocol.rotate_contract import ObjectName as RotateObjectName
from .._shared.protocol.scale_contract import DocumentName as ScaleDocumentName
from .._shared.protocol.scale_contract import ObjectName as ScaleObjectName
from .._shared.protocol.translate_contract import DocumentName as TranslateDocumentName
from .._shared.protocol.translate_contract import ObjectName as TranslateObjectName

if TYPE_CHECKING:
    from .._shared.protocol.body_create_contract import BodyName, DocumentName


class FreeCADConnection:
    """Authenticated JSON-RPC client for one FreeCAD add-on RPC endpoint."""

    if TYPE_CHECKING:

        def body_create(
            self, doc_name: DocumentName, body_name: BodyName
        ) -> object: ...

    def create_assembly(self, doc_name: CreateAssemblyDocumentName, assembly_name: CreateAssemblyName = CreateAssemblyName("Assembly"), create_joint_group: object = True, recompute: object = False, if_exists: object = "error") -> object:
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

    def create_assembly_grounded_joint(self, doc_name: GroundedDocumentName, assembly_name: GroundedAssemblyName, component_name: ComponentName, label: object = None, recompute: object = True) -> object:
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

    def create_assembly_joint(self, doc_name: JointDocumentName, assembly_name: JointAssemblyName, joint_type: object, ref1_component: object, ref2_component: object, ref1_element: object = "", ref2_element: object = "", ref1_vertex: object = None, ref2_vertex: object = None, label: object = None, solve: object = True, presolve: object = True, recompute: object = True, properties: object = None) -> object:
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

    def solve_assembly(self, doc_name: SolveDocumentName, assembly_name: SolveAssemblyName) -> object:
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

    def create_helical_gear(self, doc_name: HelicalDocumentName, gear_name: HelicalGearName, teeth: object, module: object, width: object, helix_angle: object = 15.0, pressure_angle: object = 20.0, bore_diameter: object = 0.0, clearance: object = 0.0, backlash: object = 0.0, samples_per_flank: object = 12, body_name: object = None) -> object:
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

    def create_involute_gear(self, doc_name: InvoluteDocumentName, gear_name: InvoluteGearName, teeth: object, module: object, width: object, pressure_angle: object = 20.0, bore_diameter: object = 0.0, clearance: object = 0.0, backlash: object = 0.0, samples_per_flank: object = 12, body_name: object = None, sketch_name: object = None) -> object:
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

    def create_spur_gear(self, doc_name: SpurDocumentName, gear_name: SpurGearName, teeth: object, module: object, width: object, pressure_angle: object = 20.0, bore_diameter: object = 0.0, clearance: object = 0.0, backlash: object = 0.0, samples_per_flank: object = 8, body_name: object = None, sketch_name: object = None, tooth_profile: object = "involute") -> object:
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

    def export_brep(self, doc_name: ExportBrepDocumentName, obj_name: ExportBrepObjectName, file_path: object) -> object:
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

    def export_step(self, doc_name: ExportStepDocumentName, file_path: object, obj_names: object = None) -> object:
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

    def export_stl(self, doc_name: ExportStlDocumentName, file_path: object, obj_names: object = None, mesh_deviation: object = 0.1) -> object:
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

    def import_brep(self, doc_name: ImportBrepDocumentName, file_path: object, obj_name: ImportBrepObjectName = ImportBrepObjectName("BRepImport")) -> object:
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

    def import_step(self, doc_name: ImportStepDocumentName, file_path: object) -> object:
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

    def bounding_box(self, doc_name: BoundingBoxDocumentName, obj_name: BoundingBoxObjectName) -> object:
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

    def center_of_mass(self, doc_name: CenterOfMassDocumentName, obj_name: CenterOfMassObjectName) -> object:
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

    def common_volume_along_path(self, doc_name: CommonVolumeDocumentName, moving_object: object, obstacle_objects: object, path_object: object = None, sample_count: object = 12, samples: object = None, volume_threshold_mm3: object = 1e-6, stop_on_first_hit: object = False) -> object:
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

    def rotate(self, doc_name: RotateDocumentName, obj_name: RotateObjectName, axis_x: object, axis_y: object, axis_z: object, angle_deg: object, center_x: object = 0.0, center_y: object = 0.0, center_z: object = 0.0) -> object:
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

    def scale(self, doc_name: ScaleDocumentName, obj_name: ScaleObjectName, sx: object, sy: object, sz: object) -> object:
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

    def translate(self, doc_name: TranslateDocumentName, obj_name: TranslateObjectName, dx: object, dy: object, dz: object) -> object:
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

