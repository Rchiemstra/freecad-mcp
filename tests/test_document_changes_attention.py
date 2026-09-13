"""The core Document Changes bridge only interrupts for unsafe mutation state."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.lock_indicator_ops.document_changes_controls import (
    _native_readiness,
    _requires_immediate_user_attention,
    _show_document_changes_for_attention,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "readiness",
    [
        {"quarantined": True},
        {"poisoned": True},
        {"ready": False},
    ],
)
def test_unsafe_runtime_or_rollback_state_requires_attention(readiness):
    assert _requires_immediate_user_attention(readiness) is True


def test_unavailable_native_readiness_requires_incompatible_runtime_attention(
    monkeypatch,
):
    class BrokenDocument:
        Name = "Model"

        @staticmethod
        def getMutationReadiness():
            raise RuntimeError("native readiness ABI mismatch")

    monkeypatch.setitem(
        sys.modules,
        "FreeCAD",
        SimpleNamespace(ActiveDocument=BrokenDocument()),
    )

    readiness = _native_readiness()

    assert readiness["ready"] is False
    assert readiness["reasons"] == ["native_readiness_unavailable"]
    assert "ABI mismatch" in readiness["diagnostic"]
    assert _requires_immediate_user_attention(readiness) is True


@pytest.mark.parametrize(
    "readiness",
    [
        None,
        {"ready": True},
        {"ready": False, "pending_transaction": True},
        {"ready": False, "transaction_locked": True},
        {"ready": False, "booked_transaction": 1},
        {"recomputing": True},
        {"must_execute": True},
        {"pending_removal": True},
        {"commit_barrier": True},
        {"notification_replay": True},
    ],
)
def test_transient_or_semantic_readiness_does_not_auto_open(readiness):
    assert _requires_immediate_user_attention(readiness) is False


def test_core_document_changes_panel_is_revealed_when_available():
    calls = []

    class _Dock:
        def show(self):
            calls.append("show")

        def raise_(self):
            calls.append("raise")

    dock = _Dock()
    main = SimpleNamespace(findChild=lambda _kind, _name: dock)
    widgets = SimpleNamespace(QDockWidget=object)

    assert _show_document_changes_for_attention(main, widgets) is True
    assert calls == ["show", "raise"]
