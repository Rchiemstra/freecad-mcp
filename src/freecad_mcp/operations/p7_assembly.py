"""
P7 - Assembly-aware references, sketch inspection, path wires, and pipe sweeps.
"""
from __future__ import annotations

import logging
from typing import Any

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse, add_screenshot_if_available, text_response
from ..template_resources import render_template_text

logger = logging.getLogger("FreeCADMCPserver")


def _extract_execute_output(message: str) -> str:
    marker = "Output:"
    if marker in message:
        return message.split(marker, 1)[1].strip()
    return message.strip()


def _run_json_code(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    code: str,
    fail_prefix: str,
    *,
    screenshot: bool = False,
) -> ToolResponse:
    try:
        res = freecad.execute_code(code)
        image = freecad.get_active_screenshot() if screenshot else None
        if res.get("success"):
            output = _extract_execute_output(res.get("message", ""))
            errors = res.get("recompute_errors", [])
            if errors and output.endswith("}"):
                # Keep the response JSON-first without parsing possibly large payloads.
                output += "\n" + str({"recompute_errors": errors})
            return add_screenshot_if_available(text_response(output), image, only_text_feedback)
        return text_response(f"{fail_prefix}: {res.get('error', res.get('message', 'unknown error'))}")
    except Exception as exc:
        logger.error("%s: %s", fail_prefix, exc)
        return text_response(f"{fail_prefix}: {exc}")


def _validate_if_exists(if_exists: str) -> ToolResponse | None:
    if if_exists not in {"error", "skip", "replace"}:
        return text_response("if_exists must be one of: error, skip, replace")
    return None


def _doc_preamble(doc_name: str) -> list[str]:
    return [
        "import FreeCAD, Part, math, json",
        f"_doc = FreeCAD.getDocument({doc_name!r})",
        f"if not _doc: raise RuntimeError({f'Document {doc_name!r} not found'!r})",
    ]


def _shared_helpers() -> list[str]:
    return [
        "def _vec(_v):",
        "    if _v is None: return None",
        "    return {'x': round(float(_v.x), 6), 'y': round(float(_v.y), 6), 'z': round(float(_v.z), 6)}",
        "def _bb(_bbx):",
        "    return {",
        "        'xmin': round(float(_bbx.XMin), 6), 'ymin': round(float(_bbx.YMin), 6), 'zmin': round(float(_bbx.ZMin), 6),",
        "        'xmax': round(float(_bbx.XMax), 6), 'ymax': round(float(_bbx.YMax), 6), 'zmax': round(float(_bbx.ZMax), 6),",
        "        'dx': round(float(_bbx.XLength), 6), 'dy': round(float(_bbx.YLength), 6), 'dz': round(float(_bbx.ZLength), 6),",
        "    }",
        "def _parent_of(_obj):",
        "    for _candidate in getattr(_obj, 'InList', []):",
        "        try:",
        "            if _obj in getattr(_candidate, 'Group', []): return _candidate",
        "        except Exception:",
        "            pass",
        "    for _candidate in _doc.Objects:",
        "        try:",
        "            if _obj in getattr(_candidate, 'Group', []): return _candidate",
        "        except Exception:",
        "            pass",
        "    return None",
        "def _add_to_container(_container, _obj):",
        "    if _container is None: return",
        "    if hasattr(_container, 'addObject'):",
        "        _container.addObject(_obj)",
        "        return",
        "    if hasattr(_container, 'Group'):",
        "        _grp = list(getattr(_container, 'Group', []))",
        "        if _obj not in _grp:",
        "            _grp.append(_obj)",
        "            _container.Group = _grp",
        "def _remove_from_container(_container, _obj):",
        "    if _container is None: return",
        "    if hasattr(_container, 'removeObject'):",
        "        try:",
        "            _container.removeObject(_obj)",
        "            return",
        "        except Exception:",
        "            pass",
        "    if hasattr(_container, 'Group'):",
        "        _container.Group = [o for o in _container.Group if o != _obj]",
        "def _parse_ref(_ref):",
        "    if ':' in _ref:",
        "        _name, _sub = _ref.split(':', 1)",
        "    else:",
        "        _name, _sub = _ref, ''",
        "    _obj = _doc.getObject(_name)",
        "    if not _obj: raise RuntimeError('Object not found: ' + _name)",
        "    return _obj, _sub",
        "def _subshape(_obj, _sub):",
        "    if not _sub:",
        "        return getattr(_obj, 'Shape', None)",
        "    if _sub.startswith('Face'): return _obj.Shape.Faces[int(_sub[4:]) - 1]",
        "    if _sub.startswith('Edge'): return _obj.Shape.Edges[int(_sub[4:]) - 1]",
        "    if _sub.startswith('Vertex'): return _obj.Shape.Vertexes[int(_sub[6:]) - 1]",
        "    return getattr(_obj, 'Shape', None)",
        "def _global_placement(_obj):",
        "    try:",
        "        return _obj.getGlobalPlacement()",
        "    except Exception:",
        "        return getattr(_obj, 'Placement', FreeCAD.Placement())",
        "def _global_boundbox(_obj):",
        "    _shape = getattr(_obj, 'Shape', None)",
        "    if _shape is None or _shape.isNull(): return None",
        "    _copy = _shape.copy()",
        "    _pl = _global_placement(_obj)",
        "    try:",
        "        _copy.Placement = _pl.multiply(getattr(_copy, 'Placement', FreeCAD.Placement()))",
        "    except Exception:",
        "        try: _copy.Placement = _pl",
        "        except Exception: pass",
        "    return _copy.BoundBox",
        "def _bbox_delta(_a, _b):",
        "    if _a is None or _b is None: return None",
        "    _vals = ['XMin','YMin','ZMin','XMax','YMax','ZMax']",
        "    return max(abs(float(getattr(_a, _k)) - float(getattr(_b, _k))) for _k in _vals)",
        "def _safe_check(_shape):",
        "    try:",
        "        _shape.check(False)",
        "        return True, []",
        "    except Exception as _err:",
        "        return False, [str(_err)]",
    ]


def get_document_tree_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    root_filter: str | None = None,
    max_depth: int = 4,
    include: list[str] | None = None,
    include_properties: list[str] | None = None,
    selected_nodes: list[str] | None = None,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + _shared_helpers() + [
        f"_root_filter = {root_filter!r}",
        f"_max_depth = {max_depth!r}",
        f"_include = {include!r} or ['Name', 'Label', 'TypeId', 'Visibility', 'State']",
        f"_include_properties = {include_properties!r} or []",
        f"_selected = set({selected_nodes!r} or [])",
        "def _children(_obj):",
        "    return list(getattr(_obj, 'Group', []) or [])",
        "def _field(_obj, _name):",
        "    if _name == 'Name': return _obj.Name",
        "    if _name == 'Label': return getattr(_obj, 'Label', _obj.Name)",
        "    if _name == 'TypeId': return getattr(_obj, 'TypeId', '')",
        "    if _name == 'Visibility':",
        "        try: return bool(_obj.ViewObject.Visibility)",
        "        except Exception: return None",
        "    if _name == 'State': return list(getattr(_obj, 'State', []))",
        "    return str(getattr(_obj, _name, ''))",
        "def _node(_obj, _depth, _seen):",
        "    _data = {k: _field(_obj, k) for k in _include}",
        "    if _include_properties and ((not _selected) or _obj.Name in _selected or getattr(_obj, 'Label', '') in _selected):",
        "        _props = {}",
        "        for _prop in _include_properties:",
        "            try: _props[_prop] = str(getattr(_obj, _prop))",
        "            except Exception as _err: _props[_prop] = '<error: ' + str(_err) + '>'",
        "        _data['Properties'] = _props",
        "    if _depth < _max_depth and _obj.Name not in _seen:",
        "        _seen.add(_obj.Name)",
        "        _data['children'] = [_node(_child, _depth + 1, _seen) for _child in _children(_obj)]",
        "    return _data",
        "_contained = set()",
        "for _obj in _doc.Objects:",
        "    for _child in _children(_obj): _contained.add(_child.Name)",
        "_roots = [o for o in _doc.Objects if o.Name not in _contained]",
        "if _root_filter:",
        "    _roots = [o for o in _doc.Objects if _root_filter in o.Name or _root_filter in getattr(o, 'Label', '')]",
        "_result = {'doc_name': _doc.Name, 'root_filter': _root_filter, 'max_depth': _max_depth, 'roots': [_node(o, 0, set()) for o in _roots]}",
        "print(json.dumps(_result, default=str))",
    ]
    return _run_json_code(freecad, True, "\n".join(lines), "Failed to get document tree")


def create_part_container_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    part_name: str,
    parent_container: str | None = None,
    if_exists: str = "error",
) -> ToolResponse:
    invalid = _validate_if_exists(if_exists)
    if invalid:
        return invalid
    lines = _doc_preamble(doc_name) + _shared_helpers() + [
        f"_part_name = {part_name!r}",
        f"_parent_name = {parent_container!r}",
        f"_if_exists = {if_exists!r}",
        "_existing = _doc.getObject(_part_name)",
        "if _existing and _if_exists == 'skip':",
        "    print(json.dumps({'ok': True, 'skipped': True, 'part_name': _existing.Name, 'type': _existing.TypeId}))",
        "else:",
        "    if _existing and _if_exists == 'error': raise RuntimeError('Object already exists: ' + _part_name)",
        "    if _existing and _if_exists == 'replace': _doc.removeObject(_existing.Name)",
        "    _part = _doc.addObject('App::Part', _part_name)",
        "    _parent = _doc.getObject(_parent_name) if _parent_name else None",
        "    if _parent_name and not _parent: raise RuntimeError('Parent container not found: ' + _parent_name)",
        "    _add_to_container(_parent, _part)",
        "    _doc.recompute()",
        "    print(json.dumps({'ok': True, 'part_name': _part.Name, 'label': _part.Label, 'parent_container': getattr(_parent, 'Name', None)}))",
    ]
    return _run_json_code(
        freecad,
        only_text_feedback,
        "\n".join(lines),
        "Failed to create part container",
        screenshot=True,
    )


def move_object_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    obj_name: str,
    target_container: str,
    remove_from_old_parent: bool = True,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + _shared_helpers() + [
        f"_obj_name = {obj_name!r}",
        f"_target_name = {target_container!r}",
        f"_remove_old = {remove_from_old_parent!r}",
        "_obj = _doc.getObject(_obj_name)",
        "if not _obj: raise RuntimeError('Object not found: ' + _obj_name)",
        "_target = _doc.getObject(_target_name)",
        "if not _target: raise RuntimeError('Target container not found: ' + _target_name)",
        "_old = []",
        "if _remove_old:",
        "    for _parent in list(getattr(_obj, 'InList', [])):",
        "        try:",
        "            if _obj in getattr(_parent, 'Group', []):",
        "                _old.append(_parent.Name)",
        "                _remove_from_container(_parent, _obj)",
        "        except Exception:",
        "            pass",
        "_add_to_container(_target, _obj)",
        "_doc.recompute()",
        "print(json.dumps({'ok': True, 'object_name': _obj.Name, 'target_container': _target.Name, 'old_parents': _old}))",
    ]
    return _run_json_code(freecad, only_text_feedback, "\n".join(lines), "Failed to move object", screenshot=True)


def create_subshape_binder_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    binder_name: str,
    source_object: str,
    sub_elements: list[str] | None = None,
    target_body: str | None = None,
    target_container: str | None = None,
    relative: bool = False,
    sync_placement: bool = True,
    if_exists: str = "error",
) -> ToolResponse:
    invalid = _validate_if_exists(if_exists)
    if invalid:
        return invalid
    binder_code = render_template_text(
        "p7_assembly/create_subshape_binder.py.txt",
        binder_name=repr(binder_name),
        source_name=repr(source_object),
        subs=repr(sub_elements),
        target_body_name=repr(target_body),
        target_container_name=repr(target_container),
        relative=repr(relative),
        sync_placement=repr(sync_placement),
        if_exists=repr(if_exists),
    )
    lines = _doc_preamble(doc_name) + _shared_helpers() + binder_code.strip().splitlines()
    return _run_json_code(freecad, only_text_feedback, "\n".join(lines), "Failed to create subshape binder", screenshot=True)


def create_datum_plane_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    plane_name: str,
    body_name: str,
    mode: str,
    source_ref: str | None = None,
    face_a: str | None = None,
    face_b: str | None = None,
    offset_along_normal: list[float] | None = None,
    map_mode: str = "FlatFace",
    if_exists: str = "error",
) -> ToolResponse:
    invalid = _validate_if_exists(if_exists)
    if invalid:
        return invalid
    lines = _doc_preamble(doc_name) + _shared_helpers() + [
        f"_plane_name = {plane_name!r}",
        f"_body_name = {body_name!r}",
        f"_mode = {mode!r}",
        f"_source_ref = {source_ref!r}",
        f"_face_a = {face_a!r}",
        f"_face_b = {face_b!r}",
        f"_offset = {offset_along_normal!r} or [0, 0, 0]",
        f"_map_mode = {map_mode!r}",
        f"_if_exists = {if_exists!r}",
        "_body = _doc.getObject(_body_name)",
        "if not _body: raise RuntimeError('Body not found: ' + _body_name)",
        "_existing = _doc.getObject(_plane_name)",
        "if _existing and _if_exists == 'skip':",
        "    print(json.dumps({'ok': True, 'skipped': True, 'plane_name': _existing.Name}))",
        "else:",
        "    if _existing and _if_exists == 'error': raise RuntimeError('Object already exists: ' + _plane_name)",
        "    if _existing and _if_exists == 'replace': _doc.removeObject(_existing.Name)",
        "    _plane = _body.newObject('PartDesign::Plane', _plane_name)",
        "    _support_ref = _source_ref",
        "    _attachment_base = FreeCAD.Vector(float(_offset[0]), float(_offset[1]), float(_offset[2]))",
        "    if _mode == 'midpoint_between_faces':",
        "        if not _face_a or not _face_b: raise RuntimeError('midpoint_between_faces requires face_a and face_b')",
        "        _obj_a, _sub_a = _parse_ref(_face_a)",
        "        _obj_b, _sub_b = _parse_ref(_face_b)",
        "        _shape_a = _subshape(_obj_a, _sub_a)",
        "        _shape_b = _subshape(_obj_b, _sub_b)",
        "        _ca = _shape_a.CenterOfMass",
        "        _cb = _shape_b.CenterOfMass",
        "        _mid = (_ca + _cb).multiply(0.5)",
        "        _attachment_base = (_mid - _ca) + _attachment_base",
        "        _plane.AttachmentSupport = [(_obj_a, _sub_a)]",
        "    elif _mode in ('offset_from_face', 'plane_from_binder_face', 'between_parallel_planes'):",
        "        if not _support_ref: raise RuntimeError(_mode + ' requires source_ref')",
        "        _obj, _sub = _parse_ref(_support_ref)",
        "        _plane.AttachmentSupport = [(_obj, _sub)]",
        "    elif _mode == 'through_point':",
        "        if _source_ref:",
        "            _obj, _sub = _parse_ref(_source_ref)",
        "            _plane.AttachmentSupport = [(_obj, _sub)]",
        "    else:",
        "        raise RuntimeError('Unsupported datum plane mode: ' + _mode)",
        "    _plane.MapMode = _map_mode",
        "    _plane.AttachmentOffset = FreeCAD.Placement(_attachment_base, FreeCAD.Rotation())",
        "    _doc.recompute()",
        "    _normal = None",
        "    try: _normal = _vec(_plane.Shape.Surface.Axis)",
        "    except Exception: pass",
        "    print(json.dumps({'ok': True, 'plane_name': _plane.Name, 'body_name': _body.Name, 'mode': _mode, 'map_mode': _map_mode, 'attachment_offset': _vec(_attachment_base), 'normal': _normal}))",
    ]
    return _run_json_code(freecad, only_text_feedback, "\n".join(lines), "Failed to create datum plane", screenshot=True)


def get_sketch_geometry_operation(
    freecad: FreeCADConnection,
    doc_name: str,
    sketch_name: str,
    include_constraints: bool = True,
    include_external: bool = True,
    global_coords: bool = True,
) -> ToolResponse:
    lines = _doc_preamble(doc_name) + _shared_helpers() + [
        f"_sketch_name = {sketch_name!r}",
        f"_include_constraints = {include_constraints!r}",
        f"_include_external = {include_external!r}",
        f"_global_coords = {global_coords!r}",
        "_sk = _doc.getObject(_sketch_name)",
        "if not _sk: raise RuntimeError('Sketch not found: ' + _sketch_name)",
        "def _maybe_global(_v):",
        "    if not _global_coords: return _v",
        "    try: return _sk.getGlobalPlacement().multVec(_v)",
        "    except Exception: return _sk.Placement.multVec(_v)",
        "def _construction(_idx, _geo):",
        "    try:",
        "        import Sketcher",
        "        return bool(Sketcher.GeometryFacade.getConstruction(_geo))",
        "    except Exception:",
        "        try: return bool(_sk.getConstruction(_idx))",
        "        except Exception: return False",
        "def _geo_info(_idx, _geo):",
        "    _info = {'index': _idx, 'type': type(_geo).__name__, 'construction': _construction(_idx, _geo)}",
        "    for _name in ('StartPoint', 'EndPoint', 'Center', 'Location'):",
        "        if hasattr(_geo, _name):",
        "            _val = getattr(_geo, _name)",
        "            _info[_name[0].lower() + _name[1:] + '_local'] = _vec(_val)",
        "            _info[_name[0].lower() + _name[1:] + '_global'] = _vec(_maybe_global(_val))",
        "    if hasattr(_geo, 'Radius'): _info['radius'] = round(float(_geo.Radius), 6)",
        "    if hasattr(_geo, 'MajorRadius'): _info['major_radius'] = round(float(_geo.MajorRadius), 6)",
        "    if hasattr(_geo, 'MinorRadius'): _info['minor_radius'] = round(float(_geo.MinorRadius), 6)",
        "    return _info",
        "_result = {'ok': True, 'sketch_name': _sk.Name, 'geometry_count': len(getattr(_sk, 'Geometry', [])), 'geometry': [_geo_info(i, g) for i, g in enumerate(getattr(_sk, 'Geometry', []))]}",
        "if _include_constraints:",
        "    _constraints = []",
        "    for _idx, _c in enumerate(getattr(_sk, 'Constraints', [])):",
        "        _constraints.append({",
        "            'index': _idx, 'type': str(getattr(_c, 'Type', '')),",
        "            'first': getattr(_c, 'First', None), 'first_pos': getattr(_c, 'FirstPos', None),",
        "            'second': getattr(_c, 'Second', None), 'second_pos': getattr(_c, 'SecondPos', None),",
        "            'third': getattr(_c, 'Third', None), 'third_pos': getattr(_c, 'ThirdPos', None),",
        "            'value': getattr(_c, 'Value', None),",
        "        })",
        "    _result['constraints'] = _constraints",
        "if _include_external:",
        "    _external = []",
        "    for _idx, _entry in enumerate(getattr(_sk, 'ExternalGeometry', [])):",
        "        try:",
        "            _obj, _subs = _entry",
        "            _external.append({'index': _idx, 'negative_index': -3 - _idx, 'object': _obj.Name, 'sub_elements': list(_subs) if isinstance(_subs, (list, tuple)) else [_subs]})",
        "        except Exception as _err:",
        "            _external.append({'index': _idx, 'error': str(_err)})",
        "    _result['external_geometry'] = _external",
        "print(json.dumps(_result, default=str))",
    ]
    return _run_json_code(freecad, True, "\n".join(lines), "Failed to get sketch geometry")


def sketch_add_external_projection_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    sketch_name: str,
    source_ref: str,
    projection_mode: str = "auto",
    defining: bool = False,
) -> ToolResponse:
    if projection_mode not in {"auto", "edge", "face", "point"}:
        return text_response("projection_mode must be one of: auto, edge, face, point")
    lines = _doc_preamble(doc_name) + _shared_helpers() + [
        f"_sketch_name = {sketch_name!r}",
        f"_source_ref = {source_ref!r}",
        f"_projection_mode = {projection_mode!r}",
        f"_defining = {defining!r}",
        "_sk = _doc.getObject(_sketch_name)",
        "if not _sk: raise RuntimeError('Sketch not found: ' + _sketch_name)",
        "_src, _sub = _parse_ref(_source_ref)",
        "_sk_parent = _parent_of(_sk)",
        "_src_parent = _parent_of(_src)",
        "if _sk_parent is not None and _src_parent is not None and _sk_parent != _src_parent:",
        "    print(json.dumps({'ok': False, 'error': 'binder and sketch must share parent container', 'sketch_parent': _sk_parent.Name, 'source_parent': _src_parent.Name}))",
        "else:",
        "    _bad_support = False",
        "    if getattr(_src, 'TypeId', '') == 'PartDesign::SubShapeBinder':",
        "        for _support in getattr(_src, 'Support', []):",
        "            try:",
        "                _support_obj = _support[0]",
        "                if getattr(_support_obj, 'TypeId', '') == 'Sketcher::SketchObject': _bad_support = True",
        "            except Exception: pass",
        "    if _bad_support:",
        "        print(json.dumps({'ok': False, 'error': 'binder Support must reference Part::Feature, not Sketcher::SketchObject'}))",
        "    else:",
        "        _candidate_edges = []",
        "        try: _candidate_edges = [_src.Name + ':Edge' + str(i + 1) for i in range(len(_src.Shape.Edges))]",
        "        except Exception: pass",
        "        _mode = _projection_mode",
        "        if _mode == 'auto':",
        "            if _sub.startswith('Edge'): _mode = 'edge'",
        "            elif _sub.startswith('Vertex'): _mode = 'point'",
        "            elif _sub.startswith('Face'): _mode = 'face'",
        "        _parallel = True",
        "        if _sub.startswith('Face'):",
        "            try:",
        "                _face = _subshape(_src, _sub)",
        "                _u0, _u1, _v0, _v1 = _face.ParameterRange",
        "                _face_normal = _face.normalAt((_u0 + _u1) * 0.5, (_v0 + _v1) * 0.5)",
        "                _sk_normal = _global_placement(_sk).Rotation.multVec(FreeCAD.Vector(0, 0, 1))",
        "                _parallel = abs(abs(_face_normal.normalize().dot(_sk_normal.normalize())) - 1.0) < 1e-3",
        "            except Exception:",
        "                _parallel = True",
        "        if _sub.startswith('Face') and _mode == 'face' and not _parallel:",
        "            print(json.dumps({'ok': False, 'error': 'datum normal not parallel to face; use edge projection', 'candidate_edges': _candidate_edges}))",
        "        else:",
        "            _before = len(getattr(_sk, 'ExternalGeometry', []))",
        "            _idx = _sk.addExternal(_src, _sub, bool(_defining))",
        "            _doc.recompute()",
        "            _after = len(getattr(_sk, 'ExternalGeometry', []))",
        "            print(json.dumps({'ok': _idx >= 0, 'sketch_name': _sk.Name, 'source_ref': _source_ref, 'projection_mode': _mode, 'external_index': _idx, 'external_count_before': _before, 'external_count_after': _after}))",
    ]
    return _run_json_code(freecad, only_text_feedback, "\n".join(lines), "Failed to add external projection", screenshot=True)


def build_path_wire_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    wire_name: str,
    segments: list[dict[str, Any]],
    tolerance_mm: float = 0.5,
    container: str | None = None,
    if_exists: str = "error",
) -> ToolResponse:
    invalid = _validate_if_exists(if_exists)
    if invalid:
        return invalid
    lines = _doc_preamble(doc_name) + _shared_helpers() + [
        f"_wire_name = {wire_name!r}",
        f"_segments = {segments!r}",
        f"_tol = {tolerance_mm!r}",
        f"_container_name = {container!r}",
        f"_if_exists = {if_exists!r}",
        "def _shape_from_sketch_geo(_sketch_name, _geo_index):",
        "    _sk = _doc.getObject(_sketch_name)",
        "    if not _sk: raise RuntimeError('Sketch not found: ' + _sketch_name)",
        "    _geo = _sk.Geometry[int(_geo_index)]",
        "    _shape = _geo.toShape()",
        "    try:",
        "        _shape.Placement = _global_placement(_sk).multiply(getattr(_shape, 'Placement', FreeCAD.Placement()))",
        "    except Exception:",
        "        pass",
        "    if getattr(_shape, 'ShapeType', '') == 'Edge': return _shape",
        "    if len(_shape.Edges) == 1: return _shape.Edges[0]",
        "    raise RuntimeError('Sketch geometry does not resolve to a single edge')",
        "def _endpoint(_edge, _which):",
        "    return _edge.Vertexes[0].Point if _which == 'start' else _edge.Vertexes[-1].Point",
        "_existing = _doc.getObject(_wire_name)",
        "if _existing and _if_exists == 'skip':",
        "    print(json.dumps({'ok': True, 'skipped': True, 'wire_name': _existing.Name}))",
        "else:",
        "    if _existing and _if_exists == 'error': raise RuntimeError('Object already exists: ' + _wire_name)",
        "    if _existing and _if_exists == 'replace': _doc.removeObject(_existing.Name)",
        "    _edges = []",
        "    _gaps = []",
        "    for _seg in _segments:",
        "        if _seg.get('type') == 'bridge':",
        "            if not _edges: raise RuntimeError('bridge segment requires a previous edge')",
        "            _to = _seg.get('to', {})",
        "            _target_edge = _shape_from_sketch_geo(_to['sketch'], _to['geo_index'])",
        "            _target_point = _endpoint(_target_edge, _to.get('end', 'start'))",
        "            _start_point = _endpoint(_edges[-1], 'end')",
        "            _gap = (_target_point - _start_point).Length",
        "            if _gap > _tol: raise RuntimeError('bridge gap %.6f exceeds tolerance %.6f' % (_gap, _tol))",
        "            if _gap > 1e-9: _edges.append(Part.LineSegment(_start_point, _target_point).toShape())",
        "            _gaps.append(round(float(_gap), 6))",
        "        else:",
        "            _edge = _shape_from_sketch_geo(_seg['sketch'], _seg['geo_index'])",
        "            if _seg.get('reverse', False): _edge = _edge.reversed()",
        "            _edges.append(_edge)",
        "    if not _edges: raise RuntimeError('No path segments supplied')",
        "    _groups = Part.sortEdges(_edges, _tol)",
        "    _sorted = _groups[0] if _groups and isinstance(_groups[0], list) else _groups",
        "    _wire = Part.Wire(_sorted)",
        "    _obj = _doc.addObject('Part::Feature', _wire_name)",
        "    _obj.Shape = _wire",
        "    _container = _doc.getObject(_container_name) if _container_name else None",
        "    if _container_name and not _container: raise RuntimeError('Container not found: ' + _container_name)",
        "    _add_to_container(_container, _obj)",
        "    _doc.recompute()",
        "    _ok, _check_errors = _safe_check(_wire)",
        "    print(json.dumps({'ok': True, 'wire_name': _obj.Name, 'edge_count': len(_wire.Edges), 'length_mm': round(float(_wire.Length), 6), 'bridge_gaps_mm': _gaps, 'sort_groups': len(_groups), 'check_ok': _ok, 'check_errors': _check_errors}))",
    ]
    return _run_json_code(freecad, only_text_feedback, "\n".join(lines), "Failed to build path wire", screenshot=True)


def sweep_pipe_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    path_wire: str,
    diameter_mm: float,
    solid_name: str,
    profile_mode: str = "frenet",
    color: list[float] | None = None,
    container: str | None = None,
    if_exists: str = "error",
) -> ToolResponse:
    invalid = _validate_if_exists(if_exists)
    if invalid:
        return invalid
    sweep_code = render_template_text(
        "p7_assembly/sweep_pipe.py.txt",
        path_wire_name=repr(path_wire),
        diameter=repr(diameter_mm),
        solid_name=repr(solid_name),
        profile_mode=repr(profile_mode),
        color=repr(color),
        container_name=repr(container),
        if_exists=repr(if_exists),
    )
    lines = _doc_preamble(doc_name) + _shared_helpers() + sweep_code.strip().splitlines()
    return _run_json_code(freecad, only_text_feedback, "\n".join(lines), "Failed to sweep pipe", screenshot=True)
