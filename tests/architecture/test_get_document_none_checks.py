"""``getDocument`` raises NameError for unknown names; it never returns None.

Dozens of handlers wrote ``doc = FreeCAD.getDocument(name)`` followed by an
``if doc is None`` branch. That branch was dead: an unknown document raised
NameError instead, which surfaced as "RPC task raised NameError" and an error in
FreeCAD's Report view (found by a live GUI stress run). A None-checked lookup
must catch NameError.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ADDON = Path(__file__).resolve().parents[2] / "addon" / "FreeCADMCP"
_HANDLED = {"NameError", "LookupError", "Exception", "BaseException"}
_NONE_CHECK = re.compile(r"is None|is not None|if not \w+\b|\bor \w+\.getDocument")


def _caught(handler: ast.ExceptHandler) -> set[str]:
    kind = handler.type
    if kind is None:
        return {"Exception"}
    items = kind.elts if isinstance(kind, ast.Tuple) else [kind]
    return {getattr(item, "id", getattr(item, "attr", "")) for item in items}


def _unguarded_none_checked_lookups() -> list[str]:
    found = []
    for path in sorted(ADDON.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        tree = ast.parse(source)
        parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "getDocument"
            ):
                continue
            current, guarded = node, False
            while current in parents:
                parent = parents[current]
                if isinstance(parent, ast.Try) and current in parent.body and any(
                    _caught(handler) & _HANDLED for handler in parent.handlers
                ):
                    guarded = True
                    break
                current = parent
            window = "\n".join(lines[node.lineno - 1 : node.lineno + 3])
            if not guarded and _NONE_CHECK.search(window):
                found.append(f"{path.relative_to(ADDON)}:{node.lineno}")
    return found


def test_none_checked_document_lookups_catch_name_error():
    assert _unguarded_none_checked_lookups() == []
