"""Declarative shim — generated gateway dispatch lives in generated/capabilities."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=1)
def load_gateway_dispatch() -> dict[str, Any]:
    path = (
        Path(__file__).resolve().parents[1]
        / "generated"
        / "capabilities"
        / "gateway_dispatch.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = ["load_gateway_dispatch"]
