"""Phase 16 contracts for eager GUI and personal-view composition."""

from __future__ import annotations

import inspect
from dataclasses import fields, replace
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server import rpc_server
from addon.FreeCADMCP.rpc_server.gui_personal_registry import PersonalViewRegistry
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.gui_dependencies import (
    GuiCollaborators,
)

pytestmark = pytest.mark.unit


GUI_FIELDS = [
    "freecad",
    "dispatch_gui",
    "get_request_identity",
    "reraise_if_cancelled",
    "redact_rpc_diagnostic",
    "open_document",
    "reload_document",
    "personal_view_registry",
    "set_section_view",
    "repair_placements",
    "prepare_placement_animation",
    "apply_placement_sample",
    "restore_placement_animation",
    "store_personal_view_context",
    "snapshot_personal_view_context",
    "restore_personal_view_context",
    "render_personal_view_context",
    "snapshot_view_context",
]


def _gui_collaborators(freecad) -> GuiCollaborators:
    values = {
        field.name: (freecad if field.name == "freecad" else lambda *a, **k: None)
        for field in fields(GuiCollaborators)
    }
    values["personal_view_registry"] = PersonalViewRegistry()
    return GuiCollaborators(**values)


def test_gui_dependency_shape_is_explicit_and_policy_free() -> None:
    assert [field.name for field in fields(GuiCollaborators)] == GUI_FIELDS
    assert not {
        "lease_owner",
        "token",
        "generation",
        "heartbeat",
        "dirty_state",
        "persistence",
        "recovery_policy",
        "sidecar",
        "credential",
        "selection_singleton",
        "active_document",
        "active_view",
    } & {field.name for field in fields(GuiCollaborators)}


def test_gui_dependencies_validate_required_edges() -> None:
    collaborators = rpc_server._build_gui_collaborators()
    with pytest.raises(ValueError, match="freecad"):
        replace(collaborators, freecad=None)
    with pytest.raises(TypeError, match="dispatch_gui"):
        replace(collaborators, dispatch_gui=None)
    with pytest.raises(TypeError, match="render_personal_view_context"):
        replace(collaborators, render_personal_view_context=None)


def test_default_gui_graph_is_eager_and_shares_freecad(monkeypatch) -> None:
    first = SimpleNamespace(
        getDocument=lambda _name: None,
        getUserAppDataDir=lambda: "/profile/",
    )
    monkeypatch.setattr(rpc_server, "FreeCAD", first)
    facade = rpc_server.FreeCADRPC()
    captured = facade._gui_collaborators
    monkeypatch.setattr(rpc_server, "FreeCAD", object())

    assert facade._gui_collaborators is captured
    assert captured.freecad is first
    assert captured.freecad is facade._collaboration_collaborators.freecad
    assert captured.freecad is facade._execution_collaborators.freecad
    assert captured.freecad is facade._cad_collaborators.freecad
    assert "_build_gui_collaborators" not in inspect.getsource(
        rpc_server.FreeCADRPC._gui_collaborators.fget
    )


def test_gui_identity_capture_uses_request_identity_module_lazily(
    monkeypatch,
) -> None:
    calls = []
    request_identity = SimpleNamespace(
        get_request_identity=lambda: {"instance_id": "actor"}
    )
    monkeypatch.setattr(
        rpc_server,
        "_request_identity_provider",
        lambda: calls.append("import") or request_identity,
    )

    collaborators = rpc_server._build_gui_collaborators()

    assert calls == []
    assert collaborators.get_request_identity() == {"instance_id": "actor"}
    assert calls == ["import"]


def test_explicit_gui_graph_requires_shared_freecad() -> None:
    collaboration = rpc_server._build_collaboration_collaborators()
    execution = rpc_server._build_execution_collaborators(
        compatibility_api=collaboration.compatibility_api
    )
    gui = _gui_collaborators(collaboration.freecad)
    facade = rpc_server.FreeCADRPC(
        collaboration_collaborators=collaboration,
        execution_collaborators=execution,
        gui_collaborators=gui,
    )
    assert facade._gui_collaborators is gui

    with pytest.raises(TypeError, match="GuiCollaborators"):
        rpc_server.FreeCADRPC(gui_collaborators=object())
    with pytest.raises(ValueError, match="must share freecad"):
        rpc_server.FreeCADRPC(
            collaboration_collaborators=collaboration,
            execution_collaborators=execution,
            gui_collaborators=_gui_collaborators(object()),
        )


def test_personal_context_restore_is_exact(monkeypatch) -> None:
    calls = []
    gui_module = SimpleNamespace(
        storePersonalViewContext=lambda *args: calls.append(("store", args)),
        removePersonalViewContext=lambda *args: calls.append(("remove", args)),
    )
    monkeypatch.setattr(rpc_server, "FreeCADGui", gui_module)
    collaborators = rpc_server._build_gui_collaborators()

    prior = {"active_document": "Doc", "selection_paths": ["Box.Face1"]}
    collaborators.restore_personal_view_context("Doc", "actor", prior)
    collaborators.restore_personal_view_context("Doc", "actor", None)

    assert calls == [
        ("store", ("Doc", "actor", prior)),
        ("remove", ("Doc", "actor")),
    ]


def test_view_snapshot_resolves_only_the_named_document(monkeypatch) -> None:
    camera = "#Inventor V2.1 ascii\nPerspectiveCamera { }"
    view = SimpleNamespace(
        getCamera=lambda: camera,
        getSize=lambda: (640, 480),
        objectName=lambda: "ActorView",
        getActiveObject=lambda _role: SimpleNamespace(Name="Body"),
    )
    gui_document = SimpleNamespace(
        activeView=lambda: view,
        getInEdit=lambda: SimpleNamespace(Object=SimpleNamespace(Name="Sketch")),
    )
    requested = []
    monkeypatch.setattr(
        rpc_server,
        "FreeCADGui",
        SimpleNamespace(
            getDocument=lambda name: requested.append(name) or gui_document,
            activeWorkbench=lambda: SimpleNamespace(name=lambda: "PartDesign"),
        ),
    )
    collaborators = rpc_server._build_gui_collaborators()

    assert collaborators.snapshot_view_context("Named") == {
        "active_document": "Named",
        "active_view": "ActorView",
        "active_workbench": "PartDesign",
        "edit_focus": "Sketch",
        "active_body": "Body",
        "camera": camera,
        "projection": "Perspective",
        "viewport_width": 640,
        "viewport_height": 480,
    }
    assert requested == ["Named"]


def test_live_start_composes_gui_collaborators_before_bridge_publication() -> None:
    source = inspect.getsource(
        __import__(
            "addon.FreeCADMCP.rpc_server.server_lifecycle",
            fromlist=["_compose_runtime"],
        )._compose_runtime
    )
    assert "gui_collaborators=rpc_mod._build_gui_collaborators()" in source
