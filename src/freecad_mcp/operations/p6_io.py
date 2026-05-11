"""
P6 — Import / export operations (STEP, STL, OBJ, DXF, BREP).
"""
from __future__ import annotations

import logging

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse
from .core import _run_code

logger = logging.getLogger("FreeCADMCPserver")


def _doc_preamble(doc_name: str) -> list[str]:
    return [
        "import FreeCAD, Part, json",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        f"if not _doc: raise RuntimeError({f'Document {doc_name!r} not found'!r})",
    ]


# ---------------------------------------------------------------------------
# P6-1  export_step
# ---------------------------------------------------------------------------

def export_step_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    file_path: str,
    obj_names: list[str] | None = None,
) -> ToolResponse:
    obj_str = repr(obj_names) if obj_names else "None"
    lines = _doc_preamble(doc_name) + [
        f"_path = {file_path!r}",
        f"_names = {obj_str}",
        "_objs = [_doc.getObject(_n) for _n in _names] if _names else list(_doc.Objects)",
        "_objs = [_o for _o in _objs if _o and hasattr(_o,'Shape')]",
        "if not _objs: raise RuntimeError('No exportable objects found')",
        "import Import",
        "Import.export(_objs, _path)",
        "print(json.dumps({'exported': len(_objs), 'path': _path}))",
    ]
    return _run_code(freecad, True, "\n".join(lines),
                     f"Exported STEP to '{file_path}'", "Failed to export STEP")


# ---------------------------------------------------------------------------
# P6-2  import_step
# ---------------------------------------------------------------------------

def import_step_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    file_path: str,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + [
        f"_path = {file_path!r}",
        "import Import",
        "Import.insert(_path, _doc.Name)",
        "_doc.recompute()",
        "print(json.dumps({'imported': True, 'path': _path}))",
    ]
    return _run_code(freecad, True, "\n".join(lines),
                     f"Imported STEP from '{file_path}'", "Failed to import STEP")


# ---------------------------------------------------------------------------
# P6-3  export_stl
# ---------------------------------------------------------------------------

def export_stl_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    file_path: str,
    obj_names: list[str] | None = None,
    mesh_deviation: float = 0.1,
) -> ToolResponse:
    obj_str = repr(obj_names) if obj_names else "None"
    lines = _doc_preamble(doc_name) + [
        f"_path = {file_path!r}",
        f"_names = {obj_str}",
        f"_dev = {mesh_deviation}",
        "_objs = [_doc.getObject(_n) for _n in _names] if _names else list(_doc.Objects)",
        "_objs = [_o for _o in _objs if _o and hasattr(_o,'Shape')]",
        "if not _objs: raise RuntimeError('No exportable objects found')",
        "import Mesh",
        "_meshes = []",
        "for _o in _objs:",
        "    _mesh = Mesh.Mesh(_o.Shape.tessellate(_dev))",
        "    _meshes.append(_mesh)",
        "_combined = Mesh.Mesh()",
        "for _m in _meshes: _combined.addMesh(_m)",
        "_combined.write(_path)",
        "print(json.dumps({'exported': len(_objs), 'faces': _combined.CountFacets, 'path': _path}))",
    ]
    return _run_code(freecad, True, "\n".join(lines),
                     f"Exported STL to '{file_path}'", "Failed to export STL")


# ---------------------------------------------------------------------------
# P6-4  export_brep
# ---------------------------------------------------------------------------

def export_brep_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    obj_name: str,
    file_path: str,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + [
        f"_obj = _doc.getObject({obj_name!r})",
        "if not _obj or not hasattr(_obj,'Shape'): raise RuntimeError('Object not found')",
        f"_obj.Shape.exportBrep({file_path!r})",
        "print(json.dumps({'exported': True, 'path': " + repr(file_path) + "}))",
    ]
    return _run_code(freecad, True, "\n".join(lines),
                     f"Exported BREP to '{file_path}'", "Failed to export BREP")


# ---------------------------------------------------------------------------
# P6-5  import_brep
# ---------------------------------------------------------------------------

def import_brep_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    file_path: str,
    obj_name: str = "BRepImport",
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + [
        f"_sh = Part.Shape()",
        f"_sh.importBrep({file_path!r})",
        f"_obj = _doc.addObject('Part::Feature', {obj_name!r})",
        "_obj.Shape = _sh",
        "_doc.recompute()",
        "print(json.dumps({'imported': True, 'name': _obj.Name}))",
    ]
    return _run_code(freecad, True, "\n".join(lines),
                     f"Imported BREP from '{file_path}'", "Failed to import BREP")


# ---------------------------------------------------------------------------
# P6-6  apply_material / set_color
# ---------------------------------------------------------------------------

def set_color_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    r: float,
    g: float,
    b: float,
    transparency: float = 0.0,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + [
        f"_obj = _doc.getObject({obj_name!r})",
        "if not _obj: raise RuntimeError('Object not found')",
        "try:",
        f"    _obj.ViewObject.ShapeColor = ({r},{g},{b},1.0)",
        f"    _obj.ViewObject.Transparency = int({transparency} * 100)",
        "except Exception as _e:",
        "    print('Warning: ' + str(_e))",
        "print('color applied')",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Color applied to '{obj_name}'", "Failed to set color")
