"""Cross-track availability check for the branch-built native collaboration API."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.core

def test_branch_built_freecad_exposes_the_frozen_collaboration_api():
    if os.environ.get("FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION") != "1":
        pytest.skip("Compose FreeCAD is adapter-only; use the branch-built lane")

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
        ):
            assert callable(getattr(document, method, None)), method
        for method in (
            "writeRecoverySnapshotToTransientDir",
            "advanceDocumentCollaborationEpoch",
        ):
            assert callable(getattr(FreeCAD, method, None)), method
    finally:
        FreeCAD.closeDocument(document.Name)
