"""Native qualification for typed ``recompute_and_wait``."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.core


def _require_native_collaboration() -> None:
    if os.environ.get("FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION") != "1":
        pytest.skip("Compose FreeCAD is adapter-only; use the branch-built lane")


def test_recompute_and_wait_native_commit_succeeds():
    _require_native_collaboration()

    import FreeCAD

    from addon.FreeCADMCP.collaboration_api import CollaborationAPI
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.recompute_and_wait import run_recompute_and_wait

    document = FreeCAD.newDocument("MCPTypedRecomputeAndWait")
    events: list[str] = []
    saved_path = ""
    try:
        
        if "recompute_and_wait" == "reload_document":
            saved_path = document.Name + ".FCStd"
            document.saveAs(saved_path)
        if "recompute_and_wait" == "open_document":
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
        result = run_recompute_and_wait(collab, document.Name)
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
