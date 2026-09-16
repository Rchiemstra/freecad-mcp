"""Phase 16 named-document section presentation regressions."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.gui_section_runtime import set_section_view
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.gui_interaction import (
    set_section_view as set_section_view_rpc,
)
from addon.FreeCADMCP.rpc_server.gui_personal_registry import PersonalViewRegistry

pytestmark = pytest.mark.unit


def test_section_runtime_never_reads_global_active_document():
    calls = []
    view = SimpleNamespace(
        hasClippingPlane=lambda: False,
        toggleClippingPlane=lambda *args, **kwargs: calls.append((args, kwargs)),
    )
    gui_document = SimpleNamespace(activeView=lambda: view)

    class Vector:
        def __init__(self, x, y, z):
            self.x, self.y, self.z = x, y, z
            self.Length = (x * x + y * y + z * z) ** 0.5

    class Placement:
        def __init__(self):
            self.Base = Vector(0, 0, 0)
            self.Rotation = None

    freecad = SimpleNamespace(
        Placement=Placement,
        Vector=Vector,
        Rotation=lambda *args: args,
    )
    gui = SimpleNamespace(
        ActiveDocument=SimpleNamespace(
            activeView=lambda: (_ for _ in ()).throw(
                AssertionError("global active view was accessed")
            )
        ),
        getDocument=lambda name: gui_document if name == "ActorDoc" else None,
    )

    result = set_section_view(
        freecad,
        gui,
        lambda: None,
        "ActorDoc",
        True,
        base=[1, 2, 3],
    )

    assert result["ok"] is True
    assert result["document"] == "ActorDoc"
    assert len(calls) == 1


def test_section_rpc_resolves_actor_target_before_presentation():
    document = SimpleNamespace(Name="ActorDoc", Label="Actor doc")
    registry = PersonalViewRegistry()
    registry.activate("actor", "ActorDoc")
    calls = []
    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(listDocuments=lambda: {"ActorDoc": document}),
        get_request_identity=lambda: {
            "authenticated_session_id": "session",
            "instance_id": "actor",
        },
        personal_view_registry=registry,
        snapshot_personal_view_context=lambda name, actor: {"active_document": name},
        dispatch_gui=lambda facade, callback, **_kwargs: callback(),
        set_section_view=lambda document_name, *args, **kwargs: (
            calls.append((document_name, args, kwargs))
            or {"ok": True, "document": document_name}
        ),
        reraise_if_cancelled=lambda exc: None,
        redact_rpc_diagnostic=str,
    )
    facade = SimpleNamespace(_gui_collaborators=collaborators)

    result = set_section_view_rpc(facade, True, base=[0, 0, 1])

    assert result == {"ok": True, "document": "ActorDoc"}
    assert calls[0][0] == "ActorDoc"
