"""
P5 — Measurement, validation, and transform operations.
"""
from __future__ import annotations

import logging

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse
from .core import _run_code

logger = logging.getLogger("FreeCADMCPserver")


def _doc_sk_preamble(doc_name: str) -> list[str]:
    return [
        "import FreeCAD, Part, math, json",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        f"if not _doc: raise RuntimeError({f'Document {doc_name!r} not found'!r})",
    ]


# ---------------------------------------------------------------------------
# P5-1  measure_distance
# ---------------------------------------------------------------------------

def measure_distance_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    shape1_ref: str,
    shape2_ref: str,
) -> ToolResponse:
    lines = _doc_sk_preamble(doc_name) + [
        f"_o1 = _doc.getObject({shape1_ref!r})",
        f"_o2 = _doc.getObject({shape2_ref!r})",
        "if not _o1 or not _o2: raise RuntimeError('Object not found')",
        "_d = _o1.Shape.distToShape(_o2.Shape)",
        "print(json.dumps({'distance': _d[0], 'unit': 'mm'}))",
    ]
    return _run_code(freecad, True, "\n".join(lines),
                     f"Distance between '{shape1_ref}' and '{shape2_ref}'",
                     "Failed to measure distance")


# ---------------------------------------------------------------------------
# P5-2  measure_angle
# ---------------------------------------------------------------------------

def measure_angle_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    edge1_ref: str,
    edge2_ref: str,
) -> ToolResponse:
    lines = _doc_sk_preamble(doc_name) + [
        "def _parse_ref(_r):",
        "    _parts = _r.split(':')",
        "    _obj = _doc.getObject(_parts[0])",
        "    if not _obj: raise RuntimeError('Object not found: ' + _parts[0])",
        "    if len(_parts) > 1:",
        "        _sub = _parts[1]",
        "        if _sub.startswith('Edge'):",
        "            _idx = int(_sub[4:]) - 1",
        "            return _obj.Shape.Edges[_idx]",
        "    return _obj.Shape",
        f"_e1 = _parse_ref({edge1_ref!r})",
        f"_e2 = _parse_ref({edge2_ref!r})",
        "_v1 = _e1.tangentAt(_e1.FirstParameter)",
        "_v2 = _e2.tangentAt(_e2.FirstParameter)",
        "_cos_a = max(-1.0, min(1.0, _v1.dot(_v2) / (_v1.Length * _v2.Length)))",
        "_angle_deg = math.degrees(math.acos(_cos_a))",
        "print(json.dumps({'angle_deg': round(_angle_deg, 6), 'unit': 'degrees'}))",
    ]
    return _run_code(freecad, True, "\n".join(lines),
                     f"Angle between '{edge1_ref}' and '{edge2_ref}'",
                     "Failed to measure angle")


# ---------------------------------------------------------------------------
# P5-3  measure_area
# ---------------------------------------------------------------------------

def measure_area_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    obj_name: str,
) -> ToolResponse:
    lines = _doc_sk_preamble(doc_name) + [
        f"_obj = _doc.getObject({obj_name!r})",
        "if not _obj or not hasattr(_obj, 'Shape'): raise RuntimeError('Object with Shape not found')",
        "_area = _obj.Shape.Area",
        "print(json.dumps({'area_mm2': round(_area, 6), 'area_cm2': round(_area/100.0,6), 'unit': 'mm²'}))",
    ]
    return _run_code(freecad, True, "\n".join(lines),
                     f"Surface area of '{obj_name}'", "Failed to measure area")


# ---------------------------------------------------------------------------
# P5-4  measure_volume
# ---------------------------------------------------------------------------

def measure_volume_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    obj_name: str,
) -> ToolResponse:
    lines = _doc_sk_preamble(doc_name) + [
        f"_obj = _doc.getObject({obj_name!r})",
        "if not _obj or not hasattr(_obj, 'Shape'): raise RuntimeError('Object with Shape not found')",
        "_vol = _obj.Shape.Volume",
        "print(json.dumps({'volume_mm3': round(_vol,6), 'volume_cm3': round(_vol/1000.0,6), 'unit': 'mm³'}))",
    ]
    return _run_code(freecad, True, "\n".join(lines),
                     f"Volume of '{obj_name}'", "Failed to measure volume")


# ---------------------------------------------------------------------------
# P5-5  bounding_box
# ---------------------------------------------------------------------------

def bounding_box_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    obj_name: str,
) -> ToolResponse:
    lines = _doc_sk_preamble(doc_name) + [
        f"_obj = _doc.getObject({obj_name!r})",
        "if not _obj or not hasattr(_obj, 'Shape'): raise RuntimeError('Object not found')",
        "_bb = _obj.Shape.BoundBox",
        "print(json.dumps({"
        "'xmin':round(_bb.XMin,6),'ymin':round(_bb.YMin,6),'zmin':round(_bb.ZMin,6),"
        "'xmax':round(_bb.XMax,6),'ymax':round(_bb.YMax,6),'zmax':round(_bb.ZMax,6),"
        "'dx':round(_bb.XLength,6),'dy':round(_bb.YLength,6),'dz':round(_bb.ZLength,6),"
        "'diagonal':round(_bb.DiagonalLength,6)}))",
    ]
    return _run_code(freecad, True, "\n".join(lines),
                     f"Bounding box of '{obj_name}'", "Failed to get bounding box")


# ---------------------------------------------------------------------------
# P5-6  center_of_mass
# ---------------------------------------------------------------------------

def center_of_mass_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    obj_name: str,
) -> ToolResponse:
    lines = _doc_sk_preamble(doc_name) + [
        f"_obj = _doc.getObject({obj_name!r})",
        "if not _obj or not hasattr(_obj, 'Shape'): raise RuntimeError('Object not found')",
        "_com = _obj.Shape.CenterOfMass",
        "print(json.dumps({'x':round(_com.x,6),'y':round(_com.y,6),'z':round(_com.z,6),'unit':'mm'}))",
    ]
    return _run_code(freecad, True, "\n".join(lines),
                     f"Centre of mass of '{obj_name}'", "Failed to get centre of mass")


# ---------------------------------------------------------------------------
# P5-7  validate_geometry
# ---------------------------------------------------------------------------

def validate_geometry_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    obj_name: str,
) -> ToolResponse:
    lines = _doc_sk_preamble(doc_name) + [
        f"_obj = _doc.getObject({obj_name!r})",
        "if not _obj or not hasattr(_obj, 'Shape'): raise RuntimeError('Object not found')",
        "_sh = _obj.Shape",
        "_result = {",
        "    'is_null':   _sh.isNull(),",
        "    'is_valid':  _sh.isValid(),",
        "    'is_closed': _sh.isClosed(),",
        "    'volume_mm3': round(_sh.Volume, 6),",
        "    'area_mm2':   round(_sh.Area, 6),",
        "    'face_count': len(_sh.Faces),",
        "    'edge_count': len(_sh.Edges),",
        "    'vertex_count': len(_sh.Vertexes),",
        "    'shape_type': _sh.ShapeType,",
        "}",
        "_check = _sh.analyze(False)",
        "_result['check'] = _check if isinstance(_check, str) else str(_check)",
        "print(json.dumps(_result))",
    ]
    return _run_code(freecad, True, "\n".join(lines),
                     f"Geometry validation of '{obj_name}'", "Failed to validate geometry")


# ---------------------------------------------------------------------------
# P5-8  translate
# ---------------------------------------------------------------------------

def translate_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    dx: float,
    dy: float,
    dz: float,
) -> ToolResponse:
    lines = _doc_sk_preamble(doc_name) + [
        f"_obj = _doc.getObject({obj_name!r})",
        "if not _obj: raise RuntimeError('Object not found')",
        "_pl = _obj.Placement",
        f"_pl.Base = _pl.Base + FreeCAD.Vector({dx},{dy},{dz})",
        "_obj.Placement = _pl",
        "_doc.recompute()",
        f"print('translated {obj_name} by ({dx},{dy},{dz})')",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Object '{obj_name}' translated by ({dx},{dy},{dz})",
                     "Failed to translate")


# ---------------------------------------------------------------------------
# P5-9  rotate
# ---------------------------------------------------------------------------

def rotate_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    axis_x: float,
    axis_y: float,
    axis_z: float,
    angle_deg: float,
    center_x: float = 0.0,
    center_y: float = 0.0,
    center_z: float = 0.0,
) -> ToolResponse:
    lines = _doc_sk_preamble(doc_name) + [
        f"_obj = _doc.getObject({obj_name!r})",
        "if not _obj: raise RuntimeError('Object not found')",
        f"_axis   = FreeCAD.Vector({axis_x},{axis_y},{axis_z})",
        f"_center = FreeCAD.Vector({center_x},{center_y},{center_z})",
        f"_angle  = {angle_deg}",
        "_rot = FreeCAD.Rotation(_axis, _angle)",
        "_pl = _obj.Placement",
        "_new_pl = FreeCAD.Placement(_center, FreeCAD.Rotation()) * FreeCAD.Placement(FreeCAD.Vector(), _rot) * FreeCAD.Placement(-_center, FreeCAD.Rotation()) * _pl",
        "_obj.Placement = _new_pl",
        "_doc.recompute()",
        "print('rotated')",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Object '{obj_name}' rotated {angle_deg}° about axis",
                     "Failed to rotate")


# ---------------------------------------------------------------------------
# P5-10  scale
# ---------------------------------------------------------------------------

def scale_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    sx: float,
    sy: float,
    sz: float,
) -> ToolResponse:
    lines = _doc_sk_preamble(doc_name) + [
        f"_obj = _doc.getObject({obj_name!r})",
        "if not _obj or not hasattr(_obj, 'Shape'): raise RuntimeError('Object with Shape not found')",
        f"_m = FreeCAD.Matrix()",
        f"_m.scale({sx},{sy},{sz})",
        "_obj.Shape = _obj.Shape.transformGeometry(_m)",
        "_doc.recompute()",
        "print('scaled')",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Object '{obj_name}' scaled by ({sx},{sy},{sz})",
                     "Failed to scale")
