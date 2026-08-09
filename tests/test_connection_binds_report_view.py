"""Guard: FreeCADConnection must bind new GUI read methods."""

from __future__ import annotations

import pytest

from tests.helpers import runtime_bootstrap  # noqa: F401

pytestmark = pytest.mark.unit


def test_freecad_connection_binds_get_report_view():
    from freecad_mcp.freecad_client import FreeCADConnection
    from freecad_mcp.freecad_client_ops.facade_bindings import bind_freecad_connection
    from freecad_mcp.operations.interactive import get_report_view_operation

    bind_freecad_connection(FreeCADConnection)
    assert callable(getattr(FreeCADConnection, "get_report_view", None))

    class _Conn:
        def get_report_view(self, max_lines=200, clear=False):
            return {
                "ok": True,
                "text": "hello",
                "line_count": 1,
                "total_lines": 1,
                "truncated": False,
                "cleared": clear,
                "max_lines": max_lines,
            }

    result = get_report_view_operation(_Conn(), max_lines=10, clear=False)
    assert result is not None
