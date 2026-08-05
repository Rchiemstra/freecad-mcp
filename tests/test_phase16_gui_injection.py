"""Phase 16 contracts for GUI collaborator injection."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.document_ops import (
    list_documents,
    open_document,
    reload_document,
)
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.gui_dependencies import (
    GuiCollaborators,
)
from addon.FreeCADMCP.rpc_server.gui_personal_registry import PersonalViewRegistry
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.gui_interaction import (
    activate_document,
    get_gui_state,
    get_selection,
    select_subshapes,
    set_section_view,
    set_tree_expanded,
)


pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
OWNED_ADAPTERS = (
    ROOT / "addon/FreeCADMCP/rpc_server/methods/gui_methods_ops/document_ops.py",
    ROOT / "addon/FreeCADMCP/rpc_server/methods/gui_methods_ops/gui_interaction.py",
)
CALLABLE_FIELDS = (
    "dispatch_gui",
    "get_request_identity",
    "reraise_if_cancelled",
    "ensure_v2_document",
    "redact_rpc_diagnostic",
    "open_document",
    "reload_document",
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
)
EXPECTED_FIELDS = (
    "freecad",
    "dispatch_gui",
    "get_request_identity",
    "reraise_if_cancelled",
    "document_identity_service",
    "ensure_v2_document",
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
)


def _callable(*_args, **_kwargs):
    return None


def _collaborators(**overrides):
    values = {
        "freecad": SimpleNamespace(
            listDocuments=lambda: {},
            getDocument=lambda _name: None,
            closeDocument=_callable,
        ),
        "dispatch_gui": lambda _facade, callback: callback(),
        "get_request_identity": lambda: {
            "authenticated_session_id": "session",
            "instance_id": "actor",
        },
        "reraise_if_cancelled": _callable,
        "document_identity_service": object(),
        "ensure_v2_document": _callable,
        "redact_rpc_diagnostic": lambda value, **_kwargs: str(value),
        "open_document": _callable,
        "reload_document": _callable,
        "personal_view_registry": PersonalViewRegistry(),
        "set_section_view": _callable,
        "repair_placements": _callable,
        "prepare_placement_animation": _callable,
        "apply_placement_sample": _callable,
        "restore_placement_animation": _callable,
        "store_personal_view_context": _callable,
        "snapshot_personal_view_context": _callable,
        "restore_personal_view_context": _callable,
        "render_personal_view_context": _callable,
        "snapshot_view_context": _callable,
    }
    values.update(overrides)
    return GuiCollaborators(**values)


def test_gui_collaborators_are_frozen_and_accept_optional_identity_service() -> None:
    collaborators = _collaborators(document_identity_service=None)

    assert tuple(GuiCollaborators.__dataclass_fields__) == EXPECTED_FIELDS
    assert collaborators.document_identity_service is None
    with pytest.raises(FrozenInstanceError):
        collaborators.freecad = object()
    with pytest.raises(ValueError, match="freecad collaborator is required"):
        _collaborators(freecad=None)


@pytest.mark.parametrize("field", CALLABLE_FIELDS)
def test_gui_collaborators_validate_every_callable(field: str) -> None:
    with pytest.raises(TypeError, match=field):
        _collaborators(**{field: None})


def test_open_document_uses_exact_injected_identity_and_presentation_calls() -> None:
    calls: list[tuple[str, object]] = []
    document = SimpleNamespace(Name="Model")
    identity = SimpleNamespace(session_uuid="session-1", canonical_path="/model.FCStd")
    freecad = SimpleNamespace(
        listDocuments=lambda: {},
        getDocument=lambda name: calls.append(("get", name)) or document,
        closeDocument=lambda name: calls.append(("close", name)),
    )
    identity_service = SimpleNamespace(
        assert_open_path_available=lambda path: calls.append(("available", path))
    )

    def dispatch(facade, callback, **_kwargs):
        calls.append(("dispatch", facade))
        return callback()

    collaborators = _collaborators(
        freecad=freecad,
        dispatch_gui=dispatch,
        document_identity_service=identity_service,
        open_document=lambda path: (
            calls.append(("open", path)) or {"ok": True, "document": "Model"}
        ),
        ensure_v2_document=lambda value: calls.append(("ensure", value)) or identity,
        snapshot_view_context=lambda name: (
            calls.append(("baseline", name)) or {"active_document": name}
        ),
        snapshot_personal_view_context=lambda *_args: None,
        store_personal_view_context=lambda name, actor, context: calls.append(
            ("store", (name, actor, context))
        ),
    )
    facade = SimpleNamespace(_gui_collaborators=collaborators)

    assert open_document(facade, "/model.FCStd") == {
        "ok": True,
        "document": "Model",
        "document_session_uuid": "session-1",
        "canonical_path": "/model.FCStd",
    }
    assert calls == [
        ("dispatch", facade),
        ("available", "/model.FCStd"),
        ("open", "/model.FCStd"),
        ("get", "Model"),
        ("ensure", document),
        ("baseline", "Model"),
        (
            "store",
            (
                "Model",
                "actor",
                {
                    "camera": "",
                    "projection": "",
                    "selection_paths": [],
                    "preselection_path": None,
                    "expanded_tree_paths": [],
                    "tree_horizontal_scroll": 0,
                    "tree_vertical_scroll": 0,
                    "active_document": "Model",
                    "active_view": "",
                    "active_workbench": "",
                    "edit_focus": "",
                    "temporary_overlays": [],
                },
            ),
        ),
    ]


def test_document_adapters_route_list_and_reload_through_injected_dispatcher() -> None:
    calls: list[tuple[str, object]] = []
    document = SimpleNamespace(Name="Model")
    freecad = SimpleNamespace(
        listDocuments=lambda: {"Model": document},
        getDocument=lambda _name: document,
    )

    def dispatch(facade, callback, **_kwargs):
        calls.append(("dispatch", facade))
        return callback()

    collaborators = _collaborators(
        freecad=freecad,
        dispatch_gui=dispatch,
        reload_document=lambda name: calls.append(("reload", name)) or {"ok": True},
        snapshot_personal_view_context=lambda *_args: {"active_document": "Model"},
        store_personal_view_context=lambda *_args: calls.append(("store", "context")),
    )
    facade = SimpleNamespace(
        _gui_collaborators=collaborators,
        _adapt_gui_mutation_result=lambda result, *, success_fields: {
            **result,
            **success_fields,
        },
    )

    assert list_documents(facade) == ["Model"]
    assert reload_document(facade, "Model") == {
        "ok": True,
        "document_name": "Model",
    }
    assert calls == [
        ("dispatch", facade),
        ("dispatch", facade),
        ("reload", "Model"),
        ("store", "context"),
    ]


def test_gui_interaction_routes_presentation_calls_through_injected_dispatcher() -> (
    None
):
    calls: list[tuple[str, object]] = []
    stored = {}

    class Obj:
        Name = "Body"

        def getSubObject(self, sub):
            return self if sub == "Face1" else None

    obj = Obj()
    document = SimpleNamespace(
        Name="Model",
        Label="Model label",
        Objects=[obj],
        getObject=lambda name: obj if name == "Body" else None,
    )

    def dispatch(_facade, callback, **_kwargs):
        calls.append(("dispatch", _facade))
        return callback()

    documents = {"Model": document}

    collaborators = _collaborators(
        freecad=SimpleNamespace(listDocuments=lambda: dict(documents)),
        dispatch_gui=dispatch,
        get_request_identity=lambda: {
            "authenticated_session_id": "session",
            "instance_id": "actor",
        },
        snapshot_view_context=lambda name: {"active_document": name},
        snapshot_personal_view_context=lambda name, actor: stored.get((name, actor)),
        store_personal_view_context=lambda name, actor, context: stored.__setitem__(
            (name, actor), dict(context)
        ),
        set_section_view=lambda *args, **kwargs: (
            calls.append(("section", (args, kwargs))) or {"ok": True}
        ),
    )
    facade = SimpleNamespace(_gui_collaborators=collaborators)

    assert activate_document(facade, "Model") == {
        "ok": True,
        "document": "Model",
        "label": "Model label",
    }
    assert set_tree_expanded(facade, "Model", ["Body"], "expand")["ok"] is True
    assert select_subshapes(
        facade, "Model", [{"object": "Body", "sub": "Face1"}], True
    ) == {
        "ok": True,
        "selected": [{"object": "Body", "sub": "Face1"}],
        "errors": [],
        "count": 1,
    }
    assert get_selection(facade) == {
        "ok": True,
        "selection": [{"document": "Model", "object": "Body", "sub": "Face1"}],
        "count": 1,
    }
    assert get_gui_state(facade)["selection_count"] == 1
    assert set_section_view(facade, True, {"x": 1}, [1], [0, 0, 1], False) == {
        "ok": True
    }
    assert stored[("Model", "actor")]["selection_paths"] == ["Body.Face1"]
    assert stored[("Model", "actor")]["expanded_tree_paths"] == ["Body"]
    assert sum(1 for name, _ in calls if name == "dispatch") == 6
    assert calls[-1][0] == "section"

    other = SimpleNamespace(
        Name="Other",
        Label="Other label",
        Objects=[obj],
        getObject=document.getObject,
    )
    documents["Other"] = other
    assert activate_document(facade, "Other")["ok"] is True
    assert get_gui_state(facade)["active_document"] == "Other"


def test_owned_adapters_have_no_runtime_locator_or_direct_gui_imports() -> None:
    for path in OWNED_ADAPTERS:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        assert not any(
            isinstance(node, (ast.Name, ast.Attribute))
            and getattr(node, "id", getattr(node, "attr", None)) == "_rpc_mod"
            for node in ast.walk(tree)
        ), path
        assert not any(
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "_rpc_mod"
            for node in ast.walk(tree)
        ), path
        assert not any(
            isinstance(node, (ast.Import, ast.ImportFrom))
            and (
                (
                    isinstance(node, ast.ImportFrom)
                    and (node.module or "") in {"FreeCAD", "FreeCADGui"}
                )
                or any(alias.name in {"FreeCAD", "FreeCADGui"} for alias in node.names)
            )
            for node in ast.walk(tree)
        ), path
        assert not any(
            isinstance(node, ast.Call)
            and (
                isinstance(node.func, ast.Name)
                and node.func.id == "__import__"
                or isinstance(node.func, ast.Attribute)
                and node.func.attr == "import_module"
            )
            for node in ast.walk(tree)
        ), path
        for function in (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            assert not any(
                isinstance(node, (ast.Import, ast.ImportFrom))
                for node in ast.walk(function)
            ), (path, function.name)
