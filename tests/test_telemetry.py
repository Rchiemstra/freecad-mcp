from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys

import jsonschema
import pytest

from freecad_mcp.telemetry.context import bind_context, get_context
from freecad_mcp.telemetry.events import EVENT_NAMES
from freecad_mcp.telemetry.legacy_parser import parse_legacy_lines
from freecad_mcp.telemetry.redaction import redact_payload
from freecad_mcp.telemetry.writer import TelemetryWriter
from addon.FreeCADMCP.rpc_server.execute_code_analysis import (
    analyze_execute_code,
    typed_tool_warning,
)
from addon.FreeCADMCP.rpc_server import telemetry as addon_telemetry
from scripts.analyze_mcp_telemetry import analyze


pytestmark = pytest.mark.unit


def _schema():
    path = Path(__file__).parents[1] / "src/freecad_mcp/telemetry/schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_writer_emits_schema_valid_monotonic_flushed_jsonl(tmp_path):
    destination = tmp_path / "events.jsonl"
    writer = TelemetryWriter(destination, enabled=True)
    with bind_context(
        task_id="task",
        call_id="call",
        request_id="request",
        execution_id="execution",
    ):
        first = writer.emit("test", "tool_call_received", payload={"value": 1})
        second = writer.emit(
            "test", "tool_call_completed", duration_ms=1.25, payload={}
        )
    lines = destination.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert first["sequence"] == 1 and second["sequence"] == 2
    assert second["monotonic_ns"] >= first["monotonic_ns"]
    assert first["timestamp"].endswith("Z") and len(first["timestamp"]) == 27
    for line in lines:
        jsonschema.validate(json.loads(line), _schema())


def test_redaction_removes_credentials_code_images_and_embedded_secret(monkeypatch):
    secret = "exact-private-value"
    payload = {
        "session_token": secret,
        "message": f"do not leak {secret}",
        "code": "print('raw source sentinel')",
        "screenshot": "A" * 2048,
    }
    value = redact_payload(payload)
    rendered = json.dumps(value)
    assert secret not in rendered
    assert "raw source sentinel" not in rendered
    assert '"kind": "code"' in rendered
    assert "A" * 128 not in rendered

    monkeypatch.setenv("FREECAD_MCP_TELEMETRY_MAX_PAYLOAD_BYTES", "1024")
    value = redact_payload(
        {
            **payload,
            "ordinary_payload": "B" * 4096,
        }
    )
    rendered = json.dumps(value)
    assert secret not in rendered
    assert "raw source sentinel" not in rendered
    assert "A" * 128 not in rendered
    assert value["truncated"] is True


def test_contextvars_isolate_concurrent_calls():
    async def sample(value):
        with bind_context(call_id=value):
            await asyncio.sleep(0)
            return get_context().call_id

    async def run():
        return await asyncio.gather(sample("first"), sample("second"))

    assert asyncio.run(run()) == ["first", "second"]
    assert get_context().call_id == ""


def test_abrupt_write_error_does_not_damage_prior_event(tmp_path, monkeypatch):
    destination = tmp_path / "events.jsonl"
    writer = TelemetryWriter(destination, enabled=True)
    writer.emit("test", "session_started")
    original_open = Path.open

    def failing_open(path, *args, **kwargs):
        if path == destination:
            raise OSError("simulated abrupt failure")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", failing_open)
    assert writer.emit("test", "session_stopped") is None
    monkeypatch.setattr(Path, "open", original_open)
    assert len(destination.read_text(encoding="utf-8").splitlines()) == 1


def test_separate_processes_choose_separate_files(tmp_path):
    script = (
        "from freecad_mcp.telemetry.writer import TelemetryWriter;"
        "w=TelemetryWriter();w.emit('child','session_started');print(w.path.name)"
    )
    environment = dict(os.environ)
    environment["FREECAD_MCP_DEBUG_LOG_DIR"] = str(tmp_path)
    environment["FREECAD_MCP_TELEMETRY"] = "1"
    environment["PYTHONPATH"] = os.pathsep.join(
        [str(Path(__file__).parents[1] / "src"), str(Path(__file__).parents[1])]
    )
    names = {
        subprocess.check_output(
            [sys.executable, "-c", script],
            env=environment,
            text=True,
        ).strip()
        for _ in range(2)
    }
    assert len(names) == 2
    assert len(list(tmp_path.glob("*.jsonl"))) == 2


def test_writer_rotates_with_bounded_backups(tmp_path, monkeypatch):
    destination = tmp_path / "events.jsonl"
    monkeypatch.setenv("FREECAD_MCP_TELEMETRY_MAX_BYTES", "4096")
    monkeypatch.setenv("FREECAD_MCP_TELEMETRY_BACKUPS", "2")
    writer = TelemetryWriter(destination, enabled=True)
    for index in range(12):
        writer.emit(
            "test",
            "tool_call_completed",
            payload={"index": index, "ordinary": "x" * 700},
        )
    assert destination.exists()
    assert destination.with_name("events.jsonl.1").exists()
    assert not destination.with_name("events.jsonl.3").exists()


def test_addon_writer_redacts_exact_secrets_and_caps_payload(tmp_path, monkeypatch):
    destination = tmp_path / "addon.jsonl"
    secret = "addon-one-time-private-token"
    monkeypatch.setenv("FREECAD_MCP_ADDON_TELEMETRY_FILE", str(destination))
    monkeypatch.setenv("FREECAD_MCP_TELEMETRY", "1")
    monkeypatch.setenv("FREECAD_MCP_TELEMETRY_MAX_PAYLOAD_BYTES", "1024")
    entry = addon_telemetry.emit(
        "test",
        "tool_call_completed",
        payload={
            "lease_token": secret,
            "message": f"must redact {secret}",
            "code": "print('addon raw source')",
            "screenshot": "A" * 2048,
            "ordinary": "B" * 4096,
        },
    )
    rendered = json.dumps(entry)
    assert secret not in rendered
    assert "addon raw source" not in rendered
    assert "A" * 128 not in rendered
    assert entry["payload"]["truncated"] is True


def test_required_lifecycle_names_and_legacy_parser():
    required = {
        "session_started",
        "session_stopped",
        "authentication_started",
        "authentication_completed",
        "authentication_failed",
        "tool_call_received",
        "tool_call_completed",
        "rpc_invocation_started",
        "rpc_invocation_completed",
        "rpc_invocation_failed",
        "gui_execution_queued",
        "gui_execution_started",
        "gui_execution_completed",
        "gui_execution_timeout",
        "gui_execution_late_completed",
        "worker_job_created",
        "worker_job_started",
        "worker_job_completed",
        "worker_job_timeout",
        "worker_job_cancel_requested",
        "worker_job_cancelled",
        "transaction_started",
        "transaction_committed",
        "transaction_aborted",
        "transaction_rollback_failed",
        "document_health_checked",
        "cancellation_requested",
        "cancellation_acknowledged",
        "cancellation_completed",
        "recovery_started",
        "recovery_completed",
        "recovery_failed",
    }
    assert required.issubset(EVENT_NAMES)
    parsed = list(parse_legacy_lines(["{\"kind\":\"request\",\"value\":1}\n", "raw\n"]))
    assert parsed[0]["kind"] == "request"
    assert parsed[1]["legacy"] is True
    assert parsed[1]["text"] == "raw"


def test_execute_code_ast_analysis_never_contains_source():
    source = (
        "import FreeCAD as App\n"
        "doc = App.ActiveDocument\n"
        "doc.recompute()\n"
    )
    analysis = analyze_execute_code(
        source,
        {
            "document": "Primary",
            "read_only": False,
            "execution_mode": "gui",
        },
    )
    rendered = json.dumps(analysis)
    assert source not in rendered
    assert analysis["imports"] == ["FreeCAD"]
    assert "doc.recompute" in analysis["call_families"]
    assert analysis["document_scope"] == ["Primary"]
    assert typed_tool_warning(analysis)["code"] == "TYPED_TOOL_AVAILABLE"


def test_migration_analyzer_groups_completed_public_calls_only(tmp_path):
    source = "import FreeCAD\nFreeCAD.ActiveDocument.recompute()\n"
    analysis = analyze_execute_code(
        source,
        {
            "document": "Primary",
            "read_only": False,
            "execution_mode": "gui",
        },
    )
    events = [
        {
            "event": "routing_completed",
            "status": "succeeded",
            "payload": {
                "execution_category": "public_execute_code",
                "analysis": analysis,
            },
        },
        {
            "event": "tool_call_completed",
            "status": "succeeded",
            "session_id": "session",
            "duration_ms": 12.5,
            "payload": {
                "execution_category": "public_execute_code",
                "analysis": analysis,
            },
        },
        {
            "event": "tool_call_completed",
            "status": "succeeded",
            "session_id": "session",
            "duration_ms": 2,
            "payload": {"execution_category": "typed_direct_rpc"},
        },
    ]
    destination = tmp_path / "events.jsonl"
    destination.write_text(
        "".join(json.dumps(item) + "\n" for item in events),
        encoding="utf-8",
    )
    report = analyze([destination])
    assert report["execution_categories"] == {
        "public_execute_code": 1,
        "typed_direct_rpc": 1,
    }
    assert report["public_execute_code_share"] == 0.5
    pattern = report["public_execute_patterns"][0]
    assert pattern["calls"] == 1
    assert pattern["imports"] == ["FreeCAD"]
    assert pattern["operations"] == ["FreeCAD.ActiveDocument.recompute"]
    assert pattern["document_scopes"] == [["Primary"]]
    assert pattern["access_modes"] == {"mutating": 1}
    assert pattern["execution_targets"] == {"gui": 1}
    assert pattern["outcomes"] == {"succeeded": 1}
    assert pattern["latency_ms"]["p95"] == 12.5
    assert source not in json.dumps(report)
