# -*- coding: utf-8 -*-
"""Saving the report as PDF with Microsoft Excel (as File > Save As > PDF),
so the PDF is exactly the Excel report: same page setup, formulas worked
out by Excel.

Excel is driven through COM with .NET reflection, which works the same in
pyRevit's IronPython and CPython engines.
"""

XL_TYPE_PDF = 0


class ExcelMissing(Exception):
    pass


def _invoke(obj, name, flag, args):
    from System import Array, Object
    from System.Reflection import BindingFlags
    return obj.GetType().InvokeMember(name, getattr(BindingFlags, flag), None, obj,
                                      Array[Object](list(args)))


def _get(obj, name):
    return _invoke(obj, name, "GetProperty", [])


def _set(obj, name, value):
    _invoke(obj, name, "SetProperty", [value])


def _call(obj, name, *args):
    return _invoke(obj, name, "InvokeMethod", args)


def _release(*objects):
    from System.Runtime.InteropServices import Marshal
    for obj in objects:
        if obj is not None:
            try:
                Marshal.ReleaseComObject(obj)
            except Exception:
                pass


def save_pdf(xlsx_path, pdf_path):
    """Open the workbook in a hidden Excel and save it as PDF."""
    from System import Activator, GC, Type
    excel_type = Type.GetTypeFromProgID("Excel.Application")
    if excel_type is None:
        raise ExcelMissing("Microsoft Excel is not installed on this computer")
    excel = Activator.CreateInstance(excel_type)
    books = book = None
    try:
        _set(excel, "Visible", False)
        _set(excel, "DisplayAlerts", False)
        books = _get(excel, "Workbooks")
        book = _call(books, "Open", xlsx_path)
        try:
            _call(book, "ExportAsFixedFormat", XL_TYPE_PDF, pdf_path)
        finally:
            _call(book, "Close", False)
    finally:
        try:
            _call(excel, "Quit")
        except Exception:
            pass
        _release(book, books, excel)
        GC.Collect()
        GC.WaitForPendingFinalizers()
