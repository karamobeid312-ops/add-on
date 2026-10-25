# -*- coding: utf-8 -*-
"""The LOD written from the Revit sheets, as an .xlsx in the LOD layout.

With the old LOD given, its order, areas and stage ticks are kept, every
drawing takes its sheet name and revision from Revit, and the Status column
says what changed: 'Revised', 'Renamed', 'Not in Revit' (kept as it was),
and the sheets the LOD does not have are added at the end, 'New in Revit'.
Without an LOD, the sheets are listed by area and number.

Plain Python (no Revit), so it is tested outside Revit.
"""
from lod import keyplan
from lod.compare import Change, compare, rev_of, title_of
from lod.table import rev_number, text
from vdrop import xlsx

TITLE = u"Electrical Deliverable List for Drawings"
COLUMNS = (u"S. No", u"Area/Building References", u"Document Reference Number", u"Rev.",
           u"Description / Title")
WIDTHS = (7, 22, 27, 7, 90)
TICK = u"✓"            # ✓

REVISED, RENAMED, NOT_IN_REVIT, NEW = u"Revised", u"Renamed", u"Not in Revit", u"New in Revit"
STATUS_FILL = {REVISED: "FFF2CC", RENAMED: "DDEBF7", NOT_IN_REVIT: "FFC7CE", NEW: "E2EFDA"}

AREA_ORDER = (u"General",) + keyplan.BUILDINGS


class Line(object):
    def __init__(self, number, title, rev, area, status=u"", stages=None):
        self.number = number
        self.title = title
        self.rev = rev
        self.area = area
        self.status = status
        self.stages = stages or []


def area_of(sheet):
    if sheet.area:
        return text(sheet.area)
    return keyplan.describe(sheet.name)["building"] or u"General"


def lines(sheets, table=None, prefix=u""):
    """[Line] of the new LOD, groups split by None."""
    out = []
    if table is None:
        def order(s):
            area = area_of(s)
            rank = AREA_ORDER.index(area) if area in AREA_ORDER else len(AREA_ORDER)
            return (rank, area, s.number)
        last = None
        for s in sorted((s for s in sheets if not s.placeholder), key=order):
            area = area_of(s)
            if last is not None and area != last:
                out.append(None)
            last = area
            out.append(Line(s.number, title_of(s, prefix), rev_of(s), area))
        return out

    result = compare(table, sheets, prefix, use_rev=True)
    found = dict((d.number, s) for d, s in result.matched)
    changed = {}
    for c in result.changes:
        changed.setdefault(c.sheet.number, set()).add(c.field)
    last_row = None
    seen = set()
    for d in table.drawings:
        if d.number in seen:
            continue                        # a repeated number is written once
        seen.add(d.number)
        if last_row is not None and d.row - last_row > 1:
            out.append(None)                # keep the LOD's blank lines between groups
        last_row = d.row
        sheet = found.get(d.number)
        if sheet is None:
            out.append(Line(d.number, d.title, d.rev, d.area, NOT_IN_REVIT, d.stages))
            continue
        fields = changed.get(d.number, set())
        status = REVISED if Change.REV in fields else RENAMED if Change.NAME in fields else u""
        rev = rev_of(sheet) or d.rev
        out.append(Line(d.number, title_of(sheet, prefix), rev, d.area, status, d.stages))
    extra = [s for s in result.extra if not s.placeholder]
    if extra:
        out.append(None)
        for s in extra:
            out.append(Line(s.number, title_of(s, prefix), rev_of(s), area_of(s), NEW))
    return out


def workbook(sheets, table=None, prefix=u"", project=u""):
    """vdrop.xlsx Workbook of the LOD."""
    rows = lines(sheets, table, prefix)
    stages = list(table.stage_names) if table is not None else []
    status_col = len(COLUMNS) + len(stages) + 1 if table is not None else None
    last_col = status_col or len(COLUMNS)

    book = xlsx.Workbook()
    ws = book.add_sheet(u"Drawings")
    base = xlsx.Style(size=10)
    head = base.copy(bold=True, fill="D9D9D9", halign="center", wrap=True)
    title = base.copy(bold=True, size=14, fill="D8E4BC", halign="center")
    centre = base.copy(halign="center")
    left = base.copy(halign="left")
    rev_style = centre.copy(num_format="000")

    heading = TITLE if not project else u"%s - %s" % (project, TITLE)
    ws.merge(1, 1, 1, last_col, heading, title)
    ws.heights[1] = 24
    for c, name in enumerate(COLUMNS, 1):
        ws.write(2, c, name, head)
    for i, name in enumerate(stages):
        ws.write(2, len(COLUMNS) + 1 + i, name, head)
    if status_col:
        ws.write(2, status_col, u"Status", head)
    ws.heights[2] = 30
    for c, width in enumerate(WIDTHS, 1):
        ws.widths[c] = width
    for i in range(len(stages)):
        ws.widths[len(COLUMNS) + 1 + i] = 12
    if status_col:
        ws.widths[status_col] = 14
    ws.freeze = (3, 1)
    ws.print_rows = (1, 2)

    row = 3
    serial = 0
    for line in rows:
        if line is None:
            row += 1
            continue
        serial += 1
        fill = STATUS_FILL.get(line.status)
        def style(s):
            return s.copy(fill=fill) if fill else s
        ws.write(row, 1, serial, style(centre))
        ws.write(row, 2, line.area, style(centre))
        ws.write(row, 3, line.number, style(centre))
        number = rev_number(line.rev)
        ws.write(row, 4, number if number is not None and line.rev.isdigit() else line.rev,
                 style(rev_style))
        ws.write(row, 5, line.title, style(left))
        ticks = dict(line.stages)
        for i, name in enumerate(stages):
            ws.write(row, len(COLUMNS) + 1 + i, TICK if ticks.get(name) else u"", style(centre))
        if status_col:
            ws.write(row, status_col, line.status, style(centre))
        row += 1
    return book


def summary(sheets, table=None, prefix=u""):
    """{status: count} of the new LOD."""
    counts = {}
    for line in lines(sheets, table, prefix):
        if line is not None:
            counts[line.status] = counts.get(line.status, 0) + 1
    return counts
