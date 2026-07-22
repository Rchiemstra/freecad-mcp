"""Unit tests for spoolcase feedback priorities R1-R9."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from freecad_mcp.debug_log import debug_enabled, log_event, redact_payload
from freecad_mcp.operations.core import execute_code_operation
from freecad_mcp.responses import tool_fail, tool_ok
import setup_cursor_mcp


def _text(resp) -> str:
    return resp.content[0].text


@pytest.mark.unit
class TestDebugLog:
    def test_debug_disabled_by_default(self, monkeypatch):
        monkeypatch.delenv("FREECAD_MCP_DEBUG", raising=False)
        assert debug_enabled() is False

    def test_redacts_code_and_images(self):
        payload = {
            "code": "print('secret model path')",
            "content": [{"mimeType": "image/png", "data": "A" * 500}],
        }
        safe = redact_payload(payload)
        text = json.dumps(safe)
        assert "secret model path" not in text
        assert "A" * 100 not in text

    def test_recursively_redacts_credentials_and_message_echoes(self):
        lease_token = "lease-token-must-not-reach-debug-log"
        session_token = "session-token-must-not-reach-debug-log"
        fingerprint = "sha256:fingerprint-must-not-reach-debug-log"
        wrapped_secret = "wrapped-secret-must-not-reach-debug-log"
        payload = {
            "credential": {
                "lease_id": "useful-lease-id",
                "token": lease_token,
            },
            "session_token": session_token,
            "token_fingerprint": fingerprint,
            "auth_secret": {"current": wrapped_secret},
            "nested": {
                "message": (
                    f"failed with {lease_token}, {session_token}, {fingerprint}, "
                    f"and {wrapped_secret}"
                ),
                "safe": "useful diagnostic",
            },
        }

        safe = redact_payload(payload)
        rendered = json.dumps(safe, sort_keys=True)

        assert lease_token not in rendered
        assert session_token not in rendered
        assert fingerprint not in rendered
        assert wrapped_secret not in rendered
        assert safe["credential"]["lease_id"] == "useful-lease-id"
        assert safe["nested"]["safe"] == "useful diagnostic"
        assert "[REDACTED]" in safe["nested"]["message"]

    def test_log_event_redacts_supplied_secret_from_error_and_message(
        self, monkeypatch, tmp_path
    ):
        monkeypatch.setenv("FREECAD_MCP_DEBUG", "1")
        log_file = tmp_path / "mcp_debug.log"
        secret = "out-of-band-secret-must-not-reach-debug-log"

        log_event(
            "test",
            payload={"message": f"payload echoed {secret}", "safe": "kept"},
            error=f"transport echoed {secret}",
            secrets=(secret,),
            path=log_file,
        )

        rendered = log_file.read_text(encoding="utf-8")
        entry = json.loads(rendered)
        assert secret not in rendered
        assert entry["error"] == "transport echoed [REDACTED]"
        assert entry["payload"]["message"] == "payload echoed [REDACTED]"
        assert entry["payload"]["safe"] == "kept"

    def test_log_rotation(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FREECAD_MCP_DEBUG", "1")
        monkeypatch.setenv("FREECAD_MCP_DEBUG_MAX_BYTES", "200")
        log_file = tmp_path / "mcp_debug.log"
        log_file.write_text("x" * 250, encoding="utf-8")
        log_event("test", tool="ping", path=log_file)
        assert log_file.exists()
        assert (log_file.parent / (log_file.name + ".1")).exists()


@pytest.mark.unit
class TestIsErrorSemantics:
    def test_tool_fail_sets_is_error(self):
        resp = tool_fail("boom")
        assert resp.isError is True

    def test_tool_ok_not_error(self):
        resp = tool_ok("ok")
        assert resp.isError is False

    def test_execute_code_failure_is_error(self):
        conn = MagicMock()
        conn.execute_code.return_value = {
            "success": False,
            "error": "Invalid parameters",
            "structured": {"exception_type": "ValueError", "message": "Invalid parameters"},
        }
        resp = execute_code_operation(conn, True, "raise ValueError('Invalid parameters')")
        assert resp.isError is True
        assert "Invalid parameters" in _text(resp)

    def test_execute_code_success_not_error(self):
        conn = MagicMock()
        conn.execute_code.return_value = {
            "success": True,
            "message": "Python code execution completed.\nOutput: hello",
            "recompute_errors": [],
        }
        resp = execute_code_operation(conn, True, "print('hello')", capture_view=False)
        assert resp.isError is False


@pytest.mark.unit
class TestConfigMerge:
    def test_merge_preserves_unrelated_servers(self, tmp_path):
        cfg = tmp_path / "mcp.json"
        cfg.write_text(
            json.dumps({"mcpServers": {"gmail": {"command": "gmail-mcp"}}}),
            encoding="utf-8",
        )
        setup_cursor_mcp.merge_config(cfg, {"command": "python", "args": ["run.py"]})
        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert "gmail" in data["mcpServers"]
        assert data["mcpServers"]["freecad"]["command"] == "python"
