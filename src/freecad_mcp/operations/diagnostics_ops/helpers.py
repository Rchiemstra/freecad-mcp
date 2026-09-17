from __future__ import annotations

from ...responses.constants import ToolResponse


def _response_text(resp: ToolResponse) -> str:
    return "".join(
        item.text for item in resp.content if getattr(item, "type", "") == "text"
    )


def keep_historical_extras(result: dict, raw: object, keys: tuple[str, ...]) -> dict:
    """Copy historical extras from the raw RPC payload onto the typed result."""

    if result.get("success") is not True or not isinstance(raw, dict):
        return result
    merged = dict(result)
    for key in keys:
        if key in raw:
            merged[key] = raw[key]
    return merged
