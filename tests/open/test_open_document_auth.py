"""Regression: open_document resolves actor on RPC thread before GUI dispatch."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from addon.FreeCADMCP.rpc_server.methods.gui_methods_ops import document_ops

pytestmark = pytest.mark.unit


def test_open_document_calls_request_actor_before_gui_dispatch(monkeypatch) -> None:
    order: list[str] = []

    monkeypatch.setattr(
        document_ops,
        "request_actor",
        lambda facade: order.append("actor") or "runtime",
    )
    monkeypatch.setattr(
        document_ops,
        "dispatch_gui",
        lambda facade, callback, **_kwargs: order.append("dispatch") or callback(),
    )
    monkeypatch.setattr(
        document_ops,
        "_open_checked",
        lambda facade, path, actor: {
            "ok": True,
            "document": "Model",
            "actor": actor,
        },
    )

    facade = SimpleNamespace(_gui_collaborators=MagicMock())
    result = document_ops.open_document(facade, "/model.FCStd")

    assert order == ["actor", "dispatch"]
    assert result == {"ok": True, "document": "Model", "actor": "runtime"}
