"""The worker snapshot scope is stated on execute_code."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[2]
_COPIES = (
    ROOT / "src/freecad_mcp/generated/capabilities/register_modules/tools_core_execute.py",
    ROOT / "src/freecad_mcp/capabilities/core/manifest.py",
    ROOT / "src/freecad_mcp/generated/capabilities/registry_snapshot.json",
    ROOT / "tests/fixtures/mcp_tool_registry_contract_snapshot.json",
)


def test_execute_code_still_documents_read_only_worker_mode():
    text = _COPIES[0].read_text(encoding="utf-8")
    assert "read_only=true" in text
    assert 'execution_mode="worker"' in text


def test_execute_code_names_the_worker_snapshot_documents():
    for path in _COPIES:
        text = path.read_text(encoding="utf-8")
        assert "open linked documents" in text, path.name
        assert "active document when ``document`` is omitted" in text, path.name
        assert "App.listDocuments()" in text, path.name
