"""Native qualification matrix for typed ``bounding_box``."""

from __future__ import annotations

import pytest

from tests.assembly_io_native_matrix import (
    check_missing_document,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KIND = "box"


_RUN_ARGS = lambda doc_name, ctx: (doc_name, ctx["box"])
_RUN_ARGS_MISSING = lambda _doc, _ctx: ("MissingNativeDoc", "Box")


def test_bounding_box_native_success_inspects_after_recompute(monkeypatch):
    check_success("bounding_box", _KIND, _RUN_ARGS, monkeypatch)


def test_bounding_box_native_validation_failure_restores():
    check_validation_failure("bounding_box", _KIND, _RUN_ARGS)


def test_bounding_box_native_missing_document_keeps_typed_error():
    check_missing_document("bounding_box", _RUN_ARGS_MISSING)
