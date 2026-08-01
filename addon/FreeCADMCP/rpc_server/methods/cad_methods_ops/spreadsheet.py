"""CAD RPC helpers extracted from ``FreeCADRPC`` (Phase 4 slice 4F)."""

import FreeCAD

from .spreadsheet_alias_ops import collect_spreadsheet_aliases
from .spreadsheet_cell_ops import apply_spreadsheet_cell, read_spreadsheet_cell


def spreadsheet_create(self, doc_name: str, sheet_name: str) -> dict:
    res = self._dispatch_gui(
        lambda: spreadsheet_create_gui(doc_name, sheet_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


def spreadsheet_set_cells(
    self, doc_name: str, sheet_name: str, cells: list
) -> dict:
    res = self._dispatch_gui(
        lambda: spreadsheet_set_cells_gui(doc_name, sheet_name, cells)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


def spreadsheet_get_cells(
    self, doc_name: str, sheet_name: str, addresses: list
) -> dict:
    res = self._dispatch_gui(
        lambda: spreadsheet_get_cells_gui(doc_name, sheet_name, addresses)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


def spreadsheet_set_alias(
    self, doc_name: str, sheet_name: str, address: str, alias: str
) -> dict:
    res = self._dispatch_gui(
        lambda: spreadsheet_set_alias_gui(
            doc_name, sheet_name, address, alias
        )
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


def spreadsheet_list_aliases(self, doc_name: str, sheet_name: str) -> dict:
    res = self._dispatch_gui(
        lambda: spreadsheet_list_aliases_gui(doc_name, sheet_name)
    )
    return res if isinstance(res, dict) else {"success": False, "error": res}


def spreadsheet_create_gui(doc_name, sheet_name):
    try:
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        if doc.getObject(sheet_name):
            return f"Object already exists: {sheet_name}"
        sheet = doc.addObject("Spreadsheet::Sheet", sheet_name)
        doc.recompute()
        return {"success": True, "sheet": sheet.Name}
    except Exception as e:
        return str(e)


def spreadsheet_set_cells_gui(doc_name, sheet_name, cells):
    try:
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        sheet = doc.getObject(sheet_name)
        if not sheet:
            return f"Spreadsheet '{sheet_name}' not found."
        updated = []
        for cell in cells or []:
            row, error = apply_spreadsheet_cell(sheet, cell)
            if error:
                return error
            updated.append(row)
        doc.recompute()
        return {"success": True, "sheet": sheet.Name, "updated": updated}
    except Exception as e:
        return str(e)


def spreadsheet_get_cells_gui(doc_name, sheet_name, addresses):
    try:
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        sheet = doc.getObject(sheet_name)
        if not sheet:
            return f"Spreadsheet '{sheet_name}' not found."
        out = [read_spreadsheet_cell(sheet, item) for item in (addresses or [])]
        return {"success": True, "sheet": sheet.Name, "cells": out}
    except Exception as e:
        return str(e)


def spreadsheet_set_alias_gui(doc_name, sheet_name, address, alias):
    try:
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        sheet = doc.getObject(sheet_name)
        if not sheet:
            return f"Spreadsheet '{sheet_name}' not found."
        sheet.setAlias(str(address), str(alias))
        doc.recompute()
        return {
            "success": True,
            "sheet": sheet.Name,
            "address": address,
            "alias": alias,
        }
    except Exception as e:
        return str(e)


def spreadsheet_list_aliases_gui(doc_name, sheet_name):
    try:
        doc = FreeCAD.getDocument(doc_name)
        if not doc:
            return f"Document '{doc_name}' not found."
        sheet = doc.getObject(sheet_name)
        if not sheet:
            return f"Spreadsheet '{sheet_name}' not found."
        return {
            "success": True,
            "sheet": sheet.Name,
            "aliases": collect_spreadsheet_aliases(sheet),
        }
    except Exception as e:
        return str(e)
