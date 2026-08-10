"""Static safety checks for code scheduled on FreeCAD's Qt GUI thread."""

from __future__ import annotations

import ast

from .execution_safety_ops.classify_helpers import (
    is_unsafe_call,
    is_unsafe_import,
    is_unsafe_mutation_node,
    parse_execute_code_ast,
    tree_has_expensive_method_call,
)
from .execution_safety_types.gui_blocking_risk import GuiBlockingRisk
from .execution_safety_types.gui_geometry_loop_risk import GuiGeometryLoopRisk
from .execution_safety_types.request_class import RequestClass

_BOOLEAN_METHODS = frozenset({"cut", "common", "fuse", "multiCut", "multiFuse"})
_GEOMETRY_TRANSFORM_METHODS = frozenset({"mirror", "transformGeometry"})
_WORKER_ONLY_LOOP_METHODS = frozenset({"isInside"})
_EXPENSIVE_METHODS = frozenset({
    "cut", "common", "fuse", "multiCut", "multiFuse", "section",
    "distToShape", "isInside", "isValid", "check", "checkGeometry",
    "removeSplitter",
})


def classify_execute_code(code: str, *, read_only: bool) -> RequestClass:
    """Conservatively classify arbitrary code; unknown reads fail safe to worker."""
    if not read_only:
        return RequestClass.GUI_MUTATION
    tree = parse_execute_code_ast(code)
    if tree is None:
        return RequestClass.UNKNOWN
    if tree_has_expensive_method_call(tree):
        return RequestClass.WORKER_ANALYSIS
    for node in ast.walk(tree):
        if is_unsafe_mutation_node(node):
            return RequestClass.UNKNOWN
        if is_unsafe_import(node):
            return RequestClass.UNKNOWN
        if isinstance(node, ast.Call) and is_unsafe_call(node):
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
    tree = parse_execute_code_ast(code)
    if tree is None:
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


_LOOP_NODE_TYPES = (
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)


def _is_expensive_method_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _EXPENSIVE_METHODS
    )


def _nodes_inside_loop_body(loop_node: ast.AST) -> list[ast.AST]:
    """AST nodes inside a loop/comprehension body, excluding outer iter clauses."""
    nodes: list[ast.AST] = []
    if isinstance(loop_node, (ast.For, ast.AsyncFor, ast.While)):
        for part in loop_node.body:
            nodes.extend(ast.walk(part))
        for part in getattr(loop_node, "orelse", ()):
            nodes.extend(ast.walk(part))
        return nodes
    if isinstance(loop_node, ast.DictComp):
        nodes.extend(ast.walk(loop_node.key))
        nodes.extend(ast.walk(loop_node.value))
    elif isinstance(loop_node, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
        nodes.extend(ast.walk(loop_node.elt))
    for generator in getattr(loop_node, "generators", ()):
        nodes.extend(ast.walk(generator))
    return nodes


def find_gui_geometry_loop_risk(code: str) -> GuiGeometryLoopRisk | None:
    """Detect expensive OCCT operations repeated by Python control flow.

    An RPC timeout cannot interrupt a Python/OCCT call that is already running
    on Qt's GUI thread. Default-mode payloads with geometry operations inside
    loops must therefore be made explicitly read-only (so auto mode routes them
    to the isolated worker) or explicitly forced to GUI for a true mutation.
    """
    tree = parse_execute_code_ast(code)
    if tree is None:
        return None

    expensive_nodes: list[ast.Call] = []
    seen_calls: set[int] = set()
    loops = 0
    for node in ast.walk(tree):
        if not isinstance(node, _LOOP_NODE_TYPES):
            continue
        loops += 1
        for child in _nodes_inside_loop_body(node):
            if not _is_expensive_method_call(child):
                continue
            call_id = id(child)
            if call_id in seen_calls:
                continue
            seen_calls.add(call_id)
            expensive_nodes.append(child)
    if expensive_nodes:
        expensive_calls = len(expensive_nodes)
        worker_only_calls = sum(
            1
            for call in expensive_nodes
            if call.func.attr in _WORKER_ONLY_LOOP_METHODS
        )
        return GuiGeometryLoopRisk(
            expensive_calls=expensive_calls,
            worker_only_calls=worker_only_calls,
            loops=loops,
            reason=(
                "code combines Python iteration with non-interruptible OCCT "
                "geometry operations and may freeze FreeCAD's GUI thread"
            ),
        )
    return None
