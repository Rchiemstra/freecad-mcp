"""Native qualification for typed ``redo``."""

from __future__ import annotations

import pytest

from tests.wp_c_native_matrix import check_history_missing, check_history_success

pytestmark = pytest.mark.core


def test_redo_native_success_verifies():
    check_history_success("redo", "with_undo")


def test_redo_native_missing_document_keeps_typed_error():
    check_history_missing("redo")
