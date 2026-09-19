"""Spreadsheet cell read/write helpers (Phase 4 slice 4F)."""

from __future__ import annotations

from collections.abc import Mapping


def _call_named(target: object, name: str, *args: object) -> object:
    attr = getattr(target, name, None)
    if not callable(attr):
        raise TypeError(name)
    method = attr
    return method(*args)


def _json_cell_value(value: object) -> object:
    """Return a JSON-safe evaluated Spreadsheet value without dropping units."""

    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    # FreeCAD.Quantity is deliberately represented by its display string, e.g.
    # ``"440.00 mm"``.  Numeric coercion would lose the unit and a direct
    # return makes the surrounding RPC response fail JSON serialization.
    return str(value)


def apply_spreadsheet_cell(
    sheet: object, cell: Mapping[str, object]
) -> tuple[dict[str, object] | None, str | None]:
    addr: object = cell.get("address") or cell.get("addr")
    alias = cell.get("alias")
    if not addr and alias is not None:
        getter = getattr(sheet, "getCellFromAlias", None)
        if callable(getter):
            try:
                addr = getter(alias)
            except Exception:
                addr = None
    if not addr:
        return None, f"Cell requires address or resolvable alias: {cell!r}"
    if "value" in cell:
        _call_named(sheet, "set", str(addr), str(cell["value"]))
    alias_to_set = alias if alias and cell.get("address") else cell.get("set_alias")
    if isinstance(alias_to_set, str) and alias_to_set:
        alias_setter = getattr(sheet, "setAlias", None)
        if not callable(alias_setter):
            return None, "spreadsheet cannot set aliases"
        try:
            alias_setter(str(addr), str(alias_to_set))
        except Exception as exc:
            return None, str(exc) or type(exc).__name__
    return {"address": str(addr)}, None


def read_spreadsheet_cell(sheet: object, item: object) -> dict[str, object]:
    addr: object = item
    alias: object = None
    if isinstance(item, dict):
        addr = item.get("address") or item.get("addr")
        alias = item.get("alias")
        if not addr and alias is not None:
            getter = getattr(sheet, "getCellFromAlias", None)
            if callable(getter):
                addr = getter(alias)
    row: dict[str, object] = {"address": str(addr)}
    try:
        row["alias"] = _call_named(sheet, "getAlias", str(addr))
    except Exception:
        row["alias"] = None
    try:
        row["contents"] = _call_named(sheet, "getContents", str(addr))
    except Exception as exc:
        row["contents_error"] = str(exc)
    try:
        row["value"] = _json_cell_value(_call_named(sheet, "get", str(addr)))
    except Exception as exc:
        row["value_error"] = str(exc)
    return row


__all__ = [
    "apply_spreadsheet_cell",
    "read_spreadsheet_cell",
]
