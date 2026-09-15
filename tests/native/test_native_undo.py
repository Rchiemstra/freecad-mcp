"""Native qualification for typed ``undo``."""

from __future__ import annotations

import pytest

from tests.wp_c_native_matrix import check_history_missing, check_history_success

pytestmark = pytest.mark.core


def test_undo_native_success_verifies():
    check_history_success("undo", "with_undo")


def test_undo_native_missing_document_keeps_typed_error():
    check_history_missing("undo")
