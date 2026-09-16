"""Native qualification matrix for typed ``common_volume_along_path``."""

from __future__ import annotations

import pytest

from tests.wp_c_native_matrix import check_query_missing, check_query_success

pytestmark = pytest.mark.core

_KIND = "volume"
_RUN_ARGS = lambda doc_name, ctx: (
    doc_name,
    ctx["mover"],
    [ctx["wall"]],
    None,
    2,
    [{"x": 0, "y": 0, "z": 0}, {"x": 20, "y": 0, "z": 0}],
)
_RUN_ARGS_MISSING = lambda _doc, _ctx: (
    "MissingNativeDoc",
    "Mover",
    ["Wall"],
    None,
    2,
    [{"x": 0, "y": 0, "z": 0}, {"x": 20, "y": 0, "z": 0}],
)


def test_common_volume_along_path_native_success_observes():
    check_query_success("common_volume_along_path", _KIND, _RUN_ARGS)


def test_common_volume_along_path_native_missing_document_keeps_typed_error():
    check_query_missing("common_volume_along_path", _RUN_ARGS_MISSING)
