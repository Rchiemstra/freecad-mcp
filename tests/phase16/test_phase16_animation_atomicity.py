"""Phase 16 contracts for atomic GUI-thread placement animation."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.gui_personal_registry import PersonalViewRegistry
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops import view_refresh
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.view_refresh import (
    animate_placement,
)


pytestmark = pytest.mark.unit

PNG = b"\x89PNG\r\n\x1a\nnative-personal-context"


class _Box:
    Name = "Box"
    Shape = SimpleNamespace(
        BoundBox=SimpleNamespace(
            XMin=-1.0,
            XMax=1.0,
            YMin=-1.0,
            YMax=1.0,
            ZMin=-1.0,
            ZMax=1.0,
            isValid=lambda: True,
        )
    )


class _Document:
    Name = "Model"
    Label = "Model"

    def __init__(self):
        self.box = _Box()
        self.Objects = [self.box]

    def getObject(self, name):
        return self.box if name == "Box" else None


def _context(name="Model"):
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


def _facade(*, explode=None, restore_error=None):
    document = _Document()
    placement = {"value": "original"}
    calls = []
    stored = {("Model", "actor"): _context()}
    dispatch_depth = {"value": 0}

    def dispatch(_facade, callback, **_kwargs):
        calls.append("dispatch")
        calls.append(("dispatch-options", dict(_kwargs)))
        dispatch_depth["value"] += 1
        try:
            return callback()
        finally:
            dispatch_depth["value"] -= 1

    def prepare(**options):
        assert dispatch_depth["value"] == 1
        calls.append(("prepare", options))
        return {
            "positions": [
                {"index": 0, "x": 1.0, "y": 0.0, "z": 0.0, "yaw_deg": None},
                {"index": 1, "x": 2.0, "y": 0.0, "z": 0.0, "yaw_deg": None},
            ]
        }

    def apply(plan, sample):
        assert dispatch_depth["value"] == 1
        placement["value"] = tuple(sample[key] for key in ("x", "y", "z"))
        calls.append(("apply", placement["value"]))
        if explode == "apply" and sample["index"] == 1:
            raise RuntimeError("apply failed")

    def restore(plan):
        assert dispatch_depth["value"] == 1
        placement["value"] = "original"
        calls.append("restore")
        if restore_error is not None:
            raise restore_error

    def render(name, actor, width, height, background, samples):
        assert dispatch_depth["value"] == 1
        assert placement["value"] != "original"
        calls.append(("native-render", placement["value"]))
        if explode == "render":
            raise RuntimeError("native render failed")
        return PNG

    def snapshot(name, actor):
        assert dispatch_depth["value"] == 1
        saved = stored.get((name, actor))
        return dict(saved) if saved else None

    def store(name, actor, value):
        assert dispatch_depth["value"] == 1
        calls.append("personal-store")
        stored[(name, actor)] = dict(value)

    def restore_context(name, actor, value):
        assert dispatch_depth["value"] == 1
        calls.append("personal-restore")
        if value is None:
            stored.pop((name, actor), None)
        else:
            stored[(name, actor)] = dict(value)

    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(listDocuments=lambda: {"Model": document}),
        dispatch_gui=dispatch,
        get_request_identity=lambda: {
            "authenticated_session_id": "session",
            "instance_id": "actor",
        },
        reraise_if_cancelled=lambda error: None,
        redact_rpc_diagnostic=lambda error: f"redacted:{error}",
        personal_view_registry=PersonalViewRegistry(),
        snapshot_view_context=lambda _name: _context(),
        snapshot_personal_view_context=snapshot,
        store_personal_view_context=store,
        restore_personal_view_context=restore_context,
        render_personal_view_context=render,
        prepare_placement_animation=prepare,
        apply_placement_sample=apply,
        restore_placement_animation=restore,
    )
    return (
        SimpleNamespace(_gui_collaborators=collaborators),
        placement,
        calls,
        dispatch_depth,
    )


def test_animation_is_one_gui_transaction_and_renders_each_native_personal_frame(
    monkeypatch, tmp_path
):
    facade, placement, calls, dispatch_depth = _facade()
    write_frames = view_refresh._write_animation_frames

    def checked_mkdtemp(*args, **kwargs):
        assert dispatch_depth["value"] == 0
        calls.append("mkdir")
        return str(tmp_path)

    def checked_write_frames(*args, **kwargs):
        assert dispatch_depth["value"] == 0
        calls.append("write-frames")
        return write_frames(*args, **kwargs)

    monkeypatch.setattr(view_refresh.tempfile, "mkdtemp", checked_mkdtemp)
    monkeypatch.setattr(view_refresh, "_write_animation_frames", checked_write_frames)

    result = animate_placement(
        facade,
        "Model",
        "Box",
        keyframes=[{"x": 1, "y": 0, "z": 0}, {"x": 2, "y": 0, "z": 0}],
    )

    assert result["ok"] is True
    assert calls.count("dispatch") == 1
    dispatch_options = next(
        item[1]
        for item in calls
        if isinstance(item, tuple) and item[0] == "dispatch-options"
    )
    assert dispatch_options["journal_late_completion"] is True
    assert callable(dispatch_options["late_result_transform"])
    assert [call for call in calls if call[0] == "native-render"] == [
        ("native-render", (1.0, 0.0, 0.0)),
        ("native-render", (2.0, 0.0, 0.0)),
    ]
    assert placement["value"] == "original"
    assert calls.count("personal-store") == 2
    assert calls.count("personal-restore") == 2
    restore_index = calls.index("restore")
    assert calls.index("mkdir") > restore_index
    assert calls.index("write-frames") > restore_index


@pytest.mark.parametrize("explode", ["apply", "render"])
def test_animation_restores_inside_callback_after_a_primary_failure(explode):
    facade, placement, calls, _dispatch_depth = _facade(explode=explode)

    result = animate_placement(
        facade,
        "Model",
        "Box",
        keyframes=[{"x": 1, "y": 0, "z": 0}, {"x": 2, "y": 0, "z": 0}],
    )

    assert result["ok"] is False
    assert "failed" in result["error"]
    assert result["frames"] == []
    assert calls.count("dispatch") == 1
    assert calls[-1] == "restore"
    assert placement["value"] == "original"


def test_animation_keeps_the_primary_callback_error_when_restore_also_fails():
    facade, placement, calls, _dispatch_depth = _facade(
        explode="apply", restore_error=RuntimeError("restore failed")
    )

    result = animate_placement(
        facade,
        "Model",
        "Box",
        keyframes=[{"x": 1, "y": 0, "z": 0}, {"x": 2, "y": 0, "z": 0}],
    )

    assert result["ok"] is False
    assert result["error"] == "redacted:apply failed"
    assert calls.count("dispatch") == 1
    assert calls[-1] == "restore"
    assert placement["value"] == "original"


def test_animation_restores_for_cancellation_like_callback_exception():
    class Cancelled(Exception):
        pass

    facade, placement, calls, _dispatch_depth = _facade(explode="render")
    facade._gui_collaborators.render_personal_view_context = lambda *_args: (
        _ for _ in ()
    ).throw(Cancelled("cancelled"))
    facade._gui_collaborators.reraise_if_cancelled = lambda error: (
        (_ for _ in ()).throw(error) if isinstance(error, Cancelled) else None
    )

    with pytest.raises(Cancelled, match="cancelled"):
        animate_placement(facade, "Model", "Box", keyframes=[{"x": 1, "y": 0, "z": 0}])

    assert calls.count("dispatch") == 1
    assert calls[-1] == "restore"
    assert placement["value"] == "original"


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        (
            {"keyframes": [{"x": 0, "y": 0, "z": 0}] * 121},
            "maximum of 120 frames",
        ),
        (
            {"path_object": "Path", "sample_count": 121},
            "maximum of 120 frames",
        ),
    ],
)
def test_animation_frame_cap_rejects_before_gui_dispatch(options, expected):
    facade, placement, calls, _dispatch_depth = _facade()

    result = animate_placement(facade, "Model", "Box", **options)

    assert result["ok"] is False
    assert expected in result["error"]
    assert "dispatch" not in calls
    assert placement["value"] == "original"
