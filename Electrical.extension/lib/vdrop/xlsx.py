# -*- coding: utf-8 -*-
"""Small .xlsx writer: values, formulas (with their calculated values),
styles, merged cells, column widths, frozen panes, conditional formats and
page setup.

Standard library only, so it runs in pyRevit's IronPython 2.7 and
CPython 3 engines where openpyxl / xlsxwriter may not be installed.
"""
from __future__ import division

import datetime
import math
import re
import zipfile

FONT = "Arial"

_ILLEGAL_XML = re.compile(u"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _esc(text):
    text = _ILLEGAL_XML.sub(u"", u"%s" % text)
    return (text.replace(u"&", u"&amp;").replace(u"<", u"&lt;")
            .replace(u">", u"&gt;").replace(u'"', u"&quot;"))


def col_letter(col):
    """1 -> 'A', 27 -> 'AA'."""
    letters = ""
    while col:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def ref(row, col, absolute=False):
    if absolute:
        return "$%s$%d" % (col_letter(col), row)
    return "%s%d" % (col_letter(col), row)


try:
    _INTEGERS = (int, long)  # noqa: F821  (IronPython 2.7)
except NameError:
    _INTEGERS = (int,)


def _num(value):
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, _INTEGERS):
        return str(value)
    return repr(float(value))


def _is_number(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, _INTEGERS):
        return True
    return isinstance(value, float) and not (math.isnan(value) or math.isinf(value))


def excel_date(day):
    """Excel serial number of a date."""
    if isinstance(day, datetime.datetime):
        day = day.date()
    return (day - datetime.date(1899, 12, 30)).days


# Arial (= Helvetica) character widths in 1/1000 em, for " " to "~".
_REGULAR = (
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584)
_BOLD = (
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584, 584, 611,
    975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333, 278, 333, 584, 556,
    333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278, 556, 278, 889, 611, 611,
    611, 611, 389, 556, 333, 611, 556, 778, 556, 556, 500, 389, 280, 389, 584)
_OTHER = {u"²": 333, u"°": 400, u"√": 549}


def text_points(text, size=9, bold=False):
    """Length of one line of text in points (Arial)."""
    table = _BOLD if bold else _REGULAR
    total = 0
    for ch in u"%s" % text:
        code = ord(ch)
        total += table[code - 32] if 32 <= code < 127 else _OTHER.get(ch, 600)
    return total * size / 1000.0


def width_units(points):
    """Excel column width (characters of the Arial 9 '0', 7 px at 96 dpi)
    taken by `points` of text."""
    return points / 0.75 / 7.0


def wrap_lines(text, limit, size=9, bold=False):
    """Lines of `text` wrapped at spaces to `limit` points, as Excel does
    (explicit line breaks kept)."""
    lines = []
    for paragraph in (u"%s" % text).split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = (line + " " + word).strip()
            if line and text_points(candidate, size, bold) > limit:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return lines


class Formula(object):
    """A formula (without '=') and the value it gives, shown until Excel
    recalculates."""

    def __init__(self, text, value=None):
        self.text = text
        self.value = value


class Style(object):
    def __init__(self, bold=False, italic=False, size=9, color=None, fill=None,
                 border=True, halign=None, valign="center", wrap=False,
                 num_format=None, rotation=0):
        self.bold = bold
        self.italic = italic
        self.size = size
        self.color = color          # 'RRGGBB'
        self.fill = fill            # 'RRGGBB'
        self.border = border
        self.halign = halign        # 'left', 'center', 'right'
        self.valign = valign
        self.wrap = wrap
        self.num_format = num_format
        self.rotation = rotation    # 90: text reads bottom to top

    def copy(self, **changes):
        style = Style()
        style.__dict__.update(self.__dict__)
        style.__dict__.update(changes)
        return style

    def _font(self):
        return (self.bold, self.italic, self.size, self.color)

    def _xf(self):
        return (self._font(), self.fill, self.border, self.halign, self.valign,
                self.wrap, self.num_format, self.rotation)


class Highlight(object):
    """Format applied by a conditional format: text colour and fill."""

    def __init__(self, color="9C0006", fill="FFC7CE", bold=True):
        self.color = color
        self.fill = fill
        self.bold = bold


class Sheet(object):
    def __init__(self, name):
        self.name = name[:31]
        self.cells = {}           # (row, col) -> (value, Style)
        self.merges = []
        self.widths = {}
        self.heights = {}
        self.freeze = None        # (row, col) of the first scrolling cell
        self.conditionals = []    # (range, formula, Highlight)
        self.landscape = True
        self.paper = 8            # A3
        self.print_rows = None    # (first, last) rows repeated on every page
        self.footer = None        # e.g. '&LTitle&RPage &P of &N'

    def write(self, row, col, value=None, style=None):
        self.cells[(row, col)] = (value, style)

    def merge(self, row1, col1, row2, col2, value=None, style=None):
        """Merge a range; the style goes on every cell so borders show."""
        for r in range(row1, row2 + 1):
            for c in range(col1, col2 + 1):
                self.cells[(r, c)] = (value if (r, c) == (row1, col1) else None, style)
        if (row1, col1) != (row2, col2):
            self.merges.append("%s:%s" % (ref(row1, col1), ref(row2, col2)))

    def value(self, row, col):
        return self.cells.get((row, col), (None, None))[0]

    def conditional(self, cell_range, formula, highlight=None):
        self.conditionals.append((cell_range, formula, highlight or Highlight()))


class Workbook(object):
    def __init__(self):
        self.sheets = []
        self._xfs = [None]        # cellXfs; 0 is the default style
        self._xf_index = {}
        self._dxfs = []

    def add_sheet(self, name):
        sheet = Sheet(name)
        self.sheets.append(sheet)
        return sheet

    # ------------------------------------------------------------ styles

    def _style_id(self, style):
        if style is None:
            return 0
        key = style._xf()
        if key not in self._xf_index:
            self._xf_index[key] = len(self._xfs)
            self._xfs.append(style)
        return self._xf_index[key]

    def _dxf_id(self, highlight):
        key = (highlight.color, highlight.fill, highlight.bold)
        if key not in self._dxfs:
            self._dxfs.append(key)
        return self._dxfs.index(key)

    def _styles_xml(self):
        default = Style(border=False, valign=None)
        styles = [default] + self._xfs[1:]
        fonts, fills, borders, num_formats = [], [None, "gray125"], [False, True], []
        xfs = []
        for s in styles:
            if s._font() not in fonts:
                fonts.append(s._font())
            if s.fill and s.fill not in fills:
                fills.append(s.fill)
            if s.num_format and s.num_format not in num_formats:
                num_formats.append(s.num_format)
        out = [u'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
               u'<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
        if num_formats:
            out.append(u'<numFmts count="%d">' % len(num_formats))
            for i, fmt in enumerate(num_formats):
                out.append(u'<numFmt numFmtId="%d" formatCode="%s"/>' % (164 + i, _esc(fmt)))
            out.append(u"</numFmts>")
        out.append(u'<fonts count="%d">' % len(fonts))
        for bold, italic, size, color in fonts:
            out.append(u"<font>%s%s<sz val=\"%s\"/>%s<name val=\"%s\"/></font>" % (
                u"<b/>" if bold else u"", u"<i/>" if italic else u"", _num(size),
                u'<color rgb="FF%s"/>' % color if color else u"", FONT))
        out.append(u"</fonts>")
        out.append(u'<fills count="%d">' % len(fills))
        out.append(u'<fill><patternFill patternType="none"/></fill>')
        out.append(u'<fill><patternFill patternType="gray125"/></fill>')
        for color in fills[2:]:
            out.append(u'<fill><patternFill patternType="solid"><fgColor rgb="FF%s"/>'
                       u'<bgColor indexed="64"/></patternFill></fill>' % color)
        out.append(u"</fills>")
        out.append(u'<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border>'
                   u'<border><left style="thin"><color auto="1"/></left><right style="thin">'
                   u'<color auto="1"/></right><top style="thin"><color auto="1"/></top>'
                   u'<bottom style="thin"><color auto="1"/></bottom><diagonal/></border></borders>')
        out.append(u'<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
                   u"</cellStyleXfs>")
        out.append(u'<cellXfs count="%d">' % len(styles))
        for s in styles:
            num_id = 164 + num_formats.index(s.num_format) if s.num_format else 0
            align = u""
            if s.halign or s.valign or s.wrap or s.rotation:
                align = u"<alignment%s%s%s%s/>" % (
                    u' horizontal="%s"' % s.halign if s.halign else u"",
                    u' vertical="%s"' % s.valign if s.valign else u"",
                    u' textRotation="%d"' % s.rotation if s.rotation else u"",
                    u' wrapText="1"' if s.wrap else u"")
            out.append(u'<xf numFmtId="%d" fontId="%d" fillId="%d" borderId="%d" xfId="0"'
                       u'%s%s%s%s%s>%s</xf>' % (
                           num_id, fonts.index(s._font()),
                           fills.index(s.fill) if s.fill else 0, 1 if s.border else 0,
                           u' applyNumberFormat="1"' if num_id else u"",
                           u' applyFont="1"', u' applyFill="1"' if s.fill else u"",
                           u' applyBorder="1"' if s.border else u"",
                           u' applyAlignment="1"' if align else u"", align))
        out.append(u"</cellXfs>")
        out.append(u'<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>')
        out.append(u'<dxfs count="%d">' % len(self._dxfs))
        for color, fill, bold in self._dxfs:
            out.append(u'<dxf><font>%s<color rgb="FF%s"/></font><fill><patternFill>'
                       u'<bgColor rgb="FF%s"/></patternFill></fill></dxf>' % (
                           u"<b/>" if bold else u"", color, fill))
        out.append(u"</dxfs></styleSheet>")
        return u"".join(out)

    # ------------------------------------------------------------ sheets

    def _cell_xml(self, row, col, value, style):
        attrs = u' r="%s"' % ref(row, col)
        style_id = self._style_id(style)
        if style_id:
            attrs += u' s="%d"' % style_id
        if isinstance(value, Formula):
            cached = value.value
            text = u"<f>%s</f>" % _esc(value.text)
            if _is_number(cached):
                return u"<c%s>%s<v>%s</v></c>" % (attrs, text, _num(cached))
            if cached is None:
                return u"<c%s>%s</c>" % (attrs, text)
            return u'<c%s t="str">%s<v>%s</v></c>' % (attrs, text, _esc(cached))
        if isinstance(value, datetime.date):
            value = excel_date(value)
        if _is_number(value):
            return u"<c%s><v>%s</v></c>" % (attrs, _num(value))
        if value is None or value == u"":
            return u"<c%s/>" % attrs
        text = u"%s" % value
        space = u' xml:space="preserve"' if text != text.strip() else u""
        return u'<c%s t="inlineStr"><is><t%s>%s</t></is></c>' % (attrs, space, _esc(text))

    def _sheet_xml(self, sheet):
        rows = {}
        for (r, c) in sheet.cells:
            rows.setdefault(r, []).append(c)
        last_row = max(rows) if rows else 1
        last_col = max(c for (_, c) in sheet.cells) if sheet.cells else 1
        out = [u'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
               u'<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
               u'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
               u'<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>',
               u'<dimension ref="A1:%s"/>' % ref(last_row, last_col),
               u'<sheetViews><sheetView workbookViewId="0" zoomScale="85">']
        if sheet.freeze:
            r, c = sheet.freeze
            out.append(u'<pane%s%s topLeftCell="%s" activePane="%s" state="frozen"/>' % (
                u' xSplit="%d"' % (c - 1) if c > 1 else u"",
                u' ySplit="%d"' % (r - 1) if r > 1 else u"", ref(r, c),
                u"bottomRight" if r > 1 and c > 1 else (u"bottomLeft" if r > 1 else u"topRight")))
        out.append(u"</sheetView></sheetViews>")
        out.append(u'<sheetFormatPr defaultRowHeight="12.75"/>')
        if sheet.widths:
            out.append(u"<cols>")
            for c in sorted(sheet.widths):
                out.append(u'<col min="%d" max="%d" width="%s" customWidth="1"/>' % (
                    c, c, _num(sheet.widths[c])))
            out.append(u"</cols>")
        out.append(u"<sheetData>")
        for r in sorted(set(rows) | set(sheet.heights)):
            height = sheet.heights.get(r)
            out.append(u'<row r="%d"%s>' % (
                r, u' ht="%s" customHeight="1"' % _num(height) if height else u""))
            for c in sorted(rows.get(r, [])):
                value, style = sheet.cells[(r, c)]
                out.append(self._cell_xml(r, c, value, style))
            out.append(u"</row>")
        out.append(u"</sheetData>")
        if sheet.merges:
            out.append(u'<mergeCells count="%d">' % len(sheet.merges))
            out.extend(u'<mergeCell ref="%s"/>' % m for m in sheet.merges)
            out.append(u"</mergeCells>")
        for priority, (cell_range, formula, highlight) in enumerate(sheet.conditionals):
            out.append(u'<conditionalFormatting sqref="%s"><cfRule type="expression" dxfId="%d" '
                       u'priority="%d"><formula>%s</formula></cfRule></conditionalFormatting>' % (
                           cell_range, self._dxf_id(highlight), priority + 1, _esc(formula)))
        out.append(u'<pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" '
                   u'header="0.3" footer="0.3"/>')
        out.append(u'<pageSetup paperSize="%d" orientation="%s" fitToWidth="1" fitToHeight="0"/>' % (
            sheet.paper, u"landscape" if sheet.landscape else u"portrait"))
        if sheet.footer:
            out.append(u"<headerFooter><oddFooter>%s</oddFooter></headerFooter>" % _esc(sheet.footer))
        out.append(u"</worksheet>")
        return u"".join(out)

    def _workbook_xml(self):
        out = [u'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
               u'<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
               u'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
               u"<bookViews><workbookView/></bookViews><sheets>"]
        for i, sheet in enumerate(self.sheets):
            out.append(u'<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (
                _esc(sheet.name), i + 1, i + 1))
        out.append(u"</sheets>")
        titles = [(i, s) for i, s in enumerate(self.sheets) if s.print_rows]
        if titles:
            out.append(u"<definedNames>")
            for i, s in titles:
                out.append(u'<definedName name="_xlnm.Print_Titles" localSheetId="%d">'
                           u"'%s'!$%d:$%d</definedName>" % (
                               i, _esc(s.name.replace(u"'", u"''")), s.print_rows[0], s.print_rows[1]))
            out.append(u"</definedNames>")
        out.append(u'<calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>')
        return u"".join(out)

    def save(self, path):
        # sheet XML first: it registers the styles used by the cells
        sheets = [self._sheet_xml(s) for s in self.sheets]
        parts = [
            ("[Content_Types].xml", self._content_types()),
            ("_rels/.rels",
             u'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             u'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             u'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
             u'relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'),
            ("xl/workbook.xml", self._workbook_xml()),
            ("xl/_rels/workbook.xml.rels", self._workbook_rels()),
            ("xl/styles.xml", self._styles_xml()),
        ]
        for i, xml in enumerate(sheets):
            parts.append(("xl/worksheets/sheet%d.xml" % (i + 1), xml))
        try:
            import zlib  # noqa: F401  (deflate needs it)
            compression = zipfile.ZIP_DEFLATED
        except ImportError:
            compression = zipfile.ZIP_STORED
        archive = zipfile.ZipFile(path, "w", compression)
        try:
            for name, xml in parts:
                archive.writestr(name, xml.encode("utf-8"))
        finally:
            archive.close()

    def _content_types(self):
        out = [u'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
               u'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
               u'<Default Extension="rels" ContentType="application/'
               u'vnd.openxmlformats-package.relationships+xml"/>',
               u'<Default Extension="xml" ContentType="application/xml"/>',
               u'<Override PartName="/xl/workbook.xml" ContentType="application/'
               u'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
               u'<Override PartName="/xl/styles.xml" ContentType="application/'
               u'vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
        for i in range(len(self.sheets)):
            out.append(u'<Override PartName="/xl/worksheets/sheet%d.xml" ContentType="application/'
                       u'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>' % (i + 1))
        out.append(u"</Types>")
        return u"".join(out)

    def _workbook_rels(self):
        out = [u'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
               u'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
        for i in range(len(self.sheets)):
            out.append(u'<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/'
                       u'officeDocument/2006/relationships/worksheet" '
                       u'Target="worksheets/sheet%d.xml"/>' % (i + 1, i + 1))
        out.append(u'<Relationship Id="rId%d" Type="http://schemas.openxmlformats.org/'
                   u'officeDocument/2006/relationships/styles" Target="styles.xml"/>' % (
                       len(self.sheets) + 1))
        out.append(u"</Relationships>")
        return u"".join(out)
