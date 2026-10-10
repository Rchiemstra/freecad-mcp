"""The execute_code docstring must describe the live execution venue."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]


def _manifest_doc() -> str:
    tree = ast.parse((ROOT / "src/freecad_mcp/capabilities/core/manifest.py").read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        keywords = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        name = keywords.get("name")
        doc = keywords.get("docstring")
        if (
            isinstance(name, ast.Constant)
            and name.value == "execute_code"
            and isinstance(doc, ast.Constant)
            and isinstance(doc.value, str)
        ):
            return doc.value
    raise AssertionError("execute_code docstring missing from the manifest")


def _generated_doc() -> str:
    path = (
        ROOT
        / "src/freecad_mcp/generated/capabilities/register_modules/tools_core_execute.py"
    )
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "execute_code":
            doc = ast.get_docstring(node)
            if doc:
                return doc
    raise AssertionError("execute_code docstring missing from the generated tool")


def _snapshot_doc(path: Path) -> str:
    payload = json.loads(path.read_text())
    return payload["tools"]["execute_code"]["docstring"]


def _copies() -> list[str]:
    return [
        _manifest_doc(),
        _generated_doc(),
        _snapshot_doc(ROOT / "src/freecad_mcp/generated/capabilities/registry_snapshot.json"),
        _snapshot_doc(ROOT / "tests/fixtures/mcp_tool_registry_contract_snapshot.json"),
    ]


def test_execute_code_still_documents_the_deferred_recompute_fence():
    doc = _generated_doc()
    assert "deferred-recompute fence" in doc
    assert '``recompute="target"``' in doc


def test_execute_code_docstring_states_the_live_venue():
    copies = _copies()
    assert len(set(copies)) == 1
    doc = copies[0]
    assert "document owner thread" in doc
    assert '``recompute="none"`` still' in doc
    assert "enters the commit" in doc
    assert "no document" in doc
    assert "Qt main thread" in doc
    assert "FreeCADGui.ActiveDocument" in doc
    assert "allowed off the Qt main thread" in doc
    assert "so FreeCADGui, ViewObject access" not in doc
    assert "cannot use FreeCADGui" not in doc
