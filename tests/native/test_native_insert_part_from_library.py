"""Native qualification for typed ``insert_part_from_library``."""

from __future__ import annotations

import pytest

from tests.core_doc_native_matrix import (
    check_missing_document,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KIND = "empty"


_RUN_ARGS = lambda document, ctx: (document.Name, "Fasteners/Bolts/HexBolt")
_RUN_ARGS_MISSING = lambda _document, _ctx: ("MissingNativeDoc", "Fasteners/Bolts/HexBolt")


def test_insert_part_from_library_native_success_inspects_after_recompute(monkeypatch):
    check_success("insert_part_from_library", _KIND, _RUN_ARGS, monkeypatch)


def test_insert_part_from_library_native_validation_failure_restores():
    check_validation_failure("insert_part_from_library", _KIND, _RUN_ARGS)


def test_insert_part_from_library_native_missing_document_keeps_typed_error():
    check_missing_document("insert_part_from_library", _RUN_ARGS_MISSING)
