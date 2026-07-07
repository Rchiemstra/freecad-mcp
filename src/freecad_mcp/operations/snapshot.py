"""I7 — snapshot / restore operations: cheap, in-process document copies held in
a ring buffer of the last 5 states on the FreeCAD module, so agent
experimentation is safe (P12). A bad step is one ``restore`` call away.

Backed by ``execute_code`` so the tools work with the original addon (no addon
update or FreeCAD restart) and with the in-process e2e harness. The addon also
exposes parallel ``snapshot`` / ``restore`` RPC methods (see rpc_server.py) that
share the same ``FreeCAD._mcp_snapshots`` ring buffer.
"""
from __future__ import annotations

import logging

from ..freecad_client import FreeCADConnection
from ..responses import ToolResponse
from ..template_resources import render_template_text
from .p7_assembly import _doc_preamble, _run_json_code

logger = logging.getLogger("FreeCADMCPserver")


def snapshot_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
) -> ToolResponse:
    """I7 — snapshot the current document into a ring buffer of the last 5 states.

    Returns JSON ``{ok, snapshot_id, doc, count}``. Use before a risky mutating
    step so it can be undone with ``restore``.
    """
    code = _doc_preamble(doc_name) + [render_template_text(
        "diagnostics/snapshot.py.txt", doc_name=repr(doc_name),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed to snapshot document", screenshot=False,
    )


def restore_operation(
    freecad: FreeCADConnection,
    only_text_feedback: bool,
    doc_name: str,
    snapshot_id: str | None = None,
) -> ToolResponse:
    """I7 — restore a snapshot, replacing the current document in place.

    If ``snapshot_id`` is omitted, the most recent snapshot is restored. Returns
    JSON ``{ok, restored_id, doc, new_doc, count}``.
    """
    code = _doc_preamble(doc_name) + [render_template_text(
        "diagnostics/restore.py.txt",
        doc_name=repr(doc_name),
        snapshot_id=repr(snapshot_id),
    )]
    return _run_json_code(
        freecad, only_text_feedback, "\n".join(code),
        "Failed to restore snapshot", screenshot=False,
    )
