"""D-16: typed read queries must hand ``recompute_and_wait`` a document name.

The production collaborator is ``gui_tools_ops.recompute_wait.recompute_and_wait(doc_name: str)``,
which calls ``FreeCAD.getDocument(doc_name)``. Passing the ``App.Document`` itself raised
``TypeError: argument 1 must be str, not App.Document`` on every typed query that recomputes
(spreadsheet_list_aliases, bounding_box, measure_volume, get_document_tree, ...).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.policy_runtime import optional_recompute
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.spreadsheet_list_aliases import (
    run_spreadsheet_list_aliases,
)
from tests.typed_rpc_fakes import FakeDocument, collaborators

pytestmark = pytest.mark.unit


def _strict_recompute_and_wait(calls: list[str]):
    """Mirror FreeCAD.getDocument: only a str document name is accepted."""

    def recompute_and_wait(doc_name):
        if not isinstance(doc_name, str):
            raise TypeError(f"argument 1 must be str, not {type(doc_name).__name__}")
        calls.append(doc_name)
        return {"ok": True}

    return recompute_and_wait


def test_optional_recompute_passes_document_name_to_runner():
    calls: list[str] = []
    document = FakeDocument([], name="Chair")
    optional_recompute(SimpleNamespace(recompute_and_wait=_strict_recompute_and_wait(calls)), document)
    assert calls == ["Chair"]


def test_optional_recompute_falls_back_to_document_recompute():
    document = SimpleNamespace(Name="Chair", recomputed=False)
    document.recompute = lambda: setattr(document, "recomputed", True)
    optional_recompute(SimpleNamespace(), document)
    assert document.recomputed is True


def test_spreadsheet_list_aliases_with_real_recompute_signature():
    events: list[str] = []
    document = FakeDocument(events, name="Chair")
    document.objects["Dims"] = SimpleNamespace(
        Name="Dims",
        Label="Dims",
        TypeId="Spreadsheet::Sheet",
        getAlias=lambda addr: {"B1": "seat_w", "B2": "seat_d"}.get(addr),
        getNonEmptyCells=lambda: ["B1", "B2"],
    )
    collab, _api = collaborators(document, events)
    calls: list[str] = []
    collab.recompute_and_wait = _strict_recompute_and_wait(calls)

    result = run_spreadsheet_list_aliases(collab, "Chair", "Dims")

    assert result["success"] is True, result
    assert result["aliases"] == {"seat_w": "B1", "seat_d": "B2"}
    assert calls == ["Chair"]
