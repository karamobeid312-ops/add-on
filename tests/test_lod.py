# -*- coding: utf-8 -*-
import json
import os
import zipfile

import pytest

from lod import export, keyplan
from lod.compare import Change, Sheet, compare
from lod.table import (
    NoTable, full_title, pick_sheet, read_rows, rev_text, same_title, sheet_name,
)

TICK = u"ü"     # Wingdings check mark as it is stored in the LOD
KEZAD = u"KEZAD Two Building - "


def lod_rows():
    """Cell values laid out like the Electrical LOD 'Drawings' sheet."""
    blank = [None] * 9
    return [
        [u"Contract No. & Title: 2202-108", None, None, u"", None, None, None, None, None],
        [u"Electrical Deliverable List for Drawings"] + [None] * 8,
        [u"S. No", u"Area/Building References", u"Document Reference Number", u"Rev.",
         u"Description  / Title", u"Concept Design ", u"Detailed Design ",
         u"Permitting Drawings", None],
        [None, None, None, None, u"ELECTRICAL", None, None, None, u"GENERAL"],
        [1.0, u"General", u"2202-108-VE-0000-00001", 2.0, KEZAD + u"Cover Sheet",
         TICK, TICK, None, None],
        [2.0, u"General", u"2202-108-VT-7500-00001", 2.0,
         KEZAD + u"Telephone & Data Plan - Overall Setting Out Plan", TICK, TICK, None, None],
        blank,
        [3.0, u"Main Building", u"2202-108-VE-7100-01400", 2.0,
         KEZAD + u"Main Building - Power Plan - Overall Ground Floor", TICK, TICK, None, None],
        [4.0, u"Main Building", u"2202-108-VE-7100-01401", 2.0,
         KEZAD + u"Main Building - Power Plan - Ground Floor - Part 1", None, TICK, None, None],
        [5.0, u"Main Building", u"2202-108-VE-7100-01409", 1.0,
         KEZAD + u"Main Building Tower 2 - Power Plan - 2nd Floor", None, TICK, None, None],
        [6.0, u"Main Building", u"2202-108-VE-7100-01409", 1.0,
         KEZAD + u"Main Building Tower 2 - Power Plan - 7th Floor Plan", None, TICK, None, None],
        blank,
        [7.0, u"Parking Building", u"2202-108-VE-7100-02400", 1.0,
         KEZAD + u"Parking Building - Power Plan - Overall First Floor", None, TICK, None, None],
    ]


# ------------------------------------------------------------ reading

def test_reads_the_drawings_under_the_header():
    table = read_rows(lod_rows(), u"Drawings")
    assert table.header_row == 3
    assert [d.number for d in table.drawings] == [
        u"2202-108-VE-0000-00001", u"2202-108-VT-7500-00001", u"2202-108-VE-7100-01400",
        u"2202-108-VE-7100-01401", u"2202-108-VE-7100-01409", u"2202-108-VE-7100-01409",
        u"2202-108-VE-7100-02400"]
    first = table.drawings[0]
    assert first.rev == u"002" and first.area == u"General" and first.row == 5
    assert first.title == KEZAD + u"Cover Sheet"


def test_stage_columns_and_ticks():
    table = read_rows(lod_rows())
    assert table.stage_names == [u"Concept Design", u"Detailed Design", u"Permitting Drawings"]
    d = table.drawings[3]
    assert d.stages == [(u"Concept Design", False), (u"Detailed Design", True),
                        (u"Permitting Drawings", False)]


def test_repeated_numbers():
    table = read_rows(lod_rows())
    assert list(table.duplicates()) == [u"2202-108-VE-7100-01409"]
    assert table.by_number()[u"2202-108-VE-7100-01409"].title.endswith(u"2nd Floor")


def test_no_header():
    with pytest.raises(NoTable):
        read_rows([[u"a", u"b"], [1, 2]])


def test_pick_sheet_prefers_drawings():
    rows = lod_rows()
    table = pick_sheet([(u"INDEX", [[u"S. No", u"Index"], [1, u"GENERAL"]]),
                        (u"General", rows[:6]), (u"Drawings", rows)])
    assert table.sheet_name == u"Drawings" and len(table.drawings) == 7


def test_rev_text():
    assert rev_text(2.0) == u"002"
    assert rev_text(u"2") == u"002"
    assert rev_text(u"Rev 002") == u"002"
    assert rev_text(None) == u""
    assert rev_text(u"A") == u"A"


def test_sheet_names_and_prefix():
    title = KEZAD + u"Main Building - Power Plan - Overall Ground Floor"
    assert sheet_name(title, KEZAD) == u"Main Building - Power Plan - Overall Ground Floor"
    assert sheet_name(title, u"KEZAD Two Building") == u"Main Building - Power Plan - Overall Ground Floor"
    assert sheet_name(title, u"") == title
    assert sheet_name(u"Other - X", KEZAD) == u"Other - X"
    assert full_title(u"Cover Sheet", KEZAD) == KEZAD + u"Cover Sheet"
    assert full_title(KEZAD + u"Cover Sheet", KEZAD) == KEZAD + u"Cover Sheet"
    assert same_title(u"A -B  - C", u"a - b - c")


# ------------------------------------------------------------ key plans

def test_describe():
    info = keyplan.describe(u"Main Building Tower 1 - Power Plan - Typical Floor 01 (3rd & 5th)")
    assert info["building"] == u"Main Building"
    assert info["tower"] == u"Tower 1"
    assert info["floor"] == u"Typical Floor (3rd & 5th)"
    assert info["part"] == u""
    assert keyplan.describe(u"Main Building - Power Plan - Overall 1st Floor")["floor"] == u"1st Floor"
    assert keyplan.describe(u"Main Building Tower 2 - CCTV Plan - 7th Floor Plan")["floor"] == u"7th Floor"
    assert keyplan.describe(u"Parking Building - Lighting Plan - First Floor - Part 2")["part"] == u"Part 2"
    assert keyplan.describe(u"Guard Room Building - Power Plan - Ground and First Floors")["floor"] \
        == u"Ground & First Floor"
    assert keyplan.describe(u"Main Building Tower 1 - Power Plan - Roof Floor")["floor"] == u"Roof"


def on(name, rules=None):
    rules = rules or keyplan.DEFAULT_RULES
    return sorted(p for p, v in keyplan.values(name, rules) if v is True)


@pytest.mark.parametrize("name, expected", [
    (u"Main Building Tower 2 - Containment Plan - Typical Floor 02 (4th & 6th)", u"Building 2"),
    (u"Main Building Tower 1 - Power Plan - Roof Floor", u"Building 1"),
    (u"Main Building - Power Plan - Overall Ground Floor", u"Ground Overall"),
    (u"Main Building - Power Plan - Overall First Floor", u"First Overall"),
    (u"Main Building - Power Plan - Ground Floor - Part 1", u"GF & FF Part 01"),
    (u"Main Building - Lighting Plan - First Floor - Part 2", u"GF & FF Part 02"),
    (u"Parking Building - CCTV Plan - Overall First Floor", u"Parking Overall"),
    (u"Parking Building - Lighting Plan - First Floor - Part 2", u"Parking Part 02"),
    (u"Service Building - Power Plan - Ground Floor", u"Service Building"),
    (u"Substation Building - Power Plan - Ground Floor", u"Substation"),
    (u"Site - External Lighting Plan", u"Site Overall"),
    (u"Cover Sheet", None),
])
def test_default_rules_one_picture_on(name, expected):
    always = [u"No keyplan", u"North Sign"]
    assert on(name) == sorted(always + ([expected] if expected else []))


def test_otherwise_rule():
    rules = keyplan.parse_rules(u'[{"parameter": "A", "on_if_any": ["x"]},'
                                u' {"parameter": "None", "otherwise": true}]')
    assert dict(keyplan.values(u"x", rules)) == {u"A": True, u"None": False}
    assert dict(keyplan.values(u"y", rules)) == {u"A": False, u"None": True}
    with pytest.raises(keyplan.RuleError):
        keyplan.parse_rules(u'[{"parameter": "N", "otherwise": true, "on_if_any": ["x"]}]')


def test_always_rule():
    rules = keyplan.parse_rules(u'[{"parameter": "A", "on_if_any": ["x"]},'
                                u' {"parameter": "N", "always": true}]')
    assert dict(keyplan.values(u"y", rules)) == {u"A": False, u"N": True}


def test_saved_old_defaults_read_as_new_defaults():
    old = json.dumps([{"parameter": p, "on_if_any": ["x"]}
                      for p in keyplan._OLD_DEFAULT_PARAMETERS])
    assert keyplan.parse_rules(old) == keyplan.DEFAULT_RULES


def test_whole_words_only():
    rules = [{"parameter": "P1", "on_if_any": ["Part 1"]}]
    assert on(u"X - Part 12", rules) == []
    assert on(u"X - part 1", rules) == [u"P1"]


def test_rules_from_json():
    raw = u'[{"parameter": "Shade T1", "on_if_any": ["Tower 1"]},' \
          u' {"parameter": "Level", "text": "{floor} {part}"}]'
    rules = keyplan.parse_rules(raw)
    found = dict(keyplan.values(u"Main Building Tower 1 - Lighting Plan - 2nd Floor - Part 2", rules))
    assert found == {u"Shade T1": True, u"Level": u"2nd Floor Part 2"}
    assert keyplan.parse_rules(u"") == keyplan.DEFAULT_RULES


@pytest.mark.parametrize("raw", [
    u"{",                                               # not JSON
    u'{"parameter": "A"}',                              # not a list
    u'[{"on_if_any": ["x"]}]',                          # no parameter
    u'[{"parameter": "A"}]',                            # no condition
    u'[{"parameter": "A", "on_if": ["x"]}]',            # unknown key
    u'[{"parameter": "A", "on_if_any": "x"}]',          # words not a list
    u'[{"parameter": "A", "text": "x", "on_if_any": ["y"]}]',
])
def test_bad_rules(raw):
    with pytest.raises(keyplan.RuleError):
        keyplan.parse_rules(raw)


# ------------------------------------------------------------ compare

def model_sheets():
    return [
        Sheet(1, u"2202-108-VE-0000-00001", u"Cover Sheet", rev=u"002"),
        Sheet(2, u"2202-108-VE-7100-01400", u"Main Building - Power Plan - Overall Ground Floor",
              rev=u"001"),
        Sheet(3, u"2202-108-VE-7100-01401", u"Main Building - Power Plan- Ground Floor - Part 1",
              rev=u"2"),
        Sheet(4, u"2202-108-VE-7100-02400", u"Parking - Power", rev=u"001"),
        Sheet(5, u"2202-108-VE-7100-09999", u"Extra Sheet", rev=u""),
    ]


def test_compare():
    result = compare(read_rows(lod_rows()), model_sheets(), KEZAD)
    assert [d.number[-5:] for d in result.missing] == [u"00001", u"01409"]
    assert [s.number[-5:] for s in result.extra] == [u"09999"]
    renamed = result.by_field(Change.NAME)
    assert [(c.sheet.number[-5:], c.new) for c in renamed] == [
        (u"02400", u"Parking Building - Power Plan - Overall First Floor")]
    revised = result.by_field(Change.REV)
    assert [(c.sheet.number[-5:], c.old, c.new) for c in revised] == [(u"01400", u"001", u"002")]
    assert not result.in_step()


def test_compare_without_revision_parameter():
    sheets = [Sheet(1, u"2202-108-VE-0000-00001", u"Cover Sheet", rev=None)]
    result = compare(read_rows(lod_rows()), sheets, KEZAD)
    assert result.no_rev_param == sheets
    assert not result.by_field(Change.REV)


def test_compare_full_titles():
    sheets = [Sheet(1, u"2202-108-VE-0000-00001", KEZAD + u"Cover Sheet", rev=u"002")]
    result = compare(read_rows(lod_rows()), sheets, u"")
    assert not result.changes


# ------------------------------------------------------------ export

def test_export_lines_keep_the_lod_order():
    lines = export.lines(model_sheets(), read_rows(lod_rows()), KEZAD)
    shown = [(l.number[-5:], l.status) if l else None for l in lines]
    assert shown == [
        (u"00001", u""), (u"00001", export.NOT_IN_REVIT), None,
        (u"01400", export.REVISED), (u"01401", u""), (u"01409", export.NOT_IN_REVIT), None,
        (u"02400", export.RENAMED), None,
        (u"09999", export.NEW)]
    revised = lines[3]
    assert revised.rev == u"001"           # Revit's revision is written
    assert lines[-1].area == u"General"
    renamed = [l for l in lines if l and l.status == export.RENAMED][0]
    assert renamed.title == KEZAD + u"Parking - Power"


def test_export_from_the_model_only():
    lines = export.lines(model_sheets(), None, KEZAD)
    areas = [l.area if l else None for l in lines]
    assert areas == [u"General", u"General", u"General", None, u"Main Building", u"Main Building"]


def test_export_workbook(tmp_path):
    book = export.workbook(model_sheets(), read_rows(lod_rows()), KEZAD, u"KEZAD Two")
    path = os.path.join(str(tmp_path), u"lod.xlsx")
    book.save(path)
    with zipfile.ZipFile(path) as z:
        xml = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
    assert u"2202-108-VE-7100-01400" in xml
    assert u"Not in Revit" in xml and u"New in Revit" in xml
    assert export.summary(model_sheets(), read_rows(lod_rows()), KEZAD) == {
        u"": 2, export.NOT_IN_REVIT: 2, export.REVISED: 1, export.RENAMED: 1, export.NEW: 1}


# ------------------------------------------------------------ place views

from lod import placeviews  # noqa: E402

VIEW_PART1 = u"KEZAD Two Building Lighting System Setting Out Plan - Part 01"


def test_view_key_ignores_dashes_case_and_zeros():
    assert placeviews.key(VIEW_PART1) == placeviews.key(
        u"KEZAD Two Building - Lighting System Setting Out Plan - Part 1")
    assert placeviews.key(u"Part 10") != placeviews.key(u"Part 1")


def test_match_views_to_sheets():
    sheets = [(1, u"KEZAD Two Building - Lighting System Setting Out Plan - Part 1"),
              (2, u"Lighting System Setting Out Plan"),      # prefix left out of the name
              (3, u"Power System Setting Out Plan - Part 4"),
              (4, u"Cover Sheet")]
    views = [(10, VIEW_PART1, set()),
             (11, u"KEZAD Two Building Lighting System Setting Out Plan", set()),
             (12, u"KEZAD Two Building Power System Setting Out Plan - Part 04", set([9])),
             (13, u"KEZAD Two Building Power System Setting Out Plan - Part 04", set())]
    found = placeviews.match(sheets, views, KEZAD)
    assert found == {1: [10], 2: [11], 3: [13, 12]}


def test_match_view_already_on_this_sheet_before_other_sheets():
    views = [(10, u"Plan A", set([7])), (11, u"Plan A", set([1]))]
    assert placeviews.match([(1, u"Plan A")], views) == {1: [11, 10]}


# ------------------------------------------------------------ LOD Studio

import re as _re  # noqa: E402

from lod import studio  # noqa: E402

LIB = os.path.join(os.path.dirname(__file__), "..", "Electrical.extension", "lib")


def test_studio_create_rows_tick_new_drawings_only():
    table = read_rows(lod_rows())
    sheets = [Sheet(1, u"2202-108-VE-7100-01400", u"x")]
    rows = studio.create_rows(table, sheets, KEZAD)
    numbers = [r["number"] for r in rows if r["do"]]
    assert u"2202-108-VE-7100-01400" not in numbers
    assert len(numbers) == len(set(numbers))
    assert any(r["state"] == studio.WARN and not r["can"] for r in rows)   # repeated number


def test_studio_compare_rows_tick_changes_only():
    table = read_rows(lod_rows())
    sheets = [Sheet(1, u"2202-108-VE-7100-01400", u"Old name", rev=u"001"),
              Sheet(2, u"9999", u"Extra sheet", rev=u"")]
    result = compare(table, sheets, KEZAD)
    rows = studio.compare_rows(result)
    ticked = [r for r in rows if r["do"]]
    assert set(r["c1"] for r in ticked) == {Change.NAME, Change.REV}
    assert any(r["c1"] == u"Not in the LOD" and not r["can"] for r in rows)
    assert studio.tidy_changes(result, studio.picked(rows)) == result.changes


def test_studio_view_rows():
    sheets = [(1, u"A1", u"KEZAD Two Building - Lighting System Setting Out Plan - Part 1"),
              (2, u"A2", u"Power Plan"), (3, u"A3", u"Legend Sheet"), (4, u"A4", u"Cover")]
    views = [(10, VIEW_PART1, set(), False), (11, u"Power Plan", set([9]), False),
             (12, u"Legend Sheet", set([8]), True)]
    rows = studio.view_rows(sheets, views, {9: u"B9"})
    by = dict((r["number"], r) for r in rows)
    assert by[u"A1"]["do"] and by[u"A1"]["key"] == u"1:10"
    assert not by[u"A2"]["can"] and u"B9" in by[u"A2"]["status"]
    assert by[u"A3"]["do"]                      # a legend goes on many sheets
    assert by[u"A4"]["state"] == studio.BAD


def test_studio_keyplan_rows():
    sheets = [(1, u"S1", u"Main Building Tower 2 - Power Plan - 2nd Floor"),
              (2, u"S2", u"Main Building Tower 1 - Power Plan - 2nd Floor"),
              (3, u"S3", u"Cover")]
    names = [r["parameter"] for r in keyplan.DEFAULT_RULES]
    now = {1: dict((n, n in (u"Building 2", u"No keyplan", u"North Sign")) for n in names),
           2: dict((n, n == u"Site Overall") for n in names)}   # needs changing
    rows = dict((r["number"], r) for r in studio.keyplan_rows(sheets, keyplan.DEFAULT_RULES, now))
    assert rows[u"S1"]["state"] == studio.OK and not rows[u"S1"]["do"]
    assert rows[u"S2"]["do"] and rows[u"S2"]["c2"] == u"Building 1, No keyplan, North Sign"
    assert rows[u"S3"]["state"] == studio.BAD


def test_studio_window_names_are_in_the_xaml():
    with open(os.path.join(LIB, "lod", "window.xaml"), "rb") as f:
        xaml = f.read().decode("utf-8")
    import xml.dom.minidom
    xml.dom.minidom.parseString(xaml.replace(u"<!--THEME-->", u"").encode("utf-8"))
    names = set(_re.findall(r'x:Name="(\w+)"', xaml))
    source = open(os.path.join(LIB, "lod", "window_ui.py")).read()
    listed = _re.search(r"NAMES = \(([^)]*)\)", source, _re.S).group(1)
    for name in _re.findall(r'"(\w+)"', listed):
        assert name in names, name


def test_ordinals_and_close_views():
    assert placeviews.key(u"Overall First Floor") == placeviews.key(u"Overall 1st Floor")
    views = [(1, u"Main Building Tower 1 - Lighting Plan - Floor 2 - Part 2"),
             (2, u"KEZAD Two Building Main Building Tower 1 Lighting 2nd Floor Plan")]
    near = placeviews.closest(u"KEZAD Two Building - Main Building Tower 1 - Lighting Plan - 2nd Floor",
                              views)
    assert near[0] == 2
    assert placeviews.closest(u"Cover Sheet", views) is None


def test_studio_view_rows_offer_close_view_unticked():
    sheets = [(1, u"A1", u"Main Building Tower 1 - Lighting Plan - 2nd Floor")]
    views = [(10, u"Main Building Tower 1 - Lighting Plan Zone A - 2nd Floor", set(), False)]
    r = studio.view_rows(sheets, views, {})[0]
    assert r["can"] and not r["do"] and r["key"] == u"1:10" and r["status"].startswith(u"Close")


POWER_VIEWS = [
    (20, u"KEZAD Two Building Floor Plans Power System - Ground floor Plan-Overall", set(), False),
    (21, u"KEZAD Two Building Floor Plans Power System - Ground floor Plan - Part 1", set(), False),
    (22, u"KEZAD Two Building Floor Plans Power System - Tower 1 - 3rd-5th floor Plan", set(), False),
    (23, u"KEZAD Two Building Floor Plans Power For Mechanical System - Tower 1 - 3rd-5th floor Plan",
     set(), False),
    (24, u"KEZAD Two Building - Main Building Tower 1 - Emergency Lighting Plan - 2nd Floor",
     set(), False),
]


@pytest.mark.parametrize("sheet, view", [
    (u"KEZAD Two Building - Main Building - Power Plan - Overall Ground Floor", 20),
    (u"KEZAD Two Building - Main Building - Power Plan - Ground Floor - Part 1", 21),
    (u"KEZAD Two Building - Main Building Tower 1 - Power Plan - Typical Floor 01 (3rd & 5th)", 22),
    (u"KEZAD Two Building - Main Building Tower 1 - Power for Mechanical Plan - Typical Floor 01 "
     u"(3rd & 5th)", 23),
    (u"KEZAD Two Building - Main Building Tower 1 - Emergency Lighting Plan - Second Floor", 24),
])
def test_views_worded_differently_match_by_plan(sheet, view):
    r = studio.view_rows([(1, u"S", sheet)], POWER_VIEWS, {})[0]
    assert r["key"] == u"1:%d" % view and r["do"]


def test_by_plan_never_mixes_floors_or_systems():
    sheet = u"KEZAD Two Building - Main Building Tower 1 - Lighting Plan - Typical Floor 01 (3rd & 5th)"
    r = studio.view_rows([(1, u"S", sheet)], POWER_VIEWS, {})[0]
    assert not r["do"]
