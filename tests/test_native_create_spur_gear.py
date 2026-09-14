"""Native qualification matrix for typed ``create_spur_gear``."""

from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.core


def _require_native_collaboration() -> None:
    if os.environ.get("FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION") != "1":
        pytest.skip("native qualification only")


def _collaborators(FreeCAD, validator):
    from addon.FreeCADMCP.collaboration_api import CollaborationAPI

    bridge = CollaborationAPI(document_lookup=FreeCAD.getDocument)
    return SimpleNamespace(
        validate_document_invariants=validator,
        commit_native_mutation=bridge.commit_native_mutation,
    )


def test_create_spur_gear_native_success_inspects_after_recompute(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import create_spur_gear as module

    document = FreeCAD.newDocument("MCPCreateSpurGearNative")
    events: list[str] = []

    class RecomputeProbe:
        def execute(self, _object):
            events.append("recompute")

    probe = document.addObject("App::FeaturePython", "RecomputeProbe")
    probe.Proxy = RecomputeProbe()
    document.recompute()
    events.clear()

    original_apply = module.apply_create_spur_gear

    def tracked_apply(admitted_document, request):
        events.append("apply")
        probe.touch()
        obj = admitted_document.addObject("App::FeaturePython", "CreatedNative")
        return module.CreateSpurGearReceipt(
            payload={
                "assembly": obj.Name,
                "label": obj.Label,
                "type": obj.TypeId,
                "joint_group": None,
                "joint": obj.Name,
                "joint_type": "Fixed",
                "component": "Base",
                "method": "assembly.solve()",
                "status": "ok",
                "body": obj.Name,
                "sketch": obj.Name,
                "feature": obj.Name,
                "teeth": 8,
                "module": 2.0,
                "path": "/tmp/out",
                "exported": True,
                "object": obj.Name,
                "faces": 12,
                "imported": True,
                "xmin": 0.0,
                "ymin": 0.0,
                "zmin": 0.0,
                "xmax": 1.0,
                "ymax": 1.0,
                "zmax": 1.0,
                "dx": 1.0,
                "dy": 1.0,
                "dz": 1.0,
                "diagonal": 1.732,
                "frame": "world",
                "x": 0.5,
                "y": 0.5,
                "z": 0.5,
                "unit": "mm",
                "moving_object": obj.Name,
                "sample_count": 1,
                "volume_threshold_mm3": 1e-6,
                "max_common_volume_mm3": 0.0,
                "any_collision": False,
                "samples": [],
            },
            obj=obj,
        )

    monkeypatch.setattr(module, "apply_create_spur_gear", tracked_apply)
    collaborators = _collaborators(FreeCAD, lambda _document: events.append("validate"))
    try:
        result = module.run_create_spur_gear(collaborators, document.Name, "Gear", 8, 2.0, 10.0)
        assert result["success"] is True
        assert result["committed"] is True
        assert "apply" in events
        assert "recompute" in events
        assert "validate" in events
    finally:
        FreeCAD.closeDocument(document.Name)


def test_create_spur_gear_native_validation_failure_restores(monkeypatch):
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import create_spur_gear as module

    document = FreeCAD.newDocument("MCPCreateSpurGearNativeRollback")
    original_apply = module.apply_create_spur_gear

    def tracked_apply(admitted_document, request):
        obj = admitted_document.addObject("App::FeaturePython", "RejectedNative")
        return original_apply(admitted_document, request) if False else module.CreateSpurGearReceipt(
            payload={"object": obj.Name, "assembly": obj.Name, "label": obj.Label, "type": obj.TypeId, "joint_group": None, "joint": obj.Name, "joint_type": "Fixed", "component": "Base", "method": "assembly.solve()", "status": "ok", "body": obj.Name, "sketch": obj.Name, "feature": obj.Name, "teeth": 8, "module": 2.0, "path": "/tmp/out", "exported": True, "faces": 1, "imported": True, "xmin": 0.0, "ymin": 0.0, "zmin": 0.0, "xmax": 1.0, "ymax": 1.0, "zmax": 1.0, "dx": 1.0, "dy": 1.0, "dz": 1.0, "diagonal": 1.0, "frame": "world", "x": 0.0, "y": 0.0, "z": 0.0, "unit": "mm", "moving_object": obj.Name, "sample_count": 1, "volume_threshold_mm3": 1e-6, "max_common_volume_mm3": 0.0, "any_collision": False, "samples": []},
            obj=obj,
        )

    monkeypatch.setattr(module, "apply_create_spur_gear", tracked_apply)
    collaborators = _collaborators(
        FreeCAD,
        lambda _document: (_ for _ in ()).throw(RuntimeError("forced validation failure")),
    )
    try:
        result = module.run_create_spur_gear(collaborators, document.Name, "Gear", 8, 2.0, 10.0)
        assert result["success"] is False
        assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
        assert document.getObject("RejectedNative") is None
    finally:
        FreeCAD.closeDocument(document.Name)


def test_create_spur_gear_native_missing_document_keeps_typed_error():
    _require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_spur_gear import run_create_spur_gear

    collaborators = _collaborators(FreeCAD, lambda _document: None)
    result = run_create_spur_gear(collaborators, "MissingNativeDoc", "Gear", 8, 2.0, 10.0)
    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
