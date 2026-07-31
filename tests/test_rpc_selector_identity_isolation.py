"""Focused RPC tests for selector scan isolation (P3a)."""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.document_lease import (
    DocumentIdentityError,
    DocumentIdentityService,
    IdentityMismatchError,
)
from addon.FreeCADMCP.rpc_server import rpc_server as addon_rpc


class _Document:
    def __init__(self, name: str, path: str) -> None:
        self.Name = name
        self.Label = name
        self.FileName = path
        self.Modified = False


def _install_identity_service(monkeypatch) -> DocumentIdentityService:
    service = DocumentIdentityService()
    monkeypatch.setattr(addon_rpc, "document_identity_service", service)
    monkeypatch.setattr(addon_rpc, "document_lease_service", None)
    return service


@pytest.mark.unit
def test_wedged_candidate_does_not_block_healthy_session_uuid_resolution(
    tmp_path, monkeypatch
):
    wedged_path = tmp_path / "Wedged.FCStd"
    healthy_path = tmp_path / "Healthy.FCStd"
    wedged_path.write_bytes(b"wedged")
    healthy_path.write_bytes(b"healthy")
    wedged = _Document("Wedged", str(wedged_path))
    healthy = _Document("Healthy", str(healthy_path))

    identity_service = _install_identity_service(monkeypatch)
    healthy_identity = identity_service.register_document(healthy)

    def ensure(document):
        if document is wedged:
            raise DocumentIdentityError(
                "live document identity could not be registered"
            )
        return identity_service.register_document(document)

    monkeypatch.setattr(addon_rpc, "_ensure_v2_document", ensure)
    monkeypatch.setattr(
        addon_rpc.FreeCAD,
        "listDocuments",
        lambda: {"Wedged": wedged, "Healthy": healthy},
    )

    document, identity = addon_rpc._live_document_from_selector(
        {"document_session_uuid": healthy_identity.session_uuid}
    )

    assert document is healthy
    assert identity.session_uuid == healthy_identity.session_uuid


@pytest.mark.unit
def test_selected_wedged_document_surfaces_identity_error(tmp_path, monkeypatch):
    wedged_path = tmp_path / "Wedged.FCStd"
    wedged_path.write_bytes(b"wedged")
    wedged = _Document("Wedged", str(wedged_path))

    identity_service = _install_identity_service(monkeypatch)
    wedged_identity = identity_service.register_document(wedged)

    def ensure(_document):
        raise DocumentIdentityError(
            "live document identity could not be registered"
        )

    monkeypatch.setattr(addon_rpc, "_ensure_v2_document", ensure)
    monkeypatch.setattr(
        addon_rpc.FreeCAD, "listDocuments", lambda: {"Wedged": wedged}
    )

    with pytest.raises(
        DocumentIdentityError, match="live document identity could not be registered"
    ):
        addon_rpc._live_document_from_selector(
            {"document_session_uuid": wedged_identity.session_uuid}
        )


@pytest.mark.unit
def test_selected_wedged_bound_proxy_surfaces_identity_error_via_session_uuid(
    tmp_path, monkeypatch
):
    wedged_path = tmp_path / "Wedged.FCStd"
    wedged_path.write_bytes(b"wedged")
    wedged = _Document("Wedged", str(wedged_path))

    identity_service = _install_identity_service(monkeypatch)
    wedged_identity = identity_service.register_document(wedged)
    wedged.Name = "RenamedWedged"
    wedged.Label = "RenamedWedged"
    wedged.FileName = str(tmp_path / "Different.FCStd")

    def ensure(document):
        if document is wedged:
            raise DocumentIdentityError(
                "live document identity could not be registered"
            )
        return identity_service.register_document(document)

    monkeypatch.setattr(addon_rpc, "_ensure_v2_document", ensure)
    monkeypatch.setattr(
        addon_rpc.FreeCAD,
        "listDocuments",
        lambda: {"RenamedWedged": wedged},
    )

    with pytest.raises(
        DocumentIdentityError, match="live document identity could not be registered"
    ):
        addon_rpc._live_document_from_selector(
            {"document_session_uuid": wedged_identity.session_uuid}
        )


@pytest.mark.unit
def test_selected_wedged_document_by_name_surfaces_identity_error(
    tmp_path, monkeypatch
):
    wedged_path = tmp_path / "Wedged.FCStd"
    wedged_path.write_bytes(b"wedged")
    wedged = _Document("Wedged", str(wedged_path))

    identity_service = _install_identity_service(monkeypatch)
    identity_service.register_document(wedged)

    def ensure(_document):
        raise DocumentIdentityError(
            "live document identity could not be registered"
        )

    monkeypatch.setattr(addon_rpc, "_ensure_v2_document", ensure)
    monkeypatch.setattr(
        addon_rpc.FreeCAD, "getDocument", lambda name: wedged if name == "Wedged" else None
    )

    with pytest.raises(
        DocumentIdentityError, match="live document identity could not be registered"
    ):
        addon_rpc._live_document_from_selector({"document_name": "Wedged"})


@pytest.mark.unit
def test_wedged_identity_mismatch_does_not_block_healthy_session_uuid_resolution(
    tmp_path, monkeypatch
):
    wedged_path = tmp_path / "Wedged.FCStd"
    healthy_path = tmp_path / "Healthy.FCStd"
    wedged_path.write_bytes(b"wedged")
    healthy_path.write_bytes(b"healthy")
    wedged = _Document("Wedged", str(wedged_path))
    healthy = _Document("Healthy", str(healthy_path))

    identity_service = _install_identity_service(monkeypatch)
    healthy_identity = identity_service.register_document(healthy)
    identity_service.register_document(wedged)

    def ensure(document):
        if document is wedged:
            raise IdentityMismatchError(
                "live document identity changed outside an explicit "
                "Save As, reload, or restore rebind"
            )
        return identity_service.register_document(document)

    monkeypatch.setattr(addon_rpc, "_ensure_v2_document", ensure)
    monkeypatch.setattr(
        addon_rpc.FreeCAD,
        "listDocuments",
        lambda: {"Wedged": wedged, "Healthy": healthy},
    )

    document, identity = addon_rpc._live_document_from_selector(
        {"document_session_uuid": healthy_identity.session_uuid}
    )

    assert document is healthy
    assert identity.session_uuid == healthy_identity.session_uuid


@pytest.mark.unit
def test_selected_wedged_document_surfaces_identity_mismatch_error(
    tmp_path, monkeypatch
):
    wedged_path = tmp_path / "Wedged.FCStd"
    wedged_path.write_bytes(b"wedged")
    wedged = _Document("Wedged", str(wedged_path))

    identity_service = _install_identity_service(monkeypatch)
    wedged_identity = identity_service.register_document(wedged)

    def ensure(document):
        if document is wedged:
            raise IdentityMismatchError(
                "live document identity changed outside an explicit "
                "Save As, reload, or restore rebind"
            )
        return identity_service.register_document(document)

    monkeypatch.setattr(addon_rpc, "_ensure_v2_document", ensure)
    monkeypatch.setattr(
        addon_rpc.FreeCAD, "listDocuments", lambda: {"Wedged": wedged}
    )

    with pytest.raises(IdentityMismatchError):
        addon_rpc._live_document_from_selector(
            {"document_session_uuid": wedged_identity.session_uuid}
        )


@pytest.mark.unit
def test_selected_wedged_document_by_canonical_path_surfaces_identity_error(
    tmp_path, monkeypatch
):
    wedged_path = tmp_path / "Wedged.FCStd"
    wedged_path.write_bytes(b"wedged")
    wedged = _Document("Wedged", str(wedged_path))

    identity_service = _install_identity_service(monkeypatch)
    wedged_identity = identity_service.register_document(wedged)

    def ensure(document):
        if document is wedged:
            raise DocumentIdentityError(
                "live document identity could not be registered"
            )
        return identity_service.register_document(document)

    monkeypatch.setattr(addon_rpc, "_ensure_v2_document", ensure)
    monkeypatch.setattr(
        addon_rpc.FreeCAD, "listDocuments", lambda: {"Wedged": wedged}
    )

    with pytest.raises(
        DocumentIdentityError, match="live document identity could not be registered"
    ):
        addon_rpc._live_document_from_selector(
            {"canonical_path": wedged_identity.canonical_path}
        )


@pytest.mark.unit
def test_wedged_candidate_does_not_block_healthy_canonical_path_resolution(
    tmp_path, monkeypatch
):
    wedged_path = tmp_path / "Wedged.FCStd"
    healthy_path = tmp_path / "Healthy.FCStd"
    wedged_path.write_bytes(b"wedged")
    healthy_path.write_bytes(b"healthy")
    wedged = _Document("Wedged", str(wedged_path))
    healthy = _Document("Healthy", str(healthy_path))

    identity_service = _install_identity_service(monkeypatch)
    healthy_identity = identity_service.register_document(healthy)
    identity_service.register(name="Wedged", path=str(wedged_path))

    def ensure(document):
        if document is wedged:
            raise DocumentIdentityError(
                "live document identity could not be registered"
            )
        return identity_service.register_document(document)

    monkeypatch.setattr(addon_rpc, "_ensure_v2_document", ensure)
    monkeypatch.setattr(
        addon_rpc.FreeCAD,
        "listDocuments",
        lambda: {"Wedged": wedged, "Healthy": healthy},
    )

    document, identity = addon_rpc._live_document_from_selector(
        {"canonical_path": healthy_identity.canonical_path}
    )

    assert document is healthy
    assert identity.session_uuid == healthy_identity.session_uuid
