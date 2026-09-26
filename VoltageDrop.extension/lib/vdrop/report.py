# -*- coding: utf-8 -*-
"""The voltage drop report (office sheet layout, .xlsx) and the text
summary shown after a calculation. No Revit needed."""
from __future__ import division

import datetime

from vdrop.parse import format_number
from vdrop.xlsx import Formula, Style, Workbook, col_letter, ref

SHEET_NAME = "VOLTAGE DROP CALCULATION"
TITLE = "VOLTAGE DROP CALCULATIONS"

# Columns of the office sheet, plus REMARKS.
COLUMNS = [
    # (key, heading, width, number format)
    ("sn", "S.N", 8, None),
    ("from", "FROM", 14, None),
    ("to", "TO", 16, None),
    ("length", "DISTANCE(M)", 8, "General"),
    ("phases", "PHASE", 6, "0"),
    ("voltage", "VOLTAGE", 7, "0"),
    ("tcl", "TCL(KW)", 8, "0.00"),
    ("pf", "PF", 5, "0.00"),
    ("mdl", "MDL(KW)", 8, "0.00"),
    ("kva", "MDL (KVA)", 8, "0.00"),
    ("current", "CURRENT(A)", 8, "0.0"),
    ("breaker", "Breaker Rating(A)", 8, "0"),
    ("breaker_check", "BREAKER PROTECTION ANALYSIS", 10, None),
    ("installation", "CABLE LAYING LOCATION", 10, None),
    ("runs", "NO.OF RUNS PER PHASE", 7, "0"),
    ("cores", "NO.OF CORES", 6, "0"),
    ("size", "CABLE CSA (mm2)", 7, "General"),
    ("insulation", "INSULATION", 13, None),
    ("rating", "Cable Ampacity per each run", 8, "0"),
    ("total_rating", "Cable Total Ampacity", 8, "0"),
    ("cable_check", "Cable Analysis", 8, None),
    ("depth", "DEPTH (mm)", 7, "General"),
    ("cb", "Cb\n(DEPTH DERATING FACTOR)", 8, "0.00"),
    ("temperature", u"TEMPERATURE ( °C)", 8, "General"),
    ("ca", "Ca\n(TEMPERATURE DERATING FACTOR)", 9, "0.00"),
    ("resistivity", u"THERMAL RESISITIVITY\n( °C M/W )", 9, "General"),
    ("cr", "Cr\n(SOIL THERMAL RESISTIVITY DERATING FACTOR)", 11, "0.00"),
    ("cg", "Cg\n(GROUPING DERATING FACTOR)", 9, "0.00"),
    ("capacity", "REQUIRED CURRENT CARRYING CAPACITY OF THE CABLE (A)", 11, "0.0"),
    ("mv", "Mv/A/L", 8, "0.0000"),
    ("vd", "V.D(V)", 7, "0.00"),
    ("vd_percent", "V.D(%)", 7, "0.00"),
    ("total", "CUMULATIVE V.D(%)", 9, "0.00"),
    ("limit", "MAX V.D%", 6, "General"),
    ("basis", "Calc. By\nTCL/MDL", 7, None),
    ("remarks", "REMARKS", 40, None),
]
COL = dict((key, i + 1) for i, (key, _, _, _) in enumerate(COLUMNS))
LAST_COL = len(COLUMNS)
GROUPS = [
    ("DESIGNATION", "from", "to"),
    ("FEEDER/Load DATA", "length", "kva"),
    ("CURRENT & Breaker", "current", "breaker_check"),
    ("FEEDER CABLE PARAMETERS AND DERATING", "installation", "mv"),
    ("RESULT VALUES", "vd", "total"),
]
GROUP_ROW = 19
HEADER_ROW = 20
FIRST_ROW = 21

HEADER_FILL = "D9D9D9"
SECTION_FILL = "DDEBF7"
TITLE_FILL = "BDD7EE"

_BASE = Style(size=9, halign="center")
_TEXT = _BASE.copy(halign="left")
_HEADER = _BASE.copy(bold=True, fill=HEADER_FILL, wrap=True)
_PLAIN = Style(size=9, border=False, valign=None)


class ReportInfo(object):
    """Title block of the report."""

    def __init__(self, company="", project="", location="", client="", block="",
                 revision="00", issue="", date=None, sheets="1of1"):
        self.company = company
        self.project = project
        self.location = location
        self.client = client
        self.block = block
        self.revision = revision
        self.issue = issue
        self.date = date or datetime.date.today()
        self.sheets = sheets


# ---------------------------------------------------------------- summary

def counts(result):
    rows = list(result.rows())
    failed = [r for r in rows if r.failed]
    incomplete = [r for r in rows if not r.failed and r.status() == "INCOMPLETE"]
    return rows, failed, incomplete


def worst(result):
    """Row with the highest cumulative voltage drop, or None."""
    rows = [r for r in result.rows() if r.total_percent is not None]
    return max(rows, key=lambda r: r.total_percent) if rows else None


def headline(result):
    rows, failed, incomplete = counts(result)
    if not rows:
        return "No cables to calculate."
    text = "%d cable%s: %d OK, %d failed, %d incomplete." % (
        len(rows), "" if len(rows) == 1 else "s", len(rows) - len(failed) - len(incomplete),
        len(failed), len(incomplete))
    top = worst(result)
    if top is not None:
        text += " Highest cumulative V.D %s%% (%s -> %s)." % (
            format_number(top.total_percent), top.feeder.source, top.feeder.target)
    return text


def result_text(row):
    status = row.status()
    if status == "OK":
        return "OK"
    return u"%s: %s" % (status, row.remarks())


def table(section):
    """Rows for the results table of the output window."""
    out = []
    for row in section.rows:
        out.append([
            row.number, row.feeder.source, row.feeder.target,
            format_number(row.feeder.length, 1), format_number(row.current, 1),
            format_number(row.feeder.breaker, 0), row.cable_text(),
            format_number(row.capacity, 1), format_number(row.vd_percent),
            format_number(row.total_percent), format_number(row.limit),
            result_text(row),
        ])
    return out


TABLE_COLUMNS = ["S.N", "From", "To", "Length (m)", "Ib (A)", "In (A)", "Cable",
                 "Iz (A)", "V.D %", "Total V.D %", "Max %", "Result"]


# ---------------------------------------------------------------- workbook

def _title_block(sheet, info, settings):
    company = _BASE.copy(bold=True, size=10, wrap=True)
    sheet.merge(1, 1, 4, 3, info.company, company)
    label, value = _TEXT.copy(bold=True), _TEXT
    right_label = _TEXT.copy(bold=True)
    left = [("Project:", info.project), ("Location:", info.location),
            ("Client:", info.client), ("Block:", info.block)]
    right = [("No. of Sheets", info.sheets), ("Revision No.", info.revision),
             ("Date", info.date), ("Issue", info.issue)]
    for i, (name, text) in enumerate(left):
        sheet.merge(i + 1, 4, i + 1, 6, name, label)
        sheet.merge(i + 1, 7, i + 1, COL["cable_check"], text, value)
    for i, (name, text) in enumerate(right):
        sheet.merge(i + 1, COL["depth"], i + 1, COL["cr"], name, right_label)
        style = _TEXT.copy(num_format="dd/mm/yyyy") if isinstance(text, datetime.date) else _TEXT
        sheet.merge(i + 1, COL["cg"], i + 1, LAST_COL, text, style)
    sheet.merge(5, 1, 5, LAST_COL, TITLE, _BASE.copy(bold=True, size=14, fill=TITLE_FILL))
    sheet.heights[5] = 22

    notes = [
        "Design parameters:",
        u"Design current I (A) = MDL (kVA) x 1000 / (√3 x V)     single phase: MDL (kVA) x 1000 / V",
        u"V.D (V) = mV/A/m / runs x L (m) x I (A) / 1000          V.D (%) = V.D (V) / V x 100",
        "Cumulative V.D (%) = V.D (%) + cumulative V.D (%) of the cable feeding the FROM board "
        "(starts again after a transformer or UPS)",
        "MAX allowed V.D = %s%% from the LV terminals of the transformer to the main board, "
        "%s%% to the final loads" % (format_number(settings.limit_transformer),
                                     format_number(settings.limit_total)),
        u"Breaker rating >= 1.1 x I       Iz = rating x runs x Cb x Ca x Cr x Cg >= breaker rating",
        u"mV/A/m and current ratings: DUCAB copper XLPE cable tables. "
        u"Single phase mV/A/m = 2/√3 x three phase.",
        "Derating factors parameters:",
        "1. Cables laid directly in ground: derating = ground temp. x soil thermal resis. "
        "x depth of laying x grouping",
        "2. Cables installed in ducts: derating = ground temp. x soil thermal resis. "
        "x depth of laying x grouping",
        "3. Cables installed in air (cable tray): derating = ambient air temperature x grouping",
    ]
    for i, text in enumerate(notes):
        bold = text.endswith(":")
        sheet.merge(7 + i, 1, 7 + i, COL["cable_check"], text, _PLAIN.copy(bold=bold))

    params = [
        ("Frequency", 50, "Hz"),
        ("VOLTAGE/3PHASE", settings.voltage_3ph, "V"),
        ("VOLTAGE/1PHASE", settings.voltage_1ph, "V"),
        ("Power factor (default)", settings.power_factor, ""),
        ("Ambient air temp (cable tray)", settings.air_temperature, u"°C"),
        ("Ground temp (ground / ducts)", settings.ground_temperature, u"°C"),
        ("Laying depth", settings.depth or "-", "mm"),
        ("Soil thermal resistivity", settings.soil_resistivity or "-", "K.m/W"),
        ("Grouping factor Cg", settings.grouping, ""),
        ("Maximum operating temp of XLPE", 90, u"°C"),
    ]
    for i, (name, number, unit) in enumerate(params):
        r = 7 + i
        sheet.merge(r, COL["depth"], r, COL["cg"], name, _TEXT)
        sheet.merge(r, COL["capacity"], r, COL["mv"], number, _BASE)
        sheet.write(r, COL["vd"], unit, _BASE)


def _headers(sheet):
    for title, first, last in GROUPS:
        sheet.merge(GROUP_ROW, COL[first], GROUP_ROW, COL[last], title, _HEADER)
    for key in ("sn", "limit", "basis", "remarks"):
        sheet.write(GROUP_ROW, COL[key], None, _HEADER)
    for i, (key, heading, width, _) in enumerate(COLUMNS):
        sheet.write(HEADER_ROW, i + 1, heading, _HEADER)
        sheet.widths[i + 1] = width
    sheet.heights[HEADER_ROW] = 78


def _check(ok):
    return "" if ok is None else ("PASS" if ok else "FAIL")


def _blank(value):
    return "" if value is None else value


def _row(sheet, r, row, parent_row, styles):
    f = row.feeder
    c = dict((key, ref(r, COL[key])) for key in COL)
    values = {
        "sn": row.number, "from": f.source, "to": f.target, "length": f.length,
        "phases": row.phases, "voltage": row.voltage, "tcl": f.tcl_kw,
        "pf": row.power_factor, "mdl": row.load_kw,
        "kva": Formula('IF(OR(%s="",%s=""),"",%s/%s)' % (c["mdl"], c["pf"], c["mdl"], c["pf"]),
                       _blank(row.kva)),
        "current": Formula('IF(%s="","",%s*1000/(IF(%s=3,SQRT(3),1)*%s))' % (
            c["kva"], c["kva"], c["phases"], c["voltage"]), _blank(row.current)),
        "breaker": f.breaker,
        "breaker_check": Formula('IF(OR(%s="",%s=""),"",IF(%s>=1.1*%s,"PASS","FAIL"))' % (
            c["breaker"], c["current"], c["breaker"], c["current"]), _check(row.breaker_ok)),
        "installation": row.installation, "runs": row.runs, "cores": row.cores,
        "size": row.size, "insulation": row.insulation, "rating": row.rating,
        "total_rating": Formula('IF(%s="","",%s*%s)' % (c["rating"], c["rating"], c["runs"]),
                                _blank(row.total_rating)),
        "cable_check": Formula(
            'IF(OR(%s="",AND(%s="",%s="")),"",IF(%s>=IF(%s="",%s,%s),"PASS","FAIL"))' % (
                c["capacity"], c["breaker"], c["current"], c["capacity"], c["breaker"],
                c["current"], c["breaker"]), _check(row.cable_ok)),
        "depth": row.depth, "cb": row.cb, "temperature": row.temperature, "ca": row.ca,
        "resistivity": row.resistivity, "cr": row.cr, "cg": row.cg,
        "capacity": Formula('IF(OR(%s="",%s="",%s="",%s=""),"",%s*%s*%s*%s*%s)' % (
            c["total_rating"], c["cb"], c["ca"], c["cr"],
            c["total_rating"], c["cb"], c["ca"], c["cr"], c["cg"]), _blank(row.capacity)),
        "vd": Formula('IF(OR(%s="",%s="",%s=""),"",%s*%s*%s/1000)' % (
            c["length"], c["mv"], c["current"], c["length"], c["current"], c["mv"]),
            _blank(row.vd_volts)),
        "vd_percent": Formula('IF(%s="","",%s/%s*100)' % (c["vd"], c["vd"], c["voltage"]),
                              _blank(row.vd_percent)),
        "limit": row.limit, "basis": row.basis, "remarks": row.remarks(), "mv": None,
    }
    if row.mv_row is not None:
        # table value (three phase), per run
        mv_text = format_number(row.mv_table, 4) + ("*2/SQRT(3)" if row.phases == 1 else "")
        values["mv"] = Formula("%s/%s" % (mv_text, c["runs"]), row.mv_row)
    if row.resets or parent_row is None:
        values["total"] = Formula('IF(%s="","",%s)' % (c["vd_percent"], c["vd_percent"]),
                                  _blank(row.total_percent))
    else:
        up = ref(parent_row, COL["total"])
        values["total"] = Formula('IF(OR(%s="",%s=""),"",%s+%s)' % (
            c["vd_percent"], up, c["vd_percent"], up), _blank(row.total_percent))
    for key, value in values.items():
        sheet.write(r, COL[key], value, styles[key])


def build(result, settings, info=None):
    """Workbook with the calculation of every cable in the office layout."""
    info = info or ReportInfo()
    book = Workbook()
    sheet = book.add_sheet(SHEET_NAME)
    _title_block(sheet, info, settings)
    _headers(sheet)
    styles = {}
    for key, _, _, fmt in COLUMNS:
        text = key in ("from", "to", "insulation", "remarks")
        styles[key] = (_TEXT if text else _BASE).copy(num_format=fmt, wrap=key == "remarks")
    section_style = _TEXT.copy(bold=True, fill=SECTION_FILL)

    r = FIRST_ROW
    for section in result.sections:
        sheet.merge(r, 1, r, LAST_COL, section.title, section_style)
        r += 1
        placed = {}
        for row in section.rows:
            placed[id(row)] = r
            parent_row = placed.get(id(row.parent)) if row.parent is not None else None
            _row(sheet, r, row, parent_row, styles)
            r += 1
    last = max(r - 1, FIRST_ROW)

    r += 1
    sheet.merge(r, 1, r, COL["cable_check"], headline(result), _PLAIN.copy(bold=True))

    data = lambda key: "%s%d:%s%d" % (col_letter(COL[key]), FIRST_ROW,
                                     col_letter(COL[key]), last)
    first = lambda key: ref(FIRST_ROW, COL[key])
    for key in ("breaker_check", "cable_check"):
        sheet.conditional(data(key), '%s="FAIL"' % first(key))
    sheet.conditional(data("total"), "AND(ISNUMBER(%s),%s>%s)" % (
        first("total"), first("total"), first("limit")))
    sheet.freeze = (FIRST_ROW, COL["length"])
    sheet.print_rows = (GROUP_ROW, HEADER_ROW)
    return book
