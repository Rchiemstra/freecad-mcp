"""e2e: document lease acquire → mutate → heartbeat → Save As migrate → release.

Runs under FreeCADCmd (Docker ``e2e`` service or a working FreeCAD Python).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FreeCAD = pytest.importorskip("FreeCAD")
Part = pytest.importorskip("Part")

from addon.FreeCADMCP.document_lock import (
    acquire_lease,
    check_mutation_allowed,
    get_lease,
    heartbeat_lease,
    migrate_lease_key,
    release_lease,
    reset_registry_for_tests,
    set_request_identity,
    sidecar_path_for,
)


@pytest.fixture(autouse=True)
def _clean_registry(tmp_path, monkeypatch):
    reset_registry_for_tests()
    settings = tmp_path / "freecad_mcp_settings.json"
    settings.write_text(
        json.dumps(
            {
                "enable_document_lock": True,
                "document_lock_enforcement": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "addon.FreeCADMCP.document_lock._settings_path",
        lambda: settings,
    )
    yield
    reset_registry_for_tests()
    # Close any leftover docs from this module
    for name in list(FreeCAD.listDocuments()):
        if name.startswith("Lease"):
            try:
                FreeCAD.closeDocument(name)
            except Exception:
                pass


@pytest.mark.e2e
def test_lease_acquire_mutate_save_as_release(tmp_path):
    """Plan verification path: acquire → edit → heartbeat → Save As → release."""
    doc = FreeCAD.newDocument("LeaseSaveAs")
    box = doc.addObject("Part::Box", "Box")
    box.Length = 5
    box.Width = 3
    box.Height = 2
    doc.recompute()

    session_key = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    acq = acquire_lease(
        doc_key=session_key,
        doc_name=doc.Name,
        instance_id="e2e-agent",
        pid=1,
        client="e2e",
        task_description="box then saveAs",
    )
    assert acq["success"] is True
    token = acq["token"]

    # Mutation gate: owned instance may proceed
    set_request_identity(instance_id="e2e-agent", lease_token=token)
    assert check_mutation_allowed(session_key)["success"] is True

    # "Pad/pocket" stand-in: real Part mutation while lease is held
    box.Length = 17
    doc.recompute()
    assert float(box.Length) == 17.0

    hb = heartbeat_lease(
        session_key,
        token,
        current_operation="Box:Length",
        document_dirty=True,
    )
    assert hb["success"] is True
    assert hb["lease"]["current_operation"] == "Box:Length"

    dest = tmp_path / "LeaseSaveAs.FCStd"
    doc.saveAs(str(dest))
    assert dest.is_file()

    dest_key = str(dest.resolve())
    migrated = migrate_lease_key(session_key, dest_key, doc_name=doc.Name)
    assert migrated["success"] is True
    assert migrated["lease"]["token"] == token
    assert migrated["lease"]["doc_key"] == dest_key
    assert sidecar_path_for(dest_key).is_file()
    # Old session key unlocked; new path locked
    assert get_lease(session_key) is None
    assert get_lease(dest_key) is not None
    assert not Path(f"{session_key}.freecad-mcp.lock").exists()

    # Second instance cannot steal the path sidecar
    other = acquire_lease(
        doc_key=dest_key,
        doc_name=doc.Name,
        instance_id="other-agent",
        pid=2,
        client="other",
    )
    assert other["success"] is False
    assert other["error_code"] == "document_locked_by_other"

    rel = release_lease(dest_key, token)
    assert rel["success"] is True
    assert not sidecar_path_for(dest_key).exists()
    assert get_lease(dest_key) is None

    FreeCAD.closeDocument(doc.Name)


@pytest.mark.e2e
def test_unowned_mutation_gate_refuses(tmp_path):
    doc = FreeCAD.newDocument("LeaseGate")
    key = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
    acquire_lease(
        doc_key=key,
        doc_name=doc.Name,
        instance_id="owner",
        pid=1,
    )
    set_request_identity(instance_id="intruder")
    denied = check_mutation_allowed(key)
    assert denied["success"] is False
    assert denied["error_code"] == "document_locked_by_other"
    FreeCAD.closeDocument(doc.Name)
