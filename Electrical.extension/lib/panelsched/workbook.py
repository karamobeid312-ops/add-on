# -*- coding: utf-8 -*-
"""Panel schedules as an Excel workbook: an Index sheet, then one sheet per
panel laid out as the Revit schedule (header, circuits, summary, footer,
merged cells kept).

No Revit here, so it is tested outside Revit.
"""
from __future__ import division

import re

from vdrop.xlsx import Formula, Style, Workbook, text_points, width_units

HEADER, BODY, SUMMARY, FOOTER = "Header", "Body", "Summary", "Footer"
SECTION_ORDER = (HEADER, BODY, SUMMARY, FOOTER)

INDEX = "Index"
INDEX_COLUMNS = ("#", "Panel", "Level", "Schedule view", "Circuits", "Sheet")

MIN_WIDTH, MAX_WIDTH = 4.0, 45.0

_TITLE = Style(bold=True, size=14, border=False)
_NOTE = Style(italic=True, border=False, color="595959")
_HEAD = Style(bold=True, fill="D9E1F2", halign="center", wrap=True)
_CELL = Style(halign="center", wrap=True)
_TEXT = Style(halign="left", wrap=True)
_SUM = Style(bold=True, fill="F2F2F2", halign="center", wrap=True)
_LINK = Style(color="0563C1", border=True, halign="left")

STYLES = {HEADER: _HEAD, BODY: _CELL, SUMMARY: _SUM, FOOTER: _TEXT}

_NUMBER = re.compile(r"^-?(0|[1-9]\d*)(\.\d+)?$")
_BAD_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")


class Section(object):
    """One section of a schedule: rows of cell text (row 0 first) and its
    merged ranges as (row1, col1, row2, col2), 0-based within the section."""

    def __init__(self, kind, rows, merges=None):
        self.kind = kind
        self.rows = rows
        self.merges = merges or []

    @property
    def columns(self):
        return max([len(r) for r in self.rows] or [0])


class Schedule(object):
    def __init__(self, panel, view, sections, level="", circuits=0):
        self.panel = panel
        self.view = view
        self.sections = sections
        self.level = level
        self.circuits = circuits


def cell_value(text):
    """Plain numbers become numbers so Excel can add them up; everything
    else ("20 A", "01", "3P") stays text."""
    text = (text or u"").strip()
    if _NUMBER.match(text):
        return float(text) if "." in text else int(text)
    return text


def sheet_name(name, used):
    """A valid, unique Excel sheet name: at most 31 characters, none of
    []:*?/\\, not starting or ending with an apostrophe. `used` holds the
    lower-case names already taken and is updated."""
    base = _BAD_SHEET_CHARS.sub(u"_", (name or u"").strip()).strip(u"'").strip()
    base = (base or u"Panel")[:31]
    candidate, n = base, 2
    while candidate.lower() in used:
        suffix = u" (%d)" % n
        candidate = base[:31 - len(suffix)] + suffix
        n += 1
    used.add(candidate.lower())
    return candidate


def _quoted(name):
    return u"'%s'" % name.replace(u"'", u"''")


def _width_for(text, bold):
    longest = max([text_points(line, 9, bold) for line in (u"%s" % text).split(u"\n")] or [0])
    return width_units(longest) + 1.5


def write_schedule(sheet, schedule):
    """Lay the schedule out on `sheet`, sections one under the other with a
    blank row between them. Returns the last row used."""
    row = 1
    widths = {}
    for section in schedule.sections:
        if not section.rows:
            continue
        style = STYLES.get(section.kind, _CELL)
        covered = set()
        for r1, c1, r2, c2 in section.merges:
            text = section.rows[r1][c1] if c1 < len(section.rows[r1]) else u""
            sheet.merge(row + r1, c1 + 1, row + r2, c2 + 1, cell_value(text), style)
            for r in range(r1, r2 + 1):
                for c in range(c1, c2 + 1):
                    covered.add((r, c))
        for r, cells in enumerate(section.rows):
            for c in range(section.columns):
                if (r, c) in covered:
                    continue
                text = cells[c] if c < len(cells) else u""
                sheet.write(row + r, c + 1, cell_value(text), style)
                if text:
                    widths[c + 1] = max(widths.get(c + 1, 0), _width_for(text, style.bold))
        row += len(section.rows) + 1
    for col, width in widths.items():
        sheet.widths[col] = min(max(width, MIN_WIDTH), MAX_WIDTH)
    sheet.footer = u"&L%s&RPage &P of &N" % schedule.panel.replace(u"&", u"&&")
    return row - 2


def build(schedules, project=u""):
    """Workbook with the Index sheet and one sheet per schedule."""
    book = Workbook()
    index = book.add_sheet(INDEX)
    index.landscape = False
    index.paper = 9   # A4
    index.write(1, 1, u"Panel Schedules%s" % (u" - " + project if project else u""), _TITLE)
    index.write(2, 1, u"%d panel schedule%s. Click a sheet name to open it." % (
        len(schedules), u"" if len(schedules) == 1 else u"s"), _NOTE)
    for c, title in enumerate(INDEX_COLUMNS, 1):
        index.write(4, c, title, _HEAD)
    index.freeze = (5, 1)
    used = set([INDEX.lower()])
    for n, schedule in enumerate(schedules, 1):
        name = sheet_name(schedule.panel, used)
        write_schedule(book.add_sheet(name), schedule)
        r = 4 + n
        index.write(r, 1, n, _CELL)
        index.write(r, 2, schedule.panel, _TEXT)
        index.write(r, 3, schedule.level, _TEXT)
        index.write(r, 4, schedule.view, _TEXT)
        index.write(r, 5, schedule.circuits, _CELL)
        target = (u"#%s!A1" % _quoted(name)).replace(u'"', u'""')
        index.write(r, 6, Formula(u'HYPERLINK("%s","%s")' % (target, name.replace(u'"', u'""')),
                                  name), _LINK)
    for c, width in zip(range(1, 7), (5, 24, 16, 30, 9, 26)):
        index.widths[c] = width
    return book


def headline(schedules, path):
    return u"%d panel schedule%s exported to:\n%s" % (
        len(schedules), u"" if len(schedules) == 1 else u"s", path)
