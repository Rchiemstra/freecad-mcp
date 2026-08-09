"""MCP-to-addon lifecycle integration over the real protocol boundaries.

The FreeCAD document in this test is deliberately small and in-memory, but the
transport and authorization stack is not mocked: an SDK ``ClientSession`` calls
registered FastMCP tools, ``FreeCADConnection`` uses loopback XML-RPC, the addon
authenticates ``handshake_v2``/``invoke_v2``, and the real ``GuiDispatcher``
executes each document operation on its owning Qt thread.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import threading
import time
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import FreeCAD
from PySide import QtCore
from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import TextContent

from addon.FreeCADMCP.document_lease import (
    DocumentIdentityService,
    DocumentLeaseService,
    LocalRuntimeIdentity,
    SidecarStore,
    sidecar_path_for,
)
from addon.FreeCADMCP.rpc_server import rpc_server as addon_rpc
from addon.FreeCADMCP.rpc_server.gui_dispatcher import GuiDispatcher
from addon.FreeCADMCP.rpc_server.lease_protocol import (
    RequestReplayCache,
    SessionManager,
    make_runtime_manifest,
)
from addon.FreeCADMCP.rpc_server.save_service import SaveService
from freecad_mcp import server as mcp_server
from freecad_mcp.freecad_client import FreeCADConnection
from freecad_mcp.rpc_auth import InstanceManifest
from freecad_mcp.server_state import ServerState


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _write_fcstd(path: str | os.PathLike[str], object_names: list[str]) -> None:
    """Write the minimum archive needed by SaveService plus test evidence."""

    document_xml = "<Document><Objects>{}</Objects></Document>".format(
        "".join(f'<Object name="{name}" />' for name in object_names)
    )
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Document.xml", document_xml)


class _FakeObject:
    def __init__(self, type_id: str, name: str) -> None:
        self.Name = name
        self.Label = name
        self.TypeId = type_id
        self.PropertiesList: list[str] = []
        self.State: tuple[str, ...] = ()
        self.ViewObject = SimpleNamespace()


class _FakeDocument:
    """Small App::Document contract; all mutations record their Qt affinity."""

    def __init__(self, name: str, path: Path) -> None:
        self.Name = name
        self.Label = name
        self.FileName = str(path)
        self.Modified = False
        self.Objects: list[_FakeObject] = []
        self.expected_gui_thread = None
        self.gui_thread_checks: list[bool] = []
        self.transactions: list[tuple[str, str | None]] = []
        self.recompute_count = 0

    def _record_gui_thread(self) -> None:
        self.gui_thread_checks.append(
            QtCore.QThread.currentThread() == self.expected_gui_thread
        )

    def addObject(self, type_id: str, name: str) -> _FakeObject:
        self._record_gui_thread()
        obj = _FakeObject(type_id, name)
        self.Objects.append(obj)
        self.Modified = True
        return obj

    def getObject(self, name: str) -> _FakeObject | None:
        return next((item for item in self.Objects if item.Name == name), None)

    def recompute(self) -> bool:
        self._record_gui_thread()
        self.recompute_count += 1
        return True

    def openTransaction(self, name: str) -> None:
        self._record_gui_thread()
        self.transactions.append(("open", name))

    def commitTransaction(self) -> None:
        self._record_gui_thread()
        self.transactions.append(("commit", None))

    def abortTransaction(self) -> None:
        self._record_gui_thread()
        self.transactions.append(("abort", None))

    def saveCopy(self, path: str) -> None:
        self._record_gui_thread()
        _write_fcstd(path, [item.Name for item in self.Objects])

    def save(self) -> bool:
        self._record_gui_thread()
        _write_fcstd(self.FileName, [item.Name for item in self.Objects])
        self.Modified = False
        return True


class _TracingGuiDispatcher(GuiDispatcher):
    def __init__(self) -> None:
        super().__init__()
        self.submissions: list[dict[str, Any]] = []

    def submit(
        self,
        callable_,
        timeout,
        *,
        request_id=None,
        session_id=None,
        on_complete=None,
    ):
        self.submissions.append(
            {
                "request_id": request_id,
                "caller_thread": threading.current_thread().name,
            }
        )
        return super().submit(
            callable_,
            timeout,
            request_id=request_id,
            session_id=session_id,
            on_complete=on_complete,
        )


class _TracingFreeCADRPC(addon_rpc.FreeCADRPC):
    """Record boundary crossings while retaining the production dispatch."""

    def __init__(self) -> None:
        super().__init__()
        self.handshakes = 0
        self.v2_calls: list[dict[str, Any]] = []
        self.dispatches: list[tuple[str, str]] = []

    def _dispatch(self, method, params):
        self.dispatches.append((method, threading.current_thread().name))
        return super()._dispatch(method, params)

    def handshake_v2(self, payload):
        self.handshakes += 1
        return super().handshake_v2(payload)

    def invoke_v2(self, payload):
        self.v2_calls.append(
            {
                "method": payload.get("method"),
                "request_id": payload.get("request_id"),
                "credential_count": len(payload.get("lease_credentials") or ()),
            }
        )
        return super().invoke_v2(payload)


def _json_tool_result(result) -> dict[str, Any]:
    assert result.isError is False, [
        item.text for item in result.content if isinstance(item, TextContent)
    ]
    texts = [item.text for item in result.content if isinstance(item, TextContent)]
    assert len(texts) == 1
    return json.loads(texts[0])


@pytest.mark.unit
def test_mcp_tool_to_authenticated_xmlrpc_gui_lifecycle(tmp_path, monkeypatch):
    app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
    dispatcher = _TracingGuiDispatcher()
    failures: list[BaseException] = []

    def run_mcp_session() -> None:
        try:
            asyncio.run(
                _run_mcp_tool_to_authenticated_xmlrpc_gui_lifecycle(
                    tmp_path, monkeypatch, dispatcher
                )
            )
        except BaseException as exc:  # re-raised with its worker traceback below
            failures.append(exc)

    # FastMCP executes synchronous tools on its session thread. Keep that
    # complete MCP stack off Qt's owning thread while the latter pumps queued
    # GuiDispatcher work, matching the real FreeCAD process arrangement.
    workflow = threading.Thread(
        target=run_mcp_session,
        name="test-mcp-session",
        daemon=True,
    )
    workflow.start()
    deadline = time.monotonic() + 60
    while workflow.is_alive() and time.monotonic() < deadline:
        app.processEvents()
        workflow.join(timeout=0.001)
    app.processEvents()
    assert not workflow.is_alive(), "MCP lifecycle did not drain through the Qt queue"
    dispatcher.stop_accepting()
    if failures:
        raise failures[0]


async def _run_mcp_tool_to_authenticated_xmlrpc_gui_lifecycle(
    tmp_path, monkeypatch, dispatcher
):
    """Acquire, mutate, verify-save, and release through every public layer."""

    model_path = tmp_path / "Lifecycle.FCStd"
    _write_fcstd(model_path, [])
    document = _FakeDocument("Lifecycle", model_path)
    documents = {document.Name: document}

    secret = b"freecad-mcp-lifecycle-test-secret!!"
    assert len(secret) >= 32
    secret_path = tmp_path / "profile.secret"
    secret_path.write_bytes(secret)
    secret_path.chmod(0o600)

    profile_id = str(uuid.uuid4())
    settings_path = tmp_path / "freecad_mcp_settings.json"

    monkeypatch.setattr(FreeCAD, "getUserAppDataDir", lambda: str(tmp_path))
    monkeypatch.setattr(FreeCAD, "getDocument", documents.get)
    monkeypatch.setattr(FreeCAD, "listDocuments", lambda: dict(documents))
    monkeypatch.setattr(FreeCAD, "ActiveDocument", document)

    xmlrpc_server = addon_rpc.FilteredXMLRPCServer(
        ("127.0.0.1", 0),
        allowed_ips_str="127.0.0.1",
        allow_none=True,
        logRequests=False,
    )
    port = int(xmlrpc_server.server_address[1])
    settings_path.write_text(
        json.dumps(
            {
                "document_lease_mode": "enforce",
                "profile_instance_id": profile_id,
                "instance_id": profile_id,
                "rpc_bind_host": "127.0.0.1",
                "rpc_port": port,
                "auth_secret_file": str(secret_path),
                "allowed_ips": "127.0.0.1",
            }
        ),
        encoding="utf-8",
    )

    addon_manifest = make_runtime_manifest(
        profile_id=profile_id,
        boot_id="test-boot",
        rpc_host="127.0.0.1",
        rpc_port=port,
        freecad_version="0.21.0-test",
        freecad_revision="test-revision",
        addon_version="0.1.20",
        addon_build_id="freecad-mcp-addon-0.1.20",
        profile_path_fingerprint=hashlib.sha256(
            os.path.normcase(os.path.realpath(tmp_path)).encode("utf-8")
        ).hexdigest(),
    )
    identity_service = DocumentIdentityService()
    lease_service = DocumentLeaseService(
        identity_service,
        SidecarStore(network_detector=lambda _path: False),
        local_runtime_identity=LocalRuntimeIdentity(
            addon_profile_id=addon_manifest.profile_id,
            addon_runtime_id=addon_manifest.addon_runtime_id,
            freecad_pid=addon_manifest.freecad_pid,
            freecad_process_started_at=(addon_manifest.freecad_process_started_at),
            boot_id=addon_manifest.boot_id,
            hostname=addon_rpc.platform.node(),
        ),
    )
    document.expected_gui_thread = dispatcher.thread()
    rpc = _TracingFreeCADRPC()
    worker_validations: list[dict[str, Any]] = []

    def validate_saved_worker(path, document_name, profile, expected):
        with zipfile.ZipFile(path, "r") as archive:
            document_xml = archive.read("Document.xml").decode("utf-8")
        worker_validations.append(
            {
                "path": path,
                "document_name": document_name,
                "profile": profile,
                "expected": expected,
            }
        )
        missing = [name for name in expected["objects"] if name not in document_xml]
        return {"ok": not missing, "missing": missing}

    monkeypatch.setattr(addon_rpc, "gui_dispatcher", dispatcher)
    monkeypatch.setattr(addon_rpc, "document_identity_service", identity_service)
    monkeypatch.setattr(addon_rpc, "document_lease_service", lease_service)
    monkeypatch.setattr(addon_rpc, "save_service", SaveService())
    monkeypatch.setattr(addon_rpc, "rpc_runtime_manifest", addon_manifest)
    monkeypatch.setattr(
        addon_rpc, "rpc_server_runtime_id", addon_manifest.addon_runtime_id
    )
    monkeypatch.setattr(
        addon_rpc,
        "rpc_server_actual_endpoint",
        {"host": "127.0.0.1", "port": port},
    )
    monkeypatch.setattr(
        addon_rpc,
        "rpc_session_manager",
        SessionManager(manifest=addon_manifest, secret=secret),
    )
    monkeypatch.setattr(addon_rpc, "rpc_request_replay_cache", RequestReplayCache())
    monkeypatch.setattr(
        addon_rpc, "_validate_saved_document_worker", validate_saved_worker
    )

    xmlrpc_server.register_instance(rpc)
    xmlrpc_thread = threading.Thread(
        target=xmlrpc_server.serve_forever,
        name="test-addon-xmlrpc",
        daemon=True,
    )
    xmlrpc_thread.start()

    client_manifest = InstanceManifest(
        rpc_host="127.0.0.1",
        rpc_port=port,
        profile_instance_id=profile_id,
        profile_path=str(tmp_path),
        auth_secret_file=str(secret_path),
        expected_freecad_pid=addon_manifest.freecad_pid,
        expected_freecad_process_started_at=(addon_manifest.freecad_process_started_at),
        expected_addon_runtime_id=addon_manifest.addon_runtime_id,
        expected_boot_id=addon_manifest.boot_id,
        expected_protocol_version=addon_manifest.protocol_version,
        expected_protocol_features=addon_manifest.features,
        expected_addon_version=addon_manifest.addon_version,
        expected_addon_build_id=addon_manifest.addon_build_id,
        expected_freecad_version=addon_manifest.freecad_version,
        expected_freecad_revision=addon_manifest.freecad_revision,
        expected_profile_path_fingerprint=addon_manifest.profile_path_fingerprint,
        created_at=_utc_now(),
    )
    manifest_path = tmp_path / "instance-manifest.json"
    manifest_path.write_text(
        json.dumps(client_manifest.to_dict()), encoding="utf-8"
    )
    test_state = ServerState(
        only_text_feedback=True,
        rpc_host="127.0.0.1",
        rpc_port=port,
        instance_id=profile_id,
        mcp_instance_id=str(uuid.uuid4()),
        mcp_client_label="lifecycle-test",
        mcp_pid=os.getpid(),
        mcp_host="test-host",
        mcp_process_started_at=_utc_now(),
        instance_manifest_path=str(manifest_path),
        instance_manifest_path_identity=os.path.normcase(
            os.path.realpath(str(manifest_path))
        ),
        auth_file=str(secret_path),
        instance_manifest=client_manifest,
    )
    monkeypatch.setattr(mcp_server, "state", test_state)

    raw_lease_token = ""
    try:
        async with create_connected_server_and_client_session(
            mcp_server.mcp,
            read_timeout_seconds=timedelta(seconds=20),
            raise_exceptions=True,
        ) as session:
            acquired = _json_tool_result(
                await session.call_tool(
                    "acquire_document_lock",
                    {
                        "doc_name": document.Name,
                        "task_description": "MCP boundary lifecycle test",
                        "agent_id": str(uuid.uuid4()),
                    },
                )
            )
            credential = acquired["credential"]
            session_uuid = credential["document_session_uuid"]
            raw_lease_token = credential["token"]
            assert acquired["success"] is True
            assert acquired["lease"]["state"] == "LOCKED_IDLE"
            assert test_state.document_sessions == {document.Name: session_uuid}
            assert (
                test_state.lease_manager.require(
                    document_session_uuid=session_uuid
                ).token
                == raw_lease_token
            )
            assert isinstance(test_state.freecad_connection, FreeCADConnection)
            assert test_state.authenticated_manifest.addon_runtime_id == (
                addon_manifest.addon_runtime_id
            )

            sidecar = sidecar_path_for(model_path)
            assert sidecar.is_file()
            sidecar_text = sidecar.read_text(encoding="utf-8")
            assert raw_lease_token not in sidecar_text
            assert "token_fingerprint" in sidecar_text
            persisted = lease_service.sidecar_store.read(sidecar)
            assert persisted.owner.hostname == addon_rpc.platform.node()
            assert persisted.owner.hostname != test_state.mcp_host
            assert (
                persisted.owner.boot_id == lease_service.local_runtime_identity.boot_id
            )
            assert persisted.owner.freecad_process_started_at == (
                lease_service.local_runtime_identity.freecad_process_started_at
            )

            created = await session.call_tool(
                "create_object",
                {
                    "doc_name": document.Name,
                    "obj_type": "Part::Feature",
                    "obj_name": "BoundaryObject",
                },
            )
            assert created.isError is False
            assert document.getObject("BoundaryObject") is not None
            assert document.Modified is True
            assert document.transactions == [
                ("open", "MCP: create_object"),
                ("commit", None),
            ]

            status = _json_tool_result(
                await session.call_tool(
                    "get_document_lock",
                    {
                        "selector": {
                            "document_session_uuid": session_uuid,
                            "document_name": document.Name,
                        }
                    },
                )
            )
            assert status["locked"] is True
            assert status["lease"]["lease"]["state"] == "LOCKED_IDLE"
            assert status["lease"]["document_state"]["dirty"] is True
            assert raw_lease_token not in json.dumps(status, sort_keys=True)

            finalized = _json_tool_result(
                await session.call_tool(
                    "finalize_document_edit",
                    {
                        "selector": {
                            "document_session_uuid": session_uuid,
                            "document_name": document.Name,
                            "canonical_path": str(model_path),
                        },
                        "save_mode": "save",
                        "validation_profile": "default",
                    },
                )
            )
            assert finalized["success"] is True
            assert finalized["released"] is True
            assert finalized["release"]["lease"]["state"] == "UNLOCKED_SAVED"
            assert finalized["save"]["domain_validation"]["ok"] is True
            assert document.Modified is False
            assert not sidecar.exists()
            assert lease_service.list_records() == []
            assert (
                test_state.lease_manager.get(document_session_uuid=session_uuid) is None
            )
            assert test_state.document_sessions == {}

            assert len(worker_validations) == 1
            assert worker_validations[0]["expected"]["objects"] == ["BoundaryObject"]

            assert rpc.handshakes == 1
            assert [item["method"] for item in rpc.v2_calls] == [
                "acquire_document_lock",
                "create_object",
                "finalize_document_edit",
            ]
            assert [item["credential_count"] for item in rpc.v2_calls] == [0, 1, 1]
            assert len({item["request_id"] for item in rpc.v2_calls}) == 3
            assert all(
                threading_name.startswith("FreeCADMCP-RPC")
                for method, threading_name in rpc.dispatches
                if method == "invoke_v2"
            )
            create_request_id = next(
                item["request_id"]
                for item in rpc.v2_calls
                if item["method"] == "create_object"
            )
            assert any(
                item["request_id"] == create_request_id
                for item in dispatcher.submissions
            )
            # Acquisition, guarded mutation, and finalize's save/verify/promote
            # phases each cross the production GUI dispatcher.
            # Acquisition and typed finalization deliberately use multiple
            # bounded GUI phases around caller-thread hashing/worker checks.
            # The exact number can grow when a new lightweight revalidation
            # phase is added; every live-document touch must still be queued.
            assert len(dispatcher.submissions) >= 5
            assert document.gui_thread_checks
            assert all(document.gui_thread_checks)
    finally:
        xmlrpc_server.begin_shutdown()
        xmlrpc_server.shutdown()
        xmlrpc_server.server_close()
        xmlrpc_thread.join(timeout=5)
        assert not xmlrpc_thread.is_alive()

    # Acquisition is the only permitted public disclosure of the raw token.
    # Finalization removes the sidecar and the MCP-side credential custody.
    assert raw_lease_token
    assert raw_lease_token not in json.dumps(lease_service.list_records())
