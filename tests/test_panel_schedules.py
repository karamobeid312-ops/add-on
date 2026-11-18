# -*- coding: utf-8 -*-
"""The panel schedule workbook is checked by reading the saved .xlsx back."""
import os
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from panelsched.workbook import (BODY, HEADER, INDEX, SUMMARY, Schedule, Section, build,
                                 cell_value, sheet_name)

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _schedule(panel="DB-GF-01"):
    header = Section(HEADER, [
        [u"Panel: %s" % panel, u"", u"", u""],
        [u"CKT", u"Circuit Description", u"Trip", u"Poles"],
    ], merges=[(0, 0, 0, 3)])
    body = Section(BODY, [
        [u"1", u"LIGHTING GF", u"10 A", u"1"],
        [u"3", u"AHU-01", u"32 A", u"3"],
        [u"", u"", u"", u""],
    ], merges=[(1, 1, 2, 1)])
    summary = Section(SUMMARY, [[u"Total Load", u"", u"12.5", u"kVA"]], merges=[(0, 0, 0, 1)])
    return Schedule(panel, u"%s schedule" % panel, [header, body, summary],
                    level=u"GROUND FLOOR", circuits=2)


def _saved(book):
    handle, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(handle)
    try:
        book.save(path)
        archive = zipfile.ZipFile(path)
        parts = dict((n, archive.read(n)) for n in archive.namelist())
        archive.close()
    finally:
        os.remove(path)
    return parts


def _cells(xml):
    cells = {}
    for c in ET.fromstring(xml).iter(NS + "c"):
        if c.get("t") == "inlineStr":
            cells[c.get("r")] = "".join(t.text or "" for t in c.iter(NS + "t"))
        elif c.find(NS + "f") is not None:
            cells[c.get("r")] = ("=" + c.find(NS + "f").text,
                                 c.find(NS + "v").text if c.find(NS + "v") is not None else None)
        elif c.find(NS + "v") is not None:
            cells[c.get("r")] = float(c.find(NS + "v").text)
    return cells


def _merges(xml):
    return [m.get("ref") for m in ET.fromstring(xml).iter(NS + "mergeCell")]


def _sheet_names(parts):
    return [s.get("name") for s in ET.fromstring(parts["xl/workbook.xml"]).iter(NS + "sheet")]


def test_cell_value():
    assert cell_value(u"12") == 12
    assert cell_value(u" 12.5 ") == 12.5
    assert cell_value(u"01") == u"01"          # keeps leading zeros
    assert cell_value(u"20 A") == u"20 A"
    assert cell_value(u"") == u""
    assert cell_value(None) == u""


def test_sheet_names_valid_and_unique():
    used = set([INDEX.lower()])
    assert sheet_name(u"DB/GF:01", used) == u"DB_GF_01"
    assert sheet_name(u"db_gf_01", used) == u"db_gf_01 (2)"
    assert sheet_name(u"index", used) == u"index (2)"
    long = sheet_name(u"X" * 40, used)
    assert len(long) == 31
    assert len(sheet_name(u"X" * 40, used)) == 31 and u"X" * 40 not in used
    assert sheet_name(u"", used) == u"Panel"
    assert sheet_name(u"'quoted'", used) == u"quoted"


def test_one_sheet_per_panel_after_index():
    parts = _saved(build([_schedule("MDB"), _schedule("DB-GF-01")], u"Al Barsha"))
    assert _sheet_names(parts) == [INDEX, u"MDB", u"DB-GF-01"]


def test_schedule_layout_and_merges():
    parts = _saved(build([_schedule()]))
    sheet = parts["xl/worksheets/sheet2.xml"]
    cells = _cells(sheet)
    assert cells["A1"] == u"Panel: DB-GF-01"
    assert cells["B2"] == u"Circuit Description"
    # body starts after the 2 header rows and a blank row
    assert cells["A4"] == 1 and cells["B4"] == u"LIGHTING GF" and cells["C4"] == u"10 A"
    assert cells["B5"] == u"AHU-01"
    # summary after the 3 body rows and a blank row
    assert cells["A8"] == u"Total Load" and cells["C8"] == 12.5
    assert _merges(sheet) == [u"A1:D1", u"B5:B6", u"A8:B8"]


def test_index_lists_and_links_panels():
    parts = _saved(build([_schedule("MDB")], u"Project"))
    cells = _cells(parts["xl/worksheets/sheet1.xml"])
    assert cells["A1"] == u"Panel Schedules - Project"
    assert cells["B5"] == u"MDB" and cells["C5"] == u"GROUND FLOOR" and cells["E5"] == 2
    formula, shown = cells["F5"]
    assert formula == u"=HYPERLINK(\"#'MDB'!A1\",\"MDB\")" and shown == u"MDB"


def test_apostrophe_in_panel_name_is_escaped_in_link():
    parts = _saved(build([_schedule(u"DB O'NEIL")]))
    formula, _ = _cells(parts["xl/worksheets/sheet1.xml"])["F5"]
    assert u"#'DB O''NEIL'!A1" in formula


def test_empty_sections_are_skipped():
    schedule = Schedule(u"P1", u"P1", [Section(HEADER, []), Section(BODY, [[u"1", u"X"]])])
    cells = _cells(_saved(build([schedule]))["xl/worksheets/sheet2.xml"])
    assert cells["A1"] == 1 and cells["B1"] == u"X"
