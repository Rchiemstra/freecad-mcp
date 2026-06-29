import logging
from typing import Any

from mcp.types import ImageContent

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse, add_screenshot_if_available, json_response, text_response


logger = logging.getLogger("FreeCADMCPserver")


def create_document_operation(freecad: FreeCADConnection, name: str) -> ToolResponse:
    try:
        res = freecad.create_document(name)
        if res["success"]:
            return text_response(f"Document '{res['document_name']}' created successfully")
        return text_response(f"Failed to create document: {res['error']}")
    except Exception as e:
        logger.error(f"Failed to create document: {str(e)}")
        return text_response(f"Failed to create document: {str(e)}")


def create_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_type: str,
    obj_name: str,
    analysis_name: str | None = None,
    obj_properties: dict[str, Any] | None = None,
) -> ToolResponse:
    try:
        obj_data = {
            "Name": obj_name,
            "Type": obj_type,
            "Properties": obj_properties or {},
            "Analysis": analysis_name,
        }
        res = freecad.create_object(doc_name, obj_data)
        screenshot = freecad.get_active_screenshot()

        if res["success"]:
            response = text_response(f"Object '{res['object_name']}' created successfully")
        else:
            response = text_response(f"Failed to create object: {res['error']}")
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to create object: {str(e)}")
        return text_response(f"Failed to create object: {str(e)}")


def edit_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    obj_properties: dict[str, Any],
) -> ToolResponse:
    try:
        res = freecad.edit_object(doc_name, obj_name, {"Properties": obj_properties})
        screenshot = freecad.get_active_screenshot()

        if res["success"]:
            response = text_response(f"Object '{res['object_name']}' edited successfully")
        else:
            response = text_response(f"Failed to edit object: {res['error']}")
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to edit object: {str(e)}")
        return text_response(f"Failed to edit object: {str(e)}")


def delete_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
) -> ToolResponse:
    try:
        res = freecad.delete_object(doc_name, obj_name)
        screenshot = freecad.get_active_screenshot()

        if res["success"]:
            response = text_response(f"Object '{res['object_name']}' deleted successfully")
        else:
            response = text_response(f"Failed to delete object: {res['error']}")
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to delete object: {str(e)}")
        return text_response(f"Failed to delete object: {str(e)}")


def execute_code_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    code: str,
) -> ToolResponse:
    try:
        res = freecad.execute_code(code)
        # Preserve the user's camera after arbitrary code execution. Named views
        # are still handled by get_view_operation().
        screenshot = freecad.get_active_screenshot(view_name=None)

        if res["success"]:
            response = text_response(f"Code executed successfully: {res['message']}")
        else:
            response = text_response(f"Failed to execute code: {res['error']}")
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to execute code: {str(e)}")
        return text_response(f"Failed to execute code: {str(e)}")


def get_view_operation(
    freecad: FreeCADConnection,
    view_name: str,
    width: int | None = None,
    height: int | None = None,
    focus_object: str | None = None,
) -> ToolResponse:
    screenshot = freecad.get_active_screenshot(view_name, width, height, focus_object)
    if screenshot is not None:
        label = f"View: {view_name}" + (f" | focus: {focus_object}" if focus_object else "")
        return [*text_response(label), ImageContent(type="image", data=screenshot, mimeType="image/png")]
    return text_response("Cannot get screenshot in the current view type (such as TechDraw or Spreadsheet)")


def insert_part_from_library_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    relative_path: str,
) -> ToolResponse:
    try:
        res = freecad.insert_part_from_library(relative_path)
        screenshot = freecad.get_active_screenshot()

        if res["success"]:
            response = text_response(f"Part inserted from library: {res['message']}")
        else:
            response = text_response(f"Failed to insert part from library: {res['error']}")
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to insert part from library: {str(e)}")
        return text_response(f"Failed to insert part from library: {str(e)}")


def get_objects_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
) -> ToolResponse:
    try:
        screenshot = freecad.get_active_screenshot()
        response = json_response(freecad.get_objects(doc_name))
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to get objects: {str(e)}")
        return text_response(f"Failed to get objects: {str(e)}")


def get_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
) -> ToolResponse:
    try:
        screenshot = freecad.get_active_screenshot()
        response = json_response(freecad.get_object(doc_name, obj_name))
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"Failed to get object: {str(e)}")
        return text_response(f"Failed to get object: {str(e)}")


def get_parts_list_operation(freecad: FreeCADConnection) -> ToolResponse:
    parts = freecad.get_parts_list()
    if parts:
        return json_response(parts)
    return text_response("No parts found in the parts library. You must add parts_library addon.")


def list_documents_operation(freecad: FreeCADConnection) -> ToolResponse:
    return json_response(freecad.list_documents())


# ---------------------------------------------------------------------------
# Code-generation helpers shared by all sketch / PartDesign / document ops.
# All sketch tools run through execute_code so they work with the original
# addon without any addon update or FreeCAD restart.
# ---------------------------------------------------------------------------

def _run_code(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    code: str,
    success_msg: str,
    fail_prefix: str,
) -> ToolResponse:
    """Execute generated Python code in FreeCAD and return a formatted response."""
    try:
        res = freecad.execute_code(code)
        screenshot = freecad.get_active_screenshot()
        if res["success"]:
            output = res.get("message", "")
            msg = f"{success_msg}\n{output}".strip()
            errors = res.get("recompute_errors", [])
            if errors:
                names = ", ".join(
                    f"{e['name']} (doc={e.get('doc','?')}, state={e['state']})"
                    for e in errors
                )
                msg += f"\nRecompute errors detected: {names}"
            response = text_response(msg)
        else:
            response = text_response(f"{fail_prefix}: {res.get('error', res.get('message', 'unknown error'))}")
        return add_screenshot_if_available(response, screenshot, only_text_feedback)
    except Exception as e:
        logger.error(f"{fail_prefix}: {e}")
        return text_response(f"{fail_prefix}: {e}")


def _geom_line(code: str, geom: dict) -> str:
    """Return a Python expression that adds one geometry element to _sk."""
    t = geom.get("type", "").lower()
    c = "True" if geom.get("construction") else "False"
    if t == "line":
        s, e = geom["start"], geom["end"]
        return (f"_idx = _sk.addGeometry("
                f"Part.LineSegment(FreeCAD.Vector({s['x']},{s['y']},0),"
                f"FreeCAD.Vector({e['x']},{e['y']},0)),{c}); _idxs.append(_idx)")
    if t == "circle":
        ct = geom.get("center", {"x": 0, "y": 0})
        r = geom.get("radius", 1)
        return (f"_idx = _sk.addGeometry("
                f"Part.Circle(FreeCAD.Vector({ct['x']},{ct['y']},0),FreeCAD.Vector(0,0,1),{r}),{c});"
                f" _idxs.append(_idx)")
    if t == "arc":
        ct = geom.get("center", {"x": 0, "y": 0})
        r = geom.get("radius", 1)
        sa = geom.get("start_angle", 0)
        ea = geom.get("end_angle", 90)
        return (f"_arc = Part.ArcOfCircle("
                f"Part.Circle(FreeCAD.Vector({ct['x']},{ct['y']},0),FreeCAD.Vector(0,0,1),{r}),"
                f"math.radians({sa}),math.radians({ea}));"
                f" _idx = _sk.addGeometry(_arc,{c}); _idxs.append(_idx)")
    if t == "rectangle":
        x1, y1, x2, y2 = geom.get("x1", 0), geom.get("y1", 0), geom.get("x2", 10), geom.get("y2", 10)
        return "\n".join([
            f"for _p1,_p2 in [((({x1},{y1}),({x2},{y1})),(({x2},{y1}),({x2},{y2})),(({x2},{y2}),({x1},{y2})),(({x1},{y2}),({x1},{y1})))][0]:",
            f"    _idx = _sk.addGeometry(Part.LineSegment(FreeCAD.Vector(_p1[0],_p1[1],0),FreeCAD.Vector(_p2[0],_p2[1],0)),{c}); _idxs.append(_idx)",
        ])
    if t == "point":
        x, y = geom.get("x", 0), geom.get("y", 0)
        return (f"_idx = _sk.addGeometry(Part.Point(FreeCAD.Vector({x},{y},0)),{c}); _idxs.append(_idx)")
    return f"raise ValueError('Unknown geometry type: {t!r}')"


def _constraint_line(c: dict) -> str:
    """Return a Python expression that adds one Sketcher constraint to _sk."""
    t = c.get("type", "")
    if t == "Coincident":
        return f"_sk.addConstraint(Sketcher.Constraint('Coincident',{c['geo1']},{c['pos1']},{c['geo2']},{c['pos2']}))"
    if t == "Horizontal":
        return f"_sk.addConstraint(Sketcher.Constraint('Horizontal',{c['geo']}))"
    if t == "Vertical":
        return f"_sk.addConstraint(Sketcher.Constraint('Vertical',{c['geo']}))"
    if t == "Distance":
        if "geo2" in c:
            return f"_sk.addConstraint(Sketcher.Constraint('Distance',{c['geo1']},{c.get('pos1',0)},{c['geo2']},{c.get('pos2',0)},{c['value']}))"
        if "pos" in c:
            return f"_sk.addConstraint(Sketcher.Constraint('Distance',{c['geo']},{c['pos']},{c['value']}))"
        return f"_sk.addConstraint(Sketcher.Constraint('Distance',{c['geo']},{c['value']}))"
    if t == "DistanceX":
        if "pos" in c:
            return f"_sk.addConstraint(Sketcher.Constraint('DistanceX',{c['geo']},{c['pos']},{c['value']}))"
        return f"_sk.addConstraint(Sketcher.Constraint('DistanceX',{c['geo']},{c['value']}))"
    if t == "DistanceY":
        if "pos" in c:
            return f"_sk.addConstraint(Sketcher.Constraint('DistanceY',{c['geo']},{c['pos']},{c['value']}))"
        return f"_sk.addConstraint(Sketcher.Constraint('DistanceY',{c['geo']},{c['value']}))"
    if t == "Radius":
        return f"_sk.addConstraint(Sketcher.Constraint('Radius',{c['geo']},{c['value']}))"
    if t == "Diameter":
        return f"_sk.addConstraint(Sketcher.Constraint('Diameter',{c['geo']},{c['value']}))"
    if t == "Angle":
        if "geo2" in c:
            return f"_sk.addConstraint(Sketcher.Constraint('Angle',{c['geo1']},{c.get('pos1',0)},{c['geo2']},{c.get('pos2',0)},{c['value']}))"
        return f"_sk.addConstraint(Sketcher.Constraint('Angle',{c['geo']},{c['value']}))"
    if t in ("Parallel", "Perpendicular", "Equal", "Tangent"):
        return f"_sk.addConstraint(Sketcher.Constraint({t!r},{c['geo1']},{c['geo2']}))"
    if t == "PointOnObject":
        return f"_sk.addConstraint(Sketcher.Constraint('PointOnObject',{c['geo1']},{c['pos1']},{c['geo2']}))"
    if t == "Symmetric":
        return f"_sk.addConstraint(Sketcher.Constraint('Symmetric',{c['geo1']},{c['pos1']},{c['geo2']},{c['pos2']},{c['geo3']},{c.get('pos3',0)}))"
    if t == "Block":
        return f"_sk.addConstraint(Sketcher.Constraint('Block',{c['geo']}))"
    return f"raise ValueError('Unknown constraint type: {t!r}')"


def _partdesign_bool_property_helper_code() -> list[str]:
    return [
        "def _set_feature_bool(_feature, _property_names, _value):",
        "    _properties = set(getattr(_feature, 'PropertiesList', []))",
        "    for _name in _property_names:",
        "        if _name in _properties:",
        "            setattr(_feature, _name, bool(_value))",
        "            return _name",
        "    if _value:",
        "        raise RuntimeError(",
        "            'Feature does not support any of: ' + ', '.join(_property_names)",
        "        )",
        "    return None",
    ]


def _partdesign_extrusion_helper_code() -> list[str]:
    return [
        "def _set_extrusion_symmetric(_feature, _value):",
        "    _properties = set(getattr(_feature, 'PropertiesList', []))",
        "    _side_type = 'SideType' if 'SideType' in _properties else None",
        "    if _side_type:",
        "        _candidates = ('Two sides', 'Symmetric') if _value else ('One side',)",
        "        _last_error = None",
        "        for _candidate in _candidates:",
        "            try:",
        "                setattr(_feature, _side_type, _candidate)",
        "                return _side_type",
        "            except Exception as _err:",
        "                _last_error = _err",
        "        if _last_error:",
        "            raise _last_error",
        "    if 'Symmetric' in _properties:",
        "        setattr(_feature, 'Symmetric', bool(_value))",
        "        return 'Symmetric'",
        "    if 'Midplane' in _properties:",
        "        if _value:",
        "            setattr(_feature, 'Midplane', True)",
        "            return 'Midplane'",
        "        return None",
        "    if _value:",
        "        raise RuntimeError('Feature does not support symmetric extrusion')",
        "    return None",
    ]


def _partdesign_pattern_helper_code() -> list[str]:
    return [
        "def _get_body(_doc, _source, _body_name=None):",
        "    if _body_name:",
        "        _body = _doc.getObject(_body_name)",
        "        if not _body:",
        "            raise RuntimeError('Body not found: ' + _body_name)",
        "        return _body",
        "    for _obj in _doc.Objects:",
        "        if getattr(_obj, 'TypeId', '') == 'PartDesign::Body' and _source in getattr(_obj, 'Group', []):",
        "            return _obj",
        "    raise RuntimeError('Source feature must be inside a PartDesign Body')",
        "def _set_originals(_feature, _source):",
        "    _properties = set(getattr(_feature, 'PropertiesList', []))",
        "    if 'Originals' in _properties:",
        "        _feature.Originals = [_source]",
        "        return 'Originals'",
        "    if 'Original' in _properties:",
        "        _feature.Original = _source",
        "        return 'Original'",
        "    raise RuntimeError('Pattern feature has no Originals/Original property')",
        "def _set_property(_feature, _property_names, _value):",
        "    _properties = set(getattr(_feature, 'PropertiesList', []))",
        "    for _name in _property_names:",
        "        if _name in _properties:",
        "            setattr(_feature, _name, _value)",
        "            return _name",
        "    raise RuntimeError('Feature does not support any of: ' + ', '.join(_property_names))",
        "def _origin_feature(_container, _name):",
        "    _origin = getattr(_container, 'Origin', None)",
        "    for _feature in getattr(_origin, 'OriginFeatures', []):",
        "        if getattr(_feature, 'Name', '') == _name or getattr(_feature, 'Label', '') == _name:",
        "            return _feature",
        "    return None",
        "def _resolve_linksub(_doc, _body, _spec):",
        "    if ':' in _spec:",
        "        _obj_name, _sub_name = _spec.split(':', 1)",
        "        _obj = _doc.getObject(_obj_name)",
        "        if not _obj:",
        "            raise RuntimeError('Reference object not found: ' + _obj_name)",
        "        return (_obj, [_sub_name])",
        "    for _container in (_body, _doc):",
        "        _obj = _origin_feature(_container, _spec)",
        "        if _obj:",
        "            return (_obj, [''])",
        "    _obj = _doc.getObject(_spec)",
        "    if _obj:",
        "        return (_obj, [''])",
        "    raise RuntimeError('Reference not found: ' + _spec)",
        "def _set_linksub(_feature, _property_names, _link):",
        "    _properties = set(getattr(_feature, 'PropertiesList', []))",
        "    for _name in _property_names:",
        "        if _name in _properties:",
        "            setattr(_feature, _name, _link)",
        "            return _name",
        "    raise RuntimeError('Feature does not support any of: ' + ', '.join(_property_names))",
        "def _set_tip(_body, _feature):",
        "    try:",
        "        _body.Tip = _feature",
        "    except Exception:",
        "        pass",
    ]


# ---------------------------------------------------------------------------
# Sketch operations (all use execute_code — no addon update required)
# ---------------------------------------------------------------------------

def sketch_create_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    body_name: str | None = None,
    attach_to: str | None = None,
) -> ToolResponse:
    lines = [
        "import FreeCAD",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        f"if not _doc: raise RuntimeError({f'Document {doc_name!r} not found'!r})",
    ]
    if body_name:
        lines += [
            f"_body = _doc.getObject({body_name!r})",
            f"if not _body: raise RuntimeError({f'Body {body_name!r} not found'!r})",
            f"_sk = _body.newObject('Sketcher::SketchObject', {sketch_name!r})",
        ]
    else:
        lines.append(f"_sk = _doc.addObject('Sketcher::SketchObject', {sketch_name!r})")

    if attach_to:
        if attach_to in ("XY_Plane", "XZ_Plane", "YZ_Plane"):
            lines += [
                "_plane = None",
                "for _o in _doc.Objects:",
                "    if _o.TypeId == 'App::Origin':",
                f"        for _f in getattr(_o, 'OriginFeatures', []):",
                f"            if _f.Label == {attach_to!r}: _plane = _f; break",
                "        if _plane: break",
                "if _plane: _sk.AttachmentSupport = [(_plane, '')]; _sk.MapMode = 'FlatFace'",
            ]
        elif ":" in attach_to:
            obj_n, face = attach_to.split(":", 1)
            lines += [
                f"_ref = _doc.getObject({obj_n!r})",
                f"if _ref: _sk.AttachmentSupport = [(_ref, {face!r})]; _sk.MapMode = 'FlatFace'",
            ]

    lines += [
        "_doc.recompute()",
        "print('sketch_name=' + _sk.Name)",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Sketch '{sketch_name}' created", "Failed to create sketch")


def sketch_add_geometry_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    geometry: list,
) -> ToolResponse:
    lines = [
        "import FreeCAD, Part, math",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        f"_sk = _doc.getObject({sketch_name!r})",
        "if not _sk: raise RuntimeError('Sketch not found')",
        "_idxs = []",
    ]
    for geom in geometry:
        lines.append(_geom_line("", geom))
    lines += ["_doc.recompute()", "print('indices=' + str(_idxs))"]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Geometry added to '{sketch_name}'", "Failed to add geometry")


def sketch_add_constraint_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    constraints: list,
) -> ToolResponse:
    lines = [
        "import FreeCAD, Sketcher",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        f"_sk = _doc.getObject({sketch_name!r})",
        "if not _sk: raise RuntimeError('Sketch not found')",
    ]
    for c in constraints:
        lines.append(_constraint_line(c))
    lines += ["_doc.recompute()", f"print('{len(constraints)} constraint(s) added')"]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Constraints added to '{sketch_name}'", "Failed to add constraints")


def pad_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    pad_name: str,
    length: float,
    body_name: str | None = None,
    symmetric: bool = False,
    reversed_dir: bool = False,
) -> ToolResponse:
    lines = [
        "import FreeCAD",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        f"_sk = _doc.getObject({sketch_name!r})",
        "if not _sk: raise RuntimeError('Sketch not found')",
    ]
    if body_name:
        lines += [
            f"_body = _doc.getObject({body_name!r})",
            "if not _body: raise RuntimeError('Body not found')",
        ]
    else:
        lines += [
            "_body = None",
            "for _o in _doc.Objects:",
            "    if _o.TypeId == 'PartDesign::Body' and _sk in _o.Group: _body = _o; break",
        ]
    lines += [
        f"_pad = _body.newObject('PartDesign::Pad', {pad_name!r}) if _body else _doc.addObject('PartDesign::Pad', {pad_name!r})",
        "_pad.Profile = (_sk, [''])",
        f"_pad.Length = {length}",
        *_partdesign_extrusion_helper_code(),
        *_partdesign_bool_property_helper_code(),
        f"_set_extrusion_symmetric(_pad, {symmetric})",
        f"_set_feature_bool(_pad, ('Reversed',), {reversed_dir})",
        "_sk.Visibility = False",
        "_doc.recompute()",
        "print('pad_name=' + _pad.Name)",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Pad '{pad_name}' created", "Failed to create pad")


def pocket_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    pocket_name: str,
    length: float,
    body_name: str | None = None,
    symmetric: bool = False,
    reversed_dir: bool = False,
) -> ToolResponse:
    lines = [
        "import FreeCAD",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        f"_sk = _doc.getObject({sketch_name!r})",
        "if not _sk: raise RuntimeError('Sketch not found')",
    ]
    if body_name:
        lines += [
            f"_body = _doc.getObject({body_name!r})",
            "if not _body: raise RuntimeError('Body not found')",
        ]
    else:
        lines += [
            "_body = None",
            "for _o in _doc.Objects:",
            "    if _o.TypeId == 'PartDesign::Body' and _sk in _o.Group: _body = _o; break",
        ]
    lines += [
        f"_pkt = _body.newObject('PartDesign::Pocket', {pocket_name!r}) if _body else _doc.addObject('PartDesign::Pocket', {pocket_name!r})",
        "_pkt.Profile = (_sk, [''])",
        f"_pkt.Length = {length}",
        *_partdesign_extrusion_helper_code(),
        *_partdesign_bool_property_helper_code(),
        f"_set_extrusion_symmetric(_pkt, {symmetric})",
        f"_set_feature_bool(_pkt, ('Reversed',), {reversed_dir})",
        "_sk.Visibility = False",
        "_doc.recompute()",
        "print('pocket_name=' + _pkt.Name)",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Pocket '{pocket_name}' created", "Failed to create pocket")


def linear_pattern_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    feature_name: str,
    pattern_name: str,
    length: float,
    occurrences: int,
    direction: str = "X_Axis",
    body_name: str | None = None,
    reversed_dir: bool = False,
) -> ToolResponse:
    lines = [
        "import FreeCAD",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        f"if not _doc: raise RuntimeError({f'Document {doc_name!r} not found'!r})",
        f"_src = _doc.getObject({feature_name!r})",
        "if not _src: raise RuntimeError('Source feature not found')",
        f"_length = float({length})",
        f"_occurrences = int({occurrences})",
        "if _length <= 0: raise ValueError('length must be > 0')",
        "if _occurrences < 2: raise ValueError('occurrences must be >= 2')",
        *_partdesign_pattern_helper_code(),
        *_partdesign_bool_property_helper_code(),
        f"_body = _get_body(_doc, _src, {body_name!r})",
        f"_pattern = _body.newObject('PartDesign::LinearPattern', {pattern_name!r})",
        "_set_originals(_pattern, _src)",
        "_set_property(_pattern, ('Length',), _length)",
        "_set_property(_pattern, ('Occurrences',), _occurrences)",
        f"_set_linksub(_pattern, ('Direction',), _resolve_linksub(_doc, _body, {direction!r}))",
        f"_set_feature_bool(_pattern, ('Reversed',), {reversed_dir})",
        "_set_tip(_body, _pattern)",
        "_doc.recompute()",
        "print('pattern_name=' + _pattern.Name)",
        "print('source_name=' + _src.Name)",
        "print('body_name=' + _body.Name)",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Linear pattern '{pattern_name}' created", "Failed to create linear pattern")


def polar_pattern_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    feature_name: str,
    pattern_name: str,
    occurrences: int,
    angle: float = 360.0,
    axis: str = "Z_Axis",
    body_name: str | None = None,
    reversed_dir: bool = False,
) -> ToolResponse:
    lines = [
        "import FreeCAD",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        f"if not _doc: raise RuntimeError({f'Document {doc_name!r} not found'!r})",
        f"_src = _doc.getObject({feature_name!r})",
        "if not _src: raise RuntimeError('Source feature not found')",
        f"_occurrences = int({occurrences})",
        f"_angle = float({angle})",
        "if _occurrences < 2: raise ValueError('occurrences must be >= 2')",
        "if _angle <= 0: raise ValueError('angle must be > 0')",
        *_partdesign_pattern_helper_code(),
        *_partdesign_bool_property_helper_code(),
        f"_body = _get_body(_doc, _src, {body_name!r})",
        f"_pattern = _body.newObject('PartDesign::PolarPattern', {pattern_name!r})",
        "_set_originals(_pattern, _src)",
        "_set_property(_pattern, ('Angle',), _angle)",
        "_set_property(_pattern, ('Occurrences',), _occurrences)",
        f"_set_linksub(_pattern, ('Axis',), _resolve_linksub(_doc, _body, {axis!r}))",
        f"_set_feature_bool(_pattern, ('Reversed',), {reversed_dir})",
        "_set_tip(_body, _pattern)",
        "_doc.recompute()",
        "print('pattern_name=' + _pattern.Name)",
        "print('source_name=' + _src.Name)",
        "print('body_name=' + _body.Name)",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Polar pattern '{pattern_name}' created", "Failed to create polar pattern")


def mirror_feature_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    feature_name: str,
    mirror_name: str,
    plane: str = "YZ_Plane",
    body_name: str | None = None,
) -> ToolResponse:
    lines = [
        "import FreeCAD",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        f"if not _doc: raise RuntimeError({f'Document {doc_name!r} not found'!r})",
        f"_src = _doc.getObject({feature_name!r})",
        "if not _src: raise RuntimeError('Source feature not found')",
        *_partdesign_pattern_helper_code(),
        f"_body = _get_body(_doc, _src, {body_name!r})",
        f"_mirror = _body.newObject('PartDesign::Mirrored', {mirror_name!r})",
        "_set_originals(_mirror, _src)",
        f"_set_linksub(_mirror, ('MirrorPlane', 'Plane'), _resolve_linksub(_doc, _body, {plane!r}))",
        "_set_tip(_body, _mirror)",
        "_doc.recompute()",
        "print('mirror_name=' + _mirror.Name)",
        "print('source_name=' + _src.Name)",
        "print('body_name=' + _body.Name)",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Mirror feature '{mirror_name}' created", "Failed to create mirror feature")


def create_spur_gear_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    gear_name: str,
    teeth: int,
    module: float,
    width: float,
    pressure_angle: float = 20.0,
    bore_diameter: float = 0.0,
    clearance: float = 0.0,
    backlash: float = 0.0,
    samples_per_flank: int = 8,
    body_name: str | None = None,
    sketch_name: str | None = None,
    tooth_profile: str = "involute",
) -> ToolResponse:
    lines = [
        "import math",
        "import FreeCAD, Part, Sketcher",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        f"if not _doc: raise RuntimeError({f'Document {doc_name!r} not found'!r})",
        f"_gear_name = {gear_name!r}",
        f"_body_name = {body_name!r}",
        f"_sketch_name = {sketch_name!r} or (_gear_name + '_Sketch')",
        f"_teeth = int({teeth})",
        f"_module = float({module})",
        f"_width = float({width})",
        f"_pressure_angle = math.radians(float({pressure_angle}))",
        f"_bore_diameter = float({bore_diameter})",
        f"_clearance = float({clearance})",
        f"_backlash = float({backlash})",
        f"_samples = max(3, int({samples_per_flank}))",
        f"_tooth_profile = {tooth_profile!r}.strip().lower().replace('-', '_').replace(' ', '_')",
        "_profile_aliases = {",
        "    'straight_teeth': 'straight',",
        "    'square': 'straight',",
        "    'spline': 'straight',",
        "    'trapezoid_straight_teeth': 'trapezoid',",
        "    'novikov': 'circular_arc',",
        "    'circular': 'circular_arc',",
        "    'arc': 'circular_arc',",
        "    'lantern': 'pin',",
        "    'pin_gear': 'pin',",
        "}",
        "_tooth_profile = _profile_aliases.get(_tooth_profile, _tooth_profile)",
        "_valid_profiles = {'involute', 'cycloidal', 'trapezoid', 'straight', 'circular_arc', 'pin'}",
        "if _tooth_profile not in _valid_profiles:",
        "    raise ValueError('tooth_profile must be one of: ' + ', '.join(sorted(_valid_profiles)))",
        "if _teeth < 3: raise ValueError('teeth must be >= 3')",
        "if _module <= 0: raise ValueError('module must be > 0')",
        "if _width <= 0: raise ValueError('width must be > 0')",
        "if not 0 < _pressure_angle < math.radians(45):",
        "    raise ValueError('pressure_angle must be between 0 and 45 degrees')",
        "if _bore_diameter < 0: raise ValueError('bore_diameter must be >= 0')",
        "if _clearance < 0: raise ValueError('clearance must be >= 0')",
        "if _backlash < 0: raise ValueError('backlash must be >= 0')",
        "_pitch_radius = _module * _teeth / 2.0",
        "_base_radius = _pitch_radius * math.cos(_pressure_angle)",
        "_outer_radius = _pitch_radius + _module",
        "_root_radius = max(_pitch_radius - (1.25 * _module + _clearance), _module * 0.05)",
        "if _root_radius >= _outer_radius:",
        "    raise ValueError('root radius must be smaller than outer radius')",
        "if _bore_diameter and _bore_diameter >= 2.0 * _root_radius:",
        "    raise ValueError('bore_diameter must be smaller than the root diameter')",
        "_body = _doc.getObject(_body_name) if _body_name else None",
        "if _body_name and not _body:",
        "    raise RuntimeError('Body not found: ' + _body_name)",
        "if not _body:",
        "    _body = _doc.addObject('PartDesign::Body', _gear_name + '_Body')",
        "_sk = _body.newObject('Sketcher::SketchObject', _sketch_name)",
        "_plane = None",
        "_origin = getattr(_body, 'Origin', None)",
        "for _feature in getattr(_origin, 'OriginFeatures', []):",
        "    if getattr(_feature, 'Name', '') == 'XY_Plane' or getattr(_feature, 'Label', '') == 'XY_Plane':",
        "        _plane = _feature",
        "        break",
        "if _plane:",
        "    _sk.AttachmentSupport = [(_plane, '')]",
        "    _sk.MapMode = 'FlatFace'",
        "_points = []",
        "def _rotate(_x, _y, _angle):",
        "    _ca = math.cos(_angle)",
        "    _sa = math.sin(_angle)",
        "    return (_x * _ca - _y * _sa, _x * _sa + _y * _ca)",
        "def _add_point(_x, _y):",
        "    _pt = FreeCAD.Vector(_x, _y, 0)",
        "    if not _points or (_points[-1] - _pt).Length > 1e-7:",
        "        _points.append(_pt)",
        "def _add_arc(_radius, _start, _end, _steps):",
        "    _steps = max(1, int(_steps))",
        "    for _idx in range(1, _steps + 1):",
        "        _a = _start + (_end - _start) * _idx / _steps",
        "        _add_point(_radius * math.cos(_a), _radius * math.sin(_a))",
        "def _add_radial_point(_radius, _angle):",
        "    _add_point(_radius * math.cos(_angle), _radius * math.sin(_angle))",
        # Correct involute profile: x(t)=r_b*(cos(t)+t*sin(t)), y(t)=r_b*(sin(t)-t*cos(t))
        # Polar angle at parameter t: theta(t) = t - atan(t)
        "def _build_involute_points():",
        "    _inv_alpha = math.tan(_pressure_angle) - _pressure_angle",
        "    _delta = math.pi / (2.0 * _teeth) - _backlash / (2.0 * _pitch_radius)",
        "    if _outer_radius <= _base_radius:",
        "        raise ValueError('Addendum circle must be larger than base circle — reduce pressure_angle or increase module')",
        "    _t_tip = math.sqrt((_outer_radius / _base_radius) ** 2 - 1.0)",
        "    _has_undercut = _root_radius < _base_radius",
        "    _t_root = math.sqrt((_root_radius / _base_radius) ** 2 - 1.0) if not _has_undercut else 0.0",
        "    def _ix(_t): return _base_radius * (math.cos(_t) + _t * math.sin(_t))",
        "    def _iy(_t): return _base_radius * (math.sin(_t) - _t * math.cos(_t))",
        "    def _polar(_t): return _t - math.atan(_t)",
        "    def _rot(_x, _y, _a):",
        "        _c = math.cos(_a); _s = math.sin(_a)",
        "        return _c*_x - _s*_y, _s*_x + _c*_y",
        "    for _k in range(_teeth):",
        "        _theta = 2.0 * math.pi * _k / _teeth",
        "        _phi_r = _theta - _delta - _inv_alpha",
        "        _phi_l = _theta + _delta + _inv_alpha",
        "        if _has_undercut:",
        "            _add_radial_point(_root_radius, _phi_r)",
        "        for _si in range(_samples + 1):",
        "            _t = _t_root + (_t_tip - _t_root) * _si / _samples",
        "            _x, _y = _rot(_ix(_t), _iy(_t), _phi_r)",
        "            _add_point(_x, _y)",
        "        _r_tip_ang = _phi_r + _polar(_t_tip)",
        "        _l_tip_ang = _phi_l - _polar(_t_tip)",
        "        _tip_steps = max(2, _samples // 4)",
        "        for _ti in range(1, _tip_steps):",
        "            _a = _r_tip_ang + (_l_tip_ang - _r_tip_ang) * _ti / _tip_steps",
        "            _add_point(_outer_radius * math.cos(_a), _outer_radius * math.sin(_a))",
        "        for _si in range(_samples, -1, -1):",
        "            _t = _t_root + (_t_tip - _t_root) * _si / _samples",
        "            _x, _y = _rot(_ix(_t), -_iy(_t), _phi_l)",
        "            _add_point(_x, _y)",
        "        if _has_undercut:",
        "            _add_radial_point(_root_radius, _phi_l)",
        "        if _has_undercut:",
        "            _arc_start = _phi_l",
        "            _arc_end = (_theta + 2.0*math.pi/_teeth) - _delta - _inv_alpha",
        "        else:",
        "            _arc_start = _phi_l - _polar(_t_root)",
        "            _arc_end = (_theta + 2.0*math.pi/_teeth) - _delta - _inv_alpha + _polar(_t_root)",
        "        _root_steps = max(2, _samples // 2)",
        "        for _ri in range(1, _root_steps + 1):",
        "            _a = _arc_start + (_arc_end - _arc_start) * _ri / _root_steps",
        "            _add_point(_root_radius * math.cos(_a), _root_radius * math.sin(_a))",
        "def _build_trapezoid_points():",
        "    _tooth_angle = 2.0 * math.pi / _teeth",
        "    _backlash_angle = _backlash / _pitch_radius",
        "    _root_half = max(_tooth_angle * 0.28, _tooth_angle * 0.36 - _backlash_angle / 2.0)",
        "    _tip_half = max(_tooth_angle * 0.10, _tooth_angle * 0.18 - _backlash_angle / 2.0)",
        "    if _tip_half >= _root_half:",
        "        _tip_half = _root_half * 0.65",
        "    for _tooth in range(_teeth):",
        "        _theta = 2.0 * math.pi * _tooth / _teeth",
        "        _next_theta = 2.0 * math.pi * (_tooth + 1) / _teeth",
        "        _left_root = _theta - _root_half",
        "        _left_tip = _theta - _tip_half",
        "        _right_tip = _theta + _tip_half",
        "        _right_root = _theta + _root_half",
        "        _next_left_root = _next_theta - _root_half",
        "        _add_radial_point(_root_radius, _left_root)",
        "        _add_radial_point(_outer_radius, _left_tip)",
        "        _add_radial_point(_outer_radius, _right_tip)",
        "        _add_radial_point(_root_radius, _right_root)",
        "        _add_arc(_root_radius, _right_root, _next_left_root, max(1, _samples // 3))",
        "def _build_straight_points():",
        "    _tooth_angle = 2.0 * math.pi / _teeth",
        "    _backlash_angle = _backlash / _pitch_radius",
        "    _half_width = max(_tooth_angle * 0.16, _tooth_angle * 0.25 - _backlash_angle / 2.0)",
        "    for _tooth in range(_teeth):",
        "        _theta = 2.0 * math.pi * _tooth / _teeth",
        "        _left = _theta - _half_width",
        "        _right = _theta + _half_width",
        "        _next_left = _theta + _tooth_angle - _half_width",
        "        _add_radial_point(_root_radius, _left)",
        "        _add_radial_point(_outer_radius, _left)",
        "        _add_radial_point(_outer_radius, _right)",
        "        _add_radial_point(_root_radius, _right)",
        "        _add_arc(_root_radius, _right, _next_left, max(1, _samples // 3))",
        "def _smooth_tooth_radius(_local_angle, _half_angle, _kind):",
        "    _x = min(1.0, abs(_local_angle) / _half_angle)",
        "    _shape = 0.5 + 0.5 * math.cos(math.pi * _x)",
        "    return _root_radius + (_outer_radius - _root_radius) * _shape",
        "def _build_cycloidal_points():",
        "    _tooth_angle = 2.0 * math.pi / _teeth",
        "    _steps = max(8, _samples * 2)",
        "    for _tooth in range(_teeth):",
        "        _theta = 2.0 * math.pi * _tooth / _teeth",
        "        for _sample in range(_steps):",
        "            _frac = _sample / float(_steps)",
        "            _local = -_tooth_angle / 2.0 + _tooth_angle * _frac",
        "            _angle = _theta + _local",
        "            _radius = _smooth_tooth_radius(_local, _tooth_angle / 2.0, 'cycloidal')",
        "            _add_radial_point(_radius, _angle)",
        "def _build_circular_arc_points():",
        "    _tooth_angle = 2.0 * math.pi / _teeth",
        "    _half = _tooth_angle * 0.34",
        "    _steps = max(6, _samples)",
        "    _x1 = _root_radius * math.cos(_half)",
        "    _y1 = _root_radius * math.sin(_half)",
        "    _denom = 2.0 * (_x1 - _outer_radius)",
        "    _center_x = (_root_radius * _root_radius - _outer_radius * _outer_radius) / _denom",
        "    _arc_radius = abs(_outer_radius - _center_x)",
        "    _a1 = math.atan2(-_y1, _x1 - _center_x)",
        "    _a2 = math.atan2(_y1, _x1 - _center_x)",
        "    for _tooth in range(_teeth):",
        "        _theta = 2.0 * math.pi * _tooth / _teeth",
        "        for _sample in range(_steps + 1):",
        "            _a = _a1 + (_a2 - _a1) * _sample / float(_steps)",
        "            _x = _center_x + _arc_radius * math.cos(_a)",
        "            _y = _arc_radius * math.sin(_a)",
        "            _rx, _ry = _rotate(_x, _y, _theta)",
        "            _add_point(_rx, _ry)",
        "        _right_root = _theta + _half",
        "        _next_left_root = _theta + _tooth_angle - _half",
        "        _add_arc(_root_radius, _right_root, _next_left_root, max(2, _samples // 2))",
        "def _build_pin_points():",
        "    _tooth_angle = 2.0 * math.pi / _teeth",
        "    _hub_radius = max(_pitch_radius - 0.75 * _module, _module * 0.4)",
        "    _pin_radius = min(_module * 0.55, _hub_radius * math.sin(_tooth_angle * 0.34))",
        "    _pin_radius = max(_pin_radius, _module * 0.18)",
        "    _pin_center_radius = _hub_radius + _pin_radius * 0.62",
        "    _steps = max(16, _samples * 3)",
        "    for _tooth in range(_teeth):",
        "        _theta = 2.0 * math.pi * _tooth / _teeth",
        "        for _sample in range(_steps):",
        "            _local = -_tooth_angle / 2.0 + _tooth_angle * _sample / float(_steps)",
        "            _radius = _hub_radius",
        "            _perp = abs(_pin_center_radius * math.sin(_local))",
        "            if _perp < _pin_radius:",
        "                _along = _pin_center_radius * math.cos(_local)",
        "                _radius = max(_radius, _along + math.sqrt(_pin_radius * _pin_radius - _perp * _perp))",
        "            _add_radial_point(_radius, _theta + _local)",
        "if _tooth_profile == 'involute':",
        "    _build_involute_points()",
        "elif _tooth_profile == 'trapezoid':",
        "    _build_trapezoid_points()",
        "elif _tooth_profile == 'straight':",
        "    _build_straight_points()",
        "elif _tooth_profile == 'cycloidal':",
        "    _build_cycloidal_points()",
        "elif _tooth_profile == 'circular_arc':",
        "    _build_circular_arc_points()",
        "else:",
        "    _build_pin_points()",
        "if (_points[0] - _points[-1]).Length > 1e-7:",
        "    _points.append(_points[0])",
        "_profile_indices = []",
        "for _idx in range(len(_points) - 1):",
        "    _p1 = _points[_idx]",
        "    _p2 = _points[_idx + 1]",
        "    if (_p2 - _p1).Length <= 1e-7:",
        "        continue",
        "    _geo = _sk.addGeometry(Part.LineSegment(_p1, _p2), False)",
        "    _profile_indices.append(_geo)",
        "    if len(_profile_indices) > 1:",
        "        _sk.addConstraint(",
        "            Sketcher.Constraint('Coincident', _profile_indices[-2], 2, _profile_indices[-1], 1)",
        "        )",
        "if len(_profile_indices) > 1:",
        "    _sk.addConstraint(Sketcher.Constraint('Coincident', _profile_indices[-1], 2, _profile_indices[0], 1))",
        "_construction_radii = [",
        "    ('RootRadius', _root_radius),",
        "    ('BaseRadius', _base_radius),",
        "    ('PitchRadius', _pitch_radius),",
        "    ('OuterRadius', _outer_radius),",
        "]",
        "for _label, _radius in _construction_radii:",
        "    _circle_idx = _sk.addGeometry(",
        "        Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), _radius),",
        "        True,",
        "    )",
        "    try:",
        "        _sk.addConstraint(Sketcher.Constraint('Radius', _circle_idx, _radius))",
        "        _sk.addConstraint(Sketcher.Constraint('Coincident', _circle_idx, 3, -1, 1))",
        "    except Exception:",
        "        pass",
        "if _bore_diameter > 0:",
        "    _bore_idx = _sk.addGeometry(",
        "        Part.Circle(FreeCAD.Vector(0, 0, 0), FreeCAD.Vector(0, 0, 1), _bore_diameter / 2.0),",
        "        False,",
        "    )",
        "    try:",
        "        _sk.addConstraint(Sketcher.Constraint('Radius', _bore_idx, _bore_diameter / 2.0))",
        "        _sk.addConstraint(Sketcher.Constraint('Coincident', _bore_idx, 3, -1, 1))",
        "    except Exception:",
        "        pass",
        "try:",
        "    _sk.solve()",
        "except Exception:",
        "    pass",
        f"_pad = _body.newObject('PartDesign::Pad', {gear_name!r})",
        "_pad.Profile = (_sk, [''])",
        "_pad.Length = _width",
        *_partdesign_extrusion_helper_code(),
        *_partdesign_bool_property_helper_code(),
        "_set_extrusion_symmetric(_pad, False)",
        "_set_feature_bool(_pad, ('Reversed',), False)",
        "_sk.Visibility = False",
        "_doc.recompute()",
        "print('body_name=' + _body.Name)",
        "print('sketch_name=' + _sk.Name)",
        "print('pad_name=' + _pad.Name)",
        "print('profile_segments=' + str(len(_profile_indices)))",
        "print('teeth=' + str(_teeth))",
        "print('module=' + str(_module))",
        "print('tooth_profile=' + _tooth_profile)",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Spur gear '{gear_name}' sketch and pad created", "Failed to create spur gear")


def recompute_document_operation(freecad: FreeCADConnection, doc_name: str) -> ToolResponse:
    code = f"import FreeCAD\n_d=FreeCAD.getDocument({doc_name!r})\nif not _d: raise RuntimeError('not found')\n_d.recompute()\nprint('recomputed')"
    return _run_code(freecad, True, code,
                     f"Document '{doc_name}' recomputed", "Failed to recompute")


def undo_operation(freecad: FreeCADConnection, doc_name: str) -> ToolResponse:
    code = f"import FreeCAD\n_d=FreeCAD.getDocument({doc_name!r})\nif not _d: raise RuntimeError('not found')\n_d.undo()\nprint('undo done')"
    return _run_code(freecad, True, code,
                     f"Undo performed on '{doc_name}'", "Failed to undo")


def redo_operation(freecad: FreeCADConnection, doc_name: str) -> ToolResponse:
    code = f"import FreeCAD\n_d=FreeCAD.getDocument({doc_name!r})\nif not _d: raise RuntimeError('not found')\n_d.redo()\nprint('redo done')"
    return _run_code(freecad, True, code,
                     f"Redo performed on '{doc_name}'", "Failed to redo")


# ---------------------------------------------------------------------------
# Flat geometry helpers — each calls sketch_add_geometry_operation with one item
# ---------------------------------------------------------------------------

def sketch_add_line_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str,
    x1: float, y1: float, x2: float, y2: float,
    construction: bool = False,
) -> ToolResponse:
    lines = [
        "import FreeCAD, Part",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        f"_sk = _doc.getObject({sketch_name!r})",
        "if not _sk: raise RuntimeError('Sketch not found')",
        f"_idx = _sk.addGeometry(Part.LineSegment(FreeCAD.Vector({x1},{y1},0),FreeCAD.Vector({x2},{y2},0)),{'True' if construction else 'False'})",
        "_doc.recompute()",
        "print('geometry_index=' + str(_idx))",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Line added to '{sketch_name}'", "Failed to add line")


def sketch_add_circle_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str,
    cx: float, cy: float, radius: float,
    construction: bool = False,
) -> ToolResponse:
    lines = [
        "import FreeCAD, Part",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        f"_sk = _doc.getObject({sketch_name!r})",
        "if not _sk: raise RuntimeError('Sketch not found')",
        f"_idx = _sk.addGeometry(Part.Circle(FreeCAD.Vector({cx},{cy},0),FreeCAD.Vector(0,0,1),{radius}),{'True' if construction else 'False'})",
        "_doc.recompute()",
        "print('geometry_index=' + str(_idx))",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Circle added to '{sketch_name}'", "Failed to add circle")


def sketch_add_arc_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str,
    cx: float, cy: float, radius: float,
    start_angle: float, end_angle: float,
    construction: bool = False,
) -> ToolResponse:
    lines = [
        "import FreeCAD, Part, math",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        f"_sk = _doc.getObject({sketch_name!r})",
        "if not _sk: raise RuntimeError('Sketch not found')",
        f"_circ = Part.Circle(FreeCAD.Vector({cx},{cy},0),FreeCAD.Vector(0,0,1),{radius})",
        f"_idx = _sk.addGeometry(Part.ArcOfCircle(_circ,math.radians({start_angle}),math.radians({end_angle})),{'True' if construction else 'False'})",
        "_doc.recompute()",
        "print('geometry_index=' + str(_idx))",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Arc added to '{sketch_name}'", "Failed to add arc")


def sketch_add_rectangle_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str,
    x1: float, y1: float, x2: float, y2: float,
    construction: bool = False,
) -> ToolResponse:
    c = "True" if construction else "False"
    lines = [
        "import FreeCAD, Part",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        f"_sk = _doc.getObject({sketch_name!r})",
        "if not _sk: raise RuntimeError('Sketch not found')",
        "_idxs = []",
        f"for _p1,_p2 in [(({x1},{y1}),({x2},{y1})),(({x2},{y1}),({x2},{y2})),(({x2},{y2}),({x1},{y2})),(({x1},{y2}),({x1},{y1}))]:",
        f"    _idxs.append(_sk.addGeometry(Part.LineSegment(FreeCAD.Vector(_p1[0],_p1[1],0),FreeCAD.Vector(_p2[0],_p2[1],0)),{c}))",
        "_doc.recompute()",
        "print('indices=' + str(_idxs))",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"Rectangle added to '{sketch_name}'", "Failed to add rectangle")


# ---------------------------------------------------------------------------
# Flat constraint helpers
# ---------------------------------------------------------------------------

def _run_constraint(freecad, only_text_feedback, doc_name, sketch_name, c_dict):
    lines = [
        "import FreeCAD, Sketcher",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        f"_sk = _doc.getObject({sketch_name!r})",
        "if not _sk: raise RuntimeError('Sketch not found')",
        _constraint_line(c_dict),
        "_doc.recompute()",
        "print('" + c_dict["type"] + " constraint added')",
    ]
    return _run_code(freecad, only_text_feedback, "\n".join(lines),
                     f"{c_dict['type']} constraint added to '{sketch_name}'",
                     "Failed to add constraint")


def sketch_constrain_coincident_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str,
    geo1: int, pos1: int, geo2: int, pos2: int,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Coincident", "geo1": geo1, "pos1": pos1, "geo2": geo2, "pos2": pos2})


def sketch_constrain_horizontal_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str, geo: int,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Horizontal", "geo": geo})


def sketch_constrain_vertical_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str, geo: int,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Vertical", "geo": geo})


def sketch_constrain_distance_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str,
    geo: int, value: float, pos: int | None = None,
) -> ToolResponse:
    c: dict = {"type": "Distance", "geo": geo, "value": value}
    if pos is not None:
        c["pos"] = pos
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name, c)


def sketch_constrain_radius_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str, geo: int, value: float,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Radius", "geo": geo, "value": value})


def sketch_constrain_equal_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str, geo1: int, geo2: int,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Equal", "geo1": geo1, "geo2": geo2})


def sketch_constrain_parallel_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str, geo1: int, geo2: int,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Parallel", "geo1": geo1, "geo2": geo2})


def sketch_constrain_perpendicular_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str, geo1: int, geo2: int,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Perpendicular", "geo1": geo1, "geo2": geo2})


def sketch_constrain_tangent_operation(
    freecad: FreeCADConnection, only_text_feedback: bool,
    doc_name: str, sketch_name: str, geo1: int, geo2: int,
) -> ToolResponse:
    return _run_constraint(freecad, only_text_feedback, doc_name, sketch_name,
                           {"type": "Tangent", "geo1": geo1, "geo2": geo2})


# ---------------------------------------------------------------------------
# Introspection / session hygiene
# ---------------------------------------------------------------------------

def get_recompute_log_operation(freecad: FreeCADConnection, doc_name: str) -> ToolResponse:
    code = "\n".join([
        "import FreeCAD, json",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        "if not _doc: raise RuntimeError('Document not found')",
        "_results = []",
        "for _o in _doc.Objects:",
        "    try:",
        "        _st = list(getattr(_o, 'State', []))",
        "        _results.append({'name': _o.Name, 'label': getattr(_o, 'Label', _o.Name), 'type': getattr(_o, 'TypeId', ''), 'state': _st, 'valid': not any(s in ('Invalid','Error') for s in _st)})",
        "    except Exception as _e:",
        "        _results.append({'name': getattr(_o, 'Name', '?'), 'error': str(_e)})",
        "print(json.dumps({'total': len(_doc.Objects), 'objects': _results}))",
    ])
    return _run_code(freecad, True, code,
                     f"Recompute log for '{doc_name}'", "Failed to get recompute log")


def get_sketch_diagnostics_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    sketch_name: str,
) -> ToolResponse:
    code = "\n".join([
        "import FreeCAD, json",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        "if not _doc: raise RuntimeError('Document not found')",
        f"_sk = _doc.getObject({sketch_name!r})",
        "if not _sk: raise RuntimeError('Sketch not found')",
        "_info = {",
        "    'name': _sk.Name,",
        "    'geometry_count': len(_sk.Geometry) if hasattr(_sk, 'Geometry') else 0,",
        "    'constraint_count': len(_sk.Constraints) if hasattr(_sk, 'Constraints') else 0,",
        "    'state': list(getattr(_sk, 'State', [])),",
        "    'conflicting': list(getattr(_sk, 'ConflictingConstraints', [])),",
        "    'redundant': list(getattr(_sk, 'RedundantConstraints', [])),",
        "    'malformed': list(getattr(_sk, 'MalformedConstraints', [])),",
        "    'solver_message': getattr(_sk, 'SolverMessage', None),",
        "    'is_closed': None,",
        "}",
        "try:",
        "    _shape = _sk.Shape",
        "    if _shape and not _shape.isNull(): _info['is_closed'] = _shape.isClosed()",
        "except Exception: pass",
        "print(json.dumps(_info))",
    ])
    return _run_code(freecad, True, code,
                     f"Sketch diagnostics for '{sketch_name}'", "Failed to get sketch diagnostics")


def close_document_operation(freecad: FreeCADConnection, doc_name: str) -> ToolResponse:
    code = f"import FreeCAD\nFreeCAD.closeDocument({doc_name!r})\nprint('Document closed')"
    return _run_code(freecad, True, code,
                     f"Document '{doc_name}' closed", "Failed to close document")
