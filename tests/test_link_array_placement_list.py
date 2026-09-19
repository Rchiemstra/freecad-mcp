"""D-14: App::Link array layout through create_object / edit_object.

``PlacementList`` is an ``App::PropertyPlacementList``. ``set_object_property`` converted a
Placement dict only when the current value was a single Placement, so a list of dicts reached
FreeCAD raw ("type must be 'Matrix' or 'Placement', not dict") and every array layout was
rejected. Natively, FreeCAD only lays an array out from ``PlacementList`` when the list is set
before ``ElementCount`` creates the element objects, or when ``ShowElement`` is false. On an
array whose element objects exist, the list keeps its new value but the geometry does not move,
so a plain conversion would report success for a no-op. That case must be refused instead.
"""

from __future__ import annotations

import uuid

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
pytest.importorskip("Part")

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_object import (  # noqa: E402
    apply_create_object,
    build_create_object_request,
    read_create_object_result,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.edit_object import (  # noqa: E402
    apply_edit_object,
    build_edit_object_request,
    read_edit_object_result,
)
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.edit_object_mutation import (  # noqa: E402
    EditObjectError,
)
from addon.FreeCADMCP.rpc_server.property_mapper_ops.property_assignment import (  # noqa: E402
    set_object_property,
)

pytestmark = pytest.mark.unit


def _at(x):
    return {"Base": {"x": x, "y": 0, "z": 0}, "Rotation": {"Axis": {"x": 0, "y": 0, "z": 1}, "Angle": 0}}


LAYOUT = [_at(0), _at(20), _at(40)]


@pytest.fixture()
def doc():
    document = FreeCAD.newDocument(f"D14_{uuid.uuid4().hex[:8]}")
    box = document.addObject("Part::Box", "Src")
    box.Length = box.Width = box.Height = 10
    document.recompute()
    yield document
    FreeCAD.closeDocument(document.Name)


def _array(doc, *, show_element=True):
    link = doc.addObject("App::Link", "Arr")
    link.LinkedObject = doc.getObject("Src")
    link.ShowElement = show_element
    link.ElementCount = 3
    doc.recompute()
    return link


def _edit(doc, properties):
    request = build_edit_object_request(doc.Name, "Arr", properties)
    assert not isinstance(request, dict), request
    receipt = apply_edit_object(doc, request, set_object_property)
    doc.recompute()
    return receipt


def _x_span(obj):
    box = obj.Shape.BoundBox
    return round(box.XMin, 6), round(box.XMax, 6)


def test_placement_list_dicts_lay_out_a_hidden_element_array(doc):
    link = _array(doc, show_element=False)
    receipt = _edit(doc, {"PlacementList": LAYOUT})
    assert read_edit_object_result(doc, receipt).name == "Arr"
    assert [p.Base.x for p in link.PlacementList] == [0, 20, 40]
    assert _x_span(link) == (0, 50)


def test_show_element_off_and_placement_list_in_one_edit(doc):
    link = _array(doc)
    receipt = _edit(doc, {"ShowElement": False, "PlacementList": LAYOUT})
    assert read_edit_object_result(doc, receipt).name == "Arr"
    assert _x_span(link) == (0, 50)


def test_create_object_placement_list_before_element_count(doc):
    request = build_create_object_request(
        doc.Name,
        {
            "Name": "Arr",
            "Type": "App::Link",
            "Properties": {"LinkedObject": "Src", "PlacementList": LAYOUT, "ElementCount": 3},
        },
    )
    assert not isinstance(request, dict), request
    receipt = apply_create_object(doc, request, set_object_property)
    doc.recompute()
    assert read_create_object_result(doc, receipt).name == "Arr"
    link = doc.getObject("Arr")
    assert [e.Placement.Base.x for e in link.ElementList] == [0, 20, 40]
    assert _x_span(link) == (0, 50)


def test_placement_list_on_existing_shown_elements_is_refused(doc):
    link = _array(doc)
    before = [e.Placement.Base.x for e in link.ElementList]
    request = build_edit_object_request(doc.Name, "Arr", {"PlacementList": LAYOUT})
    with pytest.raises(ValueError, match="ShowElement"):
        apply_edit_object(doc, request, set_object_property)
    assert [e.Placement.Base.x for e in link.ElementList] == before


def test_reverted_placement_list_still_fails(doc):
    link = _array(doc, show_element=False)
    receipt = _edit(doc, {"PlacementList": LAYOUT})
    link.PlacementList = [FreeCAD.Placement()] * 3
    with pytest.raises(EditObjectError) as caught:
        read_edit_object_result(doc, receipt)
    assert caught.value.code == "PROPERTY_NOT_UPDATED"
