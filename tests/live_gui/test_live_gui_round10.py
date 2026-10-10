"""Live checks for the defects the tenth agent stress run reported."""

from __future__ import annotations

import re
import time
import zipfile

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_round5 import _payload, _rejected
from tests.live_gui.test_live_gui_stress import _part_body

pytestmark = pytest.mark.live_gui


def test_reload_of_a_non_zip_keeps_the_open_document(mcp, gui_log, live_gui):
    """A file that only starts with a zip header must not close the document."""

    destination = live_gui.workdir / "not_a_zip.FCStd"
    assert_ok(mcp.call("create_document", name="LiveBadReload"))
    assert_ok(mcp.call(
        "create_object",
        doc_name="LiveBadReload",
        obj_type="Part::Box",
        obj_name="Box",
    ))
    assert_ok(mcp.call(
        "save_document_as",
        selector={"document_name": "LiveBadReload"},
        destination=str(destination),
    ))
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not zipfile.is_zipfile(destination):
        time.sleep(0.2)
    destination.write_bytes(b"PK\x03\x04not-a-valid-fcstd")

    _rejected(mcp.call("reload_document", doc_name="LiveBadReload"), "not a FreeCAD document")
    listed = _payload(assert_ok(mcp.call("get_objects", doc_name="LiveBadReload")))
    assert {item["Name"] for item in listed["objects"]} >= {"Box"}
    assert_ok(mcp.call("close_document", doc_name="LiveBadReload"))
    assert_clean(gui_log)


def test_save_as_refuses_an_existing_destination(mcp, gui_log, live_gui):
    """overwrite false must not replace a file Save As already adopted."""

    destination = live_gui.workdir / "no_clobber.FCStd"
    assert_ok(mcp.call("create_document", name="LiveNoClobber"))
    assert_ok(mcp.call(
        "create_object",
        doc_name="LiveNoClobber",
        obj_type="Part::Box",
        obj_name="Box",
    ))
    assert_ok(mcp.call(
        "save_document_as",
        selector={"document_name": "LiveNoClobber"},
        destination=str(destination),
        overwrite=False,
    ))
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and not zipfile.is_zipfile(destination):
        time.sleep(0.2)
    original = destination.read_bytes()

    _rejected(
        mcp.call(
            "save_document_as",
            selector={"document_name": "LiveNoClobber"},
            destination=str(destination),
            overwrite=False,
        ),
        "overwrite=False",
    )
    assert destination.read_bytes() == original
    assert_ok(mcp.call(
        "save_document_as",
        selector={"document_name": "LiveNoClobber"},
        destination=str(destination),
        overwrite=True,
    ))
    assert_ok(mcp.call("close_document", doc_name="LiveNoClobber"))
    assert_clean(gui_log)


def test_gui_state_and_view_follow_the_active_document(mcp, gui_log):
    """activate_document must win over the document that was created last."""

    assert_ok(mcp.call("create_document", name="LiveViewA"))
    assert_ok(mcp.call(
        "create_object",
        doc_name="LiveViewA",
        obj_type="Part::Box",
        obj_name="BoxA",
    ))
    assert_ok(mcp.call("create_document", name="LiveViewB"))
    assert_ok(mcp.call(
        "create_object",
        doc_name="LiveViewB",
        obj_type="Part::Box",
        obj_name="BoxB",
    ))
    assert_ok(mcp.call("activate_document", doc_name="LiveViewA"))

    state = _payload(assert_ok(mcp.call("get_gui_state")))
    assert state["active_document"] == "LiveViewA"
    assert_ok(mcp.call("get_view", view_name="Isometric", focus_object="BoxA"))
    assert_ok(mcp.call("get_view", view_name="Isometric"))
    _rejected(
        mcp.call("get_view", view_name="Isometric", focus_object="BoxB"),
        "not present",
    )
    assert_ok(mcp.call(
        "get_view",
        view_name="Isometric",
        focus_object="BoxB",
        document="LiveViewB",
    ))
    assert_ok(mcp.call("close_document", doc_name="LiveViewA"))
    assert_ok(mcp.call("close_document", doc_name="LiveViewB"))
    assert_clean(gui_log)


def _printed(mcp, doc_name: str, code: str) -> str:
    result = assert_ok(mcp.call(
        "execute_code",
        document=doc_name,
        execution_mode="worker",
        read_only=True,
        code=code,
    ))
    match = re.search(r"Output:\s*(.+)", result.text)
    assert match, result.text[:600]
    return match.group(1).strip()


def test_midpoint_datums_offsets_and_attachment_preview(mcp, gui_log):
    """A two-face datum sits on the bisector, and preview returns that support."""

    assert_ok(mcp.call("create_document", name="LiveDatum"))
    assert_ok(mcp.call("body_create", doc_name="LiveDatum", body_name="Body"))
    assert_ok(mcp.call(
        "sketch_create",
        doc_name="LiveDatum",
        sketch_name="BaseSketch",
        body_name="Body",
        attach_to="XY_Plane",
    ))
    assert_ok(mcp.call(
        "sketch_add_rectangle",
        doc_name="LiveDatum",
        sketch_name="BaseSketch",
        x1=0, y1=0, x2=40, y2=20,
    ))
    assert_ok(mcp.call(
        "pad_feature",
        doc_name="LiveDatum",
        sketch_name="BaseSketch",
        pad_name="Pad",
        length=10,
        body_name="Body",
        strict=True,
    ))
    faces = _printed(
        mcp,
        "LiveDatum",
        (
            "import FreeCAD as App\n"
            "pad = App.getDocument('LiveDatum').getObject('Pad')\n"
            "names = []\n"
            "for index, face in enumerate(pad.Shape.Faces, 1):\n"
            "    u0, u1, v0, v1 = face.ParameterRange\n"
            "    normal = face.normalAt((u0 + u1) / 2, (v0 + v1) / 2)\n"
            "    if abs(normal.x) > 0.9:\n"
            "        names.append('Pad:Face%d' % index)\n"
            "print(','.join(names))\n"
        ),
    )
    face_a, face_b = faces.split(",")
    assert_ok(mcp.call(
        "create_datum_plane",
        doc_name="LiveDatum",
        plane_name="MidX",
        body_name="Body",
        mode="midpoint_between_faces",
        face_a=face_a,
        face_b=face_b,
    ))
    midpoint = float(_printed(
        mcp,
        "LiveDatum",
        "import FreeCAD as App\n"
        "plane = App.getDocument('LiveDatum').getObject('MidX')\n"
        "print('%.3f %s' % (plane.Placement.Base.x, plane.MapMode))\n",
    ).split()[0])
    assert abs(midpoint - 20.0) < 1.0
    assert_ok(mcp.call(
        "create_datum_plane",
        doc_name="LiveDatum",
        plane_name="Between",
        body_name="Body",
        mode="between_parallel_planes",
        face_a=face_a,
        face_b=face_b,
    ))
    between = float(_printed(
        mcp,
        "LiveDatum",
        "import FreeCAD as App\n"
        "plane = App.getDocument('LiveDatum').getObject('Between')\n"
        "print('%.3f %s' % (plane.Placement.Base.x, plane.MapMode))\n",
    ).split()[0])
    assert abs(between - 20.0) < 1.0
    assert_ok(mcp.call(
        "create_datum_plane",
        doc_name="LiveDatum",
        plane_name="OffShort",
        body_name="Body",
        mode="offset_from_face",
        face_a=face_a,
        offset_along_normal=[20],
    ))
    assert_ok(mcp.call(
        "create_datum_plane",
        doc_name="LiveDatum",
        plane_name="OffAxis",
        body_name="Body",
        mode="offset_from_face",
        face_a=face_a,
        offset_along_normal=[20, 0, 0],
    ))
    offsets = _printed(
        mcp,
        "LiveDatum",
        (
            "import FreeCAD as App\n"
            "doc = App.getDocument('LiveDatum')\n"
            "values = []\n"
            "for name in ('OffShort', 'OffAxis'):\n"
            "    base = doc.getObject(name).AttachmentOffset.Base\n"
            "    values.append('%.3f' % base.z)\n"
            "print(' '.join(values))\n"
        ),
    )
    assert [float(item) for item in offsets.split()] == [20.0, 20.0]
    preview = _payload(assert_ok(mcp.call(
        "preview_attachment",
        doc_name="LiveDatum",
        datum_name="MidX",
    )))
    assert preview["success"] is True
    assert any(entry.get("object") == "Pad" for entry in preview["support"])
    assert_ok(mcp.call("close_document", doc_name="LiveDatum"))
    assert_clean(gui_log)


def test_delete_names_link_dependents(mcp, gui_log):
    """A body refusal must name links and link-array elements, not only features."""

    assert_ok(mcp.call("create_document", name="LiveLinks"))
    assert_ok(mcp.call("body_create", doc_name="LiveLinks", body_name="Body"))
    assert_ok(mcp.call(
        "create_object",
        doc_name="LiveLinks",
        obj_type="App::Link",
        obj_name="BodyLink",
        obj_properties={"LinkedObject": "Body"},
    ))
    assert_ok(mcp.call(
        "create_object",
        doc_name="LiveLinks",
        obj_type="App::Link",
        obj_name="BodyArray",
        obj_properties={"LinkedObject": "Body", "ElementCount": 3, "ShowElement": True},
    ))
    refused = mcp.call("delete_object", doc_name="LiveLinks", obj_name="Body")
    assert not refused.ok, refused.text[:600]
    for name in ("BodyLink", "BodyArray", "BodyArray_i0", "BodyArray_i1", "BodyArray_i2"):
        assert name in refused.text, refused.text[:800]
    listed = _payload(assert_ok(mcp.call("get_objects", doc_name="LiveLinks")))
    assert {item["Name"] for item in listed["objects"]} >= {
        "Body", "BodyLink", "BodyArray", "BodyArray_i0",
    }
    assert_ok(mcp.call("close_document", doc_name="LiveLinks"))
    assert_clean(gui_log)


def test_chamfer_and_fillet_name_a_non_c0_edge(mcp, gui_log):
    """A smooth edge must say which edge is not C0, and a sharp edge still dresses."""

    _part_body(mcp, "LiveC0", length=10)
    assert_ok(mcp.call(
        "fillet_feature",
        doc_name="LiveC0",
        base_feature="Pad",
        fillet_name="Fillet",
        radius=1,
        edge_refs=["Edge1"],
        body_name="Body",
    ))
    smooth = None
    sharp = None
    for index in range(1, 18):
        edge = f"Edge{index}"
        chamfer = mcp.call(
            "chamfer_feature",
            doc_name="LiveC0",
            base_feature="Fillet",
            chamfer_name="Probe",
            size=0.4,
            edge_refs=[edge],
            body_name="Body",
        )
        if chamfer.ok:
            sharp = edge
            assert_ok(mcp.call("undo", doc_name="LiveC0"))
        elif "not C0 continuous" in chamfer.text and edge in chamfer.text:
            smooth = edge
            break
    assert smooth, "no edge reported as not C0 continuous"
    fillet = mcp.call(
        "fillet_feature",
        doc_name="LiveC0",
        base_feature="Fillet",
        fillet_name="Again",
        radius=0.4,
        edge_refs=[smooth],
        body_name="Body",
    )
    assert not fillet.ok
    assert smooth in fillet.text and "not C0 continuous" in fillet.text
    assert sharp
    assert_ok(mcp.call(
        "chamfer_feature",
        doc_name="LiveC0",
        base_feature="Fillet",
        chamfer_name="Sharp",
        size=0.4,
        edge_refs=[sharp],
        body_name="Body",
    ))
    assert_ok(mcp.call("close_document", doc_name="LiveC0"))
    assert_clean(gui_log)


def test_a_techdraw_page_is_not_captured_as_an_empty_3d_view(mcp, gui_log):
    """A drawing sheet is not a 3D shape, so the 3D camera must say so."""

    assert_ok(mcp.call("create_document", name="LiveSheet"))
    assert_ok(mcp.call(
        "create_object",
        doc_name="LiveSheet",
        obj_type="TechDraw::DrawPage",
        obj_name="Page",
    ))
    _rejected(
        mcp.call(
            "get_view",
            view_name="Isometric",
            document="LiveSheet",
            focus_object="Page",
        ),
        "TechDraw pages are not in the 3D view",
    )
    _rejected(
        mcp.call("get_view", view_name="Isometric", document="LiveSheet"),
        "TechDraw pages are not in the 3D view",
    )
    assert_ok(mcp.call("close_document", doc_name="LiveSheet"))
    assert_clean(gui_log)


def test_measure_volume_rejects_a_wire_sketch(mcp, gui_log):
    """A sketch is a wire, so volume must say it has no solids."""

    assert_ok(mcp.call("create_document", name="LiveVol"))
    assert_ok(mcp.call("body_create", doc_name="LiveVol", body_name="Body"))
    assert_ok(mcp.call(
        "sketch_create", doc_name="LiveVol", sketch_name="Sk", body_name="Body"
    ))
    assert_ok(mcp.call(
        "sketch_add_rectangle",
        doc_name="LiveVol",
        sketch_name="Sk",
        x1=0,
        y1=0,
        x2=20,
        y2=10,
    ))
    _rejected(
        mcp.call("measure_volume", doc_name="LiveVol", obj_name="Sk"),
        "no solids",
    )
    assert_ok(mcp.call(
        "pad_feature",
        doc_name="LiveVol",
        sketch_name="Sk",
        pad_name="Pad",
        length=5,
        body_name="Body",
    ))
    volume = assert_ok(mcp.call("measure_volume", doc_name="LiveVol", obj_name="Pad"))
    assert volume.payload["volume_mm3"] == pytest.approx(20 * 10 * 5)
    assert_ok(mcp.call("close_document", doc_name="LiveVol"))
    assert_clean(gui_log)
