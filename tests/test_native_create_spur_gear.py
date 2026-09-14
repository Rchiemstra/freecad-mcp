"""Native qualification matrix for typed ``create_spur_gear``."""

from __future__ import annotations

import pytest

from tests.assembly_io_native_matrix import (
    check_missing_document,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KIND = "box"


_RUN_ARGS = lambda doc_name, ctx: (doc_name, "Gear", 12, 2.0, 5.0)
_RUN_ARGS_MISSING = lambda _doc, _ctx: ("MissingNativeDoc", "Gear", 12, 2.0, 5.0)


def test_create_spur_gear_native_success_inspects_after_recompute(monkeypatch):
    check_success("create_spur_gear", _KIND, _RUN_ARGS, monkeypatch)


def test_create_spur_gear_native_validation_failure_restores():
    check_validation_failure("create_spur_gear", _KIND, _RUN_ARGS)


def test_create_spur_gear_native_missing_document_keeps_typed_error():
    check_missing_document("create_spur_gear", _RUN_ARGS_MISSING)
