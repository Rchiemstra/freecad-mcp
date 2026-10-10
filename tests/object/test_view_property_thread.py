"""View properties must not run inside the document commit.

``create_object`` and ``edit_object`` apply their mutation on the document
owner thread. ``ViewObject`` is a GUI API and may only be touched on the Qt
main thread, after that commit has succeeded. App properties stay in the
atomic commit.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_object import (
    rpc_create_object,
    run_create_object,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.edit_object import (
    rpc_edit_object,
    run_edit_object,
)
from tests.typed_rpc_fakes import FakeDocument, collaborators

pytestmark = pytest.mark.unit

_GUI_THREAD_ERROR = (
    "GUI API 'App::DocumentObjectPy::getViewObject' may only be used from the main thread"
)


def _app_setter():
    seen: list[tuple[str, ...]] = []

    def setter(_doc, obj, properties):
        seen.append(tuple(properties))
        for key, value in properties.items():
            setattr(obj, key, value)

    return setter, seen


def _owner_thread_view_setter(document: FakeDocument):
    """Raise the live GUI-thread error when view keys are set before commit."""

    def setter(_doc, obj, properties):
        view_keys = {"ViewObject", "ShapeColor"} & set(properties)
        if view_keys and "commit" not in document.events:
            raise RuntimeError(_GUI_THREAD_ERROR)
        for key, value in properties.items():
            if key == "ViewObject" and isinstance(value, dict):
                view = getattr(obj, "ViewObject", None)
                if view is None:
                    view = SimpleNamespace()
                    obj.ViewObject = view
                for inner, item in value.items():
                    setattr(view, inner, item)
                continue
            if key == "ShapeColor":
                view = getattr(obj, "ViewObject", None)
                if view is None:
                    view = SimpleNamespace()
                    obj.ViewObject = view
                view.ShapeColor = value
                continue
            setattr(obj, key, value)

    return setter


def test_create_object_commits_app_properties_with_the_object():
    """Length stays on the created object when the call has no view dict."""

    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)
    setter, seen = _app_setter()

    result = run_create_object(
        collab,
        "Doc",
        {
            "Name": "Box",
            "Type": "Part::Box",
            "Properties": {"Length": 10, "Width": 10, "Height": 10},
        },
        set_object_property=setter,
    )

    assert result["success"] is True
    assert result["outcome"] == "committed"
    box = document.getObject("Box")
    assert box is not None
    assert box.Length == 10
    assert seen == [("Length", "Width", "Height")]
    assert "commit" in events


def test_edit_object_commits_app_visibility_without_a_view_object():
    """App Visibility is an ordinary property; this call does not touch the view."""

    events: list[str] = []
    document = FakeDocument(events)
    box = document.addObject("Part::Box", "Box")
    box.PropertiesList = ["Label", "Visibility"]
    box.Visibility = True
    document.events.clear()
    collab, _api = collaborators(document, events)
    setter, seen = _app_setter()

    result = run_edit_object(
        collab,
        "Doc",
        "Box",
        {"Properties": {"Visibility": False}},
        set_object_property=setter,
    )

    assert result["success"] is True
    assert box.Visibility is False
    assert seen == [("Visibility",)]
    assert not hasattr(box, "ViewObject") or getattr(box, "ViewObject", None) is None


def test_create_object_applies_viewobject_color_after_the_app_commit():
    """The documented ShapeColor dict is applied, and Length stays committed."""

    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)
    setter = _owner_thread_view_setter(document)

    result = run_create_object(
        collab,
        "Doc",
        {
            "Name": "Box",
            "Type": "Part::Box",
            "Properties": {
                "Length": 10,
                "ViewObject": {"ShapeColor": [1, 0, 0, 1]},
            },
        },
        set_object_property=setter,
    )

    assert result["success"] is True, result.get("error")
    box = document.getObject("Box")
    assert box is not None
    assert box.Length == 10
    assert list(box.ViewObject.ShapeColor) == [1, 0, 0, 1]


def test_edit_object_applies_viewobject_visibility_after_the_app_commit():
    """``{\"ViewObject\": {\"Visibility\": false}}`` hides the view after commit."""

    events: list[str] = []
    document = FakeDocument(events)
    box = document.addObject("Part::Box", "Box")
    box.Length = 10
    document.events.clear()
    collab, _api = collaborators(document, events)
    setter = _owner_thread_view_setter(document)

    result = run_edit_object(
        collab,
        "Doc",
        "Box",
        {"Properties": {"Label": "Hidden", "ViewObject": {"Visibility": False}}},
        set_object_property=setter,
    )

    assert result["success"] is True, result.get("error")
    assert box.Label == "Hidden"
    assert box.ViewObject.Visibility is False


def test_a_failed_view_step_is_reported_and_app_properties_stay_committed():
    """The color step can fail after Length has already been committed."""

    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)

    def setter(_doc, obj, properties):
        if "ViewObject" in properties or "ShapeColor" in properties:
            raise RuntimeError("shape color rejected")
        for key, value in properties.items():
            setattr(obj, key, value)

    result = run_create_object(
        collab,
        "Doc",
        {
            "Name": "Box",
            "Type": "Part::Box",
            "Properties": {
                "Length": 10,
                "ViewObject": {"ShapeColor": [1, 0, 0, 1]},
            },
        },
        set_object_property=setter,
        on_gui=lambda task: task(),
    )

    assert result["success"] is False
    assert result["committed"] is True
    assert result["outcome"] == "uncertain"
    assert result["error_code"] == "VIEW_PROPERTY_FAILED"
    assert "shape color rejected" in result["error"]
    assert "Box" in result["error"]
    box = document.getObject("Box")
    assert box is not None
    assert box.Length == 10


def test_a_gui_dispatch_error_names_the_view_step_and_keeps_the_object():
    events: list[str] = []
    document = FakeDocument(events)
    box = document.addObject("Part::Box", "Box")
    document.events.clear()
    collab, _api = collaborators(document, events)
    setter, _seen = _app_setter()

    result = run_edit_object(
        collab,
        "Doc",
        "Box",
        {"Properties": {"Label": "Edited", "ViewObject": {"Visibility": False}}},
        set_object_property=setter,
        on_gui=lambda _task: "RPC GUI dispatcher is not initialized",
    )

    assert result["success"] is False
    assert result["committed"] is True
    assert result["error_code"] == "VIEW_PROPERTY_FAILED"
    assert "RPC GUI dispatcher is not initialized" in result["error"]
    box = document.getObject("Box")
    assert box is not None
    assert box.Label == "Edited"


def test_an_app_property_failure_rolls_back_before_any_view_assignment():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)
    hops: list[str] = []

    def setter(_doc, _obj, properties):
        if "Length" in properties:
            raise RuntimeError("Length of box too small")
        raise AssertionError(f"view properties reached the commit: {properties!r}")

    result = run_create_object(
        collab,
        "Doc",
        {
            "Name": "Box",
            "Type": "Part::Box",
            "Properties": {
                "Length": 10,
                "ViewObject": {"ShapeColor": [1, 0, 0, 1]},
            },
        },
        set_object_property=setter,
        on_gui=lambda task: hops.append("gui") or task(),
    )

    assert result["success"] is False
    assert result["committed"] is False
    assert "Length of box too small" in result["error"]
    assert result["error_code"] != "VIEW_PROPERTY_FAILED"
    assert document.getObject("Box") is None
    assert hops == []


def test_rpc_create_object_assigns_view_properties_on_the_gui_executor():
    events: list[str] = []
    document = FakeDocument(events)
    collab, _api = collaborators(document, events)
    collab.set_object_property = _owner_thread_view_setter(document)
    hops: list[str] = []

    class _Rpc:
        _cad_collaborators = collab

        @staticmethod
        def _dispatch_gui(callback):
            return callback()

        @staticmethod
        def _dispatch_snapshot_gui(task):
            hops.append("gui")
            return task()

    result = rpc_create_object(
        _Rpc(),
        "Doc",
        {
            "Name": "Box",
            "Type": "Part::Box",
            "Properties": {
                "Length": 10,
                "ViewObject": {"ShapeColor": [1, 0, 0, 1]},
            },
        },
    )

    assert hops == ["gui"]
    assert result["success"] is True, result.get("error")
    box = document.getObject("Box")
    assert box is not None
    assert box.Length == 10
    assert list(box.ViewObject.ShapeColor) == [1, 0, 0, 1]


def test_rpc_edit_object_assigns_view_visibility_on_the_gui_executor():
    events: list[str] = []
    document = FakeDocument(events)
    box = document.addObject("Part::Box", "Box")
    document.events.clear()
    collab, _api = collaborators(document, events)
    collab.set_object_property = _owner_thread_view_setter(document)
    hops: list[str] = []

    class _Rpc:
        _cad_collaborators = collab

        @staticmethod
        def _dispatch_gui(callback):
            return callback()

        @staticmethod
        def _dispatch_snapshot_gui(task):
            hops.append("gui")
            return task()

    result = rpc_edit_object(
        _Rpc(),
        "Doc",
        "Box",
        {"Properties": {"ViewObject": {"Visibility": False}}},
    )

    assert hops == ["gui"]
    assert result["success"] is True, result.get("error")
    assert box.ViewObject.Visibility is False
