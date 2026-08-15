"""Phase 15 coverage for injected sketch and PartDesign mutations."""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import sketch_public
from tests.helpers.native_readiness import (
    attach_native_readiness,
    freecad_with_native_readiness,
)

pytestmark = pytest.mark.unit


class _CompatibilityAPI:
    def __init__(self):
        self.calls = []

    def commit_compatibility_mutation(
        self, document_name, callback, *, structural=False, postcondition=None
    ):
        self.calls.append((document_name, structural))
        callback()
        if postcondition is not None and postcondition() is False:
            return {"status": "PostconditionFailed", "committed": False}
        return {"status": "Committed", "committed": True}


class _Facade:
    def __init__(self, collaborators):
        self._cad_collaborators = collaborators

    @staticmethod
    def _dispatch_gui(callback):
        return callback()

    @staticmethod
    def _adapt_gui_mutation_result(result, **_kwargs):
        return result


def _collaborators(api):
    return SimpleNamespace(
        compatibility_api=api,
        freecad=freecad_with_native_readiness(),
        part=object(),
        sketcher=object(),
        dict_to_placement=object(),
        placement_to_dict=object(),
        set_extrusion_symmetric=object(),
        set_feature_bool=object(),
        validate_document_invariants=lambda _document: None,
        commit_compatibility_mutation=api.commit_compatibility_mutation,
    )


@pytest.mark.parametrize(
    ("method", "args", "leaf", "expected_dependencies"),
    [
        ("sketch_create", ("Doc", "Sketch"), "sketch_create_gui", ("freecad",)),
        (
            "sketch_add_geometry",
            ("Doc", "Sketch", []),
            "sketch_add_geometry_gui",
            ("freecad", "part"),
        ),
        (
            "sketch_add_constraint",
            ("Doc", "Sketch", []),
            "sketch_add_constraint_gui",
            ("freecad", "sketcher"),
        ),
        (
            "sketch_delete_constraint",
            ("Doc", "Sketch", [0], None),
            "sketch_delete_constraint_gui",
            ("freecad",),
        ),
        (
            "sketch_delete_geometry",
            ("Doc", "Sketch", [0]),
            "sketch_delete_geometry_gui",
            ("freecad",),
        ),
        (
            "sketch_attach",
            ("Doc", "Sketch", "XY_Plane"),
            "sketch_attach_gui",
            ("freecad", "dict_to_placement", "placement_to_dict"),
        ),
        (
            "sketch_edit_constraint",
            ("Doc", "Sketch"),
            "sketch_edit_constraint_gui",
            ("freecad",),
        ),
        (
            "pad_feature",
            ("Doc", "Sketch", "Pad", 1.0),
            "pad_feature_gui",
            ("freecad", "set_extrusion_symmetric", "set_feature_bool"),
        ),
        (
            "pocket_feature",
            ("Doc", "Sketch", "Pocket", 1.0),
            "pocket_feature_gui",
            ("freecad", "set_extrusion_symmetric", "set_feature_bool"),
        ),
        ("body_create", ("Doc", "Body"), "body_create_gui", ("freecad",)),
        (
            "body_set_tip",
            ("Doc", "Body", "Feature"),
            "body_set_tip_gui",
            ("freecad",),
        ),
    ],
)
def test_mutations_use_one_commit_and_exact_injected_dependencies(
    monkeypatch, method, args, leaf, expected_dependencies
):
    api = _CompatibilityAPI()
    collaborators = _collaborators(api)
    seen = []

    def gui(*_args, **kwargs):
        seen.append(kwargs)
        return {"success": True}

    monkeypatch.setattr(sketch_public, leaf, gui)

    result = getattr(sketch_public, method)(_Facade(collaborators), *args)

    assert result == {"success": True}
    expected_structural = method in {
        "sketch_create",
        "sketch_attach",
        "pad_feature",
        "pocket_feature",
        "body_create",
    }
    assert api.calls == [("Doc", expected_structural)]
    assert len(seen) == 1
    expected_kwargs = set(expected_dependencies)
    if method not in {"pad_feature", "pocket_feature"}:
        expected_kwargs.add("recompute")
        assert seen[0]["recompute"] is False
    assert set(seen[0]) == expected_kwargs
    for name in expected_dependencies:
        assert seen[0][name] is getattr(collaborators, name)


def test_mutation_wrapper_preserves_historical_failure_result(monkeypatch):
    api = _CompatibilityAPI()
    facade = _Facade(_collaborators(api))
    legacy_failure = "Document 'Doc' not found."
    monkeypatch.setattr(
        sketch_public, "sketch_create_gui", lambda *_args, **_kwargs: legacy_failure
    )

    result = sketch_public.sketch_create(facade, "Doc", "Sketch")

    assert result == legacy_failure
    assert api.calls == [("Doc", True)]


@pytest.mark.parametrize(
    ("method_name", "feature_type", "feature_name"),
    [
        ("pad_feature", "PartDesign::Pad", "Pad"),
        ("pocket_feature", "PartDesign::Pocket", "Pocket"),
    ],
)
@pytest.mark.parametrize(
    "outcome",
    [
        "committed",
        "callback_failure",
        "native_recompute_failure",
        "feature_validation_failure",
        "health_failure",
        "publication_failure",
    ],
)
def test_pad_and_pocket_hide_sketch_once_only_after_native_commit(  # noqa: C901 - failure matrix
    method_name, feature_type, feature_name, outcome
):
    events = []
    stage = {"value": "setup"}

    class Sketch:
        Name = "Sketch"
        ConflictingConstraints = ()
        RedundantConstraints = ()
        MalformedConstraints = ()
        SolverMessage = None

        def __init__(self):
            self._visibility = True
            self.Shape = SimpleNamespace(
                isNull=lambda: False,
                isClosed=lambda: True,
            )

        @property
        def Visibility(self):
            return self._visibility

        @Visibility.setter
        def Visibility(self, value):
            events.append(("visibility", stage["value"], value))
            self._visibility = value

    sketch = Sketch()

    class Body:
        TypeId = "PartDesign::Body"
        Name = "Body"

        def __init__(self):
            self.Group = [sketch]
            self.Tip = None

        def newObject(self, actual_type, actual_name):
            events.append(("new_feature", actual_type, actual_name))
            if outcome == "callback_failure":
                raise RuntimeError("feature callback failed")
            feature = SimpleNamespace(
                TypeId=actual_type,
                Name=actual_name,
                State=[],
                Shape=SimpleNamespace(
                    isNull=lambda: False,
                    Solids=(
                        [] if outcome == "feature_validation_failure" else [object()]
                    ),
                    BoundBox=SimpleNamespace(
                        XMin=0, YMin=0, ZMin=0, XMax=1, YMax=1, ZMax=1
                    ),
                ),
            )
            self.Group.append(feature)
            return feature

    body = Body()

    class Document:
        Name = "Doc"

        def __init__(self):
            self.Objects = [body]
            self.recompute_count = 0

        @staticmethod
        def getObject(name):
            return {"Sketch": sketch, "Body": body}.get(name)

        def recompute(self):
            self.recompute_count += 1
            events.append(("recompute", self.recompute_count))
            if outcome == "native_recompute_failure":
                raise RuntimeError("native recompute failed")

    document = attach_native_readiness(Document())

    class CompatibilityAPI:
        def commit_compatibility_mutation(
            self,
            document_name,
            callback,
            *,
            structural=False,
            postcondition=None,
        ):
            assert document_name == "Doc"
            assert structural is True
            stage["value"] = "native_callback"
            try:
                callback()
            except Exception:
                events.append(("native_callback_failed", outcome))
                raise
            assert sketch.Visibility is True
            assert not [event for event in events if event[0] == "visibility"]
            try:
                document.recompute()
            except Exception:
                return {"status": "RecomputeFailed", "committed": False}
            if postcondition is not None and postcondition() is False:
                return {"status": "PostconditionFailed", "committed": False}
            events.append(("publication", outcome))
            if outcome == "publication_failure":
                return {"status": "Rejected", "committed": False}
            stage["value"] = "postcommit"
            return {"status": "Committed", "committed": True}

    api = CompatibilityAPI()

    def validate(_document):
        events.append(("health", outcome))
        if outcome == "health_failure":
            raise RuntimeError("document health failed")

    collaborators = SimpleNamespace(
        compatibility_api=api,
        commit_compatibility_mutation=api.commit_compatibility_mutation,
        freecad=SimpleNamespace(
            getDocument=lambda _name: document,
            Console=SimpleNamespace(PrintMessage=lambda _message: None),
        ),
        set_extrusion_symmetric=lambda *_args: None,
        set_feature_bool=lambda *_args: None,
        validate_document_invariants=validate,
    )

    result = getattr(sketch_public, method_name)(
        _Facade(collaborators),
        "Doc",
        "Sketch",
        feature_name,
        5.0,
        body_name="Body",
    )

    visibility_events = [event for event in events if event[0] == "visibility"]
    if outcome == "committed":
        assert result["success"] is True
        assert visibility_events == [("visibility", "postcommit", False)]
        assert events.index(("publication", outcome)) < events.index(
            visibility_events[0]
        )
        assert events.index(("recompute", 1)) < events.index(("health", outcome))
        assert sketch.Visibility is False
    else:
        assert result is not True
        assert visibility_events == []
        assert sketch.Visibility is True


def test_owned_modules_are_locator_free_and_have_no_cad_imports():
    root = (
        Path(__file__).parents[1]
        / "addon"
        / "FreeCADMCP"
        / "rpc_server"
        / "methods"
        / "cad_methods_ops"
    )
    names = (
        "sketch_attach_helpers.py",
        "sketch_constraint_apply.py",
        "sketch_constraint_delete_helpers.py",
        "sketch_constraint_dispatch.py",
        "sketch_create_helpers.py",
        "sketch_geometry_ops.py",
        "sketch_gui_constraints_add.py",
        "sketch_gui_constraints.py",
        "sketch_gui_create.py",
        "sketch_gui_geometry.py",
        "sketch_public.py",
        "features_gui.py",
    )
    forbidden_modules = {"FreeCAD", "Part", "Sketcher"}

    for name in names:
        source = (root / name).read_text(encoding="utf-8")
        tree = ast.parse(source)
        assert "_rpc_mod" not in source
        assert not any(
            (
                isinstance(node, ast.Import)
                and any(alias.name in forbidden_modules for alias in node.names)
            )
            or (isinstance(node, ast.ImportFrom) and node.module in forbidden_modules)
            for node in ast.walk(tree)
        )
