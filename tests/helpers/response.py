"""Extract text/images from MCP tool responses (CallToolResult or legacy lists)."""
from __future__ import annotations

from mcp.types import ImageContent, TextContent


def response_content(response):
    return response.content if hasattr(response, "content") else response


def response_text(response) -> str:
    return " ".join(
        item.text for item in response_content(response) if isinstance(item, TextContent)
    )


def response_has_image(response) -> bool:
    return any(isinstance(item, ImageContent) for item in response_content(response))
