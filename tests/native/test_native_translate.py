"""Native qualification matrix for typed ``translate``."""

from __future__ import annotations

import pytest

from tests.assembly_io_native_matrix import (
    check_missing_document,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KIND = "box"


_RUN_ARGS = lambda doc_name, ctx: (doc_name, ctx["box"], 1.0, 2.0, 3.0)
_RUN_ARGS_MISSING = lambda _doc, _ctx: ("MissingNativeDoc", "Box", 1.0, 2.0, 3.0)


def test_translate_native_success_inspects_after_recompute(monkeypatch):
    check_success("translate", _KIND, _RUN_ARGS, monkeypatch)


def test_translate_native_validation_failure_restores():
    check_validation_failure("translate", _KIND, _RUN_ARGS)


def test_translate_native_missing_document_keeps_typed_error():
    check_missing_document("translate", _RUN_ARGS_MISSING)
