"""P10 / I10 spec: `get_view` must return a viewable image, or a structured
geometric diff when a screenshot is unavailable.

In headless/unsupported views the connection returns no screenshot; today
`get_view` replies with a prose string ("Cannot get screenshot ..."). A prose
description can be wrong while the numbers are right (and vice-versa), so the
fallback must be a *structured* diff (JSON with bbox/placement/faces etc.),
not prose.

Unit-layer spec test for the not-yet-implemented I10/P10 improvement.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from mcp.types import ImageContent, TextContent

from freecad_mcp.operations.core import get_view_operation

pytestmark = [
    pytest.mark.unit,
    pytest.mark.xfail(
        strict=True,
        reason="I10/P10 not implemented: get_view returns prose, not a structured diff, when no screenshot",
    ),
]


def _no_screenshot_conn():
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None  # headless / unsupported view
    return conn


def test_get_view_returns_structured_diff_when_no_screenshot():
    response = get_view_operation(_no_screenshot_conn(), "Isometric")
    # Must not be a bare prose string.
    content = response.content if hasattr(response, "content") else response
    text = "".join(item.text for item in content if isinstance(item, TextContent))
    assert not text.startswith("Cannot get screenshot"), (
        f"get_view returned prose fallback: {text!r}"
    )
    # Must be a structured diff: parseable JSON with at least an 'objects' or 'diff' key.
    payload = json.loads(text)
    assert isinstance(payload, dict) and ("objects" in payload or "diff" in payload), (
        f"expected a structured geometric diff, got {payload!r}"
    )
    assert not any(isinstance(item, ImageContent) for item in response)
