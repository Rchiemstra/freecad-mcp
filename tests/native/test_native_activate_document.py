"""Native qualification for typed ``activate_document``."""

from __future__ import annotations

import pytest

from tests.core_doc_lifecycle_native_matrix import (
    check_activate_document_missing,
    check_activate_document_success,
)

pytestmark = pytest.mark.core


def test_activate_document_native_success_verifies_active():
    check_activate_document_success()


def test_activate_document_native_missing_document_keeps_typed_error():
    check_activate_document_missing()
