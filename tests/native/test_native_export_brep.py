"""Native qualification matrix for typed ``export_brep``."""

from __future__ import annotations

import pytest

from tests.assembly_io_native_setup import export_temp_path, write_box_brep
from tests.assembly_io_native_matrix import (
    check_missing_document,
    check_success,
    check_validation_failure,
)

pytestmark = pytest.mark.core

_KIND = "box"


_RUN_ARGS = lambda doc_name, ctx: (doc_name, ctx["box"], export_temp_path(".brep"))
_RUN_ARGS_MISSING = lambda _doc, _ctx: ("MissingNativeDoc", "Box", export_temp_path(".brep"))


def test_export_brep_native_success_inspects_after_recompute(monkeypatch):
    check_success("export_brep", _KIND, _RUN_ARGS, monkeypatch)


def test_export_brep_native_validation_failure_restores():
    check_validation_failure("export_brep", _KIND, _RUN_ARGS)


def test_export_brep_native_missing_document_keeps_typed_error():
    check_missing_document("export_brep", _RUN_ARGS_MISSING)
