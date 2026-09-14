"""Late/replay transformation is separate from the synchronous dispatch fake."""

from __future__ import annotations

import pytest

from addon.FreeCADMCP.rpc_server.methods.dispatch_helpers_ops.late_result_transform import (
    apply_late_result_transform,
)
from tests.helpers.sync_dispatch_gui import synchronous_dispatch_gui

pytestmark = pytest.mark.unit


def test_late_transform_rewrites_the_journaled_value():
    def transform(value):
        return {"wrapped": value}

    result, error = apply_late_result_transform({"n": 1}, transform)
    assert error is None
    assert result == {"wrapped": {"n": 1}}


def test_late_transform_error_is_returned_without_replacing_the_raw_value():
    def transform(_value):
        raise RuntimeError("boom")

    result, error = apply_late_result_transform("raw", transform)
    assert result == "raw"
    assert isinstance(error, RuntimeError)


def test_missing_late_transform_is_a_no_op():
    result, error = apply_late_result_transform("raw", None)
    assert result == "raw"
    assert error is None


def test_synchronous_dispatch_does_not_use_the_late_transform():
    seen = []

    def transform(value):
        seen.append(value)
        return {"wrapped": value}

    result = synchronous_dispatch_gui(lambda: "raw", late_result_transform=transform)
    assert result == "raw"
    assert seen == []
