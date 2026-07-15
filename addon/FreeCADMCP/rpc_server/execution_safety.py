"""Static safety checks for code scheduled on FreeCAD's Qt GUI thread."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from enum import Enum


_BOOLEAN_METHODS = frozenset({"cut", "common", "fuse", "multiCut", "multiFuse"})
_GEOMETRY_TRANSFORM_METHODS = frozenset({"mirror", "transformGeometry"})
_EXPENSIVE_METHODS = frozenset({
    "cut", "common", "fuse", "multiCut", "multiFuse", "section",
    "distToShape", "isValid", "check", "checkGeometry", "removeSplitter",
})
_LIGHTWEIGHT_CALLS = frozenset({
    "print", "len", "getattr", "hasattr", "sorted", "list", "tuple", "dict",
    "set", "str", "float", "int", "bool", "round", "min", "max", "sum",
    "abs", "enumerate", "range", "zip", "any", "all",
})
_LIGHTWEIGHT_METHODS = frozenset({
    "getDocument", "listDocuments", "getObject", "getTypeIdOfProperty",
    "isNull", "isClosed", "dumps", "keys", "values", "items", "get",
})
_LIGHTWEIGHT_IMPORTS = frozenset({"FreeCAD", "json", "math"})


class RequestClass(Enum):
    GUI_MUTATION = "gui_mutation"
    GUI_LIGHTWEIGHT_READ = "gui_lightweight_read"
    WORKER_ANALYSIS = "worker_analysis"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class GuiBlockingRisk:
    boolean_calls: int
    transform_calls: int
    reason: str


def classify_execute_code(code: str, *, read_only: bool) -> RequestClass:
    """Conservatively classify arbitrary code; unknown reads fail safe to worker."""
    if not read_only:
        return RequestClass.GUI_MUTATION
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError:
        return RequestClass.UNKNOWN

    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in _EXPENSIVE_METHODS:
            return RequestClass.WORKER_ANALYSIS

    for node in ast.walk(tree):
        if isinstance(node, (ast.Delete, ast.AugAssign, ast.AnnAssign, ast.NamedExpr)):
            return RequestClass.UNKNOWN
        if isinstance(node, ast.Assign):
            if any(isinstance(target, (ast.Attribute, ast.Subscript)) for target in node.targets):
                return RequestClass.UNKNOWN
        if isinstance(node, ast.Import):
            if any(item.name.split(".")[0] not in _LIGHTWEIGHT_IMPORTS for item in node.names):
                return RequestClass.UNKNOWN
        if isinstance(node, ast.ImportFrom):
            if not node.module or node.module.split(".")[0] not in _LIGHTWEIGHT_IMPORTS:
                return RequestClass.UNKNOWN
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id not in _LIGHTWEIGHT_CALLS:
                    return RequestClass.UNKNOWN
            elif isinstance(node.func, ast.Attribute):
                if node.func.attr not in _LIGHTWEIGHT_METHODS:
                    return RequestClass.UNKNOWN
            else:
                return RequestClass.UNKNOWN
    return RequestClass.GUI_LIGHTWEIGHT_READ


def find_gui_blocking_risk(code: str, *, read_only: bool) -> GuiBlockingRisk | None:
    """Detect read-only transformed-shape boolean audits that can freeze Qt.

    ``execute_code`` is dispatched by a Qt timer and therefore runs on the GUI
    thread. OCC boolean calls are non-interruptible once entered. In particular,
    computing both halves of a symmetric difference on transformed, complex
    shapes can occupy that thread for minutes even after the RPC call times out.

    Modeling operations remain available. This guard is intentionally limited
    to read-only diagnostic payloads that combine a geometry transform with
    repeated booleans; those should use distance/vertex sampling or an isolated
    FreeCADCmd process instead.
    """
    if not read_only:
        return None
    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError:
        # Let execute_code produce its normal structured syntax error.
        return None

    boolean_calls = 0
    transform_calls = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        method = node.func.attr
        if method in _BOOLEAN_METHODS:
            boolean_calls += 1
        elif method in _GEOMETRY_TRANSFORM_METHODS:
            transform_calls += 1

    if boolean_calls >= 2 and transform_calls >= 1:
        return GuiBlockingRisk(
            boolean_calls=boolean_calls,
            transform_calls=transform_calls,
            reason=(
                "read-only code combines transformed geometry with repeated OCC "
                "booleans; this is non-interruptible and can freeze FreeCAD's UI"
            ),
        )
    return None
