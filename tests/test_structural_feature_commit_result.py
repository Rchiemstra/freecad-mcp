"""Structural feature callbacks cannot overrule the native commit outcome."""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops import sketch_public

pytestmark = pytest.mark.unit


def test_structural_feature_returns_native_rejection_not_cached_callback_result(monkeypatch):
    deferred_calls = []

    class _DeferredResult:
        @staticmethod
        def apply_after_commit():
            deferred_calls.append(True)

        @staticmethod
        def validate_after_recompute():
            pytest.fail("native rejection must not run the feature postcondition")

    def rejected_run(
        _collaborators, _doc_name, callback, *, structural, postcondition
    ):
        assert structural is True
        assert callable(postcondition)
        callback()
        return {
            "success": False,
            "ok": False,
            "error_code": "NATIVE_COMPATIBILITY_MUTATION_REJECTED",
        }

    monkeypatch.setattr(sketch_public, "run_cad_mutation", rejected_run)

    result = sketch_public._run_structural_feature(
        object(), "Model", _DeferredResult
    )

    assert result["error_code"] == "NATIVE_COMPATIBILITY_MUTATION_REJECTED"
    assert deferred_calls == []
