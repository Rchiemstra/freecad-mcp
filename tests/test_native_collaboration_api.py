"""Cross-track availability check for the branch-built native collaboration API."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.core


def _require_native_collaboration() -> None:
    if os.environ.get("FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION") != "1":
        pytest.skip("Compose FreeCAD is adapter-only; use the branch-built lane")

def test_branch_built_freecad_exposes_the_frozen_collaboration_api():
    _require_native_collaboration()

    import FreeCAD

    document = FreeCAD.newDocument("MCPNativeCollaborationAvailability")
    try:
        for method in (
            "canWriteRecoverySnapshot",
            "beginEditSession",
            "snapshotForEdit",
            "prepareEdit",
            "prepareEditAsync",
            "preparedEditStatus",
            "cancelPreparedEdit",
            "takePreparedEdit",
            "commitEdit",
            "cancelEdit",
            "editSessionStatus",
            "commitCompatibilityMutation",
        ):
            assert callable(getattr(document, method, None)), method
        for method in (
            "writeRecoverySnapshotToTransientDir",
            "advanceDocumentCollaborationEpoch",
        ):
            assert callable(getattr(FreeCAD, method, None)), method
    finally:
        FreeCAD.closeDocument(document.Name)


def test_typed_cad_adapter_publishes_one_exact_structural_revision_event():
    _require_native_collaboration()

    import FreeCAD

    from addon.FreeCADMCP.collaboration_api import CollaborationAPI
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_mutation import (
        run_cad_mutation,
    )
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.object_crud import (
        create_object,
    )
    from addon.FreeCADMCP.rpc_server.mutation_guard_ops.validate_invariants import (
        validate_document_invariants,
    )

    document = FreeCAD.newDocument("MCPTypedCadNativeAttribution")
    native_results = []
    bridge = CollaborationAPI(document_lookup=FreeCAD.getDocument)
    revision_keys = [
        {"kind": "ObjectExistence", "subject": "RemoteFeature"},
        {"kind": "ObjectStructure", "subject": "RemoteFeature"},
        {"kind": "DocumentStructure"},
        {"kind": "UnknownModelMutation"},
    ]
    session = document.beginEditSession("phase-15-revision-baseline")
    snapshot = document.snapshotForEdit(session["session_id"], revision_keys)
    document.cancelEdit(session["session_id"])
    revisions_before = {
        (revision["kind"], revision["subject"]): revision["revision"]
        for revision in snapshot["revisions"]
    }

    class RecordingAPI:
        def commit_compatibility_mutation(
            self, document_name, callback, *, structural=False
        ):
            native_result = bridge.commit_compatibility_mutation(
                document_name, callback, structural=structural
            )
            native_results.append(native_result)
            return native_result

    collaborators = SimpleNamespace(
        freecad=FreeCAD,
        create_object_gui=lambda document_name, obj: (
            FreeCAD.getDocument(document_name).addObject(obj.type, obj.name)
            is not None
        ),
        validate_document_invariants=validate_document_invariants,
        commit_compatibility_mutation=(
            RecordingAPI().commit_compatibility_mutation
        ),
    )
    facade = SimpleNamespace(
        _cad_collaborators=collaborators,
        _dispatch_gui=lambda callback: callback(),
        _adapt_gui_mutation_result=lambda result, success_fields=None: {
            "success": result is True,
            **(success_fields or {}),
        },
    )

    try:
        result = create_object(
            facade,
            document.Name,
            {"Type": "App::FeaturePython", "Name": "RemoteFeature"},
        )
        assert result == {"success": True, "object_name": "RemoteFeature"}
        assert len(native_results) == 1
        assert native_results[0]["status"] == "Committed"
        assert native_results[0]["committed"] is True
        published = native_results[0]["published_revisions"]
        assert {change["kind"] for change in published} == {
            "ObjectExistence",
            "ObjectStructure",
            "DocumentStructure",
            "UnknownModelMutation",
        }
        assert len(published) == len(revision_keys)
        assert all(
            change["revision"]
            == revisions_before[(change["kind"], change["subject"])] + 1
            for change in published
        )

        failed = run_cad_mutation(
            collaborators,
            document.Name,
            lambda: (
                document.addObject("App::FeaturePython", "RolledBackFeature")
                and False
            ),
            structural=True,
        )
        assert failed is False
        assert document.getObject("RolledBackFeature") is None
        assert len(native_results) == 1
    finally:
        FreeCAD.closeDocument(document.Name)
