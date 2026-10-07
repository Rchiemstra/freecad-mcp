"""File-included properties must verify against FreeCAD's transient copy.

``create_object`` with ``Image::ImagePlane`` and ``ImageFile`` was rolled back with
PROPERTY_NOT_UPDATED ("Created object property 'ImageFile' did not keep the assigned
value"). FreeCAD copies an ``App::PropertyFileIncluded`` value into the document's
transient directory, so the property reads back the copy's path, never the assigned one.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.property_postcondition import (
    IncludedFile,
    kept_property,
    property_kept_value,
)

pytestmark = pytest.mark.unit

PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-canvas-pixels"


class _Plane:
    """Stand-in for an ``Image::ImagePlane`` after FreeCAD included the file."""

    def __init__(self, image_file: str, label: str = "Canvas") -> None:
        self.ImageFile = image_file
        self.Label = label

    @staticmethod
    def getTypeIdOfProperty(name: str) -> str:
        return {"ImageFile": "App::PropertyFileIncluded"}.get(name, "App::PropertyString")


@pytest.fixture()
def assigned(tmp_path: Path) -> Path:
    source = tmp_path / "source" / "canvas.png"
    source.parent.mkdir()
    source.write_bytes(PNG_BYTES)
    return source


def _transient_copy(tmp_path: Path, name: str, data: bytes) -> Path:
    transient = tmp_path / "Document_transient"
    transient.mkdir(exist_ok=True)
    copy = transient / name
    copy.write_bytes(data)
    return copy


def test_included_file_reads_back_as_transient_copy(tmp_path, assigned):
    copy = _transient_copy(tmp_path, "canvas.png", PNG_BYTES)
    kept = kept_property(_Plane(str(copy)), "ImageFile")
    assert isinstance(kept, IncludedFile)
    assert kept.path == str(copy)


def test_transient_copy_with_same_bytes_keeps_the_assigned_file(tmp_path, assigned):
    copy = _transient_copy(tmp_path, "canvas.png", PNG_BYTES)
    plane = _Plane(str(copy))
    assert str(copy) != str(assigned)
    assert property_kept_value(None, str(assigned), kept_property(plane, "ImageFile"))


def test_renamed_copy_after_a_name_clash_still_verifies(tmp_path, assigned):
    # FreeCAD appends a counter when the transient directory already has the name.
    copy = _transient_copy(tmp_path, "canvas1.png", PNG_BYTES)
    plane = _Plane(str(copy))
    assert property_kept_value(None, str(assigned), kept_property(plane, "ImageFile"))


def test_copy_with_different_bytes_did_not_keep_the_file(tmp_path, assigned):
    copy = _transient_copy(tmp_path, "canvas.png", b"another image")
    plane = _Plane(str(copy))
    assert not property_kept_value(None, str(assigned), kept_property(plane, "ImageFile"))


def test_missing_copy_did_not_keep_the_file(tmp_path, assigned):
    plane = _Plane(str(tmp_path / "Document_transient" / "canvas.png"))
    assert not property_kept_value(None, str(assigned), kept_property(plane, "ImageFile"))


def test_cleared_file_property_matches_empty_value():
    assert property_kept_value(None, "", kept_property(_Plane(""), "ImageFile"))
    assert not property_kept_value(None, "", IncludedFile("/tmp/some/copy.png"))


def test_ordinary_string_property_still_compares_exactly(tmp_path, assigned):
    plane = _Plane(str(assigned), label="Canvas_01")
    kept = kept_property(plane, "Label")
    assert kept == "Canvas_01"
    assert property_kept_value(None, "Canvas_01", kept)
    assert not property_kept_value(None, "Canvas_02", kept)
