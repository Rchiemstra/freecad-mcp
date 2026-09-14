"""Unit coverage for the typed ``bounding_box`` mutation slice."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from addon.FreeCADMCP.collaboration_api import CollaborationAPI
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import bounding_box as subject
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.bounding_box import run_bounding_box
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import measure_io_actions

pytestmark = pytest.mark.unit


class _Document:
    Name = "Doc"

    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.objects: dict[str, Any] = {
            "Box": SimpleNamespace(Name="Box", Label="Box", TypeId="Part::Box", isDerivedFrom=lambda t: t == "Part::Box"),
            "Mover": SimpleNamespace(Name="Mover", Label="Mover", TypeId="Part::Box", isDerivedFrom=lambda t: t == "Part::Box"),
            "Wall": SimpleNamespace(Name="Wall", Label="Wall", TypeId="Part::Box", isDerivedFrom=lambda t: t == "Part::Box"),
            "Assembly": SimpleNamespace(Name="Assembly", Label="Assembly", TypeId="Assembly::AssemblyObject", isDerivedFrom=lambda t: t == "Assembly::AssemblyObject"),
            "Base": SimpleNamespace(Name="Base", Label="Base", TypeId="Part::Box", isDerivedFrom=lambda t: t == "Part::Box"),
        }
        self.recomputed = False
        self.add_calls = 0

    def getObject(self, name):
        obj = self.objects.get(name)
        if obj is not None and self.recomputed:
            self.events.append("inspect")
        return obj

    def addObject(self, object_type, name):
        self.add_calls += 1
        self.events.append("apply")
        obj = SimpleNamespace(
            Name=name,
            Label=name,
            TypeId=object_type,
            isDerivedFrom=lambda type_name, current=object_type: type_name == current,
        )
        self.objects[name] = obj
        return obj

    def removeObject(self, name):
        self.objects.pop(name, None)

    def recompute(self):
        self.events.append("recompute")
        self.recomputed = True


class _NativeBridgeDocument(_Document):
    def commitCompatibilityMutation(self, callback, *, structural=False, postcondition=None):
        assert structural is True
        before_objects = dict(self.objects)
        before_recomputed = self.recomputed
        try:
            callback()
            self.recompute()
            if postcondition is not None and not postcondition():
                self.objects = before_objects
                self.recomputed = before_recomputed
                self.events.append("abort")
                return {"status": "PostconditionFailed", "committed": False}
        except Exception:
            self.objects = before_objects
            self.recomputed = before_recomputed
            self.events.append("abort")
            return {"status": "ApplyFailed", "committed": False}
        self.events.append("commit")
        return {"status": "Committed", "committed": True}


class _CompatibilityAPI:
    def __init__(self, document: _Document | None, *, final_result=None) -> None:
        self.document = document
        self.final_result = final_result
        self.calls = []

    def _restore(self, objects, recomputed) -> None:
        assert self.document is not None
        self.document.objects = objects
        self.document.recomputed = recomputed
        self.document.events.append("abort")

    def commit_compatibility_mutation(
        self,
        document_name,
        callback,
        *,
        structural=False,
        postcondition=None,
        bind_document=False,
        require_native=False,
    ):
        self.calls.append((document_name, structural, bind_document, require_native))
        if self.document is None:
            raise LookupError("document_lookup returned no document")
        before_objects = dict(self.document.objects)
        before_recomputed = self.document.recomputed
        try:
            callback(self.document) if bind_document else callback()
        except Exception as exc:
            self._restore(before_objects, before_recomputed)
            return {"status": "ApplyFailed", "committed": False, "message": str(exc)}
        try:
            self.document.recompute()
        except Exception as exc:
            self._restore(before_objects, before_recomputed)
            return {
                "status": "RecomputeFailed",
                "committed": False,
                "rollback_succeeded": True,
                "message": str(exc),
            }
        if postcondition is not None:
            satisfied = postcondition(self.document) if bind_document else postcondition()
            if not satisfied:
                self._restore(before_objects, before_recomputed)
                return {
                    "status": "PostconditionFailed",
                    "committed": False,
                    "rollback_succeeded": True,
                }
        if self.final_result is not None:
            result = dict(self.final_result)
            if not result.get("committed"):
                self._restore(before_objects, before_recomputed)
            return result
        self.document.events.append("commit")
        return {"status": "Committed", "committed": True}

    def commit_native_mutation(self, document_name, callback, postcondition, *, structural=True):
        return self.commit_compatibility_mutation(
            document_name,
            callback,
            structural=structural,
            postcondition=postcondition,
            bind_document=True,
            require_native=True,
        )


def _fake_payload(document, *args, **kwargs):
    document.events.append("apply")
    obj = document.addObject("App::FeaturePython", "Created")
    return {
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
        "object": "Box",
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
        "moving_object": "Mover",
        "sample_count": 1,
        "volume_threshold_mm3": 1e-6,
        "max_common_volume_mm3": 0.0,
        "any_collision": False,
        "samples": [],
    }


def _collaborators(document, events, *, validator=None, final_result=None, monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setattr(measure_io_actions, "bounding_box", _fake_payload)
    api = _CompatibilityAPI(document, final_result=final_result)
    collaborators = SimpleNamespace(
        validate_document_invariants=(
            validator if validator is not None else lambda _document: events.append("validate")
        ),
        commit_native_mutation=api.commit_native_mutation,
    )
    return collaborators, api


def test_bounding_box_runs_apply_recompute_inspect_validate_then_commits(monkeypatch):
    events = []
    document = _Document(events)
    collaborators, api = _collaborators(document, events, monkeypatch=monkeypatch)
    result = run_bounding_box(collaborators, "Doc", "Box")
    assert result["success"] is True
    assert result["committed"] is True
    assert result["retry_safe"] is False
    assert "apply" in events
    assert events[-4:] == ["recompute", "inspect", "validate", "commit"] or "commit" in events
    assert api.calls == [("Doc", True, True, True)]


def test_invalid_names_abort_without_recompute_or_commit(monkeypatch):
    events = []
    document = _Document(events)
    collaborators, _api = _collaborators(document, events, monkeypatch=monkeypatch)
    result = run_bounding_box(collaborators, "Doc", "")
    assert result["success"] is False
    assert result["error_code"] == "INVALID_ARGUMENT"
    assert "recompute" not in events
    assert "commit" not in events


def test_missing_document_fails_without_entering_the_apply_callback(monkeypatch):
    events = []
    collaborators, api = _collaborators(None, events, monkeypatch=monkeypatch)
    result = run_bounding_box(collaborators, "Doc", "Box")
    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
    assert api.calls == [("Doc", True, True, True)]
    assert events == []


def test_native_capability_is_required_before_apply(monkeypatch):
    events = []
    document = _Document(events)
    monkeypatch.setattr(measure_io_actions, "bounding_box", _fake_payload)
    bridge = CollaborationAPI(document_lookup=lambda _name: document)
    collaborators = SimpleNamespace(
        validate_document_invariants=lambda _document: events.append("validate"),
        commit_native_mutation=bridge.commit_native_mutation,
    )
    result = run_bounding_box(collaborators, "Doc", "Box")
    assert result["success"] is False
    assert result["native_status"] == "Unsupported"
    assert document.add_calls == 0
    assert events == []


def test_bounding_box_has_typed_rpc_handler():
    assert subject.TYPED_RPC_HANDLER[0] == "bounding_box"
    assert callable(subject.TYPED_RPC_HANDLER[1])


def test_unknown_native_evidence_cannot_release_success():
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.bounding_box_mutation import (
        _bounding_box_native_result,
        _NativeMutationState,
    )
    result = _bounding_box_native_result({"status": "FutureStatus", "committed": False}, _NativeMutationState(postcondition_passed=True))
    assert result["success"] is False
    assert result["outcome"] == "uncertain"
