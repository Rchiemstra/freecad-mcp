"""Synchronous dispatch fake must accept production kwargs without applying replay."""

from __future__ import annotations

import pytest

from tests.helpers.sync_dispatch_gui import synchronous_dispatch_gui

pytestmark = pytest.mark.unit


def test_synchronous_fake_accepts_late_result_transform_without_applying_it():
    def task():
        return "raw"

    seen = []

    def transform(value):
        seen.append(value)
        return f"transformed:{value}"

    result = synchronous_dispatch_gui(
        task,
        timeout=30,
        late_result_transform=transform,
        journal_late_completion=True,
        late_on_complete=lambda *_args, **_kwargs: None,
    )
    assert result == "raw"
    assert seen == []
