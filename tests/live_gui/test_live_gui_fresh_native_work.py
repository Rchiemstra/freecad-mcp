"""Native MCP callbacks must settle fresh cells beside terminal sheet errors."""
import json
import time

import pytest

from tests.live_gui._support import assert_clean, assert_ok

pytestmark = pytest.mark.live_gui


def test_mixed_terminal_error_and_fresh_dirty_cell(mcp, gui_log, live_gui):
    doc = "FreshNativeWork"
    output = live_gui.workdir / "fresh_native_result.json"
    assert_ok(mcp.call("create_document", name=doc))
    try:
        # Start the real addon API off the GUI thread, after deferred setup
        # commits. No stand-in document, callback adapter or recompute is used.
        assert_ok(mcp.call("execute_code", document=doc, recompute="none", code=f"""
import json, threading, time
from pathlib import Path
from collaboration_api import CollaborationAPI
from rpc_method_context import rpc_method_scope
from rpc_server.mutation_guard_ops.validate_invariants import validate_document_invariants
doc = FreeCAD.getDocument('{doc}')
sheet = doc.addObject('Spreadsheet::Sheet', 'Bridge')
sheet.set('A1', '=1/0')
sheet.set('B1', '42')
def run_native_callback():
    applied = []
    try:
        deadline = time.monotonic() + 30
        while doc.HasPendingTransaction and time.monotonic() < deadline:
            time.sleep(0.01)
        assert not doc.HasPendingTransaction
        def apply(target):
            applied.append(True)
            assert 'Invalid' in target.Bridge.State
            target.Bridge.touchCells('B1')
        with rpc_method_scope('spreadsheet_set_cells'):
            result = CollaborationAPI(document_lookup=FreeCAD.getDocument).commit_native_mutation(
                '{doc}', apply, validate_document_invariants, structural=False)
        result = dict(result, callback_ran=bool(applied))
    except Exception as exc:
        result = {{'exception': str(exc), 'callback_ran': bool(applied)}}
    destination = Path({str(output)!r})
    temporary = destination.with_suffix('.tmp')
    temporary.write_text(json.dumps(result))
    temporary.replace(destination)
threading.Thread(target=run_native_callback, daemon=True).start()
"""))
        deadline = time.monotonic() + 60
        while not output.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert output.exists(), "native callback did not complete"
        result = json.loads(output.read_text())
        assert result["callback_ran"], result
        assert result.get("status") == "RecomputeFailed", result
        assert "document recompute reported an object error" in result["message"], result
        assert "Bridge" in result["message"], result
        assert_ok(mcp.call("spreadsheet_set_cells", doc_name=doc, sheet_name="Bridge",
                           cells=[{"address": "A1", "value": 21}]))
        assert_ok(mcp.call("recompute_document", doc_name=doc))
    finally:
        assert_ok(mcp.call("close_document", doc_name=doc))
    assert_clean(gui_log, r".*(Cells with errors|failed to recompute|document recompute|division by zero|ZeroDivisionError).*",
                 r".*recompute failed.*")
