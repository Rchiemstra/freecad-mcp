"""Native qualification for typed ``create_document``."""

from __future__ import annotations

import pytest

from tests.core_doc_native_matrix import (
    check_missing_document,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KIND = "empty"


_RUN_ARGS = lambda document, ctx: (document.Name + "Created",)
_RUN_ARGS_MISSING = lambda _document, _ctx: ("MissingNativeDocCreated",)


def test_create_document_native_success_inspects_after_recompute(monkeypatch):
    check_success("create_document", _KIND, _RUN_ARGS, monkeypatch)


def test_create_document_native_validation_failure_restores():
    check_validation_failure("create_document", _KIND, _RUN_ARGS)


def test_create_document_native_missing_document_keeps_typed_error():
    check_missing_document("create_document", _RUN_ARGS_MISSING)
