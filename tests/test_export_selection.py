"""Whole-document export must pick real, top-level geometry.

Exporting a document with a PartDesign Body to STEP failed with "Cannot open
file: : <path>.tmp.step": every object with a Shape was exported, including the
Body's origin axes and planes (+/-1e100 boxes) and the features already inside
the Body. ``obj_names=[]`` meant the same, and mesh_deviation=0 leaked a raw
OpenCASCADE error.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import measure_io_actions
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.export_step import (
    build_export_step_request,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.export_stl import (
    build_export_stl_request,
)

pytestmark = pytest.mark.unit


def _box(lo: float, hi: float) -> SimpleNamespace:
    return SimpleNamespace(
        isValid=lambda: True,
        XMin=lo, YMin=lo, ZMin=lo, XMax=hi, YMax=hi, ZMax=hi,
    )


def _object(name, type_id, *, bound=(0, 10), parent=None, visible=True):
    shape = SimpleNamespace(isNull=lambda: False, BoundBox=_box(*bound))
    return SimpleNamespace(
        Name=name,
        TypeId=type_id,
        Shape=shape,
        Visibility=visible,
        isDerivedFrom=lambda t, type_id=type_id: t == type_id
        or (t == "App::DatumElement" and type_id in ("App::Line", "App::Plane")),
        getParentGeoFeatureGroup=lambda parent=parent: parent,
    )


def test_whole_document_exports_visible_top_level_shapes():
    body = _object("Body", "PartDesign::Body")
    objects = [
        body,
        _object("Origin", "App::Origin", parent=body),
        _object("X_Axis", "App::Line", bound=(-1e100, 1e100), parent=body),
        _object("XY_Plane", "App::Plane", bound=(-1e100, 1e100), parent=body),
        _object("Sketch", "Sketcher::SketchObject", parent=body),
        _object("Pad", "PartDesign::Pad", parent=body),
        _object("Tool", "Part::Box", visible=False),
        _object("Loose", "Part::Box"),
    ]
    document = SimpleNamespace(Objects=objects, getObject=lambda name: None)

    selected = measure_io_actions._exportable_objects(document, None)

    assert [obj.Name for obj in selected] == ["Body", "Loose"]


@pytest.mark.parametrize(
    "build",
    [
        lambda: build_export_step_request("Doc", "/tmp/out.step", []),
        lambda: build_export_stl_request("Doc", "/tmp/out.stl", [], 0.1),
    ],
)
def test_empty_obj_names_is_an_invalid_argument(build):
    failure = build()

    assert isinstance(failure, dict)
    assert failure["error_code"] == "INVALID_ARGUMENT"


@pytest.mark.parametrize("deviation", [0, -5, float("nan"), float("inf")])
def test_mesh_deviation_must_be_positive(deviation):
    failure = build_export_stl_request("Doc", "/tmp/out.stl", None, deviation)

    assert isinstance(failure, dict)
    assert failure["error_code"] == "INVALID_ARGUMENT"
    assert "mesh_deviation" in failure["error"]
