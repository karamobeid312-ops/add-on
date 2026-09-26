# -*- coding: utf-8 -*-
"""The report is checked by evaluating every formula of the saved .xlsx
and comparing it with the value the tool calculated."""
import os
import re
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from sample_vd import feeders
from vdrop.calc import Settings, calculate
from vdrop.report import COL, COLUMNS, FIRST_ROW, HEADER_ROW, ReportInfo, build, headline
from vdrop.xlsx import col_letter

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _saved_report():
    settings = Settings()
    result = calculate(feeders(), settings)
    book = build(result, settings, ReportInfo(project="SAMPLE", issue="Tender"))
    handle, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(handle)
    try:
        book.save(path)
        archive = zipfile.ZipFile(path)
        parts = dict((n, archive.read(n)) for n in archive.namelist())
        archive.close()
    finally:
        os.remove(path)
    return result, parts


def _cells(sheet_xml):
    cells = {}
    for c in ET.fromstring(sheet_xml).iter(NS + "c"):
        formula, v, kind = c.find(NS + "f"), c.find(NS + "v"), c.get("t")
        if kind == "inlineStr":
            value = "".join(t.text or "" for t in c.iter(NS + "t"))
        elif v is None:
            value = None
        elif kind == "str":
            value = v.text or ""
        else:
            value = float(v.text)
        cells[c.get("r")] = (formula.text if formula is not None else None, value)
    return cells


# ------------------------------------------------ a small formula evaluator

_TOKEN = re.compile(r'\s*(?:(\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)|("(?:[^"]|"")*")|'
                    r'(\$?[A-Z]{1,3}\$?\d+)|([A-Z]+)\(|(<>|>=|<=|[-+*/^&=<>(),]))')


def _tokens(text):
    out, pos = [], 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        assert m and m.end() > pos, "cannot read %r" % text[pos:]
        number, string, cell, func, op = m.groups()
        if number:
            out.append(("num", float(number)))
        elif string:
            out.append(("str", string[1:-1].replace('""', '"')))
        elif cell:
            out.append(("ref", cell.replace("$", "")))
        elif func:
            out.append(("func", func))
        else:
            out.append(("op", op))
        pos = m.end()
    return out


class _Evaluator(object):
    def __init__(self, cells):
        self.cells = cells
        self.cache = {}

    def cell(self, name):
        if name not in self.cache:
            formula, value = self.cells.get(name, (None, None))
            self.cache[name] = self.formula(formula) if formula else ("" if value is None else value)
        return self.cache[name]

    def formula(self, text):
        self.toks, self.i = _tokens(text), 0
        node = self.compare()
        assert self.i == len(self.toks), text
        return node()

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def take(self, value=None):
        tok = self.toks[self.i]
        assert value is None or tok[1] == value, (tok, value)
        self.i += 1
        return tok

    def binary(self, sub, ops, apply):
        left = sub()
        while self.peek()[0] == "op" and self.peek()[1] in ops:
            op = self.take()[1]
            right = sub()
            left = (lambda l, r, o: lambda: apply(o, l(), r()))(left, right, op)
        return left

    def compare(self):
        def apply(op, a, b):
            if isinstance(a, str) or isinstance(b, str):
                a, b = str(a).upper(), str(b).upper()
                if op in ("=", "<>"):
                    return (a == b) == (op == "=")
            return {"=": a == b, "<>": a != b, "<": a < b, ">": a > b,
                    "<=": a <= b, ">=": a >= b}[op]
        return self.binary(self.concat, ("=", "<>", "<", ">", "<=", ">="), apply)

    def concat(self):
        return self.binary(self.add, ("&",), lambda op, a, b: "%s%s" % (a, b))

    def add(self):
        return self.binary(self.mul, ("+", "-"), lambda op, a, b: a + b if op == "+" else a - b)

    def mul(self):
        return self.binary(self.unary, ("*", "/"), lambda op, a, b: a * b if op == "*" else a / b)

    def unary(self):
        if self.peek() == ("op", "-"):
            self.take()
            inner = self.unary()
            return lambda: -inner()
        return self.power()

    def power(self):
        return self.binary(self.primary, ("^",), lambda op, a, b: a ** b)

    def primary(self):
        kind, value = self.take()
        if kind in ("num", "str"):
            return lambda: value
        if kind == "ref":
            return lambda: self.cell(value)
        if kind == "op" and value == "(":
            node = self.compare()
            self.take(")")
            return node
        assert kind == "func", (kind, value)
        args = []
        while self.peek() != ("op", ")"):
            args.append(self.compare())
            if self.peek() == ("op", ","):
                self.take()
        self.take(")")
        if value == "IF":
            return lambda: args[1]() if args[0]() else args[2]()
        functions = {
            "OR": lambda vals: any(vals), "AND": lambda vals: all(vals),
            "SQRT": lambda vals: vals[0] ** 0.5,
            "ISNUMBER": lambda vals: isinstance(vals[0], float),
        }
        return lambda: functions[value]([a() for a in args])


# ------------------------------------------------ tests

def test_formulas_give_the_calculated_values():
    result, parts = _saved_report()
    cells = _cells(parts["xl/worksheets/sheet1.xml"])
    evaluator = _Evaluator(cells)
    checked = 0
    for name, (formula, cached) in cells.items():
        if not formula:
            continue
        value = evaluator.cell(name)
        if isinstance(cached, float):
            assert isinstance(value, float) and abs(value - cached) <= 1e-9 * max(1, abs(cached)), \
                (name, formula, value, cached)
        else:
            assert value == cached, (name, formula, value, cached)
        checked += 1
    rows = len(list(result.rows()))
    assert checked >= rows * 10       # ten formulas per cable


def test_layout_matches_office_sheet():
    result, parts = _saved_report()
    cells = _cells(parts["xl/worksheets/sheet1.xml"])
    headings = [cells["%s%d" % (col_letter(i + 1), HEADER_ROW)][1] for i in range(len(COLUMNS))]
    assert headings[:6] == ["S.N", "FROM", "TO", "DISTANCE(M)", "PHASE", "VOLTAGE"]
    assert headings[-5:] == ["V.D(%)", "CUMULATIVE V.D(%)", "MAX V.D%", "Calc. By\nTCL/MDL",
                             "REMARKS"]
    assert cells["A%d" % FIRST_ROW][1] == "LVP-05"
    first = FIRST_ROW + 1
    assert [cells["%s%d" % (col_letter(COL[k]), first)][1] for k in ("sn", "from", "to")] == \
        ["1", "TR", "LVP-05"]
    # cumulative V.D of 1.1 adds the transformer cable's
    total = cells["%s%d" % (col_letter(COL["total"]), first + 1)][0]
    assert total == 'IF(OR(AF23="",AG22=""),"",AF23+AG22)'
    sheet = parts["xl/worksheets/sheet1.xml"].decode("utf-8")
    assert sheet.count("<conditionalFormatting") == 3
    assert 'state="frozen"' in sheet
    assert headline(result) in [v for _, v in cells.values()]
    workbook = parts["xl/workbook.xml"].decode("utf-8")
    assert "_xlnm.Print_Titles" in workbook and 'fullCalcOnLoad="1"' in workbook


def test_remarks_name_the_fix():
    result, parts = _saved_report()
    cells = _cells(parts["xl/worksheets/sheet1.xml"])
    last = FIRST_ROW + len(list(result.rows())) + len(result.sections)
    by_target = {}
    for r in range(FIRST_ROW, last):
        target = cells.get("%s%d" % (col_letter(COL["to"]), r), (None, None))[1]
        by_target[target] = cells.get("%s%d" % (col_letter(COL["remarks"]), r), (None, None))[1]
    assert by_target["AHU-01"] == u"V.D 5.52% > 4%; use 4Cx25mm²"
    assert by_target["ESMDB-WH"] in ("", None)


def test_every_part_is_well_formed():
    _, parts = _saved_report()
    assert set(parts) == {"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml",
                          "xl/_rels/workbook.xml.rels", "xl/styles.xml",
                          "xl/worksheets/sheet1.xml"}
    for xml in parts.values():
        ET.fromstring(xml)
