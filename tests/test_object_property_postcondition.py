"""D-21: create_object / edit_object must verify converted properties, not raw JSON.

``set_object_property`` converts ``"LinkedObject": "Leg"`` into the document object ``Leg`` and
a Placement dict into ``FreeCAD.Placement``. The post-recompute check compared the raw JSON
value with the converted one, so every link or placement property failed with
"did not keep the assigned value" and the call was rolled back (observed natively while
creating ``App::Link`` chair legs). A property that really did not keep its value must still fail.
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
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.create_object_mutation import (  # noqa: E402
    CreateObjectError,
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

PLACEMENT = {"Base": {"x": -380, "y": 0, "z": 0}, "Rotation": {"Axis": {"x": 0, "y": 0, "z": 1}, "Angle": 90}}


@pytest.fixture()
def doc():
    document = FreeCAD.newDocument(f"D21_{uuid.uuid4().hex[:8]}")
    document.addObject("Part::Box", "Leg")
    document.recompute()
    yield document
    FreeCAD.closeDocument(document.Name)


def _create(doc, properties):
    request = build_create_object_request(
        doc.Name, {"Name": "LegFL", "Type": "App::Link", "Properties": properties}
    )
    assert not isinstance(request, dict), request
    receipt = apply_create_object(doc, request, set_object_property)
    doc.recompute()
    return receipt


def test_link_and_placement_properties_verify(doc):
    receipt = _create(doc, {"LinkedObject": "Leg", "Placement": PLACEMENT})
    inspection = read_create_object_result(doc, receipt)
    assert inspection.name == "LegFL"
    link = doc.getObject("LegFL")
    assert link.LinkedObject is doc.getObject("Leg")
    assert link.Placement.Base == FreeCAD.Vector(-380, 0, 0)


def test_property_that_did_not_keep_its_value_still_fails(doc):
    receipt = _create(doc, {"LinkedObject": "Leg", "Placement": PLACEMENT})
    doc.getObject("LegFL").Placement = FreeCAD.Placement()  # something reverted it
    with pytest.raises(CreateObjectError) as caught:
        read_create_object_result(doc, receipt)
    assert caught.value.code == "PROPERTY_NOT_UPDATED"


def test_wrong_link_target_still_fails(doc):
    doc.addObject("Part::Box", "Other")
    receipt = _create(doc, {"LinkedObject": "Leg"})
    doc.getObject("LegFL").LinkedObject = doc.getObject("Other")
    with pytest.raises(CreateObjectError):
        read_create_object_result(doc, receipt)


def test_edit_object_placement_dict_verifies(doc):
    request = build_edit_object_request(doc.Name, "Leg", {"Placement": PLACEMENT})
    assert not isinstance(request, dict), request
    receipt = apply_edit_object(doc, request, set_object_property)
    doc.recompute()
    assert read_edit_object_result(doc, receipt).name == "Leg"


def test_edit_object_reverted_placement_fails(doc):
    request = build_edit_object_request(doc.Name, "Leg", {"Placement": PLACEMENT})
    receipt = apply_edit_object(doc, request, set_object_property)
    doc.getObject("Leg").Placement = FreeCAD.Placement()
    with pytest.raises(EditObjectError):
        read_edit_object_result(doc, receipt)
