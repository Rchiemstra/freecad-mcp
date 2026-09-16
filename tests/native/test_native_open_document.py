"""Native qualification for typed ``open_document``."""

from __future__ import annotations

import pytest

from tests.core_doc_lifecycle_native_matrix import (
    check_open_document_missing_path,
    check_open_document_success,
    check_open_document_validation_failure,
)

pytestmark = pytest.mark.core


def test_open_document_native_success_inspects_after_recompute(monkeypatch):
    check_open_document_success(monkeypatch)


def test_open_document_native_validation_failure_restores():
    check_open_document_validation_failure()


def test_open_document_native_missing_path_keeps_typed_error():
    check_open_document_missing_path()
