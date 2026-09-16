"""Shared native qualification matrix for core document ops."""

from __future__ import annotations

import importlib
import os
from collections.abc import Callable
from types import SimpleNamespace

import pytest

from tests.core_doc_native_setup import prepare_core_document


def require_native_collaboration() -> None:
    if os.environ.get("FREECAD_MCP_REQUIRE_NATIVE_COLLABORATION") != "1":
        pytest.skip("Compose FreeCAD is adapter-only; use the branch-built lane")


def collaborators(FreeCAD, validator):
    from addon.FreeCADMCP.collaboration_api import CollaborationAPI
    from addon.FreeCADMCP.rpc_server.parts_library import insert_part_from_library
    from addon.FreeCADMCP.rpc_server.property_mapper import set_object_property

    bridge = CollaborationAPI(document_lookup=FreeCAD.getDocument)
    return SimpleNamespace(
        freecad=FreeCAD,
        validate_document_invariants=validator,
        commit_native_mutation=bridge.commit_native_mutation,
        insert_part_from_library=insert_part_from_library,
        set_object_property=set_object_property,
    )


def load_runner(op: str):
    module = importlib.import_module(
        f"addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.{op}"
    )
    return module, getattr(module, f"run_{op}")


def check_success(
    op: str,
    kind: str,
    run_args: Callable[[object, dict[str, object]], tuple],
    monkeypatch,
) -> None:
    require_native_collaboration()
    import FreeCAD

    subject, runner = load_runner(op)
    document = FreeCAD.newDocument(f"MCPTyped{op}")
    doc_name = document.Name
    events: list[str] = []

    class RecomputeProbe:
        def execute(self, _object):
            events.append("recompute")

    try:
        ctx = prepare_core_document(document, kind)
        probe = document.addObject("App::FeaturePython", "RecomputeProbe")
        probe.Proxy = RecomputeProbe()
        document.recompute()
        events.clear()

        original_apply = getattr(subject, f"apply_{op}")
        original_read = getattr(subject, f"read_{op}_result")

        def tracked_apply(admitted_document, *args, **kwargs):
            events.append("apply")
            receipt = original_apply(admitted_document, *args, **kwargs)
            probe.touch()
            return receipt

        def tracked_read(admitted_document, *args, **kwargs):
            events.append("inspect")
            return original_read(admitted_document, *args, **kwargs)

        monkeypatch.setattr(subject, f"apply_{op}", tracked_apply)
        monkeypatch.setattr(subject, f"read_{op}_result", tracked_read)
        result = runner(
            collaborators(FreeCAD, lambda _d: events.append("validate")),
            *run_args(document, ctx),
        )
        assert result["success"] is True, f"error_code={result.get('error_code')}: {result}"
        assert result["committed"] is True, f"error_code={result.get('error_code')}: {result}"
        assert events == ["apply", "recompute", "inspect", "validate"], (events, result)
    finally:
        for name in list(FreeCAD.listDocuments()):
            if name.startswith("MCPTyped") or name == doc_name:
                try:
                    FreeCAD.closeDocument(name)
                except Exception:
                    pass


def check_validation_failure(
    op: str,
    kind: str,
    run_args: Callable[[object, dict[str, object]], tuple],
) -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner(op)
    document = FreeCAD.newDocument(f"MCPTyped{op}Rollback")
    try:
        ctx = prepare_core_document(document, kind)
        before_objects = tuple(obj.Name for obj in document.Objects)
        document.recompute()
        result = runner(
            collaborators(
                FreeCAD,
                lambda _d: (_ for _ in ()).throw(RuntimeError("forced validation failure")),
            ),
            *run_args(document, ctx),
        )
        assert result["success"] is False
        assert result["error_code"] == "DOCUMENT_HEALTH_DEGRADED"
        assert result["rollback_succeeded"] is True
        assert tuple(obj.Name for obj in document.Objects) == before_objects
    finally:
        FreeCAD.closeDocument(document.Name)


def check_missing_document(
    op: str,
    run_args: Callable[[object, dict[str, object]], tuple],
) -> None:
    require_native_collaboration()
    import FreeCAD

    _, runner = load_runner(op)
    result = runner(
        collaborators(FreeCAD, lambda _d: None),
        *run_args(None, {}),
    )
    assert result["success"] is False
    assert result["error_code"] == "DOCUMENT_NOT_FOUND"
