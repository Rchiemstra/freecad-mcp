"""Documented FEM types are ObjectsFem proxies, not addObject type names."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.property_postcondition import (
    property_kept_value,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.typed_rpc_document import add_object
from addon.FreeCADMCP.rpc_server.property_mapper_ops.reference_parsing import (
    resolve_references,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("requested", "maker"),
    [
        ("Fem::AnalysisPython", "makeAnalysis"),
        ("Fem::MaterialCommon", "makeMaterialSolid"),
        ("Fem::FemMeshGmsh", "makeMeshGmsh"),
    ],
)
def test_documented_fem_types_are_not_passed_to_add_object(monkeypatch, requested, maker):
    import ObjectsFem

    created = SimpleNamespace(Name="Made", TypeId="Fem::FemAnalysis")

    def factory(_document, name):
        created.Name = name
        return created

    monkeypatch.setattr(ObjectsFem, maker, factory)
    document = SimpleNamespace(
        addObject=lambda *_args: (_ for _ in ()).throw(
            RuntimeError(f"'{requested}' is not a document object type")
        )
    )

    assert add_object(document, requested, "Made") is created


def test_a_reference_dict_matches_the_link_sub_tuple_freecad_keeps():
    box = SimpleNamespace(Name="Box")
    document = SimpleNamespace(getObject=lambda name: box if name == "Box" else None)
    expected = [{"object_name": "Box", "face": "Face1"}]
    resolved = resolve_references(document, expected)

    assert property_kept_value(document, expected, resolved)
    assert resolved == [(box, ("Face1",))]
