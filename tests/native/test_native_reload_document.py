"""Native qualification for typed ``reload_document``."""

from __future__ import annotations

import pytest

from tests.core_doc_lifecycle_native_matrix import (
    check_reload_document_missing,
    check_reload_document_success,
)

pytestmark = pytest.mark.core


def test_reload_document_native_success_verifies_reopened():
    check_reload_document_success()


def test_reload_document_native_missing_document_keeps_typed_error():
    check_reload_document_missing()
