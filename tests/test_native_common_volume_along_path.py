"""Native qualification matrix for typed ``common_volume_along_path``."""

from __future__ import annotations

import pytest

from tests.assembly_io_native_matrix import (
    check_missing_document,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KIND = "volume"


_RUN_ARGS = lambda doc_name, ctx: (doc_name, ctx["mover"], [ctx["wall"]])
_RUN_ARGS_MISSING = lambda _doc, _ctx: ("MissingNativeDoc", "Mover", ["Wall"])


def test_common_volume_along_path_native_success_inspects_after_recompute(monkeypatch):
    check_success("common_volume_along_path", _KIND, _RUN_ARGS, monkeypatch)


def test_common_volume_along_path_native_validation_failure_restores():
    check_validation_failure("common_volume_along_path", _KIND, _RUN_ARGS)


def test_common_volume_along_path_native_missing_document_keeps_typed_error():
    check_missing_document("common_volume_along_path", _RUN_ARGS_MISSING)
