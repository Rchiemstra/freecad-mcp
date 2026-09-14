"""Native qualification for typed ``repair_references``."""

from __future__ import annotations

import pytest

from tests.core_doc_native_matrix import (
    check_missing_document,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KIND = "with_object"


_RUN_ARGS = lambda document, ctx: (document.Name, [{"from": "Missing", "to": ctx["object"]}])
_RUN_ARGS_MISSING = lambda _document, _ctx: ("MissingNativeDoc", [{"from": "Missing", "to": "TypedBox"}])


def test_repair_references_native_success_inspects_after_recompute(monkeypatch):
    check_success("repair_references", _KIND, _RUN_ARGS, monkeypatch)


def test_repair_references_native_validation_failure_restores():
    check_validation_failure("repair_references", _KIND, _RUN_ARGS)


def test_repair_references_native_missing_document_keeps_typed_error():
    check_missing_document("repair_references", _RUN_ARGS_MISSING)
