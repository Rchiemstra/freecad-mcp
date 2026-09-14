"""Native qualification matrix for typed ``export_stl``."""

from __future__ import annotations

import pytest

from tests.assembly_io_native_setup import export_temp_path
from tests.assembly_io_native_matrix import (
    check_missing_document,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KIND = "box"


_RUN_ARGS = lambda doc_name, ctx: (doc_name, export_temp_path(".stl"), [ctx["box"]])
_RUN_ARGS_MISSING = lambda _doc, _ctx: ("MissingNativeDoc", export_temp_path(".stl"), ["Box"])


def test_export_stl_native_success_inspects_after_recompute(monkeypatch):
    check_success("export_stl", _KIND, _RUN_ARGS, monkeypatch)


def test_export_stl_native_validation_failure_restores():
    check_validation_failure("export_stl", _KIND, _RUN_ARGS)


def test_export_stl_native_missing_document_keeps_typed_error():
    check_missing_document("export_stl", _RUN_ARGS_MISSING)
