"""Focused contracts for actor-scoped Phase 16 personal view adapters."""

from __future__ import annotations

import ast
import base64
from pathlib import Path
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.collaboration_context import (
    GuiDispatchFailure,
    render_temporary_context_gui,
)
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.collaboration_context_core import (
    request_actor,
)
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.collaboration_context_view import (
    _camera_for_named_view,
    _camera_with_yaw,
)
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.gui_interaction import (
    activate_document,
)
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.view_capture import (
    capture_view_sequence,
    capture_view_sequence_to_disk,
    get_active_screenshot,
)
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.view_refresh import (
    animate_placement,
    refresh_view,
)
from addon.FreeCADMCP.rpc_server.gui_personal_registry import PersonalViewRegistry


pytestmark = pytest.mark.unit

PNG = b"\x89PNG\r\n\x1a\nrendered"


class _Object:
    def __init__(self):
        self.Name = "Box"
        self.Shape = SimpleNamespace(
            BoundBox=SimpleNamespace(
                XMin=-2.0,
                XMax=2.0,
                YMin=-1.0,
                YMax=1.0,
                ZMin=-0.5,
                ZMax=0.5,
                isValid=lambda: True,
            )
        )

    def getSubObject(self, name):
        return self.Shape if name == "Face1" else None


class _Document:
    def __init__(self, name="Model"):
        self.Name = name
        self.Label = name
        self._box = _Object()
        self.Objects = [self._box]

    def getObject(self, name):
        return self._box if name == "Box" else None


def _baseline(name):
    return {
        "camera": (
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


def _facade(
    *,
    actor="actor-a",
    documents=None,
    saved=None,
    render=None,
    calls=None,
    dispatch=None,
    restore_error=None,
    prepare_animation=None,
    active_document=None,
):
    documents = documents or [_Document()]
    saved = saved if saved is not None else {}
    calls = calls if calls is not None else []

    def snapshot(name, requested_actor):
        calls.append(("snapshot", name, requested_actor))
        context = saved.get((name, requested_actor))
        return dict(context) if context is not None else None

    def store(name, requested_actor, context):
        calls.append(("store", name, requested_actor, dict(context)))
        saved[(name, requested_actor)] = dict(context)

    def restore(name, requested_actor, snapshot):
        calls.append(("restore", name, requested_actor, snapshot))
        if restore_error is not None:
            raise restore_error
        if snapshot is None:
            saved.pop((name, requested_actor), None)
        else:
            saved[(name, requested_actor)] = dict(snapshot)

    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(
            listDocuments=lambda: {doc.Name: doc for doc in documents},
            ActiveDocument=active_document,
        ),
        dispatch_gui=dispatch
        or (
            lambda facade, callback, **_kwargs: (
                calls.append(("dispatch", facade)) or callback()
            )
        ),
        get_request_identity=lambda: SimpleNamespace(
            authenticated_session_id="session", instance_id=actor
        ),
        reraise_if_cancelled=lambda _error: None,
        redact_rpc_diagnostic=lambda error: f"redacted:{error}",
        snapshot_personal_view_context=snapshot,
        store_personal_view_context=store,
        restore_personal_view_context=restore,
        render_personal_view_context=lambda name, requested_actor, width, height, background, samples: (
            calls.append(
                ("render", name, requested_actor, width, height, background, samples)
            )
            or (render(name, requested_actor) if render else PNG)
        ),
        snapshot_view_context=lambda name: (
            calls.append(("baseline", name)) or _baseline(name)
        ),
        personal_view_registry=PersonalViewRegistry(),
        repair_placements=lambda *args, **kwargs: {"ok": True, "touched": []},
        prepare_placement_animation=prepare_animation
        or (
            lambda *_args, **_kwargs: {
                "positions": [],
            }
        ),
        apply_placement_sample=lambda plan, sample: calls.append(
            ("apply", plan, sample)
        ),
        restore_placement_animation=lambda plan: calls.append(("restore_plan", plan)),
    )
    return SimpleNamespace(_gui_collaborators=collaborators), saved, calls


def test_screenshot_uses_document_names_complete_schema_and_png_base64():
    facade, saved, calls = _facade(saved={("Model", "actor-a"): _baseline("Model")})

    payload = get_active_screenshot(facade, focus_object="Box.Face1", yaw_deg=90)

    assert base64.b64decode(payload) == PNG
    store = next(call for call in calls if call[0] == "store")
    assert store[1:3] == ("Model", "actor-a")
    assert set(store[3]) == {
        "camera",
        "projection",
        "selection_paths",
        "preselection_path",
        "expanded_tree_paths",
        "tree_horizontal_scroll",
        "tree_vertical_scroll",
        "active_document",
        "active_view",
        "active_workbench",
        "edit_focus",
        "temporary_overlays",
    }
    assert store[3]["selection_paths"] == ["Box.Face1"]
    assert store[3]["active_document"] == "Model"
    assert isinstance(store[3]["active_view"], str)
    assert isinstance(store[3]["camera"], str)
    assert isinstance(store[3]["projection"], str)
    assert ("baseline", "Model") in calls
    assert ("render", "Model", "actor-a", -1, -1, "Current", -1) in calls
    assert saved[("Model", "actor-a")] == _baseline("Model")


def test_temporary_context_restores_exact_snapshot_after_success_and_render_error():
    previous = _baseline("Model")
    facade, _, calls = _facade(saved={("Model", "actor-a"): previous})
    context = _baseline("Model")

    assert render_temporary_context_gui(facade, "Model", "actor-a", context) == PNG
    assert calls[-1] == ("restore", "Model", "actor-a", previous)

    failing, _, failing_calls = _facade(
        saved={("Model", "actor-a"): previous},
        render=lambda *_: (_ for _ in ()).throw(RuntimeError("render")),
    )
    with pytest.raises(RuntimeError, match="render"):
        render_temporary_context_gui(failing, "Model", "actor-a", context)
    assert failing_calls[-1] == ("restore", "Model", "actor-a", previous)


def test_actor_document_switch_sequence_and_refresh_routes():
    shared = {
        ("Model", "actor-a"): _baseline("Model"),
        ("Other", "actor-a"): _baseline("Other"),
        ("Model", "actor-b"): _baseline("Model"),
    }
    switching, _, switching_calls = _facade(
        documents=[_Document("Model"), _Document("Other")], saved=shared
    )
    assert activate_document(switching, "Other")["ok"] is True
    assert base64.b64decode(get_active_screenshot(switching)) == PNG
    assert any(call[:2] == ("render", "Other") for call in switching_calls)

    facade, saved, calls = _facade(saved={("Model", "actor-a"): _baseline("Model")})
    sequence = capture_view_sequence(facade, frames=[{"label": "one", "yaw_deg": 5}])
    refreshed = refresh_view(facade, focus_objects=["Box"], capture=True)
    assert sequence["frames"][0]["label"] == "one"
    assert sequence["frames"][0]["yaw_deg"] == 5
    assert refreshed["image_base64"] == base64.b64encode(PNG).decode("ascii")
    assert sum(1 for call in calls if call[0] == "dispatch") >= 2
    assert saved[("Model", "actor-a")] == _baseline("Model")


def test_named_camera_and_yaw_use_coin_axis_angle() -> None:
    camera = "OrthographicCamera { orientation 0 0 1 0 }"
    front = _camera_for_named_view(camera, "Front")
    assert "orientation 1 0 0 1.570796327" in front
    yawed = _camera_with_yaw(camera, 90)
    assert "orientation 0 0 1 1.570796327" in yawed
    assert "orientation" in _camera_for_named_view(camera, "Back")
    assert "orientation" in _camera_for_named_view(camera, "Rear")
    assert "orientation" in _camera_for_named_view(camera, "SideLeft")


def test_cancellation_is_not_converted_to_a_view_error() -> None:
    class Cancelled(Exception):
        pass

    facade, _, _ = _facade(
        saved={("Model", "actor-a"): _baseline("Model")},
        render=lambda *_args: (_ for _ in ()).throw(Cancelled("stop")),
    )
    facade._gui_collaborators.reraise_if_cancelled = lambda error: (
        (_ for _ in ()).throw(error) if isinstance(error, Cancelled) else None
    )
    with pytest.raises(Cancelled, match="stop"):
        get_active_screenshot(facade)


def test_authenticated_runtime_id_is_stable_actor_and_unauthenticated_is_rejected():
    facade, _, _ = _facade(actor="runtime-stable")
    assert request_actor(facade) == "runtime-stable"
    facade._gui_collaborators.get_request_identity = lambda: {
        "instance_id": "caller-controlled"
    }
    with pytest.raises(PermissionError, match="authenticated MCP runtime"):
        request_actor(facade)


def test_get_active_screenshot_uses_freecad_active_document_in_multi_doc_sessions():
    model = _Document("Model")
    other = _Document("Other")
    # Empty saved: exercise ActiveDocument fallback, not remembered personal context.
    facade, _, calls = _facade(
        documents=[model, other],
        saved={},
        active_document=model,
    )

    payload = get_active_screenshot(facade)

    assert base64.b64decode(payload) == PNG
    assert any(call[:2] == ("render", "Model") for call in calls)


def test_get_active_screenshot_rejects_ambiguous_multi_doc_without_target():
    model = _Document("Model")
    other = _Document("Other")
    facade, _, _ = _facade(documents=[model, other], active_document=None)

    with pytest.raises(ValueError, match="document hint is required"):
        get_active_screenshot(facade)


def test_get_active_screenshot_document_hint_overrides_active_document():
    model = _Document("Model")
    other = _Document("Other")
    facade, _, calls = _facade(
        documents=[model, other],
        saved={("Other", "actor-a"): _baseline("Other")},
        active_document=model,
    )

    payload = get_active_screenshot(facade, document="Other")

    assert base64.b64decode(payload) == PNG
    assert any(call[:2] == ("render", "Other") for call in calls)


def test_restore_failure_preserves_primary_render_error() -> None:
    facade, _, _ = _facade(
        saved={("Model", "actor-a"): _baseline("Model")},
        render=lambda *_args: (_ for _ in ()).throw(RuntimeError("primary")),
        restore_error=RuntimeError("restore"),
    )
    with pytest.raises(RuntimeError, match="primary") as raised:
        render_temporary_context_gui(facade, "Model", "actor-a", _baseline("Model"))
    assert any("restore also failed" in note for note in raised.value.__notes__)


def test_dispatch_failure_is_preserved_without_secondary_unpacking() -> None:
    failure = {
        "success": False,
        "error_code": "GUI_COMPLETION_UNCERTAIN",
        "error": "late",
        "request_id": "request-1",
        "completion_uncertain": True,
    }
    facade, _, _ = _facade(
        dispatch=lambda _facade, _callback, **_kwargs: dict(failure)
    )
    result = refresh_view(facade)
    assert result["error_code"] == "GUI_COMPLETION_UNCERTAIN"
    assert result["request_id"] == "request-1"
    with pytest.raises(GuiDispatchFailure) as raised:
        get_active_screenshot(facade)
    assert raised.value.result == failure


def test_orbit_contract_malformed_input_and_disk_paths_are_contained(tmp_path):
    facade, _, _ = _facade(saved={("Model", "actor-a"): _baseline("Model")})
    orbit = capture_view_sequence(facade, orbit={"steps": 1})
    assert [frame["label"] for frame in orbit["frames"]] == [
        "orbit_00",
        "orbit_01",
    ]
    assert capture_view_sequence(facade, frames=[None])["ok"] is False

    outside = tmp_path / "outside.png"
    outside.write_bytes(b"keep")
    frame_dir = tmp_path / "frames"
    result = capture_view_sequence_to_disk(
        facade,
        frames=[{"path": str(outside)}],
        frame_dir=str(frame_dir),
    )
    assert result["frame_paths"] == [str(frame_dir / "frame_000.png")]
    assert outside.read_bytes() == b"keep"


def test_animation_uses_personal_renderer_and_restores_placement():
    plan = {"positions": [{"index": 0, "x": 1.0, "y": 2.0, "z": 3.0, "yaw_deg": None}]}
    facade, _, calls = _facade(
        saved={("Model", "actor-a"): _baseline("Model")},
        prepare_animation=lambda *_args, **_kwargs: plan,
    )
    result = animate_placement(
        facade, "Model", "Box", keyframes=[{"x": 1, "y": 2, "z": 3}]
    )
    assert result["ok"] is True
    assert result["frames"][0]["image_base64"] == base64.b64encode(PNG).decode("ascii")
    assert any(call[0] == "apply" for call in calls)
    assert sum(1 for call in calls if call[0] == "dispatch") == 1
    assert next(call for call in calls if call[0] == "dispatch") in calls[:2]
    assert calls[-1] == ("restore_plan", plan)


def test_owned_personal_view_adapters_do_not_import_freecad_or_locators():
    root = Path(__file__).resolve().parents[1]
    paths = (
        root
        / "addon/FreeCADMCP/rpc_server/methods/gui_methods_ops/collaboration_context.py",
        root
        / "addon/FreeCADMCP/rpc_server/methods/gui_methods_ops/collaboration_context_core.py",
        root
        / "addon/FreeCADMCP/rpc_server/methods/gui_methods_ops/collaboration_context_render.py",
        root
        / "addon/FreeCADMCP/rpc_server/methods/gui_methods_ops/collaboration_context_view.py",
        root / "addon/FreeCADMCP/rpc_server/methods/gui_methods_ops/view_capture.py",
        root / "addon/FreeCADMCP/rpc_server/methods/gui_methods_ops/view_refresh.py",
        root / "addon/FreeCADMCP/rpc_server/gui_context_runtime.py",
        root / "addon/FreeCADMCP/rpc_server/gui_context_snapshot.py",
        root / "addon/FreeCADMCP/rpc_server/gui_personal_registry.py",
        root / "addon/FreeCADMCP/rpc_server/gui_document_runtime.py",
        root / "addon/FreeCADMCP/rpc_server/gui_animation_runtime.py",
    )
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assert not any(
            isinstance(node, (ast.Name, ast.Attribute))
            and getattr(node, "id", getattr(node, "attr", None))
            in {"_rpc_mod", "FreeCAD", "FreeCADGui", "rpc_server"}
            for node in ast.walk(tree)
        )
        assert not any(
            isinstance(node, (ast.Import, ast.ImportFrom))
            and any(alias.name in {"FreeCAD", "FreeCADGui"} for alias in node.names)
            for node in ast.walk(tree)
        )
