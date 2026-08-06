"""MCP tool registration — core document (Phase 7 / 7D)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context
from mcp.types import CallToolResult

from .operations import (
    create_document_operation,
    create_object_operation,
)
from .server_ops.tool_dependencies import ToolDependencies
from .tools_server_surfaces import server_connection, server_state

if TYPE_CHECKING:
    from .instrumented_server import InstrumentedFastMCP
def _register_create_document(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def create_document(ctx: Context, name: str) -> CallToolResult:
        """Create a new document in FreeCAD.

        Args:
            name: The name of the document to create.

        Returns:
            A message indicating the success or failure of the document creation.

        Examples:
            If you want to create a document named "MyDocument", you can use the following data.
            ```json
            {
                "name": "MyDocument"
            }
            ```
        """
        return create_document_operation(server_connection(), name)

    exports['create_document'] = create_document
def _register_create_object(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
    exports: dict[str, object],
) -> None:
    @mcp.tool()
    def create_object(
        ctx: Context,
        doc_name: str,
        obj_type: str,
        obj_name: str,
        analysis_name: str | None = None,
        obj_properties: dict[str, Any] | None = None,
    ) -> CallToolResult:
        """Create a new object in FreeCAD.
        Object type is starts with "Part::" or "Draft::" or "PartDesign::" or "Fem::".

        NOTE: For mechanical parts the default workflow is a parametric PartDesign feature
        history (body_create -> sketch_create/sketch_attach -> constraints ->
        get_sketch_diagnostics -> pad_feature/pocket_feature), not generic primitives. Use
        this tool for reference/non-parametric geometry, imported assets, temporary validation
        solids, or when a specific primitive is explicitly requested. See the
        asset_creation_strategy prompt.

        Args:
            doc_name: The name of the document to create the object in.
            obj_type: The type of the object to create (e.g. 'Part::Box', 'Part::Cylinder',
                'Draft::Circle', 'PartDesign::Body', etc.).
            obj_name: The name of the object to create.
            obj_properties: The properties of the object to create.

        Returns:
            A message indicating the success or failure of the object creation and a
            screenshot of the object.

        Examples:
            If you want to create a cylinder with a height of 30 and a radius of 10,
            you can use the following data.
            ``Placement.Rotation.Angle`` is in degrees.
            ```json
            {
                "doc_name": "MyCylinder",
                "obj_name": "Cylinder",
                "obj_type": "Part::Cylinder",
                "obj_properties": {
                    "Height": 30,
                    "Radius": 10,
                    "Placement": {
                        "Base": {
                            "x": 10,
                            "y": 10,
                            "z": 0
                        },
                        "Rotation": {
                            "Axis": {
                                "x": 0,
                                "y": 0,
                                "z": 1
                            },
                            "Angle": 45
                        }
                    },
                    "ViewObject": {
                        "ShapeColor": [0.5, 0.5, 0.5, 1.0]
                    }
                }
            }
            ```

            If you want to create a circle with a radius of 10, you can use the following data.
            ```json
            {
                "doc_name": "MyCircle",
                "obj_name": "Circle",
                "obj_type": "Draft::Circle",
            }
            ```

            If you want to create a FEM analysis, you can use the following data.
            ```json
            {
                "doc_name": "MyFEMAnalysis",
                "obj_name": "FemAnalysis",
                "obj_type": "Fem::AnalysisPython",
            }
            ```

            If you want to create a FEM constraint, you can use the following data.
            ```json
            {
                "doc_name": "MyFEMConstraint",
                "obj_name": "FemConstraint",
                "obj_type": "Fem::ConstraintFixed",
                "analysis_name": "MyFEMAnalysis",
                "obj_properties": {
                    "References": [
                        {
                            "object_name": "MyObject",
                            "face": "Face1"
                        }
                    ]
                }
            }
            ```

            If you want to create a FEM mechanical material, you can use the following data.
            ```json
            {
                "doc_name": "MyFEMAnalysis",
                "obj_name": "FemMechanicalMaterial",
                "obj_type": "Fem::MaterialCommon",
                "analysis_name": "MyFEMAnalysis",
                "obj_properties": {
                    "Material": {
                        "Name": "MyMaterial",
                        "Density": "7900 kg/m^3",
                        "YoungModulus": "210 GPa",
                        "PoissonRatio": 0.3
                    }
                }
            }
            ```

            If you want to create a FEM mesh, you can use the following data.
            The `Shape` property is required (legacy `Part` is also accepted).
            On FreeCAD 1.x the size limits are `CharacteristicLengthMax/Min`;
            the legacy `ElementSizeMax/Min` keys are also accepted.
            ```json
            {
                "doc_name": "MyFEMMesh",
                "obj_name": "FemMesh",
                "obj_type": "Fem::FemMeshGmsh",
                "analysis_name": "MyFEMAnalysis",
                "obj_properties": {
                    "Shape": "MyObject",
                    "CharacteristicLengthMax": 10,
                    "CharacteristicLengthMin": 0.1
                }
            }
            ```
        """
        return create_object_operation(
            server_connection(),
            server_state().only_text_feedback,
            doc_name,
            obj_type,
            obj_name,
            analysis_name,
            obj_properties,
        )

    exports['create_object'] = create_object

def register(
    mcp: InstrumentedFastMCP,
    *,
    dependencies: ToolDependencies,
) -> dict[str, object]:
    """Register core_document MCP tools; return exports for §3.3 façade shims."""
    exports: dict[str, object] = {}
    _register_create_document(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    _register_create_object(
        mcp,
        dependencies=dependencies,
        exports=exports,
    )
    return exports
