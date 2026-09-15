from __future__ import annotations

from ...responses.constants import ToolResponse


def _response_text(resp: ToolResponse) -> str:
    return "".join(
        item.text for item in resp.content if getattr(item, "type", "") == "text"
    )
