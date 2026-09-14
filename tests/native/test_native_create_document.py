"""Native qualification for typed ``create_document``."""

from __future__ import annotations

import pytest

from tests.core_doc_lifecycle_native_matrix import (
    check_create_document_already_exists,
    check_create_document_success,
    check_create_document_validation_failure,
)

pytestmark = pytest.mark.core


def test_create_document_native_success_inspects_after_recompute(monkeypatch):
    check_create_document_success(monkeypatch)


def test_create_document_native_validation_failure_restores():
    check_create_document_validation_failure()


def test_create_document_native_duplicate_name_keeps_typed_error():
    check_create_document_already_exists()
