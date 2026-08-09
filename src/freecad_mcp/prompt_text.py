from __future__ import annotations

from importlib.resources import files


ASSET_CREATION_STRATEGY = (
    files("freecad_mcp")
    .joinpath("asset_creation_strategy.txt")
    .read_text(encoding="utf-8")
)
