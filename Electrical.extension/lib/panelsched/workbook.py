# -*- coding: utf-8 -*-
"""Panel schedules as an Excel workbook: an Index sheet, then one sheet per
panel laid out as the Revit schedule (header, circuits, summary, footer,
merged cells kept).

No Revit here, so it is tested outside Revit.
"""
from __future__ import division

import re

from vdrop.xlsx import Formula, Style, Workbook, ref, text_points, width_units

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


class CellStyle(object):
    """How Revit draws one cell. `borders` is (left, right, top, bottom);
    `size` is the text size in points; `fill` is 'RRGGBB' or None."""

    def __init__(self, bold=False, italic=False, size=None, halign=None, fill=None,
                 color=None, borders=None):
        self.bold = bold
        self.italic = italic
        self.size = size
        self.halign = halign
        self.fill = fill
        self.color = color
        self.borders = borders


class Section(object):
    """One section of a schedule: rows of cell text (row 0 first) and its
    merged ranges as (row1, col1, row2, col2), 0-based within the section.

    When read from Revit it also carries the column widths and row heights
    (feet) and the style of each cell, so the sheet can look like the
    schedule. Without them the old plain layout is used."""

    def __init__(self, kind, rows, merges=None, widths=None, heights=None, styles=None):
        self.kind = kind
        self.rows = rows
        self.merges = merges or []
        self.widths = widths
        self.heights = heights
        self.styles = styles or {}

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
    blank row between them. Returns the last row used. Schedules read with
    their column widths are laid out as Revit draws them instead."""
    sections = [s for s in schedule.sections if s.rows]
    if sections and all(_sized(s) for s in sections):
        return write_schedule_like_revit(sheet, schedule)
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


# ---------------------------------------------------------------- Revit look
#
# Revit's sections each have their own columns (the header's columns do not
# line up with the circuit table's). Excel has one set of columns, so the
# edges of every section's columns are put on one ruler and each Revit cell
# becomes a merged range between its two edges.

FEET_TO_CHARS = 12 * 96 / 7.0      # inches * 96 px / ~7 px per Excel character
FEET_TO_POINTS = 12 * 72
_EDGE_ROUND = 3                    # edges closer than ~1 mm are the same edge
MIN_ROW_POINTS = 11.0
DEFAULT_SIZE = 8


def _sized(section):
    return bool(section.widths) and len(section.widths) >= section.columns


def _edges(sections):
    """Column edges (feet, from the left of the schedule) of every section,
    merged onto one sorted ruler."""
    edges = set([0.0])
    for section in sections:
        x = 0.0
        for w in section.widths[:section.columns]:
            x += max(w, 0.0)
            edges.add(round(x, _EDGE_ROUND))
    return sorted(edges)


def _sides(section, r, c):
    style = section.styles.get((r, c))
    return style.borders if style is not None and style.borders else (False,) * 4


def _font_size(size):
    if not size:
        return DEFAULT_SIZE
    if size < 1:                    # given in feet
        size = size * FEET_TO_POINTS
    return min(max(round(size * 2) / 2.0, 6), 20)


def _xl_style(style, sides, wrap=True):
    style = style or CellStyle()
    return Style(bold=bool(style.bold), italic=bool(style.italic), size=_font_size(style.size),
                 color=style.color, fill=style.fill, border=sides,
                 halign=style.halign or "center", valign="center", wrap=wrap)


def _outline(sheet, row1, row2, col1, col2):
    """A box round a section, as Revit draws one round each part."""
    for r in range(row1, row2 + 1):
        for c in range(col1, col2 + 1):
            if r not in (row1, row2) and c not in (col1, col2):
                continue
            value, style = sheet.cells.get((r, c), (None, None))
            style = style or Style(border=False)
            sides = style.border
            if sides in (True, False, None):
                sides = (bool(sides),) * 4
            sides = (sides[0] or c == col1, sides[1] or c == col2,
                     sides[2] or r == row1, sides[3] or r == row2)
            sheet.cells[(r, c)] = (value, style.copy(border=sides))


BOX = (True, True, True, True)


def _box(section, r, c):
    style = section.styles.get((r, c))
    if style is None:
        style = section.styles[(r, c)] = CellStyle()
    style.borders = BOX


def _phase_letters(section):
    """Revit draws the R | Y | B under PHASE LOAD itself and the API gives
    no text for them: put the letters in."""
    if section.kind != BODY:
        return
    spans = dict(((m[0], m[1]), m) for m in section.merges)
    for r, cells in enumerate(section.rows):
        for c, text in enumerate(cells):
            if not _norm(text).startswith(u"PHASE LOAD"):
                continue
            m = spans.get((r, c))
            if m is None or m[3] - m[1] != 2 or m[2] + 1 >= len(section.rows):
                return
            below = m[2] + 1
            row = section.rows[below]
            if any(_norm(row[x]) in PHASES for x in range(c, c + 3) if x < len(row)):
                return
            if len(row) < c + 3:
                return
            section.merges = [mm for mm in section.merges
                              if not (mm[0] <= below <= mm[2] and mm[1] <= c + 2 and mm[3] >= c)]
            for x, letter in zip(range(c, c + 3), PHASES):
                row[x] = letter
            return


def _rule_lines(sections):
    """Revit rules the panel schedule with thin black lines that the API
    does not report cell by cell. Draw them as Revit shows them: every cell
    of the circuit table; in the header the LOAD boxes; in the footer every
    cell with text and the whole load type table."""
    for section in sections:
        rows = section.rows
        if section.kind == BODY:
            for r in range(len(rows)):
                for c in range(section.columns):
                    _box(section, r, c)
            continue
        table = None
        for r, cells in enumerate(rows):
            for c, text in enumerate(cells):
                n = _norm(text)
                if section.kind == HEADER:
                    if n == u"LOAD":
                        _box(section, r, c)
                    continue
                if n:
                    _box(section, r, c)
                if n == u"LOAD TYPE" and table is None:
                    table = (r, c)
        if table is None:
            continue
        r0, c0 = table
        last = max([c for c, t in enumerate(rows[r0]) if _norm(t)] or [c0])
        r = r0
        while r < len(rows) and any(_norm(t) for t in rows[r][c0:last + 1]):
            for c in range(c0, last + 1):
                _box(section, r, c)
            r += 1


def write_schedule_like_revit(sheet, schedule):
    """Lay the schedule out as Revit draws it: sections stacked with no gap,
    Revit's column widths and row heights, merged cells, bold, alignment,
    fills and cell borders. Returns the last row used."""
    sections = [s for s in schedule.sections if s.rows]
    for section in sections:
        _phase_letters(section)
    _rule_lines(sections)
    ruler = _edges(sections)
    index = dict((e, i) for i, e in enumerate(ruler))
    for i in range(1, len(ruler)):
        sheet.widths[i] = max(round((ruler[i] - ruler[i - 1]) * FEET_TO_CHARS, 2), 0.5)

    row = 1
    where = {}          # (section index, row, col) -> top-left Excel cell
    for si, section in enumerate(sections):
        starts, x = [], 0.0
        for w in section.widths[:section.columns]:
            starts.append(index[round(x, _EDGE_ROUND)])
            x += max(w, 0.0)
        starts.append(index[round(x, _EDGE_ROUND)])

        spans = {}
        for r1, c1, r2, c2 in section.merges:
            spans[(r1, c1)] = (r2, c2)
        covered = set()
        for (r1, c1), (r2, c2) in spans.items():
            for r in range(r1, r2 + 1):
                for c in range(c1, c2 + 1):
                    if (r, c) != (r1, c1):
                        covered.add((r, c))

        for r, cells in enumerate(section.rows):
            height = section.heights[r] if section.heights and r < len(section.heights) else None
            if height:
                sheet.heights[row + r] = max(round(height * FEET_TO_POINTS, 1), MIN_ROW_POINTS)
            for c in range(section.columns):
                if (r, c) in covered:
                    continue
                r2, c2 = spans.get((r, c), (r, c))
                g1, g2 = starts[c] + 1, starts[c2 + 1]       # 1-based Excel columns
                if g2 < g1:                                   # zero-width column
                    continue
                style = section.styles.get((r, c))
                left, _, top, _ = _sides(section, r, c)
                right = _sides(section, r, c2)[1]
                bottom = _sides(section, r2, c)[3]
                text = cells[c] if c < len(cells) else u""
                x1, x2 = row + r, row + r2
                tall = sum(section.heights[i] or 0 for i in range(r, r2 + 1)) \
                    if section.heights and r2 < len(section.heights) else 1
                # wrap only where Revit has room for two lines; else one line like Revit
                wrap = tall * FEET_TO_POINTS >= 2.2 * _font_size(style.size if style else None)
                for xr in range(x1, x2 + 1):
                    for xc in range(g1, g2 + 1):
                        sides = (left and xc == g1, right and xc == g2,
                                 top and xr == x1, bottom and xr == x2)
                        value = cell_value(text) if (xr, xc) == (x1, g1) else None
                        sheet.write(xr, xc, value, _xl_style(style, sides, wrap))
                where[(si, r, c)] = (x1, g1)
                if (x1, g1) != (x2, g2):
                    sheet.merges.append(u"%s:%s" % (ref(x1, g1), ref(x2, g2)))
        _outline(sheet, row, row + len(section.rows) - 1, 1, starts[-1])
        row += len(section.rows)
    add_formulas(sheet, sections, where)
    sheet.gridlines = False
    sheet.landscape = True
    sheet.paper = 9   # A4, fitted to one page wide
    sheet.footer = u"&L%s&RPage &P of &N" % schedule.panel.replace(u"&", u"&&")
    return row - 1



# ---------------------------------------------------------------- formulas
#
# Revit only gives the text it shows, so the totals of the office panel
# schedule are found by their labels and written back as Excel formulas
# over the circuit rows. A formula is only used when it gives the number
# Revit shows; otherwise the number is kept as it is.

PHASES = (u"R", u"Y", u"B")
_SKIP = set([u"", u"--", u"-"])


def _norm(text):
    return re.sub(r"\s+", u" ", (text or u"").strip()).upper()


def _num(text):
    value = cell_value(text)
    return value if isinstance(value, (int, float)) else None


def _decimals(text):
    text = (text or u"").strip()
    return len(text.split(u".")[1]) if u"." in text else 0


def _shows(value, text):
    """True when `value` shown with the decimals of `text` reads as `text`."""
    shown = _num(text)
    if shown is None:
        return False
    return abs(value - shown) <= 0.5 * 10 ** -_decimals(text) + 1e-9


def _number_format(text):
    d = _decimals(text)
    return u"0.%s" % (u"0" * d) if d else u"0"


class _Body(object):
    """Where the circuit table's phase and load type columns are."""

    def __init__(self, si, section, phase_cols, type_col, first_row):
        self.si = si
        self.section = section
        self.phase_cols = phase_cols          # {'R': col, 'Y': col, 'B': col}
        self.type_col = type_col              # LOAD TYPE column or None
        self.rows = range(first_row, len(section.rows))

    def number(self, r, c):
        cells = self.section.rows[r]
        return (_num(cells[c]) if c < len(cells) else None) or 0

    def load_type(self, r):
        cells = self.section.rows[r]
        return _norm(cells[self.type_col]) if self.type_col is not None and self.type_col < len(cells) else u""


def _find_body(sections):
    for si, section in enumerate(sections):
        if section.kind != BODY:
            continue
        for r, cells in enumerate(section.rows):
            texts = [_norm(t) for t in cells]
            for c in range(len(texts) - 2):
                if tuple(texts[c:c + 3]) == PHASES:
                    type_col = None
                    for rr in range(0, r + 1):
                        for cc, t in enumerate(section.rows[rr]):
                            if _norm(t) == u"LOAD TYPE":
                                type_col = cc
                    return _Body(si, section, dict(zip(PHASES, (c, c + 1, c + 2))), type_col, r + 1)
    return None


def _column_range(where, body, col):
    rows = [where.get((body.si, r, col)) for r in body.rows]
    rows = [p for p in rows if p]
    if not rows:
        return None
    return u"%s:%s" % (ref(rows[0][0], rows[0][1], True), ref(rows[-1][0], rows[-1][1], True))


def _numbers_right_of(cells, c0):
    return [(c, cells[c]) for c in range(c0 + 1, len(cells)) if _num(cells[c]) is not None]


def _scale(raw, text):
    """Revit shows W as kW in the footer: find the divisor that matches."""
    for factor in (1000, 1):
        if _shows(raw / factor, text):
            return factor
    return None


def _set_formula(sheet, at, text, value, shown):
    cur = sheet.cells.get(at, (None, None))[1] or Style()
    sheet.cells[at] = (Formula(text, value), cur.copy(num_format=_number_format(shown)))


def add_formulas(sheet, sections, where):
    """Turn the office schedule totals into formulas. Returns how many."""
    body = _find_body(sections)
    if body is None:
        return 0
    ranges = dict((p, _column_range(where, body, c)) for p, c in body.phase_cols.items())
    if not all(ranges.values()):
        return 0
    type_range = _column_range(where, body, body.type_col) if body.type_col is not None else None
    sums = dict((p, sum(body.number(r, c) for r in body.rows)) for p, c in body.phase_cols.items())
    count = 0

    for si, section in enumerate(sections):
        if si == body.si:
            continue
        rows = section.rows
        # TOTAL LOAD PER PHASE: three numbers, R then Y then B
        for r, cells in enumerate(rows):
            for c, t in enumerate(cells):
                if u"TOTAL LOAD PER PHASE" not in _norm(t):
                    continue
                for p, (cc, text) in zip(PHASES, _numbers_right_of(cells, c)[:3]):
                    factor = _scale(sums[p], text)
                    at = where.get((si, r, cc))
                    if factor and at:
                        f = u"SUM(%s)" % ranges[p] + (u"/%d" % factor if factor != 1 else u"")
                        _set_formula(sheet, at, f, sums[p] / factor, text)
                        count += 1
        # LOAD TYPE table: connected = SUMIF over R, Y, B; demanded = connected x DF
        if type_range is None:
            continue
        head = None
        labels = {}
        for r, cells in enumerate(rows):
            for c, t in enumerate(cells):
                n = _norm(t)
                if n == u"LOAD TYPE" and head is None:
                    head = (r, c)
                elif n.startswith(u"CONNECTED LOAD"):
                    labels["connected"] = r
                elif n.startswith(u"DEMAND FACTOR"):
                    labels["factor"] = r
                elif n.startswith(u"DEMANDED LOAD") or n.startswith(u"DEMAND LOAD"):
                    labels["demanded"] = r
        if head is None or "connected" not in labels:
            continue
        hr, hc = head
        types = [(c, _norm(t)) for c, t in enumerate(rows[hr]) if c > hc and _norm(t) not in _SKIP]
        total_col = None
        connected = {}
        rc = labels["connected"]
        for c, name in types:
            text = rows[rc][c] if c < len(rows[rc]) else u""
            at = where.get((si, rc, c))
            if name == u"TOTAL":
                total_col = c
                continue
            if _num(text) is None or at is None:
                continue
            raw = sum(body.number(r, pc) for r in body.rows if body.load_type(r) == name
                      for pc in body.phase_cols.values())
            factor = _scale(raw, text)
            if not factor:
                continue
            parts = u"+".join(u'SUMIF(%s,"%s",%s)' % (type_range, name.replace(u'"', u'""'), ranges[p])
                              for p in PHASES)
            f = u"(%s)/%d" % (parts, factor) if factor != 1 else parts
            _set_formula(sheet, at, f, raw / factor, text)
            connected[c] = (at, raw / factor)
            count += 1
        demanded = {}
        if "factor" in labels and "demanded" in labels:
            rf, rd = labels["factor"], labels["demanded"]
            for c, (at, value) in connected.items():
                df_text = rows[rf][c] if c < len(rows[rf]) else u""
                d_text = rows[rd][c] if c < len(rows[rd]) else u""
                df_at, d_at = where.get((si, rf, c)), where.get((si, rd, c))
                df = _num(df_text)
                if df is None or df_at is None or d_at is None or _num(d_text) is None:
                    continue
                if not _shows(value * df, d_text):
                    continue
                _set_formula(sheet, d_at, u"%s*%s" % (ref(*at), ref(*df_at)), value * df, d_text)
                demanded[c] = (d_at, value * df)
                count += 1
        if total_col is not None:
            for row_label, done in ((rc, connected), (labels.get("demanded"), demanded)):
                if row_label is None or not done:
                    continue
                done = dict(done)
                for c, name in types:       # numbers left as they are count too
                    text = rows[row_label][c] if c < len(rows[row_label]) else u""
                    at = where.get((si, row_label, c))
                    if c != total_col and c not in done and at and _num(text) is not None:
                        done[c] = (at, _num(text))
                text = rows[row_label][total_col] if total_col < len(rows[row_label]) else u""
                at = where.get((si, row_label, total_col))
                value = sum(v for _, v in done.values())
                if at is None or not _shows(value, text):
                    continue
                cells = sorted(a for a, _ in done.values())
                f = u"SUM(%s)" % u",".join(ref(*a) for a in cells)
                _set_formula(sheet, at, f, value, text)
                count += 1
    return count
