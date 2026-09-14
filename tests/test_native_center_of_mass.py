"""Native qualification matrix for typed ``center_of_mass``."""

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


def test_center_of_mass_native_success_inspects_after_recompute(monkeypatch):
    check_success("center_of_mass", _KIND, _RUN_ARGS, monkeypatch)


def test_center_of_mass_native_validation_failure_restores():
    check_validation_failure("center_of_mass", _KIND, _RUN_ARGS)


def test_center_of_mass_native_missing_document_keeps_typed_error():
    check_missing_document("center_of_mass", _RUN_ARGS_MISSING)
