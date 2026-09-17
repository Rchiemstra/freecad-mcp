"""Optional live authenticated v2 recovery smoke (native GUI / handshake dependent).

Dedicated MCP actions exist (save_document, open_document, undo, redo,
get_request_status, cancel_request). This module does not exercise them live
without native GUI x3 plus an isolated instance-manifest HMAC handshake.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


def test_authenticated_v2_recovery_smoke_not_run_without_native_gui_handshake():
    try:
        import FreeCAD
    except ModuleNotFoundError:
        pytest.skip(
            "ENVIRONMENT_ERROR: FreeCAD runtime unavailable",
            allow_module_level=False,
        )

    if getattr(FreeCAD, "__mcp_test_stub__", False):
        pytest.skip(
            "CAPABILITY_GAP: collection-time FreeCAD stub only; "
            "authenticated v2 recovery smoke requires a live CAD process",
            allow_module_level=False,
        )

    pytest.skip(
        "NOT_TESTED: this job has no identified native GUI FreeCAD binary and "
        "no isolated instance-manifest HMAC handshake on rpc port 9886; "
        "conda-forge Docker FreeCAD is headless and does not satisfy native GUI x3",
        allow_module_level=False,
    )
