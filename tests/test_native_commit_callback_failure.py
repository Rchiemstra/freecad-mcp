"""D-23: an apply/postcondition refusal inside a native commit is a proven, rolled-back rejection.

``DocumentPy::commitCompatibilityMutation`` re-raises the Python callback exception only after
the coordinator rolled the transaction back (a failed rollback is returned as a
``RollbackFailed`` result instead). ``CollaborationAPI`` let that exception escape, so all 78
typed mutations reported a clean refusal - e.g. ``pad_feature`` on a missing sketch - as
``*_NATIVE_EXCEPTION`` / "uncertain" with the sentinel class name as message
("_AbortPadFeatureMutation"), instead of the rejection "Sketch 'NoSuchSketch' not found".
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from addon.FreeCADMCP.collaboration_api import CollaborationAPI
from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.pad_feature_mutation import (
    PadFeatureError,
    run_pad_feature_native_mutation,
)

pytestmark = pytest.mark.unit


class _NativeDocument:
    """Mirror of the C++ contract for a callback failure with a successful rollback."""

    Name = "Chair"

    def __init__(self, *, rollback_fails: bool = False) -> None:
        self.rollback_fails = rollback_fails
        self.rolled_back = False

    def getObject(self, _name):
        return None

    def addObject(self, _type, _name):
        raise AssertionError("not used")

    def commitCompatibilityMutation(self, callback, *, structural=True, recompute=True, postcondition=None, object_name=None):
        try:
            callback()
        except BaseException:
            if self.rollback_fails:
                return {"status": "RollbackFailed", "committed": None, "message": "rollback failed"}
            self.rolled_back = True
            raise
        if postcondition is not None:
            try:
                satisfied = postcondition()
            except BaseException:
                self.rolled_back = True
                raise
            if not satisfied:
                return {"status": "PostconditionFailed", "committed": False, "message": "postcondition failed"}
        return {"status": "Committed", "committed": True, "message": "committed"}


def _collaborators(document: _NativeDocument) -> SimpleNamespace:
    api = CollaborationAPI(document_lookup=lambda _name: document)
    return SimpleNamespace(commit_native_mutation=api.commit_native_mutation, validate_document_invariants=lambda _d: None)


def _missing_sketch(_document) -> None:
    raise PadFeatureError("SKETCH_NOT_FOUND", "Sketch 'NoSuchSketch' not found")


def test_apply_refusal_is_a_rolled_back_rejection_with_the_real_error():
    document = _NativeDocument()
    result = run_pad_feature_native_mutation(_collaborators(document), "Chair", _missing_sketch, lambda _d: None)

    assert document.rolled_back is True
    assert result["success"] is False
    assert result["outcome"] == "rejected"
    assert result["committed"] is False
    assert result["retry_safe"] is True
    assert result["error_code"] == "SKETCH_NOT_FOUND"
    assert result["error"] == "Sketch 'NoSuchSketch' not found"
    assert "_Abort" not in result["error"]


def test_postcondition_exception_is_a_rolled_back_rejection():
    def apply(_document) -> None:
        return None

    def postcondition(_document) -> None:
        raise PadFeatureError("PAD_LENGTH_MISMATCH", "Pad 'P' Length 5 does not match 10")

    result = run_pad_feature_native_mutation(_collaborators(_NativeDocument()), "Chair", apply, postcondition)
    assert result["outcome"] == "rejected"
    assert result["error_code"] == "PAD_LENGTH_MISMATCH"


def test_failed_rollback_stays_uncertain():
    result = run_pad_feature_native_mutation(
        _collaborators(_NativeDocument(rollback_fails=True)), "Chair", _missing_sketch, lambda _d: None
    )
    assert result["success"] is False
    assert result["outcome"] == "uncertain"


def test_unrelated_native_exception_is_not_disguised_as_a_rollback():
    class _Broken(_NativeDocument):
        def commitCompatibilityMutation(self, callback, **_kwargs):
            raise RuntimeError("coordinator crashed before calling back")

    result = run_pad_feature_native_mutation(_collaborators(_Broken()), "Chair", _missing_sketch, lambda _d: None)
    assert result["outcome"] == "uncertain"
