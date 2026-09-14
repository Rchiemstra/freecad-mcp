"""Native qualification for typed ``create_object``."""

from __future__ import annotations

import pytest

from tests.core_doc_native_matrix import (
    check_missing_document,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KIND = "empty"


_RUN_ARGS = lambda document, ctx: (document.Name, {"Name": "TypedBox", "Type": "App::FeaturePython"})
_RUN_ARGS_MISSING = lambda _document, _ctx: ("MissingNativeDoc", {"Name": "TypedBox", "Type": "App::FeaturePython"})


def test_create_object_native_success_inspects_after_recompute(monkeypatch):
    check_success("create_object", _KIND, _RUN_ARGS, monkeypatch)


def test_create_object_native_validation_failure_restores():
    check_validation_failure("create_object", _KIND, _RUN_ARGS)


def test_create_object_native_missing_document_keeps_typed_error():
    check_missing_document("create_object", _RUN_ARGS_MISSING)
