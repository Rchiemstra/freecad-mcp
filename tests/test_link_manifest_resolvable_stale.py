"""Snapshot link manifest tolerates FreeCAD-resolvable stale subelement names."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from addon.FreeCADMCP.rpc_server.snapshot_service_ops.link_manifest import (
    _append_reference_rows,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def freecad_documents(monkeypatch):
    documents = {}

    def get_document(name):
        return documents.get(name)

    freecad = SimpleNamespace(getDocument=get_document)
    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.snapshot_service_ops.link_manifest.FreeCAD",
        freecad,
    )
    return documents


def test_resolvable_stale_subelement_is_not_marked_invalid(freecad_documents):
    edge = SimpleNamespace(isNull=lambda: False)
    target = SimpleNamespace(
        Name="Target",
        Document=SimpleNamespace(Name="Model"),
        Shape=SimpleNamespace(Faces=[edge], Edges=[], Vertexes=[]),
        getSubObject=lambda name: edge if name == "Face7" else None,
    )
    doc = SimpleNamespace(Name="Model", Objects=[])
    freecad_documents["Model"] = SimpleNamespace(
        getObject=lambda name: target if name == "Target" else None
    )
    links: list = []
    broken: list = []
    invalid: list = []

    _append_reference_rows(
        doc=doc,
        obj=SimpleNamespace(Name="Holder"),
        prop="Support",
        prop_type="App::PropertyLinkSub",
        refs=[(target, ["Face7"])],
        open_names={"Model"},
        links=links,
        broken=broken,
        invalid_subelements=invalid,
    )

    assert invalid == []
    assert broken == []
    assert len(links) == 1


def test_truly_invalid_subelement_still_recorded(freecad_documents):
    target = SimpleNamespace(
        Name="Target",
        Document=SimpleNamespace(Name="Model"),
        Shape=SimpleNamespace(Faces=[], Edges=[], Vertexes=[]),
        getSubObject=lambda _name: None,
    )
    doc = SimpleNamespace(Name="Model", Objects=[])
    freecad_documents["Model"] = SimpleNamespace(
        getObject=lambda name: target if name == "Target" else None
    )
    invalid: list = []

    _append_reference_rows(
        doc=doc,
        obj=SimpleNamespace(Name="Holder"),
        prop="Support",
        prop_type="App::PropertyLinkSub",
        refs=[(target, ["Face999"])],
        open_names={"Model"},
        links=[],
        broken=[],
        invalid_subelements=invalid,
    )

    assert invalid == ["Model.Target.Face999"]
