"""Live checks for the defects a fifth agent stress run reported.

Each call used to succeed silently, leak an OpenCASCADE message, or make
FreeCAD print an error; now it is rejected up front with its reason, or it
reports what it actually did.
"""

from __future__ import annotations

import re

import pytest

from tests.live_gui._support import assert_clean, assert_ok
from tests.live_gui.test_live_gui_stress import _part_body

pytestmark = pytest.mark.live_gui


def _payload(result):
    assert result.payload is not None, result.text[:600]
    return result.payload


def _rejected(result, reason):
    assert not result.ok, result.text[:600]
    assert reason in result.text, result.text[:600]


def test_dress_up_rejects_missing_edges_and_oversize_values(mcp, gui_log):
    """Edge9999 made FreeCAD log "Invalid edge link"; size 5000 leaked
    "BRep_API: command not done"."""

    _part_body(mcp, "LiveDress")
    _rejected(mcp.call("fillet_feature", doc_name="LiveDress", base_feature="Pad",
                       fillet_name="F", radius=1, edge_refs=["Edge9999"], body_name="Body"),
              "'Edge9999' does not exist on 'Pad'")
    _rejected(mcp.call("chamfer_feature", doc_name="LiveDress", base_feature="Pad",
                       chamfer_name="C", size=5000, edge_refs=["Edge1"], body_name="Body"),
              "size 5000 does not fit on 'Pad'")
    assert_ok(mcp.call("chamfer_feature", doc_name="LiveDress", base_feature="Pad",
                       chamfer_name="C", size=1, edge_refs=["Edge1"], body_name="Body"))
    assert_ok(mcp.call("close_document", doc_name="LiveDress"))
    assert_clean(gui_log)


def test_angles_beyond_a_full_turn_are_rejected(mcp, gui_log):
    """FreeCAD clamps 720 degrees to 360 without telling anyone."""

    _part_body(mcp, "LiveAngle")
    _rejected(mcp.call("polar_pattern_feature", doc_name="LiveAngle", feature_name="Pad",
                       pattern_name="PP", occurrences=4, angle=720, body_name="Body"),
              "angle must be <= 360")
    assert_ok(mcp.call("close_document", doc_name="LiveAngle"))
    assert_clean(gui_log)


@pytest.mark.parametrize("action", ["undo", "redo"])
def test_history_past_its_end_is_reported(mcp, gui_log, action):
    doc = f"LiveEmpty{action.title()}"
    assert_ok(mcp.call("create_document", name=doc))

    _rejected(mcp.call(action, doc_name=doc), f"Nothing to {action}")
    assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log)


def test_undo_steps_are_named_after_the_mcp_tool(mcp, gui_log):
    """Edit > Undo listed every MCP edit as "Collaborative operation <uuid>"."""

    assert_ok(mcp.call("create_document", name="LiveUndoName"))
    assert_ok(mcp.call("create_object", doc_name="LiveUndoName", obj_type="Part::Box",
                       obj_name="Box"))
    readiness = assert_ok(mcp.call("get_mutation_readiness", doc_name="LiveUndoName"))

    assert re.search(r'"undo_head":\s*"MCP: create_object"', readiness.text), readiness.text[:800]
    assert_ok(mcp.call("close_document", doc_name="LiveUndoName"))
    assert_clean(gui_log)


def test_import_brep_rejects_a_file_without_a_shape(mcp, gui_log, tmp_path):
    """An STL imported as BREP committed a null-shape object."""

    stl = tmp_path / "box.stl"
    assert_ok(mcp.call("create_document", name="LiveImport"))
    assert_ok(mcp.call("create_object", doc_name="LiveImport", obj_type="Part::Box",
                       obj_name="Box"))
    assert_ok(mcp.call("export_stl", doc_name="LiveImport", file_path=str(stl),
                       obj_names=["Box"]))

    _rejected(mcp.call("import_brep", doc_name="LiveImport", file_path=str(stl),
                       obj_name="Wrong"), "No BREP shape could be read")
    _rejected(mcp.call("import_brep", doc_name="LiveImport",
                       file_path=str(tmp_path / "missing.brep"), obj_name="Missing"),
              "File does not exist")
    objects = assert_ok(mcp.call("get_objects", doc_name="LiveImport"))
    assert "Wrong" not in objects.text and "Missing" not in objects.text
    assert_ok(mcp.call("close_document", doc_name="LiveImport"))
    assert_clean(gui_log)


def test_single_edge_objects_can_be_measured(mcp, gui_log):
    """measure_angle("LineA", ...) failed with "edge does not support tangentAt"
    and center_of_mass with "Object has no CenterOfMass"."""

    assert_ok(mcp.call("create_document", name="LiveLines"))
    assert_ok(mcp.call("create_object", doc_name="LiveLines", obj_type="Part::Line",
                       obj_name="LineA", obj_properties={"X2": 0, "Y2": 100, "Z2": 0}))
    assert_ok(mcp.call("create_object", doc_name="LiveLines", obj_type="Part::Line",
                       obj_name="LineB", obj_properties={"X2": 50, "Y2": 0, "Z2": 0}))

    angle = _payload(assert_ok(mcp.call("measure_angle", doc_name="LiveLines",
                                        edge1_ref="LineA", edge2_ref="LineB")))
    center = _payload(assert_ok(mcp.call("center_of_mass", doc_name="LiveLines",
                                         obj_name="LineA")))

    assert angle["angle_deg"] == pytest.approx(90.0)
    assert (center["x"], center["y"]) == (pytest.approx(0.0), pytest.approx(50.0))
    assert_ok(mcp.call("close_document", doc_name="LiveLines"))
    assert_clean(gui_log)


def test_reference_repair_can_defer_recompute(mcp, gui_log):
    """repair_references(recompute=false) still recomputed, so a batch of
    circular repairs could never be applied; validate=true let a missing
    edge through."""

    _part_body(mcp, "LiveRepair")
    assert_ok(mcp.call("chamfer_feature", doc_name="LiveRepair", base_feature="Pad",
                       chamfer_name="Ch", size=1, edge_refs=["Edge1"], body_name="Body"))
    repair = [{"object": "Ch", "property": "Base",
               "references": [{"object": "Pad", "subelements": ["Edge88888"]}]}]

    _rejected(mcp.call("repair_references", doc_name="LiveRepair", repairs=repair,
                       validate=True), "Pad.Edge88888 does not exist")
    deferred = _payload(assert_ok(mcp.call("repair_references", doc_name="LiveRepair",
                                           repairs=repair, recompute=False)))

    assert deferred["recompute"] == "deferred"
    assert deferred["repaired"] == ["Ch.Base"]
    assert_ok(mcp.call("close_document", doc_name="LiveRepair"))
    assert_clean(gui_log)


def test_dependency_graph_lists_dependents(mcp, gui_log):
    _part_body(mcp, "LiveGraph")
    assert_ok(mcp.call("fillet_feature", doc_name="LiveGraph", base_feature="Pad",
                       fillet_name="Fillet", radius=1, edge_refs=["Edge1"], body_name="Body"))

    graph = _payload(assert_ok(mcp.call("get_dependency_graph", doc_name="LiveGraph",
                                        root="Pad")))

    assert "Fillet" in graph["dependents"]
    assert graph["history_order"].index("Sk") < graph["history_order"].index("Pad")
    assert any(edge["from"] == "Pad" and edge["to"] == "Sk" for edge in graph["edges"])
    assert_ok(mcp.call("close_document", doc_name="LiveGraph"))
    assert_clean(gui_log)


def test_delete_refusal_and_force_report_dependents(mcp, gui_log):
    _part_body(mcp, "LiveDelete")
    assert_ok(mcp.call("fillet_feature", doc_name="LiveDelete", base_feature="Pad",
                       fillet_name="Fillet", radius=1, edge_refs=["Edge1"], body_name="Body"))

    _rejected(mcp.call("delete_object", doc_name="LiveDelete", obj_name="Pad"),
              "Refused to delete 'Pad'")
    forced = _payload(assert_ok(mcp.call("delete_object", doc_name="LiveDelete",
                                         obj_name="Pad", force=True)))

    assert [item["name"] for item in forced["orphans_left"]] == ["Fillet"]
    assert_ok(mcp.call("close_document", doc_name="LiveDelete"))
    assert_clean(gui_log)


def test_assembly_rejects_components_outside_it(mcp, gui_log):
    """Joints on objects outside the assembly were accepted, so the solve
    reported success while nothing moved."""

    assert_ok(mcp.call("create_document", name="LiveAsmCheck"))
    assert_ok(mcp.call("create_assembly", doc_name="LiveAsmCheck", assembly_name="Asm"))
    assert_ok(mcp.call("create_object", doc_name="LiveAsmCheck", obj_type="Part::Box",
                       obj_name="Outside"))

    _rejected(mcp.call("create_assembly_grounded_joint", doc_name="LiveAsmCheck",
                       assembly_name="Asm", component_name="Outside"),
              "'Outside' is not part of assembly 'Asm'")
    assert_ok(mcp.call("move_object", doc_name="LiveAsmCheck", obj_name="Outside",
                       target_container="Asm"))
    assert_ok(mcp.call("create_assembly_grounded_joint", doc_name="LiveAsmCheck",
                       assembly_name="Asm", component_name="Outside"))
    solved = _payload(assert_ok(mcp.call("solve_assembly", doc_name="LiveAsmCheck",
                                         assembly_name="Asm")))

    assert solved["solver_status"] == "0"
    assert_ok(mcp.call("snapshot", doc_name="LiveAsmCheck"))
    assert_ok(mcp.call("restore", doc_name="LiveAsmCheck"))
    assert_ok(mcp.call("close_document", doc_name="LiveAsmCheck"))
    assert_clean(gui_log)


@pytest.mark.parametrize(
    ("tool", "args", "reason"),
    [
        ("compute_gear_geometry", {"teeth": -5, "module": 0}, "teeth must be >= 3"),
        ("check_gear_pair", {"teeth1": 0, "module1": 2, "teeth2": 40, "module2": 2},
         "teeth1 must be >= 3"),
        ("measure_distance", {"doc_name": "LiveNames", "shape1_ref": "Box",
                              "shape2_ref": "Ghost"}, "Object not found: 'Ghost'"),
        ("relink_references", {"doc_name": "LiveNames", "from_obj": "Box", "to_obj": "Box"},
         "from_obj and to_obj must differ"),
        ("export_stl", {"doc_name": "LiveNames", "file_path": "/tmp/x.stl", "obj_names": [],
                        "mesh_deviation": 0.1}, "obj_names must not be empty"),
    ],
)
def test_more_rejections_name_their_reason(mcp, gui_log, tool, args, reason):
    if mcp.call("get_object", doc_name="LiveNames", obj_name="Box").is_error:
        assert_ok(mcp.call("create_document", name="LiveNames"))
        assert_ok(mcp.call("create_object", doc_name="LiveNames", obj_type="Part::Box",
                           obj_name="Box"))
        gui_log.reset()

    _rejected(mcp.call(tool, **args), reason)
    assert_clean(gui_log)


def test_cancelling_an_unknown_worker_job_names_it(mcp, gui_log):
    result = mcp.call("cancel_worker_job", job_id="bogus-job-id-1234")

    assert not result.ok
    assert "bogus-job-id-1234" in result.text, result.text[:600]
    assert_clean(gui_log)
