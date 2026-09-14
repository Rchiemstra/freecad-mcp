"""Native qualification matrix for typed ``scale``."""

from __future__ import annotations

import pytest

from tests.assembly_io_native_matrix import (
    check_missing_document,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KIND = "box"


_RUN_ARGS = lambda doc_name, ctx: (doc_name, ctx["box"], 2.0, 2.0, 2.0)
_RUN_ARGS_MISSING = lambda _doc, _ctx: ("MissingNativeDoc", "Box", 2.0, 2.0, 2.0)


def test_scale_native_success_inspects_after_recompute(monkeypatch):
    check_success("scale", _KIND, _RUN_ARGS, monkeypatch)


def test_scale_native_validation_failure_restores():
    check_validation_failure("scale", _KIND, _RUN_ARGS)


def test_scale_native_missing_document_keeps_typed_error():
    check_missing_document("scale", _RUN_ARGS_MISSING)
