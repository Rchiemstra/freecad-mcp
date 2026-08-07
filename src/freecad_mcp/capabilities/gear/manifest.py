"""Capability manifest for gear (bootstrapped)."""

# ruff: noqa: E501
from __future__ import annotations

from ..schema import ExecutionMode, MutationClass, SubjectManifest, ToolEntry

MANIFEST = SubjectManifest(
    subject="gear",
    register_modules=('tools_gear_1', 'tools_gear_2'),
    tools=(
        ToolEntry(
            name="create_helical_gear",
            docstring='Create a helical gear (involute profile + AdditiveHelix twist).\n\nArgs:\n    doc_name: Document to create the gear in.\n    gear_name: Name for the feature.\n    teeth: Number of teeth.\n    module: Gear module in mm (normal module).\n    width: Face width in mm.\n    helix_angle: Helix angle in degrees (default 15).\n    pressure_angle: Normal pressure angle in degrees (default 20).\n    bore_diameter: Optional centre bore diameter in mm.\n    clearance: Extra root clearance in mm.\n    backlash: Tooth backlash in mm.\n    samples_per_flank: Points per involute flank.\n    body_name: Optional existing PartDesign Body.\n\nReturns:\n    Success message with gear metadata and an isometric screenshot.',
            signature="(ctx: 'Context', doc_name: 'str', gear_name: 'str', teeth: 'int', module: 'float', width: 'float', helix_angle: 'float' = 15.0, pressure_angle: 'float' = 20.0, bore_diameter: 'float' = 0.0, clearance: 'float' = 0.0, backlash: 'float' = 0.0, samples_per_flank: 'int' = 12, body_name: 'str | None' = None) -> 'CallToolResult'",
            operation_path="freecad_mcp.operations.create_helical_gear_operation",
            rpc_method="create_helical_gear",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.MUTATION,
            register_module="tools_gear_1",
        ),
        ToolEntry(
            name="create_involute_gear",
            docstring='Create an involute spur gear using the correct mathematical involute profile.\n\nThe tooth flanks follow the true involute of the base circle:\n    x(t) = r_b*(cos(t) + t*sin(t))\n    y(t) = r_b*(sin(t) - t*cos(t))\n\nThis produces correct meshing geometry (replaces the deprecated\n``create_spur_gear`` which used a smoothstep approximation).\n\nArgs:\n    doc_name: Document to create the gear in.\n    gear_name: Name for the Pad feature.\n    teeth: Number of teeth (minimum 3).\n    module: Gear module in mm. Pitch diameter = module x teeth.\n    width: Face width (pad length) in mm.\n    pressure_angle: Pressure angle in degrees (default 20).\n    bore_diameter: Optional centre bore diameter in mm.\n    clearance: Extra root clearance in mm (added to standard 1.25m dedendum).\n    backlash: Tooth backlash in mm at the pitch circle.\n    samples_per_flank: Points per involute flank (higher = smoother, slower).\n    body_name: Optional existing PartDesign Body.\n    sketch_name: Optional sketch name (default: ``<gear_name>_Sketch``).\n\nReturns:\n    Success message with gear metadata and an isometric screenshot.\n\nExamples:\n    24-tooth module-2 gear with 6 mm bore:\n    ```json\n    {"doc_name":"GearDoc","gear_name":"Gear24","teeth":24,"module":2,"width":10,"bore_diameter":6}\n    ```',
            signature="(ctx: 'Context', doc_name: 'str', gear_name: 'str', teeth: 'int', module: 'float', width: 'float', pressure_angle: 'float' = 20.0, bore_diameter: 'float' = 0.0, clearance: 'float' = 0.0, backlash: 'float' = 0.0, samples_per_flank: 'int' = 12, body_name: 'str | None' = None, sketch_name: 'str | None' = None) -> 'CallToolResult'",
            operation_path="freecad_mcp.operations.create_involute_gear_operation",
            rpc_method="create_involute_gear",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.MUTATION,
            register_module="tools_gear_1",
        ),
        ToolEntry(
            name="create_spur_gear",
            docstring='Create a spur gear from a Sketcher tooth profile and Pad.\n\nThis tool generates the selected tooth profile in a Sketcher sketch, adds\npractical coincident and construction-circle constraints, then creates the\n3-D solid with a PartDesign Pad. It does not require the external Gear\nworkbench.\n\nArgs:\n    doc_name: The document to create the gear in.\n    gear_name: Name for the resulting Pad feature.\n    teeth: Number of teeth. Must be at least 3.\n    module: Gear module in mm.\n    width: Pad length in mm.\n    pressure_angle: Involute pressure angle in degrees. Defaults to 20.\n    bore_diameter: Optional center bore diameter in mm.\n    clearance: Extra root clearance in mm.\n    backlash: Tooth backlash in mm, applied at the pitch circle.\n    samples_per_flank: Approximation samples per tooth flank/profile side.\n    body_name: Optional existing PartDesign Body. If omitted, a new body is created.\n    sketch_name: Optional sketch name. Defaults to `<gear_name>_Sketch`.\n    tooth_profile: Tooth profile type. Supported values:\n        `involute` for normal real gears, `cycloidal` for clock-like\n        profiles, `trapezoid` for angled flat-sided visual gears,\n        `straight` / `straight_teeth` for square radial-sided teeth,\n        `circular_arc` / `novikov` for continuous circular-arc teeth, and\n        `pin` / `lantern` for hub-and-pin style gears.\n\nReturns:\n    A message indicating success or failure and an isometric screenshot.\n\nExamples:\n    Create a 24-tooth, module 2 gear with a 6 mm bore:\n    ```json\n    {\n      "doc_name": "GearDoc",\n      "gear_name": "Gear24",\n      "teeth": 24,\n      "module": 2,\n      "width": 10,\n      "bore_diameter": 6\n    }\n    ```',
            signature="(ctx: 'Context', doc_name: 'str', gear_name: 'str', teeth: 'int', module: 'float', width: 'float', pressure_angle: 'float' = 20.0, bore_diameter: 'float' = 0.0, clearance: 'float' = 0.0, backlash: 'float' = 0.0, samples_per_flank: 'int' = 8, body_name: 'str | None' = None, sketch_name: 'str | None' = None, tooth_profile: 'str' = 'involute') -> 'CallToolResult'",
            operation_path="freecad_mcp.operations.create_spur_gear_operation",
            rpc_method="create_spur_gear",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.MUTATION,
            register_module="tools_gear_1",
        ),
        ToolEntry(
            name="check_gear_pair",
            docstring='Verify that two gears form a valid meshing pair.\n\nChecks module compatibility, computes gear ratio and theoretical centre\ndistance. Optionally validates a specified centre distance.\n\nArgs:\n    teeth1: Teeth count of the first gear (driver).\n    module1: Module of the first gear in mm.\n    teeth2: Teeth count of the second gear (driven).\n    module2: Module of the second gear in mm.\n    pressure_angle: Shared pressure angle in degrees.\n    center_distance: Optional measured centre distance to validate in mm.\n\nReturns:\n    JSON with ``meshes`` (bool), ``gear_ratio``, ``theoretical_cd_mm``, and notes.',
            signature="(ctx: 'Context', teeth1: 'int', module1: 'float', teeth2: 'int', module2: 'float', pressure_angle: 'float' = 20.0, center_distance: 'float | None' = None) -> 'CallToolResult'",
            operation_path="freecad_mcp.operations.check_gear_pair_operation",
            rpc_method="check_gear_pair",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.READ,
            register_module="tools_gear_2",
        ),
        ToolEntry(
            name="compute_gear_geometry",
            docstring='Compute standard gear geometry parameters without creating geometry.\n\nReturns pitch diameter, base diameter, addendum, dedendum, circular pitch,\nand base pitch for the specified gear.\n\nArgs:\n    teeth: Number of teeth.\n    module: Gear module in mm.\n    pressure_angle: Pressure angle in degrees (default 20).\n    clearance: Extra root clearance in mm.\n    backlash: Tooth backlash in mm.\n    helix_angle: Helix angle in degrees (0 = spur gear).\n\nReturns:\n    JSON with all standard gear parameters.',
            signature="(ctx: 'Context', teeth: 'int', module: 'float', pressure_angle: 'float' = 20.0, clearance: 'float' = 0.0, backlash: 'float' = 0.0, helix_angle: 'float' = 0.0) -> 'CallToolResult'",
            operation_path="freecad_mcp.operations.compute_gear_geometry_operation",
            rpc_method="compute_gear_geometry",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.READ,
            register_module="tools_gear_2",
        ),
    ),
)
