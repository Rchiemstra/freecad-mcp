"""Live FreeCADCmd worker execution, crash recovery, and launch probing."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
FreeCADGui = pytest.importorskip("FreeCADGui")
pytest.importorskip("Part")

if not hasattr(FreeCADGui, "addCommand"):
    FreeCADGui.addCommand = lambda *_args, **_kwargs: None

from addon.FreeCADMCP.rpc_server.snapshot_service import (
    _selection_state,
    create_primary_snapshot_gui,
    create_snapshot_bundle_gui,
)
from addon.FreeCADMCP.rpc_server.worker_manager import WorkerManager, WorkerRuntime
from addon.FreeCADMCP.rpc_server.worker_protocol import read_json_limited, write_json_atomic


MODULE_DIR = Path(__file__).parents[2] / "addon" / "FreeCADMCP" / "rpc_server"


def _runtime() -> WorkerRuntime:
    version = tuple(str(value) for value in FreeCAD.Version()[:4])
    while len(version) < 4:
        version += ("",)
    return WorkerRuntime(
        gui_executable=sys.executable,
        freecad_home=FreeCAD.getHomePath(),
        gui_version=version,
    )


def _document(name: str):
    doc = FreeCAD.newDocument(name)
    box = doc.addObject("Part::Box", "Box")
    box.Length = 17
    box.Width = 3
    box.Height = 2
    doc.recompute()
    return doc


@pytest.mark.e2e
def test_explicit_worker_sees_unsaved_snapshot_and_next_job_succeeds(tmp_path):
    doc = _document("WorkerSnapshot")
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        workspace = manager.create_workspace()
        snapshot = create_primary_snapshot_gui(doc.Name, str(workspace))
        first = manager.execute(
            "d=FreeCAD.getDocument('WorkerSnapshot'); print(float(d.Box.Length))",
            {"document": doc.Name, "read_only": True, "execution_mode": "worker"},
            snapshot,
            workspace,
        )
        assert first["success"] is True
        assert "17.0" in first["message"]

        workspace = manager.create_workspace()
        snapshot = create_primary_snapshot_gui(doc.Name, str(workspace))
        second = manager.execute(
            "print('second worker ok')",
            {"document": doc.Name, "read_only": True, "execution_mode": "worker"},
            snapshot,
            workspace,
        )
        assert second["success"] is True
        assert "second worker ok" in second["message"]
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_python_and_fcmacro_launch_probe_then_keep_python_production_path(tmp_path):
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    executable = manager.discover_executable()
    production = MODULE_DIR / "worker_entry.py"
    macro_probe = tmp_path / "worker entry probe.FCMacro"
    shutil.copy2(production, macro_probe)

    for entry in (production, macro_probe):
        result_path = tmp_path / f"{entry.suffix[1:]}-result.json"
        job_path = tmp_path / f"{entry.suffix[1:]}-job.json"
        job = {
            "schema_version": 1,
            "job_id": str(uuid.uuid4()),
            "kind": "probe",
            "result_path": str(result_path),
        }
        write_json_atomic(job_path, job)
        completed = subprocess.run(
            [str(executable), "-P", str(MODULE_DIR), str(entry), "--pass", str(job_path)],
            capture_output=True,
            timeout=30,
            check=False,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr
        result = read_json_limited(result_path)
        assert result["status"] == "ok"

    # Production retains only the verified .py entry; FCMacro exists only as a
    # generated probe artifact and is never shipped.
    assert production.exists()
    assert not (MODULE_DIR / "worker_entry.FCMacro").exists()


@pytest.mark.e2e
def test_timeout_and_crash_do_not_poison_the_next_worker_job():
    doc = _document("WorkerRecovery")
    manager = WorkerManager(_runtime(), str(MODULE_DIR))

    def run(code: str, timeout: float = 10):
        workspace = manager.create_workspace()
        snapshot = create_primary_snapshot_gui(doc.Name, str(workspace))
        return manager.execute(
            code,
            {
                "document": doc.Name,
                "read_only": True,
                "execution_mode": "worker",
                "timeout_seconds": timeout,
            },
            snapshot,
            workspace,
        )

    try:
        timed_out = run("import time; time.sleep(5)", timeout=1)
        assert timed_out["error_code"] == "worker_timeout"
        assert run("print('after timeout')")["success"] is True

        crashed = run("import os; os._exit(23)")
        assert crashed["error_code"] == "worker_crash"
        recovered = run("print('after crash')")
        assert recovered["success"] is True
        assert "after crash" in recovered["message"]
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_dynamic_freecadgui_import_returns_structured_worker_error():
    doc = _document("WorkerGuiRestriction")
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        workspace = manager.create_workspace()
        snapshot = create_primary_snapshot_gui(doc.Name, str(workspace))
        result = manager.execute(
            "__import__('Free' + 'CADGui')",
            {"document": doc.Name, "read_only": True, "execution_mode": "worker"},
            snapshot,
            workspace,
        )
        assert result["success"] is False
        assert result["error_code"] == "unsupported_worker_gui"
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_dependency_bundle_captures_unsaved_link_and_linksub_state(tmp_path):
    source = FreeCAD.newDocument("WorkerSource")
    box = source.addObject("Part::Box", "Box")
    box.Length = 10
    source.recompute()
    source.saveAs(str(tmp_path / "WorkerSource.FCStd"))

    main = FreeCAD.newDocument("WorkerAssembly")
    main.saveAs(str(tmp_path / "WorkerAssembly.FCStd"))
    link = main.addObject("App::Link", "ExternalBox")
    link.LinkedObject = box
    support = main.addObject("App::FeaturePython", "FaceSupport")
    support.addProperty("App::PropertyLinkSub", "Support")
    # PropertyLinkSub itself is document-scoped, so point it at the local
    # App::Link while that link carries the external document reference.
    support.Support = (link, ["Face1"])
    main.recompute()
    main.save()

    # Change only live state after both documents have saved disk versions.
    box.Length = 29
    source.recompute()
    main.recompute()
    original_files = (source.FileName, main.FileName)
    FreeCAD.setActiveDocument(main.Name)

    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        workspace = manager.create_workspace()
        snapshot = create_snapshot_bundle_gui(main.Name, str(workspace))
        assert snapshot["ok"] is True, snapshot
        assert {item["document_name"] for item in snapshot["documents"]} == {
            source.Name,
            main.Name,
        }
        result = manager.execute(
            "m=FreeCAD.getDocument('WorkerAssembly'); "
            "print(float(m.ExternalBox.LinkedObject.Length)); "
            "print(m.FaceSupport.Support[1])",
            {"document": main.Name, "read_only": True, "execution_mode": "worker"},
            snapshot,
            workspace,
        )
        assert result["success"] is True
        assert "29.0" in result["message"]
        assert "Face1" in result["message"]
        assert (source.FileName, main.FileName) == original_files
        assert FreeCAD.ActiveDocument.Name == main.Name
    finally:
        manager.stop()
        FreeCAD.closeDocument(main.Name)
        FreeCAD.closeDocument(source.Name)


@pytest.mark.e2e
def test_broken_app_link_is_rejected_before_worker_launch(tmp_path):
    doc = FreeCAD.newDocument("BrokenLinkDoc")
    doc.addObject("App::Link", "Broken")
    try:
        snapshot = create_snapshot_bundle_gui(doc.Name, str(tmp_path))
        assert snapshot["ok"] is False
        assert snapshot["error_code"] == "external_link_unresolved"
    finally:
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
@pytest.mark.parametrize("subelement", ["Face999", "Edge999", "Vertex999"])
def test_invalid_linksub_subelements_are_rejected(tmp_path, subelement):
    doc = _document("Invalid" + subelement)
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSub", "Support")
    holder.Support = (doc.Box, [subelement])
    doc.recompute()
    try:
        snapshot = create_snapshot_bundle_gui(doc.Name, str(tmp_path))
        assert snapshot["ok"] is False
        assert snapshot["error_code"] == "external_subelement_unresolved"
        assert subelement in snapshot["error"]
    finally:
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_linksublist_valid_face_edge_vertex_survive_exact_name_aliases():
    doc = _document("ValidSubelementList")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSubList", "Supports")
    holder.Supports = [
        (doc.Box, ["Face1"]),
        (doc.Box, ["Edge1"]),
        (doc.Box, ["Vertex1"]),
    ]
    doc.recompute()
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        workspace = manager.create_workspace()
        snapshot = create_snapshot_bundle_gui(doc.Name, str(workspace))
        assert snapshot["ok"] is True, snapshot
        result = manager.execute(
            "d=FreeCAD.getDocument('ValidSubelementList'); "
            "print(d.Holder.Supports)",
            {"document": doc.Name, "read_only": True, "execution_mode": "worker"},
            snapshot,
            workspace,
        )
        assert result["success"] is True
        for name in ("Face1", "Edge1", "Vertex1"):
            assert name in result["message"]
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_linksublist_mixed_valid_and_invalid_is_rejected(tmp_path):
    doc = _document("MixedSubelementList")
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkSubList", "Supports")
    holder.Supports = [(doc.Box, ["Face1"]), (doc.Box, ["Edge999"])]
    doc.recompute()
    try:
        snapshot = create_snapshot_bundle_gui(doc.Name, str(tmp_path))
        assert snapshot["ok"] is False
        assert snapshot["error_code"] == "external_subelement_unresolved"
        assert "Edge999" in snapshot["error"]
    finally:
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
@pytest.mark.parametrize("field", ["target_object", "target_document"])
def test_reopened_manifest_rejects_broken_target_identity(field):
    doc = _document("BrokenManifestTarget" + field)
    holder = doc.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLink", "Support")
    holder.Support = doc.Box
    doc.recompute()
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        workspace = manager.create_workspace()
        snapshot = create_snapshot_bundle_gui(doc.Name, str(workspace))
        assert snapshot["ok"] is True
        snapshot["expected_links"][0][field] = "DoesNotExist"
        result = manager.execute(
            "print('must not execute')",
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
def test_cyclic_document_dependencies_are_snapshotted_once(tmp_path):
    left = FreeCAD.newDocument("CycleLeft")
    left_box = left.addObject("Part::Box", "LeftBox")
    left.saveAs(str(tmp_path / "CycleLeft.FCStd"))
    right = FreeCAD.newDocument("CycleRight")
    right_box = right.addObject("Part::Box", "RightBox")
    right.saveAs(str(tmp_path / "CycleRight.FCStd"))
    left_link = left.addObject("App::Link", "RightLink")
    right_link = right.addObject("App::Link", "LeftLink")
    left_link.LinkedObject = right_box
    right_link.LinkedObject = left_box
    left.recompute()
    right.recompute()

    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        workspace = manager.create_workspace()
        snapshot = create_snapshot_bundle_gui(left.Name, str(workspace))
        assert snapshot["ok"] is True
        names = [item["document_name"] for item in snapshot["documents"]]
        assert sorted(names) == ["CycleLeft", "CycleRight"]
        assert len(names) == len(set(names))
        result = manager.execute(
            "print(FreeCAD.getDocument('CycleLeft').RightLink.LinkedObject.Name); "
            "print(FreeCAD.getDocument('CycleRight').LeftLink.LinkedObject.Name)",
            {"document": left.Name, "read_only": True, "execution_mode": "worker"},
            snapshot,
            workspace,
        )
        assert result["success"] is True
        assert "RightBox" in result["message"]
        assert "LeftBox" in result["message"]
    finally:
        manager.stop()
        FreeCAD.closeDocument(right.Name)
        FreeCAD.closeDocument(left.Name)


@pytest.mark.e2e
def test_duplicate_labels_use_distinct_internal_names_and_property_link_list(tmp_path):
    first = _document("DuplicateNameOne")
    second = _document("DuplicateNameTwo")
    first.Label = "Duplicate Label"
    second.Label = "Duplicate Label"
    first.saveAs(str(tmp_path / "DuplicateNameOne.FCStd"))
    second.saveAs(str(tmp_path / "DuplicateNameTwo.FCStd"))
    main = FreeCAD.newDocument("DuplicateLabelAssembly")
    main.saveAs(str(tmp_path / "DuplicateLabelAssembly.FCStd"))
    first_link = main.addObject("App::Link", "FirstSource")
    second_link = main.addObject("App::Link", "SecondSource")
    first_link.LinkedObject = first.Box
    second_link.LinkedObject = second.Box
    holder = main.addObject("App::FeaturePython", "Holder")
    holder.addProperty("App::PropertyLinkList", "Sources")
    holder.Sources = [first_link, second_link]
    main.recompute()
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        workspace = manager.create_workspace()
        snapshot = create_snapshot_bundle_gui(main.Name, str(workspace))
        assert snapshot["ok"] is True, snapshot
        assert {item["document_name"] for item in snapshot["documents"]} == {
            first.Name,
            second.Name,
            main.Name,
        }
        result = manager.execute(
            "d=FreeCAD.getDocument('DuplicateLabelAssembly'); "
            "print([o.LinkedObject.Document.Name for o in d.Holder.Sources])",
            {"document": main.Name, "read_only": True, "execution_mode": "worker"},
            snapshot,
            workspace,
        )
        assert result["success"] is True
        assert first.Name in result["message"]
        assert second.Name in result["message"]
    finally:
        manager.stop()
        FreeCAD.closeDocument(main.Name)
        FreeCAD.closeDocument(second.Name)
        FreeCAD.closeDocument(first.Name)


@pytest.mark.e2e
def test_unopened_dependency_is_rejected_without_disk_fallback(tmp_path):
    source = _document("UnopenedDependency")
    source_path = tmp_path / "UnopenedDependency.FCStd"
    source.saveAs(str(source_path))
    main = FreeCAD.newDocument("UnopenedDependencyAssembly")
    main.saveAs(str(tmp_path / "UnopenedDependencyAssembly.FCStd"))
    link = main.addObject("App::Link", "ExternalBox")
    link.LinkedObject = source.Box
    main.recompute()
    main.save()
    FreeCAD.closeDocument(source.Name)
    try:
        snapshot = create_snapshot_bundle_gui(main.Name, str(tmp_path / "worker"))
        assert snapshot["ok"] is False
        assert snapshot["error_code"] == "external_link_unresolved"
    finally:
        FreeCAD.closeDocument(main.Name)


@pytest.mark.e2e
def test_brep_and_step_artifacts_are_sanitized_promoted_and_cleaned():
    doc = _document("WorkerArtifacts")
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    artifact_paths = []
    try:
        workspace = manager.create_workspace()
        snapshot = create_primary_snapshot_gui(doc.Name, str(workspace))
        result = manager.execute(
            "d=FreeCAD.getDocument('WorkerArtifacts'); "
            "emit_artifact('box brep', d.Box, 'brep'); "
            "emit_artifact('box step', d.Box, 'step')",
            {"document": doc.Name, "read_only": True, "execution_mode": "worker"},
            snapshot,
            workspace,
        )
        assert result["success"] is True
        assert [item["name"] for item in result["artifacts"]] == ["box_brep", "box_step"]
        assert [item["format"] for item in result["artifacts"]] == ["brep", "step"]
        artifact_paths = [Path(item["path"]) for item in result["artifacts"]]
        assert all(path.is_file() and path.stat().st_size > 0 for path in artifact_paths)
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)
    assert artifact_paths and not any(path.exists() for path in artifact_paths)


@pytest.mark.e2e
def test_runtime_temp_quota_terminates_worker_and_cleans_partial_files(tmp_path):
    doc = _document("WorkerRuntimeQuota")
    manager = WorkerManager(
        _runtime(),
        str(MODULE_DIR),
        temp_root=tmp_path / "workers",
        monitor_interval_seconds=0.01,
    )
    try:
        workspace = manager.create_workspace()
        snapshot = create_primary_snapshot_gui(doc.Name, str(workspace))
        manager.temp_root_limit_bytes = manager._temp_usage() + 32 * 1024
        result = manager.execute(
            "import time\n"
            "with open('quota-fill.bin', 'wb') as handle:\n"
            "    for _ in range(128):\n"
            "        handle.write(b'x' * 8192)\n"
            "        handle.flush()\n"
            "        time.sleep(0.01)",
            {"document": doc.Name, "read_only": True, "execution_mode": "worker"},
            snapshot,
            workspace,
        )
        assert result["success"] is False
        assert result["error_code"] == "resource_limit_exceeded"
        assert not workspace.exists()
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_worker_stdout_is_truncated_while_streaming():
    doc = _document("WorkerStdoutQuota")
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    try:
        workspace = manager.create_workspace()
        snapshot = create_primary_snapshot_gui(doc.Name, str(workspace))
        result = manager.execute(
            "print('x' * (2 * 1024 * 1024))",
            {"document": doc.Name, "read_only": True, "execution_mode": "worker"},
            snapshot,
            workspace,
        )
        assert result["success"] is True
        assert result["stdout_truncated"] is True
        assert len(result["message"].encode("utf-8")) < 2 * 1024 * 1024
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_active_cancellation_kills_descendant_and_next_job_succeeds(tmp_path):
    if sys.platform == "win32":
        pytest.skip("POSIX descendant-state assertion; Windows uses Job Object tests")
    doc = _document("WorkerActiveCancellation")
    manager = WorkerManager(_runtime(), str(MODULE_DIR))
    pidfile = tmp_path / "descendant.pid"
    result = []
    try:
        workspace = manager.create_workspace()
        snapshot = create_primary_snapshot_gui(doc.Name, str(workspace))
        code = (
            "import subprocess,time\n"
            "child=subprocess.Popen(['sleep','60'])\n"
            f"open({str(pidfile)!r},'w').write(str(child.pid))\n"
            "time.sleep(60)"
        )
        thread = threading.Thread(
            target=lambda: result.append(
                manager.execute(
                    code,
                    {"read_only": True, "execution_mode": "worker"},
                    snapshot,
                    workspace,
                )
            )
        )
        thread.start()
        deadline = time.monotonic() + 10
        status = {}
        while time.monotonic() < deadline:
            status = manager.status()
            if status.get("active_job_id") and pidfile.exists():
                break
            time.sleep(0.05)
        child_pid = int(pidfile.read_text())
        cancellation = manager.cancel(status["active_job_id"])
        assert cancellation["success"] is True
        thread.join(timeout=10)
        assert result[0]["error_code"] == "worker_cancelled"

        deadline = time.monotonic() + 5
        state_path = Path(f"/proc/{child_pid}/status")
        while state_path.exists() and time.monotonic() < deadline:
            state = next(
                line for line in state_path.read_text().splitlines()
                if line.startswith("State:")
            )
            if "Z (zombie)" in state:
                break
            time.sleep(0.05)
        if state_path.exists():
            state = next(
                line for line in state_path.read_text().splitlines()
                if line.startswith("State:")
            )
            assert "Z (zombie)" in state, f"running descendant remains: {state}"
            assert os.environ.get("EXPECT_REAPED_DESCENDANT") != "1", state

        workspace = manager.create_workspace()
        snapshot = create_primary_snapshot_gui(doc.Name, str(workspace))
        recovered = manager.execute(
            "print('after cancellation')",
            {"read_only": True, "execution_mode": "worker"},
            snapshot,
            workspace,
        )
        assert recovered["success"] is True
        assert manager.cancel(recovered["execution"]["job_id"])["error_code"] == (
            "worker_job_not_found"
        )
    finally:
        manager.stop()
        FreeCAD.closeDocument(doc.Name)
