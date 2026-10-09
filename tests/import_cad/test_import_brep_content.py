"""``import_brep`` must reject files that yield no shape.

Importing an STL through ``import_brep`` reported success and committed a
Part::Feature with a null shape: ``Shape.importBrep`` does not raise for a
file it cannot parse, it just leaves the shape empty.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import measure_io_actions
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.typed_runtime import (
    TypedMutationError,
)

pytestmark = pytest.mark.unit


class _Shape:
    parsed = True

    def __init__(self) -> None:
        self._null = True

    def importBrep(self, _path: str) -> None:
        self._null = not self.parsed

    def isNull(self) -> bool:
        return self._null

    @property
    def Vertexes(self) -> list[object]:
        return [] if self._null else [object()]


@pytest.fixture
def document(monkeypatch):
    added: list[str] = []
    monkeypatch.setattr(
        measure_io_actions,
        "load_module",
        lambda name: SimpleNamespace(Shape=_Shape),
    )

    def add_object(_type, name):
        added.append(name)
        return SimpleNamespace(Name=name, Label=name)

    return SimpleNamespace(addObject=add_object, added=added)


def test_a_parsed_brep_is_imported(document, tmp_path, monkeypatch):
    path = tmp_path / "part.brep"
    path.write_text("DBRep_DrawableShape")
    monkeypatch.setattr(_Shape, "parsed", True)

    result = measure_io_actions.import_brep(document, str(path), "Part")

    assert result["object"] == "Part"
    assert document.added == ["Part"]


def test_an_unparseable_file_is_rejected_without_an_object(document, tmp_path, monkeypatch):
    path = tmp_path / "body.stl"
    path.write_text("solid body\nendsolid body\n")
    monkeypatch.setattr(_Shape, "parsed", False)

    with pytest.raises(TypedMutationError) as caught:
        measure_io_actions.import_brep(document, str(path), "WrongFormat")

    assert caught.value.code == "INVALID_FILE"
    assert "body.stl" in str(caught.value)
    assert document.added == []


def test_a_missing_file_is_rejected(document, tmp_path):
    with pytest.raises(TypedMutationError) as caught:
        measure_io_actions.import_brep(document, str(tmp_path / "nope.brep"), "Part")

    assert caught.value.code == "FILE_NOT_FOUND"
    assert document.added == []
