"""Capability manifest for assembly (bootstrapped)."""

from __future__ import annotations

from ..schema import ExecutionMode, MutationClass, SubjectManifest, ToolEntry

MANIFEST = SubjectManifest(
    subject="assembly",
    register_modules=('tools_assembly',),
    tools=(
        ToolEntry(
            name="create_assembly",
            docstring='Create a built-in Assembly workbench assembly object.',
            signature='(ctx: \'Context\', doc_name: \'str\', assembly_name: \'str\' = \'Assembly\', create_joint_group: \'bool\' = True, recompute: \'bool\' = False, if_exists: "Literal[\'error\', \'skip\', \'replace\']" = \'error\') -> \'CallToolResult\'',
            operation_path="freecad_mcp.operations.create_assembly_operation",
            rpc_method="create_assembly",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.MUTATION,
            register_module="tools_assembly",
        ),
        ToolEntry(
            name="create_assembly_grounded_joint",
            docstring='Ground an assembly component through the headless Assembly API.',
            signature="(ctx: 'Context', doc_name: 'str', assembly_name: 'str', component_name: 'str', label: 'str | None' = None, recompute: 'bool' = True) -> 'CallToolResult'",
            operation_path="freecad_mcp.operations.create_assembly_grounded_joint_operation",
            rpc_method="create_assembly_grounded_joint",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.MUTATION,
            register_module="tools_assembly",
        ),
        ToolEntry(
            name="create_assembly_joint",
            docstring='Create a built-in Assembly joint from two component subelement references.',
            signature='(ctx: \'Context\', doc_name: \'str\', assembly_name: \'str\', joint_type: "Literal[\'Fixed\', \'Revolute\', \'Cylindrical\', \'Slider\', \'Ball\', \'Distance\', \'Parallel\', \'Perpendicular\', \'Angle\', \'RackPinion\', \'Screw\', \'Gears\', \'Belt\']", ref1_component: \'str\', ref2_component: \'str\', ref1_element: \'str\' = \'\', ref2_element: \'str\' = \'\', ref1_vertex: \'str | None\' = None, ref2_vertex: \'str | None\' = None, label: \'str | None\' = None, solve: \'bool\' = True, presolve: \'bool\' = True, recompute: \'bool\' = True, properties: \'dict[str, Any] | None\' = None) -> \'CallToolResult\'',
            operation_path="freecad_mcp.operations.create_assembly_joint_operation",
            rpc_method="create_assembly_joint",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.MUTATION,
            register_module="tools_assembly",
        ),
        ToolEntry(
            name="solve_assembly",
            docstring='Re-solve an Assembly after editing a joint or a referenced face (I9 / P9).\n\nTries ``assembly.solve()`` (C++), then ``JointObject.solveIfAllowed``, then a\nplain recompute, and reports which method succeeded. Returns JSON\n``{ok, assembly, method, status}`` plus a screenshot.\n\nArgs:\n    doc_name: The document containing the assembly.\n    assembly_name: The name of the Assembly::AssemblyObject to solve.',
            signature="(ctx: 'Context', doc_name: 'str', assembly_name: 'str') -> 'CallToolResult'",
            operation_path="freecad_mcp.operations.solve_assembly_operation",
            rpc_method="solve_assembly",
            execution_mode=ExecutionMode.TYPED_GATEWAY,
            gui_thread=False,
            mutation_class=MutationClass.MUTATION,
            register_module="tools_assembly",
        ),
    ),
)
