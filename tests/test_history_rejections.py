"""Undo/redo refusals must reach the agent as rejections, not as uncertain.

undo on a misspelled document or an empty history answered "undo response
unavailable: FreeCAD RPC error -32000: ..." with outcome "uncertain", which
tells an agent the document state is unknown although nothing happened.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from freecad_mcp._shared.protocol.redo_contract import parse_redo_response
from freecad_mcp._shared.protocol.undo_contract import parse_undo_response
from freecad_mcp.generated.capabilities.connection_methods import connection_model_ops

pytestmark = pytest.mark.unit


def _connection(readiness):
    return SimpleNamespace(server=SimpleNamespace(get_mutation_readiness=lambda _name: readiness))


@pytest.mark.parametrize(
    "readiness, code",
    [
        ({"success": True, "ready": True, "documents": []}, "DOCUMENT_NOT_FOUND"),
        ({"success": True, "ready": False, "documents": [{}], "reasons": ["recomputing"]},
         "MUTATION_NOT_READY"),
        ({"success": False, "ok": False, "outcome": "rejected", "committed": False,
          "retry_safe": True, "error_code": "DOCUMENT_NOT_FOUND",
          "error": "Document 'NoSuchDoc' not found"}, "DOCUMENT_NOT_FOUND"),
    ],
)
@pytest.mark.parametrize("undo, parse", [(True, parse_undo_response), (False, parse_redo_response)])
def test_preparation_failures_are_rejections(readiness, code, undo, parse):
    prepared = connection_model_ops._prepare_history_mutation(
        _connection(readiness), "NoSuchDoc", undo=undo
    )

    parsed = parse(prepared)

    assert parsed["outcome"] == "rejected", parsed
    assert parsed["error_code"] == code
