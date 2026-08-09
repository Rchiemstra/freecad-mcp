"""Additional Phase 16 view contracts for native personal contexts."""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.gui_personal_registry import PersonalViewRegistry
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.collaboration_context_core import (
    activate_personal_target,
    resolve_document,
)
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.collaboration_context_view import (
    build_view_context,
    update_personal_view,
)
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.view_capture import (
    capture_view_sequence,
    capture_view_sequence_to_disk,
)

pytestmark = pytest.mark.unit


def _bound(xmin, xmax, ymin, ymax, zmin, zmax):
    return SimpleNamespace(
        XMin=xmin,
        XMax=xmax,
        YMin=ymin,
        YMax=ymax,
        ZMin=zmin,
        ZMax=zmax,
        isValid=lambda: True,
    )


class _Document:
    def __init__(self, name, objects=()):
        self.Name = name
        self.Label = name
        self.Objects = list(objects)

    def getObject(self, name):
        return next((obj for obj in self.Objects if obj.Name == name), None)


def _baseline(name, camera=None):
    return {
        "camera": camera
        or (
            "OrthographicCamera { position 0 0 100 orientation 0 0 0 1 "
            "focalDistance 100 height 100 }"
        ),
        "projection": "Orthographic",
        "selection_paths": [],
        "preselection_path": None,
        "expanded_tree_paths": [],
        "tree_horizontal_scroll": 0,
        "tree_vertical_scroll": 0,
        "active_document": name,
        "active_view": "view-1",
        "active_workbench": "Part",
        "edit_focus": "",
        "temporary_overlays": [],
    }


def _facade(documents, saved=None, viewport_size=(400, 100)):
    saved = {} if saved is None else saved

    def snapshot(name, actor):
        value = saved.get((name, actor))
        return dict(value) if value is not None else None

    def store(name, actor, value):
        saved[(name, actor)] = dict(value)

    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(
            listDocuments=lambda: {doc.Name: doc for doc in documents}
        ),
        dispatch_gui=lambda _facade, callback, **_kwargs: callback(),
        get_request_identity=lambda: SimpleNamespace(
            authenticated_session_id="session", instance_id="actor-a"
        ),
        reraise_if_cancelled=lambda _error: None,
        redact_rpc_diagnostic=lambda error: f"redacted:{error}",
        snapshot_personal_view_context=snapshot,
        store_personal_view_context=store,
        restore_personal_view_context=lambda _name, _actor, _value: None,
        render_personal_view_context=lambda *_args: b"png",
        snapshot_view_context=lambda name: {
            **_baseline(name),
            "viewport_width": viewport_size[0],
            "viewport_height": viewport_size[1],
        },
        personal_view_registry=PersonalViewRegistry(),
    )
    return SimpleNamespace(_gui_collaborators=collaborators), saved


def _float_field(camera, field):
    match = re.search(rf"{field}\s+([-+0-9.eE]+)", camera)
    assert match is not None
    return float(match.group(1))


def test_fit_uses_portrait_aspect_and_updates_perspective_clipping_planes():
    box = SimpleNamespace(Name="Box", BoundBox=_bound(-10, 10, -1, 1, -1, 1))
    document = _Document("Model", [box])
    perspective = (
        "PerspectiveCamera { position 0 0 100 orientation 0 0 0 1 "
        "focalDistance 100 heightAngle 0.785398 }"
    )
    facade, _ = _facade(
        [document], {("Model", "actor-a"): _baseline("Model", perspective)}
    )

    portrait = build_view_context(
        facade, document, "actor-a", fit=True, width=100, height=400
    )
    landscape = build_view_context(
        facade, document, "actor-a", fit=True, width=400, height=100
    )

    assert _float_field(portrait["camera"], "focalDistance") > _float_field(
        landscape["camera"], "focalDistance"
    )
    assert _float_field(portrait["camera"], "nearDistance") > 0
    assert _float_field(portrait["camera"], "farDistance") > _float_field(
        portrait["camera"], "nearDistance"
    )


def test_fit_uses_viewport_aspect_for_default_and_partial_dimensions():
    box = SimpleNamespace(Name="Box", BoundBox=_bound(-10, 10, -1, 1, -1, 1))
    document = _Document("Model", [box])
    perspective = (
        "PerspectiveCamera { position 0 0 100 orientation 0 0 0 1 "
        "focalDistance 100 heightAngle 0.785398 }"
    )
    saved = {("Model", "actor-a"): _baseline("Model", perspective)}
    portrait, _ = _facade([document], saved, viewport_size=(100, 400))
    landscape, _ = _facade([document], saved, viewport_size=(400, 100))

    default_portrait = build_view_context(portrait, document, "actor-a", fit=True)
    partial_portrait = build_view_context(
        portrait, document, "actor-a", fit=True, width=100
    )
    default_landscape = build_view_context(landscape, document, "actor-a", fit=True)

    portrait_distance = _float_field(default_portrait["camera"], "focalDistance")
    assert _float_field(partial_portrait["camera"], "focalDistance") == pytest.approx(
        portrait_distance
    )
    assert portrait_distance > _float_field(
        default_landscape["camera"], "focalDistance"
    )


def test_fit_recurses_container_children_and_accepts_mesh_and_direct_bounds():
    mesh = SimpleNamespace(
        Name="Mesh",
        Mesh=SimpleNamespace(BoundBox=_bound(20, 30, -2, 2, -2, 2)),
    )
    direct = SimpleNamespace(Name="Direct", BoundBox=_bound(-30, -20, -2, 2, -2, 2))
    container = SimpleNamespace(Name="Group", Group=[mesh, direct])
    document = _Document("Model", [container])
    facade, _ = _facade([document], viewport_size=(100, 100))

    context = build_view_context(facade, document, "actor-a", fit=True)

    assert _float_field(context["camera"], "height") >= 72
    assert _float_field(context["camera"], "nearDistance") > 0


def test_native_active_marker_recovers_actor_target_in_a_fresh_registry():
    model = _Document("Model")
    other = _Document("Other")
    facade, saved = _facade([model, other])

    update_personal_view(facade, "Model", lambda _document, _context: None)
    update_personal_view(facade, "Other", lambda _document, _context: None)
    recovered, _ = _facade([model, other], saved)

    assert resolve_document(recovered, "actor-a").Name == "Other"
    assert not any(
        overlay["identifier"] == "freecad-mcp:active-target"
        for overlay in saved[("Model", "actor-a")]["temporary_overlays"]
    )
    assert any(
        overlay["identifier"] == "freecad-mcp:active-target"
        for overlay in saved[("Other", "actor-a")]["temporary_overlays"]
    )


def test_active_marker_update_rolls_back_contexts_and_registry_on_failure():
    model = _Document("Model")
    other = _Document("Other")
    facade, saved = _facade([model, other])
    update_personal_view(facade, "Model", lambda _document, _context: None)
    saved[("Other", "actor-a")] = _baseline("Other")
    before = {key: dict(value) for key, value in saved.items()}
    original_store = facade._gui_collaborators.store_personal_view_context

    def failing_store(name, actor, value):
        if name == "Other":
            raise RuntimeError("marker store failed")
        original_store(name, actor, value)

    facade._gui_collaborators.store_personal_view_context = failing_store
    with pytest.raises(RuntimeError, match="marker store failed"):
        activate_personal_target(facade, "actor-a", other)

    assert saved == before
    assert (
        facade._gui_collaborators.personal_view_registry.current_target("actor-a")
        == "Model"
    )


def test_sequence_rejects_orbit_and_combined_frame_limits_before_rendering():
    document = _Document("Model")
    facade, _ = _facade([document])

    orbit = capture_view_sequence(facade, orbit={"steps": 121})
    combined = capture_view_sequence(facade, frames=[{}] * 120, orbit={"steps": 2})

    assert orbit["ok"] is False
    assert combined["ok"] is False
    assert "maximum of 120" in orbit["error"]
    assert "maximum of 120" in combined["error"]


def test_disk_capture_returns_structured_error_when_directory_creation_fails(
    monkeypatch, tmp_path
):
    document = _Document("Model")
    facade, _ = _facade([document])
    target = tmp_path / "unavailable"

    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.view_capture.os.makedirs",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(PermissionError("denied")),
    )
    result = capture_view_sequence_to_disk(facade, frames=[{}], frame_dir=str(target))

    assert result["ok"] is False
    assert result["frame_paths"] == []
    assert result["frames"] == []
    assert result["frame_dir"] is None
    assert result["error"] == "redacted:denied"
