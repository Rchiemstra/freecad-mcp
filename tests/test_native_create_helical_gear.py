"""Native qualification matrix for typed ``create_helical_gear``."""

from __future__ import annotations

import pytest

from tests.assembly_io_native_matrix import (
    check_missing_document,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KIND = "box"


_RUN_ARGS = lambda doc_name, ctx: (
    doc_name,
    "Gear",
    6,
    2.0,
    1.0,
    15.0,
    20.0,
    0.0,
    0.0,
    0.0,
    4,
)
_RUN_ARGS_MISSING = lambda _doc, _ctx: (
    "MissingNativeDoc",
    "Gear",
    6,
    2.0,
    1.0,
    15.0,
    20.0,
    0.0,
    0.0,
    0.0,
    4,
)


def test_create_helical_gear_native_success_inspects_after_recompute(monkeypatch):
    check_success("create_helical_gear", _KIND, _RUN_ARGS, monkeypatch)


def test_create_helical_gear_native_validation_failure_restores():
    check_validation_failure("create_helical_gear", _KIND, _RUN_ARGS)


def test_create_helical_gear_native_missing_document_keeps_typed_error():
    check_missing_document("create_helical_gear", _RUN_ARGS_MISSING)
