"""Integrator-owned registration order for Phase 7 / 7D."""

from . import tools_advanced_a as _tools_advanced_a
from . import tools_advanced_b as _tools_advanced_b
from . import tools_advanced_b2 as _tools_advanced_b2
from . import tools_assembly as _tools_assembly
from . import tools_core_document as _tools_core_document
from . import tools_core_execute as _tools_core_execute
from . import tools_core_objects as _tools_core_objects
from . import tools_diagnostics as _tools_diagnostics
from . import tools_document_history as _tools_document_history
from . import tools_features_advanced_a as _tools_features_advanced_a
from . import tools_features_advanced_b as _tools_features_advanced_b
from . import tools_features_basic_1 as _tools_features_basic_1
from . import tools_features_basic_2 as _tools_features_basic_2
from . import tools_features_boolean as _tools_features_boolean
from . import tools_gear_1 as _tools_gear_1
from . import tools_gear_2 as _tools_gear_2
from . import tools_gui_document_a as _tools_gui_document_a
from . import tools_gui_document_b as _tools_gui_document_b
from . import tools_gui_view_a as _tools_gui_view_a
from . import tools_gui_view_b as _tools_gui_view_b
from . import tools_io_export as _tools_io_export
from . import tools_io_import as _tools_io_import
from . import tools_lease_acquire_a as _tools_lease_acquire_a
from . import tools_lease_acquire_b as _tools_lease_acquire_b
from . import tools_lease_lifecycle as _tools_lease_lifecycle
from . import tools_measure_a as _tools_measure_a
from . import tools_measure_b as _tools_measure_b
from . import tools_parametric_body as _tools_parametric_body
from . import tools_parametric_sheet_a as _tools_parametric_sheet_a
from . import tools_parametric_sheet_b as _tools_parametric_sheet_b
from . import tools_partdesign_a as _tools_partdesign_a
from . import tools_partdesign_a2 as _tools_partdesign_a2
from . import tools_partdesign_b as _tools_partdesign_b
from . import tools_partdesign_b2 as _tools_partdesign_b2
from . import tools_runtime_control as _tools_runtime_control
from . import tools_runtime_info as _tools_runtime_info
from . import tools_sketch_constraints_1 as _tools_sketch_constraints_1
from . import tools_sketch_constraints_2 as _tools_sketch_constraints_2
from . import tools_sketch_create_1 as _tools_sketch_create_1
from . import tools_sketch_create_2 as _tools_sketch_create_2
from . import tools_sketch_curves_a as _tools_sketch_curves_a
from . import tools_sketch_curves_a2 as _tools_sketch_curves_a2
from . import tools_sketch_curves_b as _tools_sketch_curves_b
from . import tools_sketch_curves_b2 as _tools_sketch_curves_b2
from . import tools_sketch_primitives as _tools_sketch_primitives
from . import tools_transform as _tools_transform
from . import tools_worker as _tools_worker

REGISTER_TOOL_MODULE_OBJECTS = (
    _tools_runtime_info,
    _tools_runtime_control,
    _tools_lease_acquire_a,
    _tools_lease_acquire_b,
    _tools_lease_lifecycle,
    _tools_core_document,
    _tools_core_objects,
    _tools_core_execute,
    _tools_worker,
    _tools_gui_view_a,
    _tools_gui_view_b,
    _tools_gui_document_a,
    _tools_gui_document_b,
    _tools_diagnostics,
    _tools_sketch_create_1,
    _tools_sketch_create_2,
    _tools_sketch_primitives,
    _tools_sketch_constraints_1,
    _tools_sketch_constraints_2,
    _tools_features_basic_1,
    _tools_features_basic_2,
    _tools_document_history,
    _tools_parametric_sheet_a,
    _tools_parametric_sheet_b,
    _tools_parametric_body,
    _tools_sketch_curves_a,
    _tools_sketch_curves_a2,
    _tools_sketch_curves_b,
    _tools_sketch_curves_b2,
    _tools_features_advanced_a,
    _tools_features_advanced_b,
    _tools_features_boolean,
    _tools_gear_1,
    _tools_gear_2,
    _tools_measure_a,
    _tools_measure_b,
    _tools_transform,
    _tools_io_export,
    _tools_io_import,
    _tools_assembly,
    _tools_partdesign_a,
    _tools_partdesign_a2,
    _tools_partdesign_b,
    _tools_partdesign_b2,
    _tools_advanced_a,
    _tools_advanced_b,
    _tools_advanced_b2,
)

REGISTER_TOOL_MODULES = tuple(
    module.__name__.rsplit(".", maxsplit=1)[-1]
    for module in REGISTER_TOOL_MODULE_OBJECTS
)
