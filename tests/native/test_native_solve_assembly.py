"""Native qualification matrix for typed ``solve_assembly``."""

from __future__ import annotations

import pytest

from tests.assembly_io_native_matrix import (
    check_missing_document,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KIND = "assembly_only"


_RUN_ARGS = lambda doc_name, ctx: (doc_name, ctx.get("assembly", "Assembly"))
_RUN_ARGS_MISSING = lambda _doc, _ctx: ("MissingNativeDoc", "Assembly")


def test_solve_assembly_native_success_inspects_after_recompute(monkeypatch):
    check_success("solve_assembly", _KIND, _RUN_ARGS, monkeypatch)


def test_solve_assembly_native_validation_failure_restores():
    check_validation_failure("solve_assembly", _KIND, _RUN_ARGS)


def test_solve_assembly_native_missing_document_keeps_typed_error():
    check_missing_document("solve_assembly", _RUN_ARGS_MISSING)
