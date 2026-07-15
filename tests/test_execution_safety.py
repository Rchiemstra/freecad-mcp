"""Regression tests for GUI-thread execute_code safety checks."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


_MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "addon"
    / "FreeCADMCP"
    / "rpc_server"
    / "execution_safety.py"
)
_SPEC = importlib.util.spec_from_file_location("freecad_mcp_execution_safety", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
find_gui_blocking_risk = _MODULE.find_gui_blocking_risk
classify_execute_code = _MODULE.classify_execute_code
RequestClass = _MODULE.RequestClass


HANGING_SYMMETRY_AUDIT = r'''
sp = S("X90_SpoolWithRails")
spm = sp.transformGeometry(matrix)
dif = sp.cut(spm).Volume + spm.cut(sp).Volume
gh = S("X90_CableGuideHalf")
gm = S("X90_CableGuideMirror")
ghm = gh.transformGeometry(matrix)
dif2 = ghm.cut(gm).Volume + gm.cut(ghm).Volume
'''


def test_blocks_repeated_booleans_on_transformed_shapes_in_read_only_code():
    risk = find_gui_blocking_risk(HANGING_SYMMETRY_AUDIT, read_only=True)
    assert risk is not None
    assert risk.boolean_calls == 4
    assert risk.transform_calls == 2


def test_allows_lightweight_transformed_shape_distance_audit():
    code = "mirrored = shape.transformGeometry(matrix)\nprint(shape.distToShape(mirrored)[0])"
    assert find_gui_blocking_risk(code, read_only=True) is None


def test_allows_single_boolean_in_read_only_code():
    code = "mirrored = shape.transformGeometry(matrix)\nprint(shape.cut(mirrored).Volume)"
    assert find_gui_blocking_risk(code, read_only=True) is None


def test_modeling_payload_is_not_blocked_by_read_only_guard():
    assert find_gui_blocking_risk(HANGING_SYMMETRY_AUDIT, read_only=False) is None


def test_syntax_errors_are_left_for_execute_code_reporting():
    assert find_gui_blocking_risk("if :", read_only=True) is None


def test_mutating_declaration_stays_on_gui_thread():
    assert classify_execute_code("doc.addObject('Part::Feature', 'Box')", read_only=False) == (
        RequestClass.GUI_MUTATION
    )


def test_allowlisted_lightweight_read_stays_on_gui_thread():
    code = "import FreeCAD\ndoc = FreeCAD.getDocument('Model')\nprint(len(doc.Objects))"
    assert classify_execute_code(code, read_only=True) == RequestClass.GUI_LIGHTWEIGHT_READ


def test_known_expensive_analysis_routes_to_worker():
    assert classify_execute_code("print(shape.distToShape(other)[0])", read_only=True) == (
        RequestClass.WORKER_ANALYSIS
    )


def test_expensive_method_alias_routes_to_worker():
    code = "operation = shape.cut\nprint(operation(other).Volume)"
    assert classify_execute_code(code, read_only=True) == RequestClass.WORKER_ANALYSIS


def test_dynamic_method_lookup_fails_safe_to_worker():
    code = "operation = getattr(shape, method_name)\nprint(operation(other))"
    assert classify_execute_code(code, read_only=True) == RequestClass.UNKNOWN


def test_imported_helper_fails_safe_to_worker():
    code = "from custom_analysis import inspect_shape\nprint(inspect_shape(shape))"
    assert classify_execute_code(code, read_only=True) == RequestClass.UNKNOWN


def test_unknown_import_and_syntax_fail_safe_to_worker():
    assert classify_execute_code("import numpy", read_only=True) == RequestClass.UNKNOWN
    assert classify_execute_code("if :", read_only=True) == RequestClass.UNKNOWN


def test_attribute_write_declared_read_only_fails_safe_to_worker():
    assert classify_execute_code("obj.Label = 'changed'", read_only=True) == RequestClass.UNKNOWN
