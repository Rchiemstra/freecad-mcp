"""Native qualification for typed ``recompute_and_wait``."""

from __future__ import annotations

import pytest

from tests.core_doc_native_matrix import (
    check_missing_document,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KIND = "with_object"


_RUN_ARGS = lambda document, ctx: (document.Name,)
_RUN_ARGS_MISSING = lambda _document, _ctx: ("MissingNativeDoc",)


def test_recompute_and_wait_native_success_inspects_after_recompute(monkeypatch):
    check_success("recompute_and_wait", _KIND, _RUN_ARGS, monkeypatch)


def test_recompute_and_wait_native_validation_failure_restores():
    check_validation_failure("recompute_and_wait", _KIND, _RUN_ARGS)


def test_recompute_and_wait_native_missing_document_keeps_typed_error():
    check_missing_document("recompute_and_wait", _RUN_ARGS_MISSING)
