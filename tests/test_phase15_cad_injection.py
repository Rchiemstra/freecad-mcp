"""Focused collaborator-injection contracts for non-sketch CAD RPCs."""

from __future__ import annotations

import ast
import sys
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server import object_factory
from addon.FreeCADMCP.rpc_server.fem_executor_ops import solver_resolution
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import (
    expressions,
    fem_analysis,
    object_crud,
    recompute_helpers,
    references,
    spreadsheet,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from addon.FreeCADMCP.rpc_server.property_mapper import Object

pytestmark = pytest.mark.unit


class _NativeAPI:
    def __init__(self):
        self.documents = []
        self.structural_scopes = []

    def commit_compatibility_mutation(
        self, document_name, callback, *, structural=False
    ):
        self.documents.append(document_name)
        self.structural_scopes.append(structural)
        callback()
        return {"status": "Committed", "committed": True}


def _collaborators(**overrides):
    native = _NativeAPI()
    values = {
        field.name: (
            object()
            if field.name in {"freecad", "part", "sketcher"}
            else lambda *a, **k: None
        )
        for field in fields(CadCollaborators)
        if field.name != "compatibility_api"
    }
    values.update(overrides)
    return CadCollaborators(compatibility_api=native, **values), native


def _rpc(collaborators):
    return SimpleNamespace(
        _cad_collaborators=collaborators,
        _dispatch_gui=lambda callback, **_kwargs: callback(),
        _adapt_gui_mutation_result=lambda result, success_fields=None: {
            "success": result is True,
            **(success_fields or {}),
        },
    )


def _fem_proxy(module_tail: str, class_name: str):
    proxy_type = type(
        class_name,
        (),
        {"__module__": f"femobjects.{module_tail}"},
    )
    return proxy_type()


def _provider_module(module_name: str, class_names, calls):
    values = {"__name__": module_name}

    for class_name in class_names:
        def initialize(_self, view, *, provider_name=class_name):
            calls.append((provider_name, view))

        values[class_name] = type(
            class_name,
            (),
            {"__module__": module_name, "__init__": initialize},
        )
    return SimpleNamespace(**values)


def test_object_create_uses_the_exact_injected_factory_once():
    calls = []

    def factory(document, obj):
        calls.append((document, obj))
        return True

    collaborators, native = _collaborators(create_object_gui=factory)

    result = object_crud.create_object(
        _rpc(collaborators), "Doc", {"Type": "PartDesign::Feature", "Name": "Pad"}
    )

    assert result == {"success": True, "object_name": "Pad"}
    assert calls[0][0] == "Doc"
    assert calls[0][1].name == "Pad"
    assert native.documents == ["Doc"]
    assert native.structural_scopes == [True]


def test_object_create_defers_presentation_properties_until_after_native_commit():
    class Created:
        def __init__(self):
            self.ViewObject = None

    class Document:
        def __init__(self):
            self.created = None

        def getObject(self, name):
            return self.created if name == "Pad" else None

    document = Document()
    created = Created()
    presentation_calls = []

    class NativeAPI:
        def commit_compatibility_mutation(
            self, _document_name, callback, *, structural=False
        ):
            assert structural is True
            callback()
            assert created.ViewObject is None
            created.ViewObject = SimpleNamespace()
            return {"status": "Committed", "committed": True}

    def factory(_document_name, obj):
        assert obj.properties == {"Length": 10}
        document.created = created
        return True

    def set_properties(actual_document, actual_object, properties):
        assert actual_object.ViewObject is not None
        presentation_calls.append((actual_document, actual_object, properties))

    collaborators, _native = _collaborators(
        freecad=SimpleNamespace(getDocument=lambda _name: document),
        create_object_gui=factory,
        set_object_property=set_properties,
    )
    collaborators = replace(collaborators, compatibility_api=NativeAPI())

    result = object_crud.create_object(
        _rpc(collaborators),
        "Doc",
        {
            "Type": "PartDesign::Feature",
            "Name": "Pad",
            "Properties": {
                "Length": 10,
                "ShapeColor": [1.0, 0.0, 0.0],
                "ViewObject": {"LineColor": [0.0, 1.0, 0.0]},
            },
        },
    )

    assert result == {"success": True, "object_name": "Pad"}
    assert presentation_calls == [
        (
            document,
            created,
            {
                "ShapeColor": [1.0, 0.0, 0.0],
                "ViewObject": {"LineColor": [0.0, 1.0, 0.0]},
            },
        )
    ]


@pytest.mark.parametrize(
    "outcome",
    [
        "committed",
        "callback_failure",
        "leaf_recompute_failure",
        "validation_recompute_failure",
        "health_failure",
        "publication_failure",
    ],
)
def test_object_edit_applies_presentation_once_only_after_native_commit(  # noqa: C901 - failure matrix
    outcome,
):
    events = []
    stage = {"value": "setup"}
    edited = SimpleNamespace(Name="Pad")

    class Document:
        def __init__(self):
            self.recompute_count = 0

        @staticmethod
        def getObject(name):
            return edited if name == "Pad" else None

        def recompute(self):
            self.recompute_count += 1
            events.append(("recompute", self.recompute_count))
            if outcome == "leaf_recompute_failure" and self.recompute_count == 1:
                raise RuntimeError("leaf recompute failed")
            if (
                outcome == "validation_recompute_failure"
                and self.recompute_count == 2
            ):
                raise RuntimeError("validation recompute failed")

    document = Document()
    model_calls = []
    presentation_calls = []

    def set_properties(actual_document, actual_object, actual_properties):
        assert actual_document is document
        assert actual_object is edited
        if actual_properties == {"Length": 10}:
            model_calls.append((stage["value"], dict(actual_properties)))
            events.append(("model", stage["value"]))
            if outcome == "callback_failure":
                raise RuntimeError("model callback failed")
            return
        presentation_calls.append(
            (stage["value"], dict(actual_properties))
        )
        events.append(("presentation", stage["value"]))

    class NativeAPI:
        def commit_compatibility_mutation(
            self, document_name, callback, *, structural=False
        ):
            assert document_name == "Doc"
            assert structural is False
            stage["value"] = "native_callback"
            callback()
            assert presentation_calls == []
            events.append(("publication", outcome))
            if outcome == "publication_failure":
                return {"status": "Rejected", "committed": False}
            stage["value"] = "postcommit"
            return {"status": "Committed", "committed": True}

    def validate(_document):
        events.append(("health", outcome))
        if outcome == "health_failure":
            raise RuntimeError("document health failed")

    collaborators, _native = _collaborators(
        freecad=SimpleNamespace(
            getDocument=lambda _name: document,
            Console=SimpleNamespace(PrintMessage=lambda _message: None),
        ),
        set_object_property=set_properties,
        validate_document_invariants=validate,
    )
    collaborators = replace(collaborators, compatibility_api=NativeAPI())

    result = object_crud.edit_object(
        _rpc(collaborators),
        "Doc",
        "Pad",
        {
            "Properties": {
                "Length": 10,
                "ShapeColor": [1.0, 0.0, 0.0],
                "ViewObject": {"LineColor": [0.0, 1.0, 0.0]},
            }
        },
    )

    assert model_calls == [("native_callback", {"Length": 10})]
    assert result == {"success": outcome == "committed", "object_name": "Pad"}
    if outcome == "committed":
        assert presentation_calls == [
            (
                "postcommit",
                {
                    "ShapeColor": [1.0, 0.0, 0.0],
                    "ViewObject": {"LineColor": [0.0, 1.0, 0.0]},
                },
            )
        ]
        assert events.index(("publication", outcome)) < events.index(
            ("presentation", "postcommit")
        )
    else:
        assert presentation_calls == []


def test_expression_mutation_receives_the_exact_injected_freecad():
    class Object:
        Name = "Pad"

        def __init__(self):
            self.State = []

        def setExpression(self, path, expression):
            self.bound = (path, expression)

    class Document:
        def __init__(self):
            self.object = Object()

        def getObject(self, _name):
            return self.object

        def recompute(self):
            self.recomputed = True

    document = Document()
    freecad = SimpleNamespace(getDocument=lambda name: document if name == "Doc" else None)
    collaborators, native = _collaborators(freecad=freecad)

    result = expressions.set_expression(
        _rpc(collaborators), "Doc", "Pad", "Length", "Spreadsheet.value"
    )

    assert result["success"] is True
    assert document.object.bound == ("Length", "Spreadsheet.value")
    assert native.documents == ["Doc"]
    assert native.structural_scopes == [False]


def test_spreadsheet_read_is_not_native_but_create_is():
    class Sheet:
        Name = "Sheet"

        def getAlias(self, _address):
            return ""

        def getContents(self, _address):
            return "42"

        def get(self, _address):
            return "42"

    class Document:
        def __init__(self):
            self.sheet = Sheet()
            self.has_sheet = False

        def getObject(self, name):
            return self.sheet if name == "NewSheet" and self.has_sheet else None

        def addObject(self, _type, name):
            self.sheet.Name = name
            self.has_sheet = True
            return self.sheet

        def recompute(self):
            pass

    document = Document()
    freecad = SimpleNamespace(getDocument=lambda _name: document)
    collaborators, native = _collaborators(freecad=freecad)
    rpc = _rpc(collaborators)

    created = spreadsheet.spreadsheet_create(rpc, "Doc", "NewSheet")
    read = spreadsheet.spreadsheet_get_cells(rpc, "Doc", "NewSheet", ["A1"])

    assert created["success"] is True
    assert read["cells"] == [{"address": "A1", "alias": "", "contents": "42", "value": "42"}]
    assert native.documents == ["Doc"]
    assert native.structural_scopes == [True]


def test_fem_analysis_declares_structural_scope_for_solver_and_result_objects():
    calls = []
    collaborators, native = _collaborators(
        freecad=SimpleNamespace(getDocument=lambda _name: SimpleNamespace(recompute=lambda: None)),
        run_fem_analysis=lambda document_name, analysis_name: (
            calls.append((document_name, analysis_name))
            or {"success": True, "result_objects": ["CCX_Results"]}
        ),
    )

    result = fem_analysis.run_fem_analysis(
        _rpc(collaborators), "Doc", "Analysis", timeout=30
    )

    assert result == {"success": True, "result_objects": ["CCX_Results"]}
    assert calls == [("Doc", "Analysis")]
    assert native.documents == ["Doc"]
    assert native.structural_scopes == [True]


@pytest.mark.parametrize(
    (
        "object_type",
        "module_tail",
        "proxy_class",
        "provider_class",
        "properties",
        "analysis_name",
    ),
    [
        (
            "Fem::MaterialCommon",
            "material_common",
            "MaterialCommon",
            "VPMaterialCommon",
            {},
            None,
        ),
        (
            "Fem::FemMeshGmsh",
            "mesh_gmsh",
            "MeshGmsh",
            "VPMeshGmsh",
            {"Part": "Geometry", "ElementSizeMax": 4.0},
            "Analysis",
        ),
        (
            "Fem::ConstraintFlowVelocity",
            "constraint_flowvelocity",
            "ConstraintFlowVelocity",
            "VPConstraintFlowVelocity",
            {},
            None,
        ),
    ],
)
def test_fem_object_factory_defers_view_provider_until_after_commit(
    monkeypatch,
    object_type,
    module_tail,
    proxy_class,
    provider_class,
    properties,
    analysis_name,
):
    created = []
    provider_calls = []

    class Analysis:
        def addObject(self, obj):
            return [obj]

    class Document:
        Name = "Doc"

        def __init__(self):
            self.Objects = []
            self.analysis = Analysis()
            self.geometry = object()

        def getObject(self, name):
            return self.geometry if name == "Geometry" else None

        def recompute(self):
            pass

        @property
        def Analysis(self):
            return self.analysis

    document = Document()

    def make_fem(_document, name):
        assert solver_resolution.FreeCAD.GuiUp is False
        result = SimpleNamespace(
            Name=name,
            Proxy=_fem_proxy(module_tail, proxy_class),
            ViewObject=None,
            Shape=None,
        )
        document.Objects.append(result)
        created.append(result)
        return result

    class GmshTools:
        def __init__(self, obj):
            self.obj = obj

        def create_mesh(self):
            assert self.obj.ViewObject is None

    monkeypatch.setattr(solver_resolution.FreeCAD, "GuiUp", True)
    monkeypatch.setattr(object_factory.FreeCAD, "getDocument", lambda _name: document)
    monkeypatch.setattr(object_factory.ObjectsFem, "makeMaterialSolid", make_fem)
    monkeypatch.setattr(object_factory.ObjectsFem, "makeAnalysis", make_fem)
    monkeypatch.setattr(object_factory.ObjectsFem, "makeMeshGmsh", make_fem)
    monkeypatch.setattr(
        object_factory.ObjectsFem, "makeConstraintFlowVelocity", make_fem
    )
    monkeypatch.setattr(object_factory, "set_object_property", lambda *_args: None)
    monkeypatch.setitem(sys.modules, "femmesh", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules, "femmesh.gmshtools", SimpleNamespace(GmshTools=GmshTools)
    )
    monkeypatch.setattr(
        solver_resolution,
        "_import_module",
        lambda module_name: _provider_module(
            module_name, [provider_class], provider_calls
        ),
    )

    deferred = object_factory.create_object_gui(
        "Doc",
        Object(
            name="Created",
            type=object_type,
            analysis=analysis_name,
            properties=dict(properties),
        ),
    )

    assert callable(getattr(deferred, "apply_after_commit", None))
    assert provider_calls == []
    assert created[0].ViewObject is None
    created[0].ViewObject = object()
    deferred.apply_after_commit()
    assert provider_calls == [(provider_class, created[0].ViewObject)]


def test_fem_analysis_python_object_needs_no_explicit_presentation_replay(monkeypatch):
    document = SimpleNamespace(Objects=[], recompute=lambda: None)

    def make_analysis(_document, name):
        created = SimpleNamespace(Name=name, Proxy=None, ViewObject=None)
        document.Objects.append(created)
        return created

    monkeypatch.setattr(solver_resolution.FreeCAD, "GuiUp", True)
    monkeypatch.setattr(object_factory.FreeCAD, "getDocument", lambda _name: document)
    monkeypatch.setattr(object_factory.ObjectsFem, "makeMaterialSolid", make_analysis)
    monkeypatch.setattr(object_factory.ObjectsFem, "makeAnalysis", make_analysis)
    monkeypatch.setattr(
        solver_resolution,
        "_import_module",
        lambda _name: pytest.fail("a C++ FEM object must not resolve a Python ViewProvider"),
    )
    monkeypatch.setattr(object_factory, "set_object_property", lambda *_args: None)

    result = object_factory.create_object_gui(
        "Doc",
        Object(name="Analysis", type="Fem::AnalysisPython", properties={}),
    )

    assert result is True
    assert solver_resolution.FreeCAD.GuiUp is True


def test_fem_solver_mystran_replays_same_model_module_view_proxy(monkeypatch):
    provider_calls = []
    model_module_name = "femsolver.mystran.solver"
    model_module = _provider_module(
        model_module_name, ["ViewProxy"], provider_calls
    )
    proxy_type = type("Proxy", (), {"__module__": model_module_name})
    created = SimpleNamespace(Name="Mystran", Proxy=proxy_type(), ViewObject=None)
    document = SimpleNamespace(Objects=[], recompute=lambda: None)

    def make_solver(_document, _name):
        assert solver_resolution.FreeCAD.GuiUp is False
        document.Objects.append(created)
        return created

    monkeypatch.setattr(solver_resolution.FreeCAD, "GuiUp", True)
    monkeypatch.setattr(object_factory.FreeCAD, "getDocument", lambda _name: document)
    monkeypatch.setattr(object_factory.ObjectsFem, "makeMaterialSolid", make_solver)
    monkeypatch.setattr(object_factory.ObjectsFem, "makeAnalysis", make_solver)
    monkeypatch.setattr(object_factory.ObjectsFem, "makeSolverMystran", make_solver)
    monkeypatch.setattr(object_factory, "set_object_property", lambda *_args: None)
    monkeypatch.setattr(solver_resolution, "_getmodule", lambda _class: model_module)
    reloaded = []
    monkeypatch.setattr(
        solver_resolution,
        "_reload",
        lambda module: reloaded.append(module) or module,
    )
    monkeypatch.setattr(
        solver_resolution,
        "_import_module",
        lambda _name: pytest.fail("Mystran must use its same-module ViewProxy"),
    )

    deferred = object_factory.create_object_gui(
        "Doc",
        Object(name="Mystran", type="Fem::SolverMystran", properties={}),
    )

    assert callable(getattr(deferred, "apply_after_commit", None))
    assert provider_calls == []
    created.ViewObject = object()
    deferred.apply_after_commit()
    assert provider_calls == [("ViewProxy", created.ViewObject)]
    assert reloaded == [model_module]


def test_fem_presentation_resolution_fails_closed_only_on_true_ambiguity(
    monkeypatch,
):
    document = SimpleNamespace(Objects=[])
    created = SimpleNamespace(
        Name="Ambiguous",
        Proxy=_fem_proxy("ambiguous", "Ambiguous"),
        ViewObject=None,
    )
    monkeypatch.setattr(solver_resolution.FreeCAD, "GuiUp", True)
    monkeypatch.setattr(
        solver_resolution,
        "_import_module",
        lambda module_name: _provider_module(
            module_name, ["VPFirst", "VPSecond"], []
        ),
    )

    with (
        pytest.raises(RuntimeError, match=r"ambiguous.*VPFirst, VPSecond"),
        solver_resolution.defer_fem_presentation(document),
    ):
        document.Objects.append(created)

    assert solver_resolution.FreeCAD.GuiUp is True


def test_fem_solver_and_result_presentations_replay_only_after_native_commit(
    monkeypatch,
):
    provider_calls = []

    class Document:
        def __init__(self):
            self.Objects = []

        def recompute(self):
            pass

    document = Document()

    class NativeAPI:
        def commit_compatibility_mutation(
            self, _document_name, callback, *, structural=False
        ):
            assert structural is True
            callback()
            assert all(obj.ViewObject is None for obj in document.Objects)
            for obj in document.Objects:
                obj.ViewObject = object()
            return {"status": "Committed", "committed": True}

    def run_analysis(_document_name, _analysis_name):
        assert solver_resolution.FreeCAD.GuiUp is False
        for name, module_tail, proxy_class in (
            ("CalculiX", "solver_ccxtools", "SolverCcxTools"),
            ("CCX_Results", "result_mechanical", "ResultMechanical"),
            ("CCX_Results_Mesh", "mesh_result", "MeshResult"),
        ):
            document.Objects.append(
                SimpleNamespace(
                    Name=name,
                    Proxy=_fem_proxy(module_tail, proxy_class),
                    ViewObject=None,
                )
            )
        return {"success": True, "result_object": "CCX_Results"}

    monkeypatch.setattr(solver_resolution.FreeCAD, "GuiUp", True)
    monkeypatch.setattr(
        solver_resolution,
        "_import_module",
        lambda module_name: _provider_module(
            module_name,
            {
                "femviewprovider.view_solver_ccxtools": ["VPSolverCcxTools"],
                "femviewprovider.view_result_mechanical": ["VPResultMechanical"],
                "femviewprovider.view_mesh_result": ["VPFemMeshResult"],
            }[module_name],
            provider_calls,
        ),
    )
    collaborators, _native = _collaborators(
        freecad=SimpleNamespace(getDocument=lambda _name: document),
        run_fem_analysis=run_analysis,
    )
    collaborators = replace(collaborators, compatibility_api=NativeAPI())

    result = fem_analysis.run_fem_analysis(
        _rpc(collaborators), "Doc", "Analysis", timeout=30
    )

    assert result == {"success": True, "result_object": "CCX_Results"}
    assert [kind for kind, _view in provider_calls] == [
        "VPSolverCcxTools",
        "VPResultMechanical",
        "VPFemMeshResult",
    ]
    assert [view for _kind, view in provider_calls] == [
        obj.ViewObject for obj in document.Objects
    ]


def test_failed_fem_analysis_does_not_replay_deferred_presentation(monkeypatch):
    provider_calls = []
    document = SimpleNamespace(Objects=[], recompute=lambda: None)

    def run_analysis(_document_name, _analysis_name):
        document.Objects.append(
            SimpleNamespace(
                Name="CalculiX",
                Proxy=_fem_proxy("solver_ccxtools", "SolverCcxTools"),
                ViewObject=None,
            )
        )
        return {"success": False, "error": "solver failed"}

    monkeypatch.setattr(solver_resolution.FreeCAD, "GuiUp", True)
    monkeypatch.setattr(
        solver_resolution,
        "_import_module",
        lambda module_name: _provider_module(
            module_name, ["VPSolverCcxTools"], provider_calls
        ),
    )
    collaborators, native = _collaborators(
        freecad=SimpleNamespace(getDocument=lambda _name: document),
        run_fem_analysis=run_analysis,
    )

    result = fem_analysis.run_fem_analysis(
        _rpc(collaborators), "Doc", "Analysis", timeout=30
    )

    assert result == {"success": False, "error": "solver failed"}
    assert native.structural_scopes == [True]
    assert provider_calls == []
    assert solver_resolution.FreeCAD.GuiUp is True


def test_transaction_control_uses_injected_dependencies_outside_native_commit():
    class Document:
        def __init__(self):
            self.calls = []

        def recompute(self):
            self.calls.append("recompute")

        def undo(self):
            self.calls.append("undo")

        def redo(self):
            self.calls.append("redo")

    document = Document()
    waited = []
    collaborators, native = _collaborators(
        freecad=SimpleNamespace(getDocument=lambda _name: document),
        recompute_and_wait=lambda name: waited.append(name) or {"ok": True},
    )
    rpc = _rpc(collaborators)

    recompute_helpers.recompute_document(rpc, "Doc")
    recompute_helpers.undo(rpc, "Doc")
    recompute_helpers.redo(rpc, "Doc")
    assert recompute_helpers.recompute_and_wait(rpc, "Doc") == {"ok": True}

    assert document.calls == ["recompute", "undo", "redo"]
    assert waited == ["Doc"]
    assert native.documents == []


def test_deferred_reference_repair_stays_atomic_without_native_recompute():
    calls = []

    def repair(document_name, repairs, *, recompute, validate):
        calls.append((document_name, repairs, recompute, validate))
        return {
            "ok": True,
            "repair_committed": True,
            "recompute": {"requested": False, "deferred": True},
        }

    collaborators, native = _collaborators(repair_references_gui=repair)
    result = references.repair_references(_rpc(collaborators), "Doc", [{}])

    assert result["recompute"]["deferred"] is True
    assert calls == [("Doc", [{}], False, False)]
    assert native.documents == []


def test_owned_non_sketch_modules_are_locator_free_and_have_no_cad_imports():
    root = (
        Path(__file__).parents[1]
        / "addon"
        / "FreeCADMCP"
        / "rpc_server"
        / "methods"
        / "cad_methods_ops"
    )
    names = (
        "assembly.py",
        "diagnostics.py",
        "expressions.py",
        "fem_analysis.py",
        "object_crud.py",
        "recompute_helpers.py",
        "references.py",
        "spreadsheet.py",
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
