"""Native qualification for typed ``delete_object``."""

from __future__ import annotations

import pytest

from tests.core_doc_native_matrix import (
    check_missing_document,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KIND = "with_object"


_RUN_ARGS = lambda document, ctx: (document.Name, ctx["object"])
_RUN_ARGS_MISSING = lambda _document, _ctx: ("MissingNativeDoc", "TypedBox")


def test_delete_object_native_success_inspects_after_recompute(monkeypatch):
    check_success("delete_object", _KIND, _RUN_ARGS, monkeypatch)


def test_delete_object_native_object_is_gone_after_recompute():
    from tests.core_doc_native_matrix import collaborators, require_native_collaboration

    require_native_collaboration()
    import FreeCAD
    from addon.FreeCADMCP.rpc_server.methods.cad_methods_ops.delete_object import run_delete_object

    document = FreeCAD.newDocument("MCPTypeddelete_objectGone")
    try:
        document.addObject("App::FeaturePython", "TypedBox")
        document.recompute()
        result = run_delete_object(
            collaborators(FreeCAD, lambda _d: None),
            document.Name,
            "TypedBox",
        )
        assert result["success"] is True, result
        assert document.getObject("TypedBox") is None
    finally:
        FreeCAD.closeDocument(document.Name)


def test_delete_object_native_validation_failure_restores():
    check_validation_failure("delete_object", _KIND, _RUN_ARGS)


def test_delete_object_native_missing_document_keeps_typed_error():
    check_missing_document("delete_object", _RUN_ARGS_MISSING)
