"""Focused collaborator-injection contracts for non-sketch CAD RPCs."""

from __future__ import annotations

import ast
import sys
from dataclasses import fields, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.collaboration_api import CollaborationAPI
from addon.FreeCADMCP.rpc_server import object_factory
from addon.FreeCADMCP.rpc_server.fem_executor_ops import solver_resolution
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import (
    assembly,
    expressions,
    fem_analysis,
    object_crud,
    recompute_helpers,
    references,
    spreadsheet,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import sketch_public
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.cad_dependencies import (
    CadCollaborators,
)
from addon.FreeCADMCP.rpc_server.property_mapper import Object
from tests.helpers.native_readiness import freecad_with_native_readiness

pytestmark = pytest.mark.unit


class _NativeAPI:
    def __init__(self):
        self.documents = []
        self.structural_scopes = []
        self.recompute_policies = []

    def commit_compatibility_mutation(
        self,
        document_name,
        callback,
        *,
        structural=False,
        recompute=True,
        postcondition=None,
    ):
        self.documents.append(document_name)
        self.structural_scopes.append(structural)
        self.recompute_policies.append(recompute)
        callback()
        if postcondition is not None and postcondition() is False:
            return {"status": "PostconditionFailed", "committed": False}
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
    freecad = values["freecad"]
    values["freecad"] = (
        freecad_with_native_readiness(freecad)
        if callable(getattr(freecad, "getDocument", None))
        else freecad_with_native_readiness()
    )
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

    def factory(document, obj, *, recompute=True):
        calls.append((document, obj, recompute))
        return True

    collaborators, native = _collaborators(create_object_gui=factory)

    result = object_crud.create_object(
        _rpc(collaborators), "Doc", {"Type": "PartDesign::Feature", "Name": "Pad"}
    )

    assert result == {"success": True, "object_name": "Pad"}
    assert calls[0][0] == "Doc"
    assert calls[0][1].name == "Pad"
    assert calls[0][2] is False
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
            self,
            _document_name,
            callback,
            *,
            structural=False,
            postcondition=None,
        ):
            assert structural is True
            callback()
            assert created.ViewObject is None
            assert postcondition is not None
            assert postcondition() is True
            created.ViewObject = SimpleNamespace()
            return {"status": "Committed", "committed": True}

    def factory(_document_name, obj, *, recompute=True):
        assert recompute is False
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
        "native_recompute_failure",
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
            if outcome == "native_recompute_failure":
                raise RuntimeError("native recompute failed")

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
        presentation_calls.append((stage["value"], dict(actual_properties)))
        events.append(("presentation", stage["value"]))

    class NativeAPI:
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
            callback()
            assert presentation_calls == []
            try:
                document.recompute()
            except RuntimeError:
                return {"status": "RecomputeFailed", "committed": False}
            assert postcondition is not None
            if postcondition() is False:
                return {"status": "PostconditionFailed", "committed": False}
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
    assert document.recompute_count == (0 if outcome == "callback_failure" else 1)
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


def test_typed_delete_forwards_recursive_and_force_with_compatibility_defaults(
    monkeypatch,
):
    seen = []

    def delete_leaf(*_args, **kwargs):
        seen.append(kwargs)
        return {
            "ok": True,
            "object": "Body",
            "refused": False,
            "deleted": ["Body"],
        }

    monkeypatch.setattr(object_crud, "delete_object_gui", delete_leaf)
    collaborators, native = _collaborators()
    rpc = SimpleNamespace(
        _cad_collaborators=collaborators,
        _dispatch_gui=lambda callback, **_kwargs: callback(),
        _adapt_gui_mutation_result=lambda result, **_kwargs: result,
    )

    result = object_crud.delete_object(
        rpc,
        "Doc",
        "Body",
        recursive=True,
        force=False,
    )

    assert result["deleted"] == ["Body"]
    assert seen == [
        {
            "freecad": collaborators.freecad,
            "recompute": False,
            "recursive": True,
            "force": False,
        }
    ]
    assert native.structural_scopes == [True]


@pytest.mark.parametrize(
    ("module", "method_name", "leaf_name", "args"),
    [
        (
            sketch_public,
            "sketch_attach",
            "sketch_attach_gui",
            ("Doc", "Sketch", "XY_Plane"),
        ),
        (assembly, "solve_assembly", "solve_assembly_gui", ("Doc", "Assembly")),
    ],
)
def test_structural_wrappers_reach_native_with_explicit_structural_scope(
    monkeypatch,
    module,
    method_name,
    leaf_name,
    args,
):
    native_options = []

    class Document:
        Name = "Doc"
        Objects = ()

        def commitCompatibilityMutation(self, callback, **options):
            native_options.append(options)
            callback()
            assert options["postcondition"]() is True
            return {"status": "Committed", "committed": True}

    document = Document()
    freecad = SimpleNamespace(getDocument=lambda _name: document)
    leaf_calls = []
    collaborators, _native = _collaborators(freecad=freecad)
    collaborators = replace(
        collaborators,
        compatibility_api=CollaborationAPI(document_lookup=freecad.getDocument),
    )
    monkeypatch.setattr(
        module,
        leaf_name,
        lambda *_args, **kwargs: (
            leaf_calls.append(kwargs) or {"success": True, "ok": True}
        ),
    )
    rpc = SimpleNamespace(
        _cad_collaborators=collaborators,
        _dispatch_gui=lambda callback, **_kwargs: callback(),
        _adapt_gui_mutation_result=lambda result, **_kwargs: result,
    )

    result = getattr(module, method_name)(rpc, *args)

    assert result["success"] is True
    assert len(native_options) == 1
    assert native_options[0]["structural"] is True
    assert "trusted_structural" not in native_options[0]
    assert leaf_calls[0]["recompute"] is False


def test_assembly_without_apply_only_solver_fails_before_recompute(monkeypatch):
    class Assembly:
        Name = "Assembly"

        @staticmethod
        def isDerivedFrom(_type_id):
            return True

    assembly_object = Assembly()
    recompute_calls = []
    assembly_object.Document = SimpleNamespace(
        recompute=lambda: recompute_calls.append(True)
    )
    document = SimpleNamespace(
        getObject=lambda name: assembly_object if name == "Assembly" else None,
        recompute=lambda: recompute_calls.append(True),
    )
    monkeypatch.setitem(
        sys.modules,
        "JointObject",
        SimpleNamespace(
            solveIfAllowed=lambda *_args: (_ for _ in ()).throw(
                RuntimeError("solver unavailable")
            )
        ),
    )

    result = assembly.solve_assembly_gui(
        "Doc",
        "Assembly",
        freecad=SimpleNamespace(getDocument=lambda _name: document),
        recompute=False,
    )

    assert result["error_code"] == "UNSUPPORTED_NATIVE_PHASE_BOUNDARY"
    assert recompute_calls == []


def test_delete_leaf_refuses_or_recursively_deletes_without_orphans():
    class Node:
        def __init__(self, name, type_id):
            self.Name = name
            self.TypeId = type_id
            self.State = []
            self.OutList = []

    root = Node("Body", "PartDesign::Body")
    child = Node("Pad", "PartDesign::Pad")
    grandchild = Node("Fillet", "PartDesign::Fillet")
    root.OutList = [child]
    child.OutList = [grandchild]

    class Document:
        def __init__(self):
            self.objects = {item.Name: item for item in (root, child, grandchild)}
            self.removed = []
            self.recompute_calls = 0

        def getObject(self, name):
            return self.objects.get(name)

        def removeObject(self, name):
            self.removed.append(name)
            self.objects.pop(name, None)

        def recompute(self):
            self.recompute_calls += 1

    document = Document()
    freecad = SimpleNamespace(
        getDocument=lambda _name: document,
        Console=SimpleNamespace(PrintMessage=lambda _message: None),
    )

    refused = object_crud.delete_object_gui("Doc", "Body", freecad=freecad)

    assert refused["refused"] is True
    assert [item["name"] for item in refused["dependents"]] == ["Pad", "Fillet"]
    assert refused["deleted"] == []
    assert document.removed == []
    assert document.recompute_calls == 0

    deleted = object_crud.delete_object_gui(
        "Doc",
        "Body",
        freecad=freecad,
        recursive=True,
    )

    assert deleted["refused"] is False
    assert deleted["deleted"] == ["Fillet", "Pad", "Body"]
    assert document.removed == ["Fillet", "Pad", "Body"]
    assert document.objects == {}
    assert document.recompute_calls == 1


def test_delete_leaf_force_reports_preserved_dependents():
    dependent = SimpleNamespace(
        Name="Pad",
        TypeId="PartDesign::Pad",
        State=["Touched"],
        OutList=[],
    )
    root = SimpleNamespace(
        Name="Body",
        TypeId="PartDesign::Body",
        State=[],
        OutList=[dependent],
    )
    objects = {"Body": root, "Pad": dependent}
    document = SimpleNamespace(
        getObject=lambda name: objects.get(name),
        removeObject=lambda name: objects.pop(name, None),
        recompute=lambda: None,
    )

    result = object_crud.delete_object_gui(
        "Doc",
        "Body",
        freecad=SimpleNamespace(
            getDocument=lambda _name: document,
            Console=SimpleNamespace(PrintMessage=lambda _message: None),
        ),
        force=True,
    )

    assert result["deleted"] == ["Body"]
    assert result["orphans_left"] == ["Pad"]
    assert set(objects) == {"Pad"}


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
            self.recompute_calls = 0

        def getObject(self, _name):
            return self.object

        def recompute(self):
            self.recompute_calls += 1

    document = Document()
    freecad = SimpleNamespace(
        getDocument=lambda name: document if name == "Doc" else None
    )

    class NativeAPI:
        @staticmethod
        def commit_compatibility_mutation(
            _document_name,
            callback,
            *,
            structural=False,
            postcondition=None,
        ):
            assert structural is False
            callback()
            document.recompute()
            assert postcondition is not None
            if postcondition() is False:
                return {"status": "PostconditionFailed", "committed": False}
            return {"status": "Committed", "committed": True}

    collaborators, _native = _collaborators(freecad=freecad)
    collaborators = replace(collaborators, compatibility_api=NativeAPI())

    result = expressions.set_expression(
        _rpc(collaborators), "Doc", "Pad", "Length", "Spreadsheet.value"
    )

    assert result["success"] is True
    assert document.object.bound == ("Length", "Spreadsheet.value")
    assert document.recompute_calls == 1


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
            self.recompute_calls = 0

        def getObject(self, name):
            return self.sheet if name == "NewSheet" and self.has_sheet else None

        def addObject(self, _type, name):
            self.sheet.Name = name
            self.has_sheet = True
            return self.sheet

        def recompute(self):
            self.recompute_calls += 1

    document = Document()
    freecad = SimpleNamespace(getDocument=lambda _name: document)

    class NativeAPI:
        @staticmethod
        def commit_compatibility_mutation(
            _document_name,
            callback,
            *,
            structural=False,
            postcondition=None,
        ):
            assert structural is True
            callback()
            document.recompute()
            assert postcondition is not None
            if postcondition() is False:
                return {"status": "PostconditionFailed", "committed": False}
            return {"status": "Committed", "committed": True}

    collaborators, native = _collaborators(freecad=freecad)
    collaborators = replace(collaborators, compatibility_api=NativeAPI())
    rpc = _rpc(collaborators)

    created = spreadsheet.spreadsheet_create(rpc, "Doc", "NewSheet")
    read = spreadsheet.spreadsheet_get_cells(rpc, "Doc", "NewSheet", ["A1"])

    assert created["success"] is True
    assert read["cells"] == [
        {"address": "A1", "alias": "", "contents": "42", "value": "42"}
    ]
    assert native.documents == []
    assert document.recompute_calls == 1


def test_fem_analysis_fails_before_solver_or_native_callback():
    calls = []
    collaborators, native = _collaborators(
        freecad=SimpleNamespace(
            getDocument=lambda _name: SimpleNamespace(recompute=lambda: None)
        ),
        run_fem_analysis=lambda document_name, analysis_name: (
            calls.append((document_name, analysis_name))
            or {"success": True, "result_objects": ["CCX_Results"]}
        ),
    )

    result = fem_analysis.run_fem_analysis(
        _rpc(collaborators), "Doc", "Analysis", timeout=30
    )

    assert result["error_code"] == "UNSUPPORTED_NATIVE_PHASE_BOUNDARY"
    assert result["operation"] == "run_fem_analysis"
    assert result["retryable"] is False
    assert calls == []
    assert native.documents == []


def test_public_gmsh_creation_fails_before_factory_or_native_callback():
    factory_calls = []
    collaborators, native = _collaborators(
        create_object_gui=lambda *_args, **_kwargs: factory_calls.append(True) or True,
    )
    rpc = SimpleNamespace(
        _cad_collaborators=collaborators,
        _dispatch_gui=lambda callback, **_kwargs: callback(),
        _adapt_gui_mutation_result=lambda result, **_kwargs: result,
    )

    result = object_crud.create_object(
        rpc,
        "Doc",
        {
            "Type": "Fem::FemMeshGmsh",
            "Name": "Mesh",
            "Analysis": "Analysis",
            "Properties": {"Part": "Box"},
        },
    )

    assert result["error_code"] == "UNSUPPORTED_NATIVE_PHASE_BOUNDARY"
    assert result["operation"] == "create_object:Fem::FemMeshGmsh"
    assert factory_calls == []
    assert native.documents == []


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
        lambda _name: pytest.fail(
            "a C++ FEM object must not resolve a Python ViewProvider"
        ),
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
    model_module = _provider_module(model_module_name, ["ViewProxy"], provider_calls)
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
        lambda module_name: _provider_module(module_name, ["VPFirst", "VPSecond"], []),
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

    assert result["error_code"] == "UNSUPPORTED_NATIVE_PHASE_BOUNDARY"
    assert provider_calls == []
    assert document.Objects == []


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

    assert result["error_code"] == "UNSUPPORTED_NATIVE_PHASE_BOUNDARY"
    assert native.structural_scopes == []
    assert document.Objects == []
    assert provider_calls == []
    assert solver_resolution.FreeCAD.GuiUp is True


def test_transaction_control_uses_injected_dependencies_outside_native_commit():
    from addon.FreeCADMCP.part3_collaboration.operation_terminal_store import (
        clear_operation_terminal_store,
    )

    clear_operation_terminal_store()

    class Document:
        Name = "Doc"
        Uid = SimpleNamespace(Value="uid-doc")

        def __init__(self):
            self.calls = []
            self.UndoNames = ["EditA"]
            self.UndoCount = 1
            self.RedoNames = []
            self.RedoCount = 0

        def collaborationIdentity(self):
            return {
                "instance_id": 1,
                "lifecycle_epoch": 1,
                "state": "Live",
            }

        def getMutationReadiness(self):
            return {
                "ready": True,
                "stable_event_supported": True,
                "pending_transaction": False,
                "booked_transaction": 0,
                "transaction_locked": False,
                "recomputing": False,
                "must_execute": False,
                "pending_removal": False,
                "commit_barrier": False,
                "notification_replay": False,
                "poisoned": False,
                "quarantined": False,
                "diagnostic": "Ready for mutation",
            }

        def recompute(self):
            self.calls.append("recompute")

        def undo(self):
            self.calls.append("undo")
            self.UndoNames = []
            self.UndoCount = 0
            self.RedoNames = ["EditA"]
            self.RedoCount = 1

        def redo(self):
            self.calls.append("redo")

    document = Document()
    waited = []
    collaborators, native = _collaborators(
        freecad=SimpleNamespace(
            getDocument=lambda _name: document,
            listDocuments=lambda: {"Doc": document},
        ),
        recompute_and_wait=lambda name: waited.append(name) or {"ok": True},
    )
    rpc = SimpleNamespace(
        _cad_collaborators=collaborators,
        _execution_collaborators=SimpleNamespace(
            request_identity_provider=lambda: SimpleNamespace(
                get_request_identity=lambda: {
                    "authenticated_session_id": "auth-a",
                    "instance_id": "runtime-owner",
                }
            )
        ),
        _dispatch_gui=lambda callback, **_kwargs: callback(),
        _adapt_gui_mutation_result=lambda result, success_fields=None: (
            result
            if isinstance(result, dict)
            else {"success": result is True, **(success_fields or {})}
        ),
    )
    selector = {
        "document_uid": "uid-doc",
        "document_instance_id": 1,
        "lifecycle_epoch": 1,
        "document_name": "Doc",
    }

    recompute_helpers.recompute_document(rpc, "Doc")
    recompute_helpers.undo(
        rpc,
        selector,
        "op-undo",
        expected_undo_count=1,
        expected_undo_head="EditA",
    )
    recompute_helpers.redo(
        rpc,
        selector,
        "op-redo",
        expected_redo_count=1,
        expected_redo_head="EditA",
    )
    assert recompute_helpers.recompute_and_wait(rpc, "Doc") == {"ok": True}

    assert document.calls == ["recompute", "undo", "recompute", "redo", "recompute"]
    assert waited == ["Doc"]
    assert native.documents == []


def test_deferred_reference_repair_stays_atomic_without_native_recompute():
    calls = []

    class Document:
        Name = "Doc"
        Objects = ()

        def recompute(self):
            pytest.fail("deferred reference repair must not implicitly recompute")

    document = Document()

    def repair(document_name, repairs, *, recompute, validate, phase):
        calls.append((document_name, repairs, recompute, validate, phase))
        return {
            "ok": True,
            "repair_committed": True,
            "recompute": {"requested": False, "deferred": True},
        }

    collaborators, native = _collaborators(
        freecad=SimpleNamespace(getDocument=lambda _name: document),
        repair_references_gui=repair,
    )
    result = references.repair_references(_rpc(collaborators), "Doc", [{}])

    assert result["recompute"]["deferred"] is True
    assert calls == [("Doc", [{}], False, False, "complete")]
    assert native.documents == ["Doc"]
    assert native.structural_scopes == [False]
    assert native.recompute_policies == [False]


def test_eager_reference_repair_refuses_recompute_true():
    """WP03 pins repair_references to none; recompute=True is RECOMPUTE_DEFERRED."""

    def repair(*_args, **_kwargs):
        pytest.fail("repair must not run when recompute=True is refused")

    document = SimpleNamespace(Name="Doc", Objects=())
    collaborators, native = _collaborators(
        freecad=SimpleNamespace(getDocument=lambda _name: document),
        repair_references_gui=repair,
    )
    result = references.repair_references(
        _rpc(collaborators),
        "Doc",
        [{}],
        recompute=True,
        validate=True,
    )

    assert result["success"] is False
    assert result["error_code"] == "RECOMPUTE_DEFERRED"
    assert result["repair_committed"] is False
    assert native.documents == []


def test_remaining_invalid_reference_repair_rolls_back_response_truthfully():
    document = SimpleNamespace(Name="Doc", Objects=())

    def repair(_document_name, _repairs, *, recompute, validate, phase):
        assert recompute is False
        assert validate is True
        assert phase == "complete"
        return {
            "ok": False,
            "repair_committed": True,
            "remaining_invalid_repaired_properties": [{"property": "Support"}],
        }

    collaborators, native = _collaborators(
        freecad=SimpleNamespace(getDocument=lambda _name: document),
        repair_references_gui=repair,
    )

    result = references.repair_references(
        _rpc(collaborators), "Doc", [{}], validate=True
    )

    assert result["ok"] is False
    assert result["repair_committed"] is False
    assert native.documents == ["Doc"]
    assert native.recompute_policies == [False]


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
