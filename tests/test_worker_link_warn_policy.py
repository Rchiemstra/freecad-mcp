"""link_policy=warn snapshot and worker validation (live FreeCAD)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
FreeCADGui = pytest.importorskip("FreeCADGui")
Part = pytest.importorskip("Part")

if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *_args, **_kwargs: None

from addon.FreeCADMCP.rpc_server import worker_entry as worker_entry_module
from addon.FreeCADMCP.rpc_server.snapshot_service import (
    create_snapshot_bundle_gui,
    materialize_load_aliases,
)
from addon.FreeCADMCP.rpc_server.worker_entry import (
    ExternalLinkUnresolved,
    ExternalSubelementUnresolved,
    _validate_expected_links_pre_recompute,
    run_job,
)
from addon.FreeCADMCP.rpc_server.worker_manager import (
    WorkerManager,
    WorkerRuntime,
    _merge_link_warnings,
)
from addon.FreeCADMCP.rpc_server.worker_protocol import ProtocolError, write_json_atomic
from addon.FreeCADMCP.rpc_server.worker_protocol import validate_subelement_reference

MODULE_DIR = Path(__file__).parents[1] / "addon" / "FreeCADMCP" / "rpc_server"


def _six_face_target_document(name: str):
    doc = FreeCAD.newDocument(name)
    target = doc.addObject("Part::Feature", "Target")
    target.Shape = Part.makeBox(10, 10, 10)
    doc.recompute()
    return doc


def _expanded_target_shape():
    base = Part.makeBox(10, 10, 10)
    extra = Part.makeBox(4, 4, 4, FreeCAD.Vector(10, 0, 0))
    return base.fuse(extra)


def _recompute_expand_target(doc_name: str, *, target_name: str = "Target"):
    def _hook():
        for open_doc in FreeCAD.listDocuments().values():
            open_doc.recompute()
        live = FreeCAD.getDocument(doc_name)
        live.getObject(target_name).Shape = _expanded_target_shape()

    return _hook


def _assert_face7_invalid_then_valid(target):
    with pytest.raises(Exception):
        validate_subelement_reference(target, "Face7")
    target.Shape = _expanded_target_shape()
    validate_subelement_reference(target, "Face7")


def _run_warn_snapshot_job(
    monkeypatch,
    tmp_path,
    snapshot: dict,
    *,
    code: str = "print('worker-ok')",
    recompute_hook,
    job_id: str,
):
    materialize_load_aliases(snapshot)
    monkeypatch.setattr(
        worker_entry_module,
        "_recompute_snapshot_documents",
        recompute_hook,
    )
    result_path = tmp_path / f"{job_id}-result.json"
    job_path = tmp_path / f"{job_id}-job.json"
    write_json_atomic(
        job_path,
        {
            "schema_version": 1,
            "job_id": job_id,
            "kind": "execute_code",
            "code": code,
            "artifact_directory": str(tmp_path / f"artifacts-{job_id}"),
            "result_path": str(result_path),
            "snapshot": snapshot,
            "options": {"recompute": "none"},
        },
    )
    exit_code = run_job(str(job_path))
    worker_result = json.loads(result_path.read_text(encoding="utf-8"))
    return exit_code, worker_result


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


def _execute_warn_snapshot(doc, manager: WorkerManager, code: str = "print('worker-ok')"):
    workspace = manager.create_workspace()
    snapshot = create_snapshot_bundle_gui(doc.Name, str(workspace), link_policy="warn")
    assert snapshot["ok"] is True, snapshot
    result = manager.execute(
        code,
        {"document": doc.Name, "read_only": True, "execution_mode": "worker"},
        snapshot,
        workspace,
    )
    return snapshot, result


def _warn_mixed_support_snapshot(doc, manager: WorkerManager):
    workspace = manager.create_workspace()
    snapshot = create_snapshot_bundle_gui(doc.Name, str(workspace), link_policy="warn")
    assert snapshot["ok"] is True, snapshot
    return workspace, snapshot


def _worker_execute_must_not_run(
    doc,
    manager: WorkerManager,
    snapshot: dict,
    workspace: str,
    *,
    code: str = "print('must-not-run')",
) -> dict:
    return manager.execute(
        code,
        {"document": doc.Name, "read_only": True, "execution_mode": "worker"},
        snapshot,
        workspace,
    )


@pytest.mark.e2e
def test_warn_wholly_invalid_linksub_executes(tmp_path):
    doc = _box_document("WarnWhollyInvalid")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Box, ["Face999"])
    doc.recompute()
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        snapshot, result = _execute_warn_snapshot(doc, manager)
        assert result["success"] is True
        assert "worker-ok" in result["message"]
        assert any("Face999" in item for item in snapshot.get("link_warnings", []))
        assert snapshot.get("expected_links") == []
        assert len(snapshot.get("ignored_links") or []) == 1
        assert result["link_warnings"] == snapshot["link_warnings"]
        assert result["structured"]["link_warnings"] == snapshot["link_warnings"]
        assert result["session"]["link_warnings"] == snapshot["link_warnings"]
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_mixed_subelement_on_one_target_executes(tmp_path):
    doc = _box_document("WarnMixedSub")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Box, ["Face1", "Face999"])
    doc.recompute()
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        snapshot, result = _execute_warn_snapshot(doc, manager)
        assert result["success"] is True
        assert snapshot["expected_links"][0]["subelements"] == ["Face1"]
        ignored = snapshot["ignored_links"][0]
        assert ignored["reference_index"] == 0
        assert ignored["subelements"] == ["Face999"]
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_linksublist_mixed_valid_invalid_executes(tmp_path):
    doc = _box_document("WarnLinkSubList")
    box2 = doc.addObject("Part::Box", "Box2")
    box2.Length = 5
    box2.Width = 4
    box2.Height = 3
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSubList", "Supports")
    holder.Supports = [
        (doc.Box, ["Face1"]),
        (box2, ["Face999"]),
        (doc.Box, ["Face4"]),
    ]
    doc.recompute()
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        snapshot, result = _execute_warn_snapshot(doc, manager)
        assert result["success"] is True
        assert [row["subelements"] for row in snapshot["expected_links"]] == [
            ["Face1"],
            ["Face4"],
        ]
        assert snapshot["ignored_links"][0]["reference_index"] == 1
        assert snapshot["ignored_links"][0]["subelements"] == ["Face999"]
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_duplicate_occurrences_around_invalid_entry(tmp_path):
    doc = _box_document("WarnDupAroundInvalid")
    box2 = doc.addObject("Part::Box", "Box2")
    box2.Length = 5
    box2.Width = 4
    box2.Height = 3
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSubList", "Supports")
    holder.Supports = [
        (doc.Box, ["Face1"]),
        (box2, ["Face999"]),
        (doc.Box, ["Face1"]),
    ]
    doc.recompute()
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        snapshot, result = _execute_warn_snapshot(doc, manager)
        assert result["success"] is True
        assert len(snapshot["expected_links"]) == 2
        assert snapshot["expected_links"][0]["subelements"] == ["Face1"]
        assert snapshot["expected_links"][1]["subelements"] == ["Face1"]
        assert snapshot["ignored_links"][0]["reference_index"] == 1
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_retained_face_missing_before_phase1_fails(tmp_path):
    doc = _box_document("WarnRetainedMissing")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Box, ["Face1", "Face999"])
    doc.recompute()
    workspace = str(tmp_path / "ws-retained")
    snapshot = create_snapshot_bundle_gui(doc.Name, workspace, link_policy="warn")
    materialize_load_aliases(snapshot)
    load_path = snapshot["documents"][0]["load_path"]
    FreeCAD.closeDocument(doc.Name)
    reopened = FreeCAD.openDocument(load_path)
    reopened.Holder.Support = (reopened.Box, ["Face999"])
    with pytest.raises(ExternalLinkUnresolved):
        _validate_expected_links_pre_recompute(snapshot)
    FreeCAD.closeDocument(reopened.Name)


@pytest.mark.e2e
def test_warn_extra_valid_reference_fails(tmp_path):
    doc = _box_document("WarnExtraValid")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Box, ["Face1", "Face999"])
    doc.recompute()
    workspace = str(tmp_path / "ws-extra")
    snapshot = create_snapshot_bundle_gui(doc.Name, workspace, link_policy="warn")
    materialize_load_aliases(snapshot)
    load_path = snapshot["documents"][0]["load_path"]
    FreeCAD.closeDocument(doc.Name)
    reopened = FreeCAD.openDocument(load_path)
    reopened.Holder.Support = (reopened.Box, ["Face1", "Face2", "Face999"])
    with pytest.raises(ExternalLinkUnresolved):
        _validate_expected_links_pre_recompute(snapshot)
    FreeCAD.closeDocument(reopened.Name)


@pytest.mark.e2e
def test_warn_forged_valid_reference_into_ignored_links_fails(tmp_path):
    doc = _box_document("WarnForgedIgnore")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Box, ["Face1", "Face999"])
    doc.recompute()
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        workspace, snapshot = _warn_mixed_support_snapshot(doc, manager)
        ignored = dict(snapshot["ignored_links"][0])
        ignored["subelements"] = ["Face1", "Face999"]
        snapshot["expected_links"] = []
        snapshot["ignored_links"] = [ignored]
        result = _worker_execute_must_not_run(
            doc,
            manager,
            snapshot,
            workspace,
            code="print('forged-ignore-executed')",
        )
        assert result["success"] is False
        assert result["error_code"] == "external_link_unresolved"
        assert "forged-ignore-executed" not in result["message"]
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_tampered_ignored_metadata_fails(tmp_path):
    doc = _box_document("WarnTamperIgnored")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Box, ["Face1", "Face999"])
    doc.recompute()
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        workspace = manager.create_workspace()
        snapshot = create_snapshot_bundle_gui(doc.Name, str(workspace), link_policy="warn")
        snapshot["ignored_links"][0]["subelements"] = ["Face1"]
        result = manager.execute(
            "print('must-not-run')",
            {"document": doc.Name, "read_only": True, "execution_mode": "worker"},
            snapshot,
            workspace,
        )
        assert result["success"] is False
        assert result["error_code"] == "external_link_unresolved"
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_merged_snapshot_and_remap_warnings(monkeypatch, tmp_path):
    doc = _box_document("WarnMergeRemap")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Box, ["Face1", "Face999"])
    doc.recompute()
    workspace = str(tmp_path / "ws-merge-remap")
    snapshot = create_snapshot_bundle_gui(doc.Name, workspace, link_policy="warn")
    assert snapshot["ok"] is True, snapshot
    materialize_load_aliases(snapshot)
    remap_targets = {"doc_name": snapshot["primary_document"], "holder_name": holder.Name}

    def recompute_then_remap():
        for open_doc in FreeCAD.listDocuments().values():
            open_doc.recompute()
        live = FreeCAD.getDocument(remap_targets["doc_name"])
        live.getObject(remap_targets["holder_name"]).Support = (
            live.Box,
            ["Face6", "Face999"],
        )

    monkeypatch.setattr(
        worker_entry_module,
        "_recompute_snapshot_documents",
        recompute_then_remap,
    )

    result_path = tmp_path / "merge-remap-result.json"
    job_path = tmp_path / "merge-remap-job.json"
    write_json_atomic(
        job_path,
        {
            "schema_version": 1,
            "job_id": "warn-merge-remap",
            "kind": "execute_code",
            "code": "print('merged-ok')",
            "artifact_directory": str(tmp_path / "artifacts-merge"),
            "result_path": str(result_path),
            "snapshot": snapshot,
            "options": {"recompute": "none"},
        },
    )
    assert run_job(str(job_path)) == 0
    worker_result = json.loads(result_path.read_text(encoding="utf-8"))
    merged = _merge_link_warnings(snapshot, worker_result)
    assert any("invalid_subelement" in item for item in merged)
    assert any("Face1 -> Face6" in item for item in merged)
    assert merged == list(dict.fromkeys(merged))
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_merged_snapshot_and_remap_warnings_on_user_error(monkeypatch, tmp_path):
    doc = _box_document("WarnMergeRemapErr")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Box, ["Face1", "Face999"])
    doc.recompute()
    workspace = str(tmp_path / "ws-merge-remap-err")
    snapshot = create_snapshot_bundle_gui(doc.Name, workspace, link_policy="warn")
    assert snapshot["ok"] is True, snapshot
    materialize_load_aliases(snapshot)
    remap_targets = {"doc_name": snapshot["primary_document"], "holder_name": holder.Name}

    def recompute_then_remap():
        for open_doc in FreeCAD.listDocuments().values():
            open_doc.recompute()
        live = FreeCAD.getDocument(remap_targets["doc_name"])
        live.getObject(remap_targets["holder_name"]).Support = (
            live.Box,
            ["Face6", "Face999"],
        )

    monkeypatch.setattr(
        worker_entry_module,
        "_recompute_snapshot_documents",
        recompute_then_remap,
    )

    result_path = tmp_path / "merge-remap-error.json"
    job_path = tmp_path / "merge-remap-error-job.json"
    write_json_atomic(
        job_path,
        {
            "schema_version": 1,
            "job_id": "warn-merge-remap-error",
            "kind": "execute_code",
            "code": "raise RuntimeError('user failure')",
            "artifact_directory": str(tmp_path / "artifacts-merge-error"),
            "result_path": str(result_path),
            "snapshot": snapshot,
            "options": {"recompute": "none"},
        },
    )
    assert run_job(str(job_path)) == 1
    worker_result = json.loads(result_path.read_text(encoding="utf-8"))
    assert worker_result["error"]["type"] == "RuntimeError"
    merged = _merge_link_warnings(snapshot, worker_result)
    assert any("invalid_subelement" in item for item in merged)
    assert any("Face1 -> Face6" in item for item in merged)
    assert merged == list(dict.fromkeys(merged))
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_ignored_only_valid_face1_fails(tmp_path):
    doc = _box_document("WarnIgnoredOnlyValid")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Box, ["Face1", "Face999"])
    doc.recompute()
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        workspace, snapshot = _warn_mixed_support_snapshot(doc, manager)
        ignored = dict(snapshot["ignored_links"][0])
        ignored["subelements"] = ["Face1"]
        snapshot["expected_links"] = []
        snapshot["ignored_links"] = [ignored]
        result = _worker_execute_must_not_run(doc, manager, snapshot, workspace)
        assert result["success"] is False
        assert result["error_code"] == "external_link_unresolved"
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_ignored_target_document_tamper_fails(tmp_path):
    doc = _box_document("WarnIgnoredTargetDoc")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Box, ["Face1", "Face999"])
    doc.recompute()
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        workspace, snapshot = _warn_mixed_support_snapshot(doc, manager)
        snapshot["ignored_links"][0]["target_document"] = "OtherDoc"
        result = _worker_execute_must_not_run(doc, manager, snapshot, workspace)
        assert result["success"] is False
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_ignored_target_object_tamper_fails(tmp_path):
    doc = _box_document("WarnIgnoredTargetObj")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Box, ["Face1", "Face999"])
    doc.recompute()
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        workspace, snapshot = _warn_mixed_support_snapshot(doc, manager)
        snapshot["ignored_links"][0]["target_object"] = "MissingBox"
        result = _worker_execute_must_not_run(doc, manager, snapshot, workspace)
        assert result["success"] is False
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_ignored_reference_index_tamper_fails(tmp_path):
    doc = _box_document("WarnIgnoredIndex")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Box, ["Face1", "Face999"])
    doc.recompute()
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        workspace, snapshot = _warn_mixed_support_snapshot(doc, manager)
        snapshot["ignored_links"][0]["reference_index"] = 9
        result = _worker_execute_must_not_run(doc, manager, snapshot, workspace)
        assert result["success"] is False
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_ignored_unknown_owner_property_fails(tmp_path):
    doc = _box_document("WarnIgnoredOwner")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Box, ["Face1", "Face999"])
    doc.recompute()
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        workspace, snapshot = _warn_mixed_support_snapshot(doc, manager)
        snapshot["ignored_links"][0]["property"] = "MissingProperty"
        result = _worker_execute_must_not_run(doc, manager, snapshot, workspace)
        assert result["success"] is False
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_post_recompute_retained_becomes_invalid_fails(monkeypatch, tmp_path):
    doc = _box_document("WarnPostInvalid")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Box, ["Face1", "Face999"])
    doc.recompute()
    workspace = str(tmp_path / "ws-post-invalid")
    snapshot = create_snapshot_bundle_gui(doc.Name, workspace, link_policy="warn")
    materialize_load_aliases(snapshot)
    doc_name = snapshot["primary_document"]

    def recompute_then_break_kept():
        for open_doc in FreeCAD.listDocuments().values():
            open_doc.recompute()
        live = FreeCAD.getDocument(doc_name)
        live.Holder.Support = (live.Box, ["Face999", "Face999"])

    monkeypatch.setattr(
        worker_entry_module,
        "_recompute_snapshot_documents",
        recompute_then_break_kept,
    )
    result_path = tmp_path / "post-invalid.json"
    job_path = tmp_path / "post-invalid-job.json"
    write_json_atomic(
        job_path,
        {
            "schema_version": 1,
            "job_id": "warn-post-invalid",
            "kind": "execute_code",
            "code": "print('must-not-run')",
            "artifact_directory": str(tmp_path / "artifacts-post-invalid"),
            "result_path": str(result_path),
            "snapshot": snapshot,
            "options": {"recompute": "none"},
        },
    )
    assert run_job(str(job_path)) == 1
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert "must-not-run" not in result["stdout"]
    assert result["error"]["type"] in {
        "ExternalLinkUnresolved",
        "ExternalSubelementUnresolved",
    }
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_strict_linksub_worker_executes(tmp_path):
    doc = _box_document("WarnStrictHappy")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Box, ["Face6"])
    doc.recompute()
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        snapshot, result = _execute_warn_snapshot(
            doc, manager, code="print('strict-warn-ok')"
        )
        assert snapshot["link_policy"] == "warn"
        assert snapshot["expected_links"][0]["subelements"] == ["Face6"]
        assert result["success"] is True
        assert "strict-warn-ok" in result["message"]
        assert result.get("link_warnings") in (None, [])
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_retained_target_object_change_fails(tmp_path):
    doc = _box_document("WarnTargetObj")
    box2 = doc.addObject("Part::Box", "Box2")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Box, ["Face1", "Face999"])
    doc.recompute()
    workspace = str(tmp_path / "ws-target-obj")
    snapshot = create_snapshot_bundle_gui(doc.Name, workspace, link_policy="warn")
    materialize_load_aliases(snapshot)
    load_path = snapshot["documents"][0]["load_path"]
    FreeCAD.closeDocument(doc.Name)
    reopened = FreeCAD.openDocument(load_path)
    reopened.Holder.Support = (reopened.Box2, ["Face1", "Face999"])
    with pytest.raises(ExternalLinkUnresolved):
        _validate_expected_links_pre_recompute(snapshot)
    FreeCAD.closeDocument(reopened.Name)


@pytest.mark.e2e
def test_warn_retained_subelement_name_change_fails(tmp_path):
    doc = _box_document("WarnSubName")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Box, ["Face1", "Face999"])
    doc.recompute()
    workspace = str(tmp_path / "ws-subname")
    snapshot = create_snapshot_bundle_gui(doc.Name, workspace, link_policy="warn")
    materialize_load_aliases(snapshot)
    load_path = snapshot["documents"][0]["load_path"]
    FreeCAD.closeDocument(doc.Name)
    reopened = FreeCAD.openDocument(load_path)
    reopened.Holder.Support = (reopened.Box, ["Face2", "Face999"])
    with pytest.raises(ExternalLinkUnresolved):
        _validate_expected_links_pre_recompute(snapshot)
    FreeCAD.closeDocument(reopened.Name)


@pytest.mark.e2e
def test_warn_linksublist_reorder_fails(tmp_path):
    doc = _box_document("WarnListReorder")
    box2 = doc.addObject("Part::Box", "Box2")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSubList", "Supports")
    holder.Supports = [
        (doc.Box, ["Face1"]),
        (box2, ["Face999"]),
        (doc.Box, ["Face4"]),
    ]
    doc.recompute()
    workspace = str(tmp_path / "ws-reorder")
    snapshot = create_snapshot_bundle_gui(doc.Name, workspace, link_policy="warn")
    materialize_load_aliases(snapshot)
    load_path = snapshot["documents"][0]["load_path"]
    FreeCAD.closeDocument(doc.Name)
    reopened = FreeCAD.openDocument(load_path)
    reopened.Holder.Supports = [
        (reopened.Box, ["Face4"]),
        (reopened.Box2, ["Face999"]),
        (reopened.Box, ["Face1"]),
    ]
    with pytest.raises(ExternalLinkUnresolved):
        _validate_expected_links_pre_recompute(snapshot)
    FreeCAD.closeDocument(reopened.Name)


@pytest.mark.e2e
def test_warn_linksublist_duplicate_occurrence_lost_fails(tmp_path):
    doc = _box_document("WarnDupLost")
    box2 = doc.addObject("Part::Box", "Box2")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSubList", "Supports")
    holder.Supports = [
        (doc.Box, ["Face1"]),
        (box2, ["Face999"]),
        (doc.Box, ["Face1"]),
    ]
    doc.recompute()
    workspace = str(tmp_path / "ws-dup-lost")
    snapshot = create_snapshot_bundle_gui(doc.Name, workspace, link_policy="warn")
    materialize_load_aliases(snapshot)
    load_path = snapshot["documents"][0]["load_path"]
    FreeCAD.closeDocument(doc.Name)
    reopened = FreeCAD.openDocument(load_path)
    reopened.Holder.Supports = [
        (reopened.Box, ["Face1"]),
        (reopened.Box2, ["Face999"]),
    ]
    with pytest.raises(ExternalLinkUnresolved):
        _validate_expected_links_pre_recompute(snapshot)
    FreeCAD.closeDocument(reopened.Name)


@pytest.mark.e2e
def test_warn_tampered_expected_link_row_fails(tmp_path):
    doc = _box_document("WarnTamperExpected")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Box, ["Face1", "Face999"])
    doc.recompute()
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        workspace = manager.create_workspace()
        snapshot = create_snapshot_bundle_gui(doc.Name, str(workspace), link_policy="warn")
        snapshot["expected_links"] = []
        result = manager.execute(
            "print('must-not-run')",
            {"document": doc.Name, "read_only": True, "execution_mode": "worker"},
            snapshot,
            workspace,
        )
        assert result["success"] is False
        assert result["error_code"] == "external_link_unresolved"
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.unit
def test_validate_snapshot_rejects_malformed_ignored_subelements_type():
    from addon.FreeCADMCP.rpc_server.worker_protocol import validate_snapshot_manifest

    with pytest.raises(ProtocolError):
        validate_snapshot_manifest(
            {
                "link_policy": "warn",
                "expected_links": [],
                "ignored_links": [
                    {
                        "owner_document": "Doc",
                        "owner_object": "Holder",
                        "property": "Support",
                        "reference_index": 0,
                        "target_document": "Doc",
                        "target_object": "Box",
                        "subelements": "Face999",
                    }
                ],
            }
        )


@pytest.mark.unit
def test_validate_snapshot_rejects_ignored_links_under_strict_policy():
    with pytest.raises(ProtocolError):
        from addon.FreeCADMCP.rpc_server.worker_protocol import validate_snapshot_manifest

        validate_snapshot_manifest(
            {
                "link_policy": "strict",
                "expected_links": [],
                "ignored_links": [
                    {
                        "owner_document": "Doc",
                        "owner_object": "Holder",
                        "property": "Support",
                        "reference_index": 0,
                        "target_document": "Doc",
                        "target_object": "Box",
                        "subelements": ["Face999"],
                    }
                ],
            }
        )


@pytest.mark.unit
def test_validate_snapshot_rejects_duplicate_ignored_reference_index():
    from addon.FreeCADMCP.rpc_server.worker_protocol import validate_snapshot_manifest

    entry = {
        "owner_document": "Doc",
        "owner_object": "Holder",
        "property": "Support",
        "reference_index": 0,
        "target_document": "Doc",
        "target_object": "Box",
        "subelements": ["Face999"],
    }
    with pytest.raises(ProtocolError, match="duplicate reference_index"):
        validate_snapshot_manifest(
            {
                "link_policy": "warn",
                "expected_links": [],
                "ignored_links": [entry, dict(entry)],
            }
        )


@pytest.mark.e2e
def test_warn_ignored_face7_becomes_valid_after_recompute(monkeypatch, tmp_path):
    doc = _six_face_target_document("WarnIgnoredFace7Valid")
    with pytest.raises(Exception):
        validate_subelement_reference(doc.Target, "Face7")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Target, ["Face7"])
    doc.recompute()
    workspace = str(tmp_path / "ws-ignored-face7")
    snapshot = create_snapshot_bundle_gui(doc.Name, workspace, link_policy="warn")
    assert snapshot["ok"] is True, snapshot
    assert snapshot.get("expected_links") == []
    assert snapshot["ignored_links"][0]["subelements"] == ["Face7"]
    doc_name = snapshot["primary_document"]
    exit_code, worker_result = _run_warn_snapshot_job(
        monkeypatch,
        tmp_path,
        snapshot,
        recompute_hook=_recompute_expand_target(doc_name),
        job_id="ignored-face7-valid",
    )
    assert exit_code == 0
    assert worker_result["status"] == "ok"
    assert "worker-ok" in worker_result["stdout"]
    merged = _merge_link_warnings(snapshot, worker_result)
    assert any("Face7" in item for item in merged)
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_mixed_retained_and_ignored_face7_becomes_valid(monkeypatch, tmp_path):
    doc = _six_face_target_document("WarnMixedFace7Valid")
    doc.Target.Shape = Part.makeBox(10, 10, 10)
    with pytest.raises(Exception):
        validate_subelement_reference(doc.Target, "Face7")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Target, ["Face1", "Face7"])
    doc.recompute()
    workspace = str(tmp_path / "ws-mixed-face7")
    snapshot = create_snapshot_bundle_gui(doc.Name, workspace, link_policy="warn")
    assert snapshot["ok"] is True, snapshot
    assert snapshot["expected_links"][0]["subelements"] == ["Face1"]
    assert snapshot["ignored_links"][0]["subelements"] == ["Face7"]
    doc_name = snapshot["primary_document"]
    exit_code, worker_result = _run_warn_snapshot_job(
        monkeypatch,
        tmp_path,
        snapshot,
        recompute_hook=_recompute_expand_target(doc_name),
        job_id="mixed-face7-valid",
    )
    assert exit_code == 0
    assert worker_result["status"] == "ok"
    assert "worker-ok" in worker_result["stdout"]
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_retained_remap_and_ignored_face7_becomes_valid(monkeypatch, tmp_path):
    doc = _six_face_target_document("WarnRemapIgnoredFace7")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Target, ["Face1", "Face7"])
    doc.recompute()
    workspace = str(tmp_path / "ws-remap-ignored-face7")
    snapshot = create_snapshot_bundle_gui(doc.Name, workspace, link_policy="warn")
    assert snapshot["ok"] is True, snapshot
    doc_name = snapshot["primary_document"]
    holder_name = holder.Name

    def recompute_remap_and_expand():
        for open_doc in FreeCAD.listDocuments().values():
            open_doc.recompute()
        live = FreeCAD.getDocument(doc_name)
        live.Target.Shape = _expanded_target_shape()
        live.getObject(holder_name).Support = (live.Target, ["Face6", "Face7"])

    exit_code, worker_result = _run_warn_snapshot_job(
        monkeypatch,
        tmp_path,
        snapshot,
        recompute_hook=recompute_remap_and_expand,
        job_id="remap-ignored-face7",
    )
    assert exit_code == 0
    merged = _merge_link_warnings(snapshot, worker_result)
    assert any("invalid_subelement" in item for item in merged)
    assert any("Face1 -> Face6" in item for item in merged)
    assert merged == list(dict.fromkeys(merged))
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_post_recompute_ignored_occurrence_disappears_fails(monkeypatch, tmp_path):
    doc = _six_face_target_document("WarnIgnoredDisappears")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Target, ["Face1", "Face7"])
    doc.recompute()
    snapshot = create_snapshot_bundle_gui(
        doc.Name, str(tmp_path / "ws-ignored-gone"), link_policy="warn"
    )
    doc_name = snapshot["primary_document"]
    holder_name = holder.Name

    def recompute_drop_ignored():
        for open_doc in FreeCAD.listDocuments().values():
            open_doc.recompute()
        live = FreeCAD.getDocument(doc_name)
        live.getObject(holder_name).Support = (live.Target, ["Face1"])

    exit_code, worker_result = _run_warn_snapshot_job(
        monkeypatch,
        tmp_path,
        snapshot,
        code="print('must-not-run')",
        recompute_hook=recompute_drop_ignored,
        job_id="ignored-disappears",
    )
    assert exit_code == 1
    assert "must-not-run" not in worker_result["stdout"]
    assert worker_result["error"]["type"] == "ExternalLinkUnresolved"
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_post_recompute_extra_ignored_occurrence_fails(monkeypatch, tmp_path):
    doc = _six_face_target_document("WarnIgnoredExtra")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Target, ["Face7"])
    doc.recompute()
    snapshot = create_snapshot_bundle_gui(
        doc.Name, str(tmp_path / "ws-ignored-extra"), link_policy="warn"
    )
    doc_name = snapshot["primary_document"]
    holder_name = holder.Name

    def recompute_duplicate_ignored():
        for open_doc in FreeCAD.listDocuments().values():
            open_doc.recompute()
        live = FreeCAD.getDocument(doc_name)
        live.Target.Shape = _expanded_target_shape()
        live.getObject(holder_name).Support = (live.Target, ["Face7", "Face7"])

    exit_code, worker_result = _run_warn_snapshot_job(
        monkeypatch,
        tmp_path,
        snapshot,
        code="print('must-not-run')",
        recompute_hook=recompute_duplicate_ignored,
        job_id="ignored-extra",
    )
    assert exit_code == 1
    assert worker_result["error"]["type"] == "ExternalLinkUnresolved"
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_post_recompute_ignored_only_linksub_disappears_fails(monkeypatch, tmp_path):
    doc = _six_face_target_document("WarnIgnoredOnlyGone")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Target, ["Face7"])
    doc.recompute()
    snapshot = create_snapshot_bundle_gui(
        doc.Name, str(tmp_path / "ws-ignored-only-gone"), link_policy="warn"
    )
    assert snapshot.get("expected_links") == []
    assert snapshot["ignored_links"][0]["reference_index"] == 0
    doc_name = snapshot["primary_document"]
    holder_name = holder.Name

    def recompute_clear_support():
        for open_doc in FreeCAD.listDocuments().values():
            open_doc.recompute()
        live = FreeCAD.getDocument(doc_name)
        live.getObject(holder_name).Support = None

    exit_code, worker_result = _run_warn_snapshot_job(
        monkeypatch,
        tmp_path,
        snapshot,
        code="print('must-not-run')",
        recompute_hook=recompute_clear_support,
        job_id="ignored-only-gone",
    )
    assert exit_code == 1
    assert "must-not-run" not in worker_result["stdout"]
    assert worker_result["error"]["type"] == "ExternalLinkUnresolved"
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_post_recompute_ignored_only_linksublist_occurrence_disappears_fails(
    monkeypatch, tmp_path
):
    doc = _six_face_target_document("WarnIgnoredListGone")
    box = doc.addObject("Part::Box", "Box")
    box.Length = 5
    box.Width = 4
    box.Height = 3
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSubList", "Supports")
    holder.Supports = [
        (doc.Target, ["Face7"]),
        (box, ["Face1"]),
    ]
    doc.recompute()
    snapshot = create_snapshot_bundle_gui(
        doc.Name, str(tmp_path / "ws-ignored-list-gone"), link_policy="warn"
    )
    assert snapshot["ignored_links"][0]["reference_index"] == 0
    doc_name = snapshot["primary_document"]
    holder_name = holder.Name
    box_name = box.Name

    def recompute_drop_ignored_row():
        for open_doc in FreeCAD.listDocuments().values():
            open_doc.recompute()
        live = FreeCAD.getDocument(doc_name)
        live.getObject(holder_name).Supports = [
            (live.getObject(box_name), ["Face1"]),
        ]

    exit_code, worker_result = _run_warn_snapshot_job(
        monkeypatch,
        tmp_path,
        snapshot,
        code="print('must-not-run')",
        recompute_hook=recompute_drop_ignored_row,
        job_id="ignored-list-gone",
    )
    assert exit_code == 1
    assert "must-not-run" not in worker_result["stdout"]
    assert worker_result["error"]["type"] == "ExternalLinkUnresolved"
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_post_recompute_all_ignored_property_empty_fails(monkeypatch, tmp_path):
    doc = _box_document("WarnAllIgnoredEmpty")
    box2 = doc.addObject("Part::Box", "Box2")
    box2.Length = 5
    box2.Width = 4
    box2.Height = 3
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSubList", "Supports")
    holder.Supports = [
        (doc.Box, ["Face999"]),
        (box2, ["Face888"]),
    ]
    doc.recompute()
    snapshot = create_snapshot_bundle_gui(
        doc.Name, str(tmp_path / "ws-all-ignored-empty"), link_policy="warn"
    )
    assert snapshot.get("expected_links") == []
    assert len(snapshot["ignored_links"]) == 2
    doc_name = snapshot["primary_document"]
    holder_name = holder.Name

    def recompute_clear_supports():
        for open_doc in FreeCAD.listDocuments().values():
            open_doc.recompute()
        live = FreeCAD.getDocument(doc_name)
        live.getObject(holder_name).Supports = []

    exit_code, worker_result = _run_warn_snapshot_job(
        monkeypatch,
        tmp_path,
        snapshot,
        code="print('must-not-run')",
        recompute_hook=recompute_clear_supports,
        job_id="all-ignored-empty",
    )
    assert exit_code == 1
    assert "must-not-run" not in worker_result["stdout"]
    assert worker_result["error"]["type"] == "ExternalLinkUnresolved"
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_post_recompute_mixed_reference_disappears_fails(monkeypatch, tmp_path):
    doc = _six_face_target_document("WarnMixedRefGone")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Target, ["Face1", "Face7"])
    doc.recompute()
    snapshot = create_snapshot_bundle_gui(
        doc.Name, str(tmp_path / "ws-mixed-ref-gone"), link_policy="warn"
    )
    doc_name = snapshot["primary_document"]
    holder_name = holder.Name

    def recompute_clear_support():
        for open_doc in FreeCAD.listDocuments().values():
            open_doc.recompute()
        live = FreeCAD.getDocument(doc_name)
        live.getObject(holder_name).Support = None

    exit_code, worker_result = _run_warn_snapshot_job(
        monkeypatch,
        tmp_path,
        snapshot,
        code="print('must-not-run')",
        recompute_hook=recompute_clear_support,
        job_id="mixed-ref-gone",
    )
    assert exit_code == 1
    assert "must-not-run" not in worker_result["stdout"]
    assert worker_result["error"]["type"] == "ExternalLinkUnresolved"
    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_warn_ignored_only_face7_still_invalid_executes(monkeypatch, tmp_path):
    doc = _six_face_target_document("WarnIgnoredOnlyStable")
    with pytest.raises(Exception):
        validate_subelement_reference(doc.Target, "Face7")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Target, ["Face7"])
    doc.recompute()
    snapshot = create_snapshot_bundle_gui(
        doc.Name, str(tmp_path / "ws-ignored-only-stable"), link_policy="warn"
    )
    doc_name = snapshot["primary_document"]

    def recompute_only():
        for open_doc in FreeCAD.listDocuments().values():
            open_doc.recompute()

    exit_code, worker_result = _run_warn_snapshot_job(
        monkeypatch,
        tmp_path,
        snapshot,
        recompute_hook=recompute_only,
        job_id="ignored-only-stable",
    )
    assert exit_code == 0
    assert worker_result["status"] == "ok"
    assert "worker-ok" in worker_result["stdout"]
    FreeCAD.closeDocument(doc.Name)
