"""Two-phase expected-link validation and worker integration (live FreeCAD)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
FreeCADGui = pytest.importorskip("FreeCADGui")
pytest.importorskip("Part")

if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *_args, **_kwargs: None

from addon.FreeCADMCP.rpc_server import worker_entry as worker_entry_module
from addon.FreeCADMCP.rpc_server.worker_entry import (
    ExternalLinkUnresolved,
    ExternalSubelementUnresolved,
    _validate_expected_links_post_recompute,
    _validate_expected_links_pre_recompute,
    run_job,
)
from addon.FreeCADMCP.rpc_server.snapshot_service import (
    _collect_link_manifest,
    create_snapshot_bundle_gui,
)
from addon.FreeCADMCP.rpc_server.worker_manager import (
    WorkerManager,
    WorkerRuntime,
    _merge_link_warnings,
)
from addon.FreeCADMCP.rpc_server.worker_protocol import write_json_atomic

MODULE_DIR = Path(__file__).parents[1] / "addon" / "FreeCADMCP" / "rpc_server"


def _runtime() -> WorkerRuntime:
    version = tuple(str(value) for value in FreeCAD.Version()[:4])
    while len(version) < 4:
        version += ("",)
    return WorkerRuntime(
        gui_executable=__import__("sys").executable,
        freecad_home=FreeCAD.getHomePath(),
        gui_version=version,
    )


def _box_document(name: str):
    doc = FreeCAD.newDocument(name)
    box = doc.addObject("Part::Box", "Box")
    box.Length = 17
    box.Width = 3
    box.Height = 2
    doc.recompute()
    return doc


def _linksub_holder(doc, prop_name: str = "Support", *, prop_type="App::PropertyLinkSub"):
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty(prop_type, prop_name)
    return holder


def _document_name_after_save_reopen(doc, path: Path) -> str:
    doc.saveAs(str(path))
    FreeCAD.closeDocument(doc.Name)
    reopened = FreeCAD.openDocument(str(path))
    name = reopened.Name
    FreeCAD.closeDocument(name)
    return name


def _expected_entry(
    doc,
    holder,
    subelements,
    *,
    prop="Support",
    target_name="Box",
    property_type="App::PropertyLinkSub",
):
    return {
        "owner_document": doc.Name,
        "owner_object": holder.Name,
        "property": prop,
        "property_type": property_type,
        "target_document": doc.Name,
        "target_object": target_name,
        "subelements": list(subelements),
    }


def _manifest_rows_for_linksublist(doc, holder, refs):
    rows = []
    for target, subelements in refs:
        rows.append(
            _expected_entry(
                doc,
                holder,
                subelements,
                prop="Supports",
                target_name=target.Name,
                property_type="App::PropertyLinkSubList",
            )
        )
    return rows


@pytest.mark.e2e
def test_linksub_exact_target_and_subelement_no_warning():
    doc = _box_document("LinkExact")
    holder = _linksub_holder(doc)
    holder.Support = (doc.Box, ["Face6"])
    entry = _expected_entry(doc, holder, ["Face6"])
    anchors = _validate_expected_links_pre_recompute({"expected_links": [entry]})
    doc.recompute()
    assert _validate_expected_links_post_recompute(anchors) == []
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_xlinksub_exact_target_and_subelement_no_warning():
    doc = _box_document("XLinkExact")
    holder = _linksub_holder(doc, prop_type="App::PropertyXLinkSub")
    holder.Support = (doc.Box, ["Face3"])
    entry = _expected_entry(
        doc,
        holder,
        ["Face3"],
        property_type="App::PropertyXLinkSub",
    )
    anchors = _validate_expected_links_pre_recompute({"expected_links": [entry]})
    doc.recompute()
    assert _validate_expected_links_post_recompute(anchors) == []
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_linksublist_distinct_targets_exact_reopen():
    doc = _box_document("LinkSubListDistinct")
    box2 = doc.addObject("Part::Box", "Box2")
    box2.Length = 5
    box2.Width = 4
    box2.Height = 3
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSubList", "Supports")
    refs = [(doc.Box, ["Face1"]), (box2, ["Face2"])]
    holder.Supports = refs
    doc.recompute()
    rows = _manifest_rows_for_linksublist(doc, holder, refs)
    anchors = _validate_expected_links_pre_recompute({"expected_links": rows})
    assert [item["ref_index"] for item in anchors] == [0, 1]
    doc.recompute()
    assert _validate_expected_links_post_recompute(anchors) == []
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_linksublist_preserves_separated_duplicate_multiplicity():
    doc = _box_document("LinkSubListMultiplicity")
    box2 = doc.addObject("Part::Box", "Box2")
    box2.Length = 5
    box2.Width = 4
    box2.Height = 3
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSubList", "Supports")
    refs = [(doc.Box, ["Face1"]), (box2, ["Face2"]), (doc.Box, ["Face1"])]
    holder.Supports = refs
    doc.recompute()
    rows = _manifest_rows_for_linksublist(doc, holder, refs)
    anchors = _validate_expected_links_pre_recompute({"expected_links": rows})
    assert [item["ref_index"] for item in anchors] == [0, 1, 2]
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_linksublist_pre_fails_when_final_duplicate_occurrence_missing():
    doc = _box_document("LinkSubListMissingDup")
    box2 = doc.addObject("Part::Box", "Box2")
    box2.Length = 5
    box2.Width = 4
    box2.Height = 3
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSubList", "Supports")
    holder.Supports = [(doc.Box, ["Face1"]), (box2, ["Face2"])]
    doc.recompute()
    rows = _manifest_rows_for_linksublist(
        doc,
        holder,
        [(doc.Box, ["Face1"]), (box2, ["Face2"]), (doc.Box, ["Face1"])],
    )
    with pytest.raises(ExternalLinkUnresolved):
        _validate_expected_links_pre_recompute({"expected_links": rows})
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
@pytest.mark.parametrize("missing_index", [0, 1, 2])
def test_linksublist_pre_fails_when_entry_missing(missing_index):
    doc = _box_document(f"LinkSubListMissing{missing_index}")
    box2 = doc.addObject("Part::Box", "Box2")
    box2.Length = 5
    box2.Width = 4
    box2.Height = 3
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSubList", "Supports")
    full_refs = [(doc.Box, ["Face1"]), (box2, ["Face2"]), (doc.Box, ["Face4"])]
    rows = _manifest_rows_for_linksublist(doc, holder, full_refs)
    reopened = [item for index, item in enumerate(full_refs) if index != missing_index]
    holder.Supports = reopened
    doc.recompute()
    with pytest.raises(ExternalLinkUnresolved):
        _validate_expected_links_pre_recompute({"expected_links": rows})
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_linksublist_pre_fails_when_unexpected_extra_entry_present():
    doc = _box_document("LinkSubListExtra")
    box2 = doc.addObject("Part::Box", "Box2")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSubList", "Supports")
    rows = _manifest_rows_for_linksublist(
        doc, holder, [(doc.Box, ["Face1"]), (box2, ["Face2"])]
    )
    holder.Supports = [
        (doc.Box, ["Face1"]),
        (box2, ["Face2"]),
        (doc.Box, ["Face3"]),
    ]
    doc.recompute()
    with pytest.raises(ExternalLinkUnresolved):
        _validate_expected_links_pre_recompute({"expected_links": rows})
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_linksublist_post_fails_when_entries_reorder_after_recompute():
    doc = _box_document("LinkSubListReorder")
    box2 = doc.addObject("Part::Box", "Box2")
    box2.Length = 5
    box2.Width = 4
    box2.Height = 3
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSubList", "Supports")
    refs = [(doc.Box, ["Face1"]), (box2, ["Face2"])]
    holder.Supports = refs
    doc.recompute()
    rows = _manifest_rows_for_linksublist(doc, holder, refs)
    anchors = _validate_expected_links_pre_recompute({"expected_links": rows})
    holder.Supports = [(box2, ["Face2"]), (doc.Box, ["Face1"])]
    with pytest.raises(ExternalLinkUnresolved):
        _validate_expected_links_post_recompute(anchors)
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_linksublist_post_emits_deterministic_multi_remap_warnings():
    doc = _box_document("LinkSubListMultiRemap")
    box2 = doc.addObject("Part::Box", "Box2")
    box2.Length = 5
    box2.Width = 4
    box2.Height = 3
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSubList", "Supports")
    refs = [(doc.Box, ["Face1"]), (box2, ["Face2"])]
    holder.Supports = refs
    doc.recompute()
    rows = _manifest_rows_for_linksublist(doc, holder, refs)
    anchors = _validate_expected_links_pre_recompute({"expected_links": rows})
    holder.Supports = [(doc.Box, ["Face6"]), (box2, ["Face4"])]
    warnings = _validate_expected_links_post_recompute(anchors)
    assert warnings == [
        f"subelement_remapped:{doc.Name}.Holder.Supports: Face1 -> Face6",
        f"subelement_remapped:{doc.Name}.Holder.Supports: Face2 -> Face4",
    ]
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_pre_fails_owner_document_missing():
    doc = _box_document("OwnerDocMissing")
    holder = _linksub_holder(doc)
    holder.Support = (doc.Box, ["Face1"])
    entry = _expected_entry(doc, holder, ["Face1"])
    entry["owner_document"] = "MissingDocument"
    with pytest.raises(ExternalLinkUnresolved):
        _validate_expected_links_pre_recompute({"expected_links": [entry]})
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_pre_fails_owner_object_missing():
    doc = _box_document("OwnerObjMissing")
    holder = _linksub_holder(doc)
    holder.Support = (doc.Box, ["Face1"])
    entry = _expected_entry(doc, holder, ["Face1"])
    entry["owner_object"] = "MissingHolder"
    with pytest.raises(ExternalLinkUnresolved):
        _validate_expected_links_pre_recompute({"expected_links": [entry]})
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_pre_fails_property_missing():
    doc = _box_document("PropertyMissing")
    holder = _linksub_holder(doc)
    holder.Support = (doc.Box, ["Face1"])
    entry = _expected_entry(doc, holder, ["Face1"])
    entry["property"] = "MissingProperty"
    with pytest.raises(ExternalLinkUnresolved):
        _validate_expected_links_pre_recompute({"expected_links": [entry]})
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_pre_fails_property_getter_raises(monkeypatch):
    doc = _box_document("LinkGetterError")
    holder = _linksub_holder(doc)
    holder.Support = (doc.Box, ["Face1"])
    entry = _expected_entry(doc, holder, ["Face1"])

    class BrokenDoc:
        Name = doc.Name

        def getObject(self, name):
            if name == holder.Name:

                class BrokenHolder:
                    Name = holder.Name

                    @property
                    def Support(self):
                        raise RuntimeError("property getter failed")

                return BrokenHolder()
            return doc.getObject(name)

    monkeypatch.setattr(
        "addon.FreeCADMCP.rpc_server.worker_entry.FreeCAD.getDocument",
        lambda name: BrokenDoc() if name == doc.Name else FreeCAD.getDocument(name),
    )
    with pytest.raises(ExternalLinkUnresolved):
        _validate_expected_links_pre_recompute({"expected_links": [entry]})
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_pre_fails_target_document_mismatch():
    doc = _box_document("TargetDocMismatch")
    holder = _linksub_holder(doc)
    holder.Support = (doc.Box, ["Face1"])
    entry = _expected_entry(doc, holder, ["Face1"])
    entry["target_document"] = "OtherDocument"
    with pytest.raises(ExternalLinkUnresolved):
        _validate_expected_links_pre_recompute({"expected_links": [entry]})
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_pre_fails_target_object_mismatch():
    doc = _box_document("TargetObjMismatch")
    holder = _linksub_holder(doc)
    holder.Support = (doc.Box, ["Face1"])
    entry = _expected_entry(doc, holder, ["Face1"])
    entry["target_object"] = "MissingBox"
    with pytest.raises(ExternalLinkUnresolved):
        _validate_expected_links_pre_recompute({"expected_links": [entry]})
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_pre_fails_subelement_name_mismatch():
    doc = _box_document("SubelementMismatch")
    holder = _linksub_holder(doc)
    holder.Support = (doc.Box, ["Face2"])
    entry = _expected_entry(doc, holder, ["Face6"])
    with pytest.raises(ExternalLinkUnresolved):
        _validate_expected_links_pre_recompute({"expected_links": [entry]})
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_post_fails_when_target_object_changes():
    doc = _box_document("PostTargetChange")
    holder = _linksub_holder(doc)
    holder.Support = (doc.Box, ["Face2"])
    entry = _expected_entry(doc, holder, ["Face2"])
    anchors = _validate_expected_links_pre_recompute({"expected_links": [entry]})
    second = doc.addObject("Part::Box", "Box2")
    second.Length = 5
    second.Width = 5
    second.Height = 5
    doc.recompute()
    holder.Support = (second, ["Face2"])
    with pytest.raises(ExternalLinkUnresolved):
        _validate_expected_links_post_recompute(anchors)
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_post_fails_invalid_subelement_face999():
    doc = _box_document("PostFace999")
    holder = _linksub_holder(doc)
    holder.Support = (doc.Box, ["Face2"])
    entry = _expected_entry(doc, holder, ["Face2"])
    anchors = _validate_expected_links_pre_recompute({"expected_links": [entry]})
    holder.Support = (doc.Box, ["Face999"])
    with pytest.raises(ExternalSubelementUnresolved):
        _validate_expected_links_post_recompute(anchors)
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_post_fails_when_subelement_list_grows():
    doc = _box_document("SubelementGrows")
    holder = _linksub_holder(doc)
    holder.Support = (doc.Box, ["Face2"])
    entry = _expected_entry(doc, holder, ["Face2"])
    anchors = _validate_expected_links_pre_recompute({"expected_links": [entry]})
    holder.Support = (doc.Box, ["Face2", "Face1"])
    with pytest.raises(ExternalLinkUnresolved):
        _validate_expected_links_post_recompute(anchors)
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_save_reopen_phase1_matches_manifest_before_recompute(tmp_path):
    doc = _box_document("SaveReopen")
    holder = _linksub_holder(doc)
    holder.Support = (doc.Box, ["Face6"])
    path = tmp_path / "save_reopen.FCStd"
    entry = _expected_entry(doc, holder, ["Face6"])
    doc_name = _document_name_after_save_reopen(doc, path)
    entry["owner_document"] = doc_name
    entry["target_document"] = doc_name
    reopened = FreeCAD.openDocument(str(path))
    anchors = _validate_expected_links_pre_recompute({"expected_links": [entry]})
    assert anchors[0]["ref_index"] == 0
    FreeCAD.closeDocument(reopened.Name)


@pytest.mark.e2e
def test_run_job_recompute_remap_warning_and_user_code_executes(monkeypatch, tmp_path):
    doc = _box_document("RunJobRemap")
    holder = _linksub_holder(doc)
    holder.Support = (doc.Box, ["Face6"])
    fcstd = tmp_path / "run_job_remap.FCStd"
    entry = _expected_entry(doc, holder, ["Face6"])
    doc_name = _document_name_after_save_reopen(doc, fcstd)
    entry["owner_document"] = doc_name
    entry["target_document"] = doc_name
    holder_name = "Holder"

    def recompute_then_remap():
        for open_doc in FreeCAD.listDocuments().values():
            open_doc.recompute()
        live = FreeCAD.getDocument(doc_name)
        live.getObject(holder_name).Support = (live.Box, ["Face1"])

    monkeypatch.setattr(
        worker_entry_module,
        "_recompute_snapshot_documents",
        recompute_then_remap,
    )

    result_path = tmp_path / "result.json"
    job_path = tmp_path / "job.json"
    write_json_atomic(
        job_path,
        {
            "schema_version": 1,
            "job_id": "remap-job",
            "kind": "execute_code",
            "code": "print('user-code-executed')",
            "artifact_directory": str(tmp_path / "artifacts"),
            "result_path": str(result_path),
            "snapshot": {
                "primary_document": doc_name,
                "documents": [
                    {
                        "document_name": doc_name,
                        "load_path": str(fcstd),
                    }
                ],
                "expected_links": [entry],
            },
            "options": {"recompute": "none"},
        },
    )
    assert run_job(str(job_path)) == 0
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "ok"
    assert "user-code-executed" in result["stdout"]
    assert len(result["link_warnings"]) == 1
    assert "Face6 -> Face1" in result["link_warnings"][0]
    assert result["session"]["link_warnings"] == result["link_warnings"]


@pytest.mark.e2e
def test_run_job_preserves_remap_warnings_when_user_code_raises(monkeypatch, tmp_path):
    doc = _box_document("RunJobRemapError")
    holder = _linksub_holder(doc)
    holder.Support = (doc.Box, ["Face6"])
    fcstd = tmp_path / "run_job_remap_error.FCStd"
    entry = _expected_entry(doc, holder, ["Face6"])
    doc_name = _document_name_after_save_reopen(doc, fcstd)
    holder_name = "Holder"
    entry["owner_document"] = doc_name
    entry["target_document"] = doc_name

    def recompute_then_remap():
        for open_doc in FreeCAD.listDocuments().values():
            open_doc.recompute()
        live = FreeCAD.getDocument(doc_name)
        live.getObject(holder_name).Support = (live.Box, ["Face1"])

    monkeypatch.setattr(
        worker_entry_module,
        "_recompute_snapshot_documents",
        recompute_then_remap,
    )

    result_path = tmp_path / "result-error.json"
    job_path = tmp_path / "job-error.json"
    write_json_atomic(
        job_path,
        {
            "schema_version": 1,
            "job_id": "remap-error-job",
            "kind": "execute_code",
            "code": "raise RuntimeError('user failure')",
            "artifact_directory": str(tmp_path / "artifacts-error"),
            "result_path": str(result_path),
            "snapshot": {
                "primary_document": doc_name,
                "documents": [
                    {
                        "document_name": doc_name,
                        "load_path": str(fcstd),
                    }
                ],
                "expected_links": [entry],
            },
            "options": {"recompute": "none"},
        },
    )
    assert run_job(str(job_path)) == 1
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "error"
    assert result["error"]["type"] == "RuntimeError"
    assert "Face6 -> Face1" in result["link_warnings"][0]


@pytest.mark.e2e
def test_run_job_fatal_validation_does_not_execute_user_code(tmp_path):
    doc = _box_document("RunJobFatal")
    holder = _linksub_holder(doc)
    holder.Support = (doc.Box, ["Face2"])
    fcstd = tmp_path / "run_job_fatal.FCStd"
    entry = _expected_entry(doc, holder, ["Face6"])
    doc_name = _document_name_after_save_reopen(doc, fcstd)
    entry["owner_document"] = doc_name
    entry["target_document"] = doc_name

    result_path = tmp_path / "result-fatal.json"
    job_path = tmp_path / "job-fatal.json"
    write_json_atomic(
        job_path,
        {
            "schema_version": 1,
            "job_id": "fatal-job",
            "kind": "execute_code",
            "code": "print('must-not-execute')",
            "artifact_directory": str(tmp_path / "artifacts-fatal"),
            "result_path": str(result_path),
            "snapshot": {
                "primary_document": doc_name,
                "documents": [
                    {
                        "document_name": doc_name,
                        "load_path": str(fcstd),
                    }
                ],
                "expected_links": [entry],
            },
            "options": {"recompute": "none"},
        },
    )
    assert run_job(str(job_path)) == 1
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["error"]["type"] == "ExternalLinkUnresolved"
    assert "must-not-execute" not in result["stdout"]


@pytest.mark.e2e
def test_worker_manager_merges_snapshot_link_warnings_on_success(tmp_path):
    doc = _box_document("ManagerSnapWarn")
    holder = _linksub_holder(doc)
    holder.Support = (doc.Box, ["Face1"])
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        workspace = manager.create_workspace()
        snapshot = create_snapshot_bundle_gui(doc.Name, str(workspace))
        assert snapshot["ok"] is True
        snapshot["link_warnings"] = ["invalid_subelement:Doc.Box.Face999"]
        result = manager.execute(
            "print('manager-user-code')",
            {"document": doc.Name, "read_only": True, "execution_mode": "worker"},
            snapshot,
            workspace,
        )
        assert result["success"] is True
        assert "manager-user-code" in result["message"]
        assert result["link_warnings"] == ["invalid_subelement:Doc.Box.Face999"]
        assert result["structured"]["link_warnings"] == result["link_warnings"]
        assert result["session"]["link_warnings"] == result["link_warnings"]
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_link_policy_warn_omits_invalid_live_reference(tmp_path):
    doc = _box_document("WarnPolicyPhase")
    holder = _linksub_holder(doc)
    holder.Support = (doc.Box, ["Face999"])
    doc.recompute()
    try:
        strict = create_snapshot_bundle_gui(doc.Name, str(tmp_path / "strict"))
        assert strict["ok"] is False
        warned = create_snapshot_bundle_gui(
            doc.Name, str(tmp_path / "warn"), link_policy="warn"
        )
        assert warned["ok"] is True
        assert any("Face999" in item for item in warned.get("link_warnings", []))
        assert all(
            "Face999" not in link.get("subelements", [])
            for link in warned.get("expected_links", [])
        )
    finally:
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.unit
def test_merge_link_warnings_preserves_order_without_duplicates():
    snapshot = {"link_warnings": ["invalid_subelement:Doc.Box.Face999"]}
    worker = {
        "link_warnings": [
            "invalid_subelement:Doc.Box.Face999",
            "subelement_remapped:Doc.Holder.Support: Face6 -> Face1",
        ]
    }
    merged = _merge_link_warnings(snapshot, worker)
    assert merged == [
        "invalid_subelement:Doc.Box.Face999",
        "subelement_remapped:Doc.Holder.Support: Face6 -> Face1",
    ]
