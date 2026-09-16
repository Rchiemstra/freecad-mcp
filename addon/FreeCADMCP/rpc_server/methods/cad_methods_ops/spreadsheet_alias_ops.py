"""Spreadsheet alias enumeration (Phase 4 slice 4F)."""

from __future__ import annotations

from collections.abc import Iterable


def collect_spreadsheet_aliases(sheet: object) -> dict[str, str]:
    aliases: dict[str, str] = {}
    addrs = _spreadsheet_cell_addresses(sheet)
    getter = getattr(sheet, "getAlias", None)
    if not callable(getter):
        return aliases
    for addr in addrs:
        try:
            alias = getter(str(addr))
        except Exception:
            alias = None
        if alias:
            aliases[str(alias)] = str(addr)
    return aliases


def _spreadsheet_cell_addresses(sheet: object) -> list[str]:
    getter = getattr(sheet, "getNonEmptyCells", None)
    if callable(getter):
        try:
            raw = getter()
            addrs = _stringify_addresses(raw)
            if addrs:
                return addrs
        except Exception:
            pass
    return [
        chr(64 + col) + str(row)
        for col in range(1, 27)
        for row in range(1, 101)
    ]


def _stringify_addresses(raw: object) -> list[str]:
    if isinstance(raw, str) or not isinstance(raw, Iterable):
        return []
    return [str(addr) for addr in raw]


__all__ = [
    "collect_spreadsheet_aliases",
]
