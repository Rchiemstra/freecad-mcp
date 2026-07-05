from __future__ import annotations

from importlib.resources import files
from string import Template


def read_template_text(name: str) -> str:
    """Read a packaged text template from freecad_mcp/templates."""
    return (
        files("freecad_mcp")
        .joinpath("templates")
        .joinpath(name)
        .read_text(encoding="utf-8")
    )


def read_template_lines(name: str) -> list[str]:
    return read_template_text(name).strip().splitlines()


def render_template_text(name: str, **values: str) -> str:
    return Template(read_template_text(name)).substitute(values)
