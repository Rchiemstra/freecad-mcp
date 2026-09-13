"""Native qualification for typed ``repair_references``."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.core


def _require_native_collaboration() -> None:
    if os.environ.get("FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION") != "1":
        pytest.skip("Compose FreeCAD is adapter-only; use the branch-built lane")


def test_repair_references_native_commit_succeeds():
    _require_native_collaboration()

    import FreeCAD

    from addon.FreeCADMCP.collaboration_api import CollaborationAPI
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.repair_references import run_repair_references

    document = FreeCAD.newDocument("MCPTypedRepairReferences")
    events: list[str] = []
    saved_path = ""
    try:
        pad = document.addObject('App::FeaturePython', 'TypedPad')
    sketch = document.addObject('App::FeaturePython', 'TypedSketch')
    sketch.addProperty('App::PropertyLinkSubList', 'Support')
    document.recompute()
        if "repair_references" == "reload_document":
            saved_path = document.Name + ".FCStd"
            document.saveAs(saved_path)
        if "repair_references" == "open_document":
            saved_path = document.Name + ".FCStd"
            document.saveAs(saved_path)
            FreeCAD.closeDocument(document.Name)
        bridge = CollaborationAPI(document_lookup=FreeCAD.getDocument)
        collab = SimpleNamespace(
            freecad=FreeCAD,
            validate_document_invariants=lambda _document: events.append("validate"),
            commit_native_mutation=bridge.commit_native_mutation,
            insert_part_from_library=lambda doc_name, _path: FreeCAD.getDocument(doc_name).addObject(
                "App::FeaturePython", "LibraryPart"
            ),
            set_object_property=lambda _doc, obj, properties: [
                setattr(obj, key, value) for key, value in properties.items()
            ],
        )
        result = run_repair_references(collab, document.Name, [{'object': 'TypedSketch', 'property': 'Support', 'references': [{'object': 'TypedPad', 'subelements': []}]}])
        assert result["success"] is True
        assert result["committed"] is True
        assert result["retry_safe"] is False
        assert "validate" in events
    finally:
        if True:
            remaining = getattr(FreeCAD, "listDocuments", lambda: {})()
            for doc_name in list(remaining):
                if doc_name.startswith("MCPTyped") or doc_name == document.Name:
                    try:
                        FreeCAD.closeDocument(doc_name)
                    except Exception:
                        pass
