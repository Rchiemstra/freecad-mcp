"""Tests for execution-mode banners on execute_code results."""

from __future__ import annotations

from mcp.types import TextContent

from freecad_mcp.responses import from_execute_result


def _text(response) -> str:
    content = response.content if hasattr(response, "content") else response
    return " ".join(item.text for item in content if isinstance(item, TextContent))


def test_success_shows_worker_execution_banner():
    resp = from_execute_result(
        {
            "success": True,
            "message": "Python code execution completed.\nOutput: hello",
            "execution": {
                "mode": "worker",
                "job_id": "abc-123",
                "duration_ms": 42.5,
                "snapshot_duration_ms": 10.0,
            },
            "structured": {"freecad_version": ["1", "0", "0"]},
        },
        success_prefix="Code executed successfully",
        fail_prefix="Failed",
        capture_view=False,
    )
    text = _text(resp)
    assert "[execution: worker" in text
    assert "job=abc-123" in text
    assert "42ms" in text or "43ms" in text
    assert resp.structuredContent["execution"]["mode"] == "worker"
    assert "hello" in text


def test_success_shows_gui_execution_banner():
    resp = from_execute_result(
        {
            "success": True,
            "message": "Python code execution completed.\nOutput: hi",
            "execution": {"mode": "gui"},
        },
        success_prefix="Code executed successfully",
        fail_prefix="Failed",
        capture_view=False,
    )
    assert "[execution: gui]" in _text(resp)
