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


def test_delete_object_native_validation_failure_restores():
    check_validation_failure("delete_object", _KIND, _RUN_ARGS)


def test_delete_object_native_missing_document_keeps_typed_error():
    check_missing_document("delete_object", _RUN_ARGS_MISSING)
