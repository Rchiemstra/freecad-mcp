"""Native qualification for typed ``open_document``."""

from __future__ import annotations

import pytest

from tests.core_doc_native_setup import temp_document_path
from tests.core_doc_native_matrix import (
    check_missing_document,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KIND = "saved"


_RUN_ARGS = lambda document, ctx: (ctx["path"],)
_RUN_ARGS_MISSING = lambda _document, _ctx: ("/no/such/document.FCStd",)


def test_open_document_native_success_inspects_after_recompute(monkeypatch):
    check_success("open_document", _KIND, _RUN_ARGS, monkeypatch)


def test_open_document_native_validation_failure_restores():
    check_validation_failure("open_document", _KIND, _RUN_ARGS)


def test_open_document_native_missing_document_keeps_typed_error():
    check_missing_document("open_document", _RUN_ARGS_MISSING)
