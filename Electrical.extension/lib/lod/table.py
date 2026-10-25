# -*- coding: utf-8 -*-
"""Reading the drawings of a List of Deliverables from the cell values of
its Excel sheet, and matching LOD titles with Revit sheet names.

Plain Python (no Revit), so it is tested outside Revit.

The table is found by its header row: the columns are recognised by their
headings ('S. No', 'Area/Building References', 'Document Reference Number',
'Rev.', 'Description / Title', and the stage columns after the title such as
'Concept Design'), wherever they are on the sheet. Every row below the header
with a document number is a drawing; blank rows and section labels
('ELECTRICAL') are skipped.
"""
import re

REV_DIGITS = 3        # 2 -> '002'

_SPACES = re.compile(r"\s+")
_DASHES = re.compile(r"\s*-\s*")
# a document number has digits and dashes: 2202-108-VE-7100-01400
_NUMBER = re.compile(r"^[A-Za-z0-9]+(-[A-Za-z0-9]+)+$")


class Drawing(object):
    """One drawing of the LOD."""

    def __init__(self, number, title, rev="", area="", row=None, stages=None):
        self.number = number
        self.title = title
        self.rev = rev                  # '002', or '' when the LOD has none
        self.area = area                # 'Main Building'...
        self.row = row                  # 1-based row in the sheet
        self.stages = stages or []      # [(stage heading, ticked)]

    def __repr__(self):
        return "Drawing(%r, %r, rev=%r)" % (self.number, self.title, self.rev)


class Table(object):
    def __init__(self, sheet_name, drawings, stage_names, header_row):
        self.sheet_name = sheet_name
        self.drawings = drawings
        self.stage_names = stage_names
        self.header_row = header_row

    def duplicates(self):
        """{number: [drawings]} for numbers used more than once."""
        seen = {}
        for d in self.drawings:
            seen.setdefault(d.number, []).append(d)
        return dict((n, ds) for n, ds in seen.items() if len(ds) > 1)

    def by_number(self):
        """{number: drawing}, the first one when a number is repeated."""
        found = {}
        for d in self.drawings:
            found.setdefault(d.number, d)
        return found


class NoTable(Exception):
    pass


# ------------------------------------------------------------------ text

def text(value):
    """Cell value as clean text: floats that are whole numbers lose '.0'."""
    if value is None:
        return u""
    if isinstance(value, float) and value == int(value):
        value = int(value)
    return _SPACES.sub(u" ", u"%s" % value).strip()


def rev_text(value, digits=REV_DIGITS):
    """'002' from 2, 2.0, '2', '02', 'Rev 002'; '' when there is no number;
    other text (e.g. 'A') unchanged."""
    value = text(value)
    match = re.search(r"\d+", value)
    if not match:
        return value
    return (match.group(0).lstrip("0") or "0").zfill(digits)


def rev_number(value):
    """2 from '002'; None when there is no number."""
    match = re.search(r"\d+", text(value))
    return int(match.group(0)) if match else None


def same_title(a, b):
    """Titles equal apart from case, spaces and spacing around dashes."""
    def norm(value):
        return _DASHES.sub(u" - ", text(value)).lower()
    return norm(a) == norm(b)


def tidy(title):
    """Title with single spaces and ' - ' between its parts."""
    return _DASHES.sub(u" - ", text(title))


def sheet_name(title, prefix=u""):
    """Revit sheet name for an LOD title: the title without the common
    prefix (e.g. 'KEZAD Two Building - ') when one is set."""
    title = text(title)
    prefix = text(prefix)
    if prefix:
        core = prefix.rstrip(u" -").lower()
        low = title.lower()
        if low.startswith(core):
            rest = title[len(core):]
            stripped = rest.lstrip(u" -")
            if stripped != rest or not rest:
                return stripped
    return title


def full_title(name, prefix=u""):
    """LOD title for a Revit sheet name: the prefix put back."""
    name = text(name)
    prefix = text(prefix)
    if not prefix:
        return name
    core = prefix.rstrip(u" -")
    if name.lower().startswith(core.lower()):
        return name
    return u"%s - %s" % (core, name)


# ------------------------------------------------------------------ header

_HEADINGS = (
    ("number", ("document reference", "document no", "drawing no", "drawing number",
                "dwg no", "sheet number", "sheet no")),
    ("title", ("description", "title", "drawing title", "sheet name")),
    ("rev", ("rev",)),
    ("area", ("area", "building")),
    ("serial", ("s. no", "s.no", "sr. no", "sr no", "serial", "no.")),
)


def _kind(heading):
    low = text(heading).lower()
    if not low:
        return None
    for kind, words in _HEADINGS:
        for word in words:
            if kind == "rev":
                if re.match(r"^rev(\.|ision)?\b", low):
                    return kind
            elif low.startswith(word) or (kind != "serial" and word in low):
                return kind
    return None


def find_header(rows):
    """(row index, {kind: column index}) of the header row: the first row
    with a document number and a title heading."""
    for r, row in enumerate(rows):
        columns = {}
        for c, value in enumerate(row):
            kind = _kind(value)
            if kind and kind not in columns:
                columns[kind] = c
        if "number" in columns and "title" in columns:
            return r, columns
    return None, None


def _is_number(value):
    value = text(value)
    return bool(value) and bool(_NUMBER.match(value)) and any(ch.isdigit() for ch in value)


def _ticked(value):
    value = text(value)
    # the LOD ticks stages with a Wingdings check mark ('ü'); anything typed counts
    return bool(value) and value not in (u"-", u"0", u"x", u"X", u"no", u"No", u"NO")


def read_rows(rows, sheet_name=u""):
    """Table of drawings from a sheet's cell values (list of rows, each a
    list of values, top-left cell first)."""
    header, columns = find_header(rows)
    if header is None:
        raise NoTable(u"No header with 'Document Reference Number' and "
                      u"'Description / Title' on sheet '%s'." % sheet_name)
    title_col = columns["title"]
    width = max(len(r) for r in rows) if rows else 0
    used = set(columns.values())
    stage_cols = []
    for c in range(title_col + 1, width):
        heading = text(rows[header][c]) if c < len(rows[header]) else u""
        if heading and c not in used:
            stage_cols.append((c, heading))
        elif not heading and stage_cols:
            break

    def cell(row, col):
        return row[col] if col is not None and col < len(row) else None

    drawings = []
    for r in range(header + 1, len(rows)):
        row = rows[r]
        number = text(cell(row, columns["number"]))
        if not _is_number(number):
            continue
        drawings.append(Drawing(
            number=number,
            title=text(cell(row, title_col)),
            rev=rev_text(cell(row, columns.get("rev"))),
            area=text(cell(row, columns.get("area"))),
            row=r + 1,
            stages=[(h, _ticked(cell(row, c))) for c, h in stage_cols]))
    return Table(sheet_name, drawings, [h for _, h in stage_cols], header + 1)


def pick_sheet(sheets):
    """The (name, rows) of the drawings table among (name, rows) pairs:
    a sheet named 'Drawings' first, otherwise the one with the most drawings."""
    best = None
    for name, rows in sheets:
        try:
            table = read_rows(rows, name)
        except NoTable:
            continue
        if not table.drawings:
            continue
        if u"drawing" in name.lower():
            return table
        if best is None or len(table.drawings) > len(best.drawings):
            best = table
    if best is None:
        raise NoTable(u"No sheet of the workbook has a table of drawings with "
                      u"'Document Reference Number' and 'Description / Title' columns.")
    return best
