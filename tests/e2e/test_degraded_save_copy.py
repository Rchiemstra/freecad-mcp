from __future__ import annotations

import pytest

pytest.importorskip("FreeCAD")

pytestmark = pytest.mark.e2e


def test_rpc_v1_save_as_persists_fcstd_without_moving_canonical_savepoint(
    freecad_session,
    tmp_path,
):
    doc = freecad_session.doc
    doc.addObject("Part::Feature", "Feature")
    doc.recompute()
    destination = tmp_path / "degraded-save.FCStd"
    canonical_before = str(doc.FileName or "")

    result = freecad_session._dispatch(
        "save_document_as",
        {"document_name": doc.Name},
        str(destination),
        False,
        "",
        "default",
    )

    assert result["success"] is True
    assert result["saved"] is True
    assert result["verified"] is False
    assert result["storage_verified"] is True
    assert result["protocol_verified"] is False
    assert result["degraded"] is True
    assert result["effective_operation"] == "save_document_copy"
    assert result["canonical_savepoint_changed"] is False
    assert str(doc.FileName or "") == canonical_before
    assert destination.is_file()
    assert result["file_evidence"]["archive"]["ok"] is True
