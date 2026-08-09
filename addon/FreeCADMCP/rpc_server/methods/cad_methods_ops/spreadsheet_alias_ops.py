"""Spreadsheet alias enumeration (Phase 4 slice 4F)."""

from __future__ import annotations


def collect_spreadsheet_aliases(sheet) -> dict[str, str]:
    aliases: dict[str, str] = {}
    addrs = _spreadsheet_cell_addresses(sheet)
    for addr in addrs:
        try:
            alias = sheet.getAlias(str(addr))
        except Exception:
            alias = None
        if alias:
            aliases[str(alias)] = str(addr)
    return aliases


def _spreadsheet_cell_addresses(sheet) -> list[str]:
    if hasattr(sheet, "getNonEmptyCells"):
        try:
            addrs = list(sheet.getNonEmptyCells())
            if addrs:
                return addrs
        except Exception:
            pass
    return [
        chr(64 + col) + str(row)
        for col in range(1, 27)
        for row in range(1, 101)
    ]
