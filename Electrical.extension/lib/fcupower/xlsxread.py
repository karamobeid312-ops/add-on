# -*- coding: utf-8 -*-
"""Small .xlsx reader: the cell values of every sheet.

Standard library only (zipfile and regular expressions, no XML parser), so
it runs in pyRevit's IronPython 2.7 and CPython 3 engines without Excel,
openpyxl or pyexpat. Formulas give their last calculated value, as Excel
saved it.
"""
import re
import zipfile

_SHEET = re.compile(r"<sheet\b([^>]*?)/?>", re.S)
_REL = re.compile(r"<Relationship\b([^>]*?)/?>", re.S)
_ATTR = re.compile(r'([\w:]+)\s*=\s*"([^"]*)"')
_SI = re.compile(r"<si\b[^>]*>(.*?)</si>|<si\b[^>]*/>", re.S)
_T = re.compile(r"<t\b[^>]*>(.*?)</t>|<t\b[^>]*/>", re.S)
_PHONETIC = re.compile(r"<rPh\b.*?</rPh>", re.S)
_ROW = re.compile(r"<row\b([^>]*?)(?:/>|>(.*?)</row>)", re.S)
_CELL = re.compile(r"<c\b([^>]*?)(?:/>|>(.*?)</c>)", re.S)
_V = re.compile(r"<v\b[^>]*>(.*?)</v>", re.S)
_IS = re.compile(r"<is\b[^>]*>(.*?)</is>", re.S)
_REF = re.compile(r"([A-Z]+)(\d+)")
_ENTITY = re.compile(r"&(#x[0-9a-fA-F]+|#\d+|amp|lt|gt|quot|apos);")
_NAMED = {"amp": u"&", "lt": u"<", "gt": u">", "quot": u'"', "apos": u"'"}


class NotXlsx(Exception):
    pass


def _unichr(code):
    try:
        return unichr(code)  # noqa: F821  IronPython 2.7
    except NameError:
        return chr(code)


def _entity(match):
    name = match.group(1)
    if name in _NAMED:
        return _NAMED[name]
    try:
        return _unichr(int(name[2:], 16) if name[1] == "x" else int(name[1:]))
    except ValueError:
        return match.group(0)


def unescape(text):
    return _ENTITY.sub(_entity, text or u"")


def _attrs(text):
    return dict(_ATTR.findall(text or ""))


def _text(zf, name):
    try:
        data = zf.read(name)
    except KeyError:
        return u""
    return data.decode("utf-8")


def column_index(letters):
    """'A' -> 0, 'AA' -> 26."""
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def _runs(xml):
    return u"".join(unescape(t or u"") for t in _T.findall(_PHONETIC.sub(u"", xml or u"")))


def _shared(zf):
    return [_runs(body) for body in _SI.findall(_text(zf, "xl/sharedStrings.xml"))]


def _number(text):
    try:
        value = float(text)
    except ValueError:
        return text
    return int(value) if value == int(value) and abs(value) < 1e15 else value


def _cell_value(attrs, body, shared):
    kind = attrs.get("t", "n")
    if kind == "inlineStr":
        found = _IS.search(body or u"")
        return _runs(found.group(1)) if found else u""
    found = _V.search(body or u"")
    if found is None:
        return None
    raw = unescape(found.group(1))
    if kind == "s":
        try:
            return shared[int(raw)]
        except (ValueError, IndexError):
            return u""
    if kind in ("str", "e"):
        return raw
    if kind == "b":
        return raw.strip() == "1"
    return _number(raw)


def parse_sheet(xml, shared):
    """[[values]] of a worksheet's XML: one list per row from row 1, cells
    in their columns (None where empty)."""
    rows = {}
    next_row = 1
    for row_attrs, row_body in _ROW.findall(xml):
        number = _attrs(row_attrs).get("r")
        number = int(number) if number and number.isdigit() else next_row
        next_row = number + 1
        cells = {}
        next_col = 0
        for cell_attrs, body in _CELL.findall(row_body or u""):
            attrs = _attrs(cell_attrs)
            ref = _REF.match(attrs.get("r", ""))
            col = column_index(ref.group(1)) if ref else next_col
            next_col = col + 1
            value = _cell_value(attrs, body, shared)
            if value is not None and value != u"":
                cells[col] = value
        if cells:
            rows[number] = cells
    if not rows:
        return []
    width = max(max(c) for c in rows.values()) + 1
    out = []
    for number in range(1, max(rows) + 1):
        cells = rows.get(number, {})
        out.append([cells.get(i) for i in range(width)])
    return out


def _sheet_paths(zf):
    """[(sheet name, path in the zip)] in the workbook's order."""
    rels = {}
    for attrs in _REL.findall(_text(zf, "xl/_rels/workbook.xml.rels")):
        a = _attrs(attrs)
        target = a.get("Target", "")
        if target.startswith("/"):
            target = target[1:]
        elif not target.startswith("xl/"):
            target = "xl/" + target
        rels[a.get("Id")] = target
    out = []
    for i, attrs in enumerate(_SHEET.findall(_text(zf, "xl/workbook.xml"))):
        a = _attrs(attrs)
        rid = a.get("r:id") or next((v for k, v in a.items() if k.endswith(":id")), None)
        path = rels.get(rid) or "xl/worksheets/sheet%d.xml" % (i + 1)
        out.append((unescape(a.get("name", "Sheet%d" % (i + 1))), path))
    return out


def read(path):
    """[(sheet name, rows)] of an .xlsx / .xlsm file."""
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipfile, IOError, OSError):
        raise NotXlsx(path)
    try:
        shared = _shared(zf)
        return [(name, parse_sheet(_text(zf, p), shared)) for name, p in _sheet_paths(zf)]
    finally:
        zf.close()
