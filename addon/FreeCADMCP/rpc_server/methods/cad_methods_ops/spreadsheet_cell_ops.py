"""Spreadsheet cell read/write helpers (Phase 4 slice 4F)."""

from __future__ import annotations


def _json_cell_value(value):
    """Return a JSON-safe evaluated Spreadsheet value without dropping units."""

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    # FreeCAD.Quantity is deliberately represented by its display string, e.g.
    # ``"440.00 mm"``.  Numeric coercion would lose the unit and a direct
    # return makes the surrounding RPC response fail JSON serialization.
    return str(value)


def apply_spreadsheet_cell(sheet, cell: dict) -> tuple[dict | None, str | None]:
    addr = cell.get("address") or cell.get("addr")
    alias = cell.get("alias")
    if not addr and alias:
        try:
            addr = sheet.getCellFromAlias(alias)
        except Exception:
            addr = None
    if not addr:
        return None, f"Cell requires address or resolvable alias: {cell!r}"
    if "value" in cell:
        sheet.set(str(addr), str(cell["value"]))
    if alias and cell.get("address"):
        sheet.setAlias(str(addr), str(alias))
    elif cell.get("set_alias"):
        sheet.setAlias(str(addr), str(cell["set_alias"]))
    return {"address": str(addr), "alias": alias}, None


def read_spreadsheet_cell(sheet, item) -> dict:
    addr = item
    alias = None
    if isinstance(item, dict):
        addr = item.get("address") or item.get("addr")
        alias = item.get("alias")
        if not addr and alias:
            addr = sheet.getCellFromAlias(alias)
    row = {"address": str(addr)}
    try:
        row["alias"] = sheet.getAlias(str(addr))
    except Exception:
        row["alias"] = None
    try:
        row["contents"] = sheet.getContents(str(addr))
    except Exception as e:
        row["contents_error"] = str(e)
    try:
        row["value"] = _json_cell_value(sheet.get(str(addr)))
    except Exception as e:
        row["value_error"] = str(e)
    return row
