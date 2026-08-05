"""Phase 16 resilience coverage for authenticated document/view adapters."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.gui_document_runtime import (
    open_document as runtime_open_document,
)
from addon.FreeCADMCP.rpc_server.gui_document_runtime import (
    reload_document as runtime_reload_document,
)
from addon.FreeCADMCP.rpc_server.gui_personal_registry import PersonalViewRegistry
from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops.dispatch_core import (
    dispatch as dispatch_core,
)
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.collaboration_context_dispatch import (
    GuiDispatchFailure,
)
from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops.document_ops import (
    list_documents,
    open_document,
    reload_document,
)

pytestmark = pytest.mark.unit


class _Cancelled(Exception):
    pass


class _Document:
    def __init__(self, name, filename=""):
        self.Name = name
        self.Label = name
        self.FileName = filename


class _GuiModule:
    def __init__(self, documents):
        self._documents = documents
        self.ActiveDocument = None

    def getDocument(self, name):
        return self._documents.get(name)


class _FreeCAD:
    def __init__(self, documents, *, opened=None, open_error=None):
        self.documents = documents
        self.ActiveDocument = next(iter(documents.values()), None)
        self._opened = opened
        self._open_error = open_error

    def getDocument(self, name):
        return self.documents.get(name)

    def setActiveDocument(self, name):
        self.ActiveDocument = self.documents.get(name)

    def listDocuments(self):
        return dict(self.documents)

    def closeDocument(self, name):
        self.documents.pop(name, None)

    def openDocument(self, _path):
        if self._open_error is not None:
            raise self._open_error
        if self._opened is not None:
            self.documents[self._opened.Name] = self._opened
            self.ActiveDocument = self._opened
        return self._opened


def test_transport_dispatch_is_policy_free_and_calls_the_public_method_once() -> None:
    calls = []
    facade = SimpleNamespace(
        get_gui_state=lambda: calls.append("get_gui_state") or {"ok": True}
    )

    assert dispatch_core(facade, "get_gui_state", ()) == {"ok": True}
    assert calls == ["get_gui_state"]


def test_transport_dispatch_rejects_private_and_unknown_methods() -> None:
    facade = SimpleNamespace(_private=lambda: None)
    with pytest.raises(Exception, match="not supported"):
        dispatch_core(facade, "_private", ())
    with pytest.raises(Exception, match="not supported"):
        dispatch_core(facade, "missing", ())


def test_list_documents_preserves_structured_dispatch_failure() -> None:
    failure = {
        "success": False,
        "error_code": "GUI_COMPLETION_UNCERTAIN",
        "error": "late",
        "completion_uncertain": True,
    }
    facade = SimpleNamespace(
        _gui_collaborators=SimpleNamespace(
            dispatch_gui=lambda _facade, _callback, **_kwargs: dict(failure),
            freecad=SimpleNamespace(listDocuments=dict),
        )
    )

    with pytest.raises(GuiDispatchFailure) as caught:
        list_documents(facade)

    assert caught.value.result == failure


def test_open_native_rejection_keeps_its_public_error_code() -> None:
    document = _Document("Model")
    closed = []
    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(
            listDocuments=dict,
            getDocument=lambda _name: document,
            closeDocument=closed.append,
        ),
        dispatch_gui=lambda _facade, callback, **_kwargs: callback(),
        get_request_identity=lambda: {
            "authenticated_session_id": "session",
            "instance_id": "runtime",
        },
        open_document=lambda _path: {"ok": True, "document": "Model"},
        snapshot_personal_view_context=lambda *_args: None,
        snapshot_view_context=lambda _name: (_ for _ in ()).throw(
            RuntimeError("presentation")
        ),
        reraise_if_cancelled=lambda _error: None,
        redact_rpc_diagnostic=lambda error: f"redacted:{error}",
    )
    facade = SimpleNamespace(_gui_collaborators=collaborators)

    assert open_document(facade, "/model.FCStd") == {
        "ok": False,
        "success": False,
        "error_code": "DUPLICATE_OR_INVALID_DOCUMENT_OPEN",
        "error": "redacted:presentation",
    }
    assert closed == ["Model"]


def test_post_open_cancellation_rolls_back_actor_context_then_closes() -> None:
    class _CancellingRegistry(PersonalViewRegistry):
        def activate(self, actor_id, document_name, metadata=None):
            raise _Cancelled("post-open")

    human = _Document("Human")
    model = _Document("Model")
    documents = {"Human": human}
    prior_model = {"active_document": "Model", "temporary_overlays": []}
    prior_human = {
        "active_document": "Human",
        "temporary_overlays": [{"kind": "active_document_target"}],
    }
    contexts = {
        ("Model", "runtime"): dict(prior_model),
        ("Human", "runtime"): dict(prior_human),
    }
    closed = []
    registry = _CancellingRegistry()
    registry.restore_target("runtime", "Human")

    def store(name, actor, context):
        contexts[(name, actor)] = dict(context)

    collaborators = SimpleNamespace(
        freecad=SimpleNamespace(
            listDocuments=lambda: dict(documents),
            getDocument=documents.get,
            closeDocument=lambda name: closed.append(name) or documents.pop(name),
        ),
        dispatch_gui=lambda _facade, callback, **_kwargs: callback(),
        get_request_identity=lambda: {
            "authenticated_session_id": "session",
            "instance_id": "runtime",
        },
        open_document=lambda _path: (
            documents.__setitem__("Model", model) or {"ok": True, "document": "Model"}
        ),
        snapshot_view_context=lambda name: {"active_document": name},
        snapshot_personal_view_context=lambda name, actor: (
            dict(contexts[(name, actor)]) if (name, actor) in contexts else None
        ),
        store_personal_view_context=store,
        restore_personal_view_context=lambda name, actor, prior: (
            contexts.pop((name, actor), None)
            if prior is None
            else contexts.__setitem__((name, actor), dict(prior))
        ),
        personal_view_registry=registry,
        reraise_if_cancelled=lambda error: (
            (_ for _ in ()).throw(error) if isinstance(error, _Cancelled) else None
        ),
        redact_rpc_diagnostic=lambda error: f"redacted:{error}",
    )
    facade = SimpleNamespace(_gui_collaborators=collaborators)

    with pytest.raises(_Cancelled, match="post-open"):
        open_document(facade, "/model.FCStd")

    assert contexts[("Model", "runtime")] == prior_model
    assert contexts[("Human", "runtime")] == prior_human
    assert registry.current_target("runtime") == "Human"
    assert closed == ["Model"]


@pytest.mark.parametrize("opened, error", [(None, None), (None, RuntimeError("open"))])
def test_runtime_open_restores_human_active_document_after_null_or_failure(
    opened, error
) -> None:
    human = _Document("Human")
    freecad = _FreeCAD({"Human": human}, opened=opened, open_error=error)
    gui = _GuiModule(freecad.documents)

    if error is None:
        assert runtime_open_document(freecad, gui, "/model.FCStd")["ok"] is False
    else:
        with pytest.raises(RuntimeError, match="open"):
            runtime_open_document(freecad, gui, "/model.FCStd")

    assert freecad.ActiveDocument is human
    assert gui.ActiveDocument is human


def test_runtime_reload_restores_human_active_document_after_failed_reopen(
    tmp_path,
) -> None:
    human = _Document("Human")
    model_path = tmp_path / "model.FCStd"
    model_path.write_text("placeholder", encoding="utf-8")
    model = _Document("Model", str(model_path))
    freecad = _FreeCAD({"Human": human, "Model": model})
    gui = _GuiModule(freecad.documents)

    assert (
        runtime_reload_document(
            freecad,
            gui,
            "Model",
        )
        == f"FreeCAD did not reopen '{model_path}'."
    )
    assert freecad.ActiveDocument is human
    assert gui.ActiveDocument is human


def test_null_open_and_reopen_sentinels_survive_restore_failures(tmp_path) -> None:
    human = _Document("Human")
    errors = []
    freecad = _FreeCAD({"Human": human})
    freecad.Console = SimpleNamespace(PrintError=errors.append)
    gui = _GuiModule(freecad.documents)
    gui.getDocument = lambda _name: (_ for _ in ()).throw(RuntimeError("restore"))

    open_failure = runtime_open_document(freecad, gui, "/missing.FCStd")
    assert open_failure == {"ok": False, "error": "Failed to open: /missing.FCStd"}

    model_path = tmp_path / "model.FCStd"
    model_path.write_text("placeholder", encoding="utf-8")
    model = _Document("Model", str(model_path))
    freecad.documents["Model"] = model
    reload_failure = runtime_reload_document(
        freecad,
        gui,
        "Model",
    )

    assert reload_failure == f"FreeCAD did not reopen '{model_path}'."
    assert len(errors) == 2


def test_reload_restores_actor_context_when_reload_raises() -> None:
    prior = {"active_document": "Model", "selection_paths": ["Box.Face1"]}
    calls = []
    document = _Document("Model")
    collaborators = SimpleNamespace(
        dispatch_gui=lambda _facade, callback, **_kwargs: callback(),
        get_request_identity=lambda: {
            "authenticated_session_id": "session",
            "instance_id": "runtime",
        },
        snapshot_personal_view_context=lambda *_args: dict(prior),
        restore_personal_view_context=lambda *args: calls.append(args),
        reload_document=lambda _name: (_ for _ in ()).throw(RuntimeError("reload")),
        freecad=SimpleNamespace(getDocument=lambda _name: document),
        reraise_if_cancelled=lambda _error: None,
        redact_rpc_diagnostic=lambda error: f"redacted:{error}",
    )
    facade = SimpleNamespace(
        _gui_collaborators=collaborators,
        _adapt_gui_mutation_result=lambda value, **_kwargs: value,
    )

    assert reload_document(facade, "Model") == {
        "ok": False,
        "error": "redacted:reload",
    }
    assert calls == [("Model", "runtime", prior)]


def test_returned_reload_failure_survives_actor_restore_failure(caplog) -> None:
    prior = {"active_document": "Model"}
    collaborators = SimpleNamespace(
        dispatch_gui=lambda _facade, callback, **_kwargs: callback(),
        get_request_identity=lambda: {
            "authenticated_session_id": "session",
            "instance_id": "runtime",
        },
        snapshot_personal_view_context=lambda *_args: dict(prior),
        restore_personal_view_context=lambda *_args: (_ for _ in ()).throw(
            RuntimeError("restore-secret")
        ),
        reload_document=lambda _name: "original reload failure",
        freecad=SimpleNamespace(getDocument=lambda _name: _Document("Model")),
        reraise_if_cancelled=lambda _error: None,
        redact_rpc_diagnostic=lambda _error: "redacted-secondary",
    )
    facade = SimpleNamespace(
        _gui_collaborators=collaborators,
        _adapt_gui_mutation_result=lambda value, **_kwargs: value,
    )

    assert reload_document(facade, "Model") == "original reload failure"
    assert "redacted-secondary" in caplog.text
    assert "restore-secret" not in caplog.text
