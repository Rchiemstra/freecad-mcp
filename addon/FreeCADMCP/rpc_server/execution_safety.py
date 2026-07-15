"""Static safety checks for code scheduled on FreeCAD's Qt GUI thread."""

from __future__ import annotations

import ast
from dataclasses import dataclass


_BOOLEAN_METHODS = frozenset({"cut", "common", "fuse", "multiCut", "multiFuse"})
_GEOMETRY_TRANSFORM_METHODS = frozenset({"mirror", "transformGeometry"})


@dataclass(frozen=True)
class GuiBlockingRisk:
    boolean_calls: int
    transform_calls: int
    reason: str


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
