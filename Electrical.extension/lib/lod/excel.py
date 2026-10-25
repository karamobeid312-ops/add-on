# -*- coding: utf-8 -*-
"""Reading the LOD workbook (.xlsx or .xls) with Microsoft Excel, through
COM with .NET reflection like vdrop.excel, so it works in pyRevit's
IronPython and CPython engines. The workbook is opened read-only and closed
again; it is never changed."""
from vdrop.excel import ExcelMissing, _call, _get, _release, _set

__all__ = ["ExcelMissing", "read_sheets"]


def _values(sheet):
    """Cell values of the used range, as rows from cell A1."""
    used = _get(sheet, "UsedRange")
    try:
        first_row = int(_get(used, "Row"))
        first_col = int(_get(used, "Column"))
        rows_obj = _get(used, "Rows")
        cols_obj = _get(used, "Columns")
        n_rows = int(_get(rows_obj, "Count"))
        n_cols = int(_get(cols_obj, "Count"))
        _release(rows_obj, cols_obj)
        data = _get(used, "Value2")
    finally:
        _release(used)
    width = first_col - 1 + n_cols
    rows = [[None] * width for _ in range(first_row - 1)]
    if data is None:
        return rows
    if not hasattr(data, "GetValue"):              # a single cell
        row = [None] * width
        row[first_col - 1] = data
        return rows + [row]
    r0, c0 = data.GetLowerBound(0), data.GetLowerBound(1)
    for i in range(n_rows):
        row = [None] * (first_col - 1)
        for j in range(n_cols):
            row.append(data.GetValue(r0 + i, c0 + j))
        rows.append(row)
    return rows


def read_sheets(path):
    """[(sheet name, rows of cell values)] of every worksheet."""
    from System import Activator, GC, Type
    excel_type = Type.GetTypeFromProgID("Excel.Application")
    if excel_type is None:
        raise ExcelMissing("Microsoft Excel is not installed on this computer")
    excel = Activator.CreateInstance(excel_type)
    books = book = sheets = None
    found = []
    try:
        _set(excel, "Visible", False)
        _set(excel, "DisplayAlerts", False)
        books = _get(excel, "Workbooks")
        # Open(Filename, UpdateLinks=0, ReadOnly=True)
        book = _call(books, "Open", path, 0, True)
        try:
            sheets = _get(book, "Worksheets")
            for i in range(1, int(_get(sheets, "Count")) + 1):
                sheet = _invoke_item(sheets, i)
                try:
                    found.append((u"%s" % _get(sheet, "Name"), _values(sheet)))
                finally:
                    _release(sheet)
        finally:
            _call(book, "Close", False)
    finally:
        try:
            _call(excel, "Quit")
        except Exception:
            pass
        _release(sheets, book, books, excel)
        GC.Collect()
        GC.WaitForPendingFinalizers()
    return found


def _invoke_item(collection, index):
    from System import Array, Object
    from System.Reflection import BindingFlags
    return collection.GetType().InvokeMember("Item", BindingFlags.GetProperty, None, collection,
                                             Array[Object]([index]))
