"""Native qualification for typed ``close_document``."""

from __future__ import annotations

import pytest

from tests.core_doc_lifecycle_native_matrix import (
    check_close_document_missing,
    check_close_document_success,
)

pytestmark = pytest.mark.core


def test_close_document_native_success_verifies_closed():
    check_close_document_success()


def test_close_document_native_missing_document_keeps_typed_error():
    check_close_document_missing()
