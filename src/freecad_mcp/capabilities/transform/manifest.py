"""Capability manifest for transform (bootstrapped)."""

# ruff: noqa: E501
from __future__ import annotations

from ..schema import ExecutionMode, MutationClass, SubjectManifest, ToolEntry

MANIFEST = SubjectManifest(
    subject="transform",
    register_modules=('tools_transform',),
    tools=(
        ToolEntry(
            name="rotate",
            docstring='Rotate an object around a specified axis.\n\nArgs:\n    doc_name: Document containing the object.\n    obj_name: Name of the object to rotate.\n    axis_x: X component of the rotation axis vector.\n    axis_y: Y component of the rotation axis vector.\n    axis_z: Z component of the rotation axis vector.\n    angle_deg: Rotation angle in degrees (positive = CCW by right-hand rule).\n    center_x: X coordinate of the rotation centre (default 0).\n    center_y: Y coordinate of the rotation centre (default 0).\n    center_z: Z coordinate of the rotation centre (default 0).\n\nReturns:\n    Success message and a screenshot.',
            signature="(ctx: 'Context', doc_name: 'str', obj_name: 'str', axis_x: 'float', axis_y: 'float', axis_z: 'float', angle_deg: 'float', center_x: 'float' = 0.0, center_y: 'float' = 0.0, center_z: 'float' = 0.0) -> 'CallToolResult'",
            operation_path="freecad_mcp.operations.rotate_operation",
            rpc_method="rotate",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.MUTATION,
            register_module="tools_transform",
        ),
        ToolEntry(
            name="scale",
            docstring='Scale an object non-uniformly along the three axes.\n\nNote: scaling a PartDesign solid converts it to a dumb Part::Feature.\nUse for Part workbench shapes or final geometry only.\n\nArgs:\n    doc_name: Document containing the object.\n    obj_name: Name of the object to scale.\n    sx: Scale factor along X.\n    sy: Scale factor along Y.\n    sz: Scale factor along Z.\n\nReturns:\n    Success message and a screenshot.',
            signature="(ctx: 'Context', doc_name: 'str', obj_name: 'str', sx: 'float', sy: 'float', sz: 'float') -> 'CallToolResult'",
            operation_path="freecad_mcp.operations.scale_operation",
            rpc_method="scale",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.MUTATION,
            register_module="tools_transform",
        ),
        ToolEntry(
            name="translate",
            docstring='Translate (move) an object by a displacement vector.\n\nArgs:\n    doc_name: Document containing the object.\n    obj_name: Name of the object to translate.\n    dx: X displacement in mm.\n    dy: Y displacement in mm.\n    dz: Z displacement in mm.\n\nReturns:\n    Success message and a screenshot.',
            signature="(ctx: 'Context', doc_name: 'str', obj_name: 'str', dx: 'float', dy: 'float', dz: 'float') -> 'CallToolResult'",
            operation_path="freecad_mcp.operations.translate_operation",
            rpc_method="translate",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.MUTATION,
            register_module="tools_transform",
        ),
    ),
)
