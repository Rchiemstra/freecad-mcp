"""Shared pytest fixtures for the freecad-mcp test suite."""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from mcp.types import ImageContent, TextContent


# ---------------------------------------------------------------------------
# Connection factories
# ---------------------------------------------------------------------------

def _ok_conn(output: str = "done", recompute_errors: list | None = None):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {
        "success": True,
        "message": output,
        "recompute_errors": recompute_errors or [],
    }
    return conn


def _fail_conn(error: str = "oops"):
    conn = MagicMock()
    conn.get_active_screenshot.return_value = None
    conn.execute_code.return_value = {"success": False, "error": error}
    return conn


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _text(response) -> str:
    return " ".join(item.text for item in response if isinstance(item, TextContent))


def _has_image(response) -> bool:
    return any(isinstance(item, ImageContent) for item in response)


def _code(conn) -> str:
    """Return the code string passed to execute_code on the last call."""
    return conn.execute_code.call_args[0][0]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ok_conn():
    return _ok_conn()


@pytest.fixture
def fail_conn():
    return _fail_conn()
