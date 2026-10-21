# -*- coding: utf-8 -*-
"""MDB / SMDB load schedules: one Excel sheet per board, in the office
format (MDB1.xlsx), from the boards and ways shown in Power Studio.

Each sheet lists the board's outgoing ways with breaker, cable, R/Y/B
connected load, diversity factor and diversified load. A way to another
board takes its loads from that board's sheet (formulas), a way to a DB
looks them up in the 'Electrical Equipment Schedule' sheet (the Revit
panel loads), and a final circuit has its own values. Totals, connected /
diversified load and overall diversity are Excel formulas, so the file
can be changed by hand afterwards.

Kept free of Revit and WPF, so it runs under pytest.
"""
from __future__ import division

import re

from sld import sizing
from sld.model import DB_BOX, FEEDER, PFC, TO_UPS, natural_key, trim_number
from vdrop.xlsx import Formula, Style, Workbook, col_letter

RCD_TEXT = u"300(s)"            # 'RCD (mA)' column, as on the office schedules
SCHEDULE_SHEET = u"Electrical Equipment Schedule"
FIRST_ROW = 8                   # first way row
TYPES = (("PWR", "PWR"), ("LTG", "LTG"), ("WH", "WH"), ("MO", "MO"), ("A/C", "AC"))

# columns
C_NO, C_DESC, C_PH, C_RCD, C_CB, C_TYPE, C_RUNS, C_CORES, C_SIZE, C_ECC = range(1, 11)
C_KR, C_KY, C_KB, C_TCL, C_DF, C_DTYPE, C_QR, C_QY, C_QB, C_TDL, C_REM = range(11, 22)
LAST_COL = C_REM

WIDTHS = {1: 11.7, 2: 24.0, 3: 8.7, 4: 9.0, 5: 10.0, 6: 18.0, 7: 9.0, 8: 8.7, 9: 8.7,
          10: 10.6, 11: 10.3, 12: 9.5, 13: 9.5, 14: 10.0, 15: 9.0, 16: 9.0, 17: 9.5,
          18: 9.7, 19: 9.5, 20: 12.4, 21: 16.0}

_BAD_SHEET = re.compile(r"[\[\]:*?/\\]")
_LTG = re.compile(r"^L\w*DB|LIGHT|LTG", re.IGNORECASE)
_AC = re.compile(r"^A\w*DB|FCU|AHU|FAHU|VRF|CHILLER|HVAC|ERV|\bAC\b|A/C", re.IGNORECASE)
_WH = re.compile(r"HEATER|\bWH\b|^WH-|EWH", re.IGNORECASE)
_MO = re.compile(r"PUMP|MOTOR|\bFAN\b|^[A-Z]*EF-|^[A-Z]*SF-|JET\s*FAN", re.IGNORECASE)


def load_type(name):
    """Diversity type guessed from the name: LDB is LTG, ADB / FCU / AHU
    is AC, a heater WH, a pump or fan MO, anything else PWR."""
    name = name or ""
    for pattern, kind in ((_LTG, "LTG"), (_AC, "AC"), (_WH, "WH"), (_MO, "MO")):
        if pattern.search(name):
            return kind
    return "PWR"


# ---------------------------------------------------------------- styles

_TITLE = Style(bold=True, size=10, halign="left", border=False)
_INFO = Style(size=10, halign="left")
_INFO_BOLD = Style(bold=True, size=10, halign="left", wrap=True)
_HEAD = Style(size=11, halign="center", wrap=True)
_HEAD_LEFT = Style(bold=True, size=11, halign="left")
_CELL = Style(size=10, halign="center", wrap=True)
_NAME = Style(size=10, halign="left", wrap=True)
_NUM = Style(size=10, halign="center", num_format="0.00")
_TOTAL = Style(bold=True, size=10, halign="center", wrap=True)
_TOTAL_NUM = Style(bold=True, size=10, halign="center", num_format="0.00")
_TOTAL_LEFT = Style(bold=True, size=10, halign="left", wrap=True)
_PERCENT = Style(bold=True, size=10, halign="center", num_format="0%")


# ---------------------------------------------------------------- data

class Row(object):
    """One way on a board's sheet.

    source: 'link' (another board's sheet), 'lookup' (a DB in the
    equipment schedule), 'value' (its own loads) or None (spare, no load).
    """

    def __init__(self, label, name, phases=3, breaker=u"", cable=None, source=None,
                 phase_kw=None, demand_kw=None, target=None, kind="PWR", remark=u""):
        self.label = label
        self.name = name
        self.phases = phases
        self.breaker = breaker
        self.cable = cable              # sld.cablespec.CableSpec or None
        self.source = source
        self.phase_kw = phase_kw        # (R, Y, B) connected kW
        self.demand_kw = demand_kw      # diversified kW
        self.target = target            # board id ('link') or DB name ('lookup')
        self.kind = kind
        self.remark = remark

    @property
    def connected_kw(self):
        return sum(self.phase_kw) if self.phase_kw else None

    @property
    def factor(self):
        cl = self.connected_kw
        if not cl or self.demand_kw is None:
            return None
        return self.demand_kw / cl


class Sheet(object):
    """A board's load schedule."""

    def __init__(self, board_id, name, title, info):
        self.board_id = board_id
        self.name = name                # Excel sheet name
        self.title = title              # board name
        self.info = info                # header values (see _board_info)
        self.rows = []

    @property
    def total_row(self):
        return FIRST_ROW + max(len(self.rows), 1)

    def totals(self):
        """(R, Y, B connected, R, Y, B diversified, TCL, TDL) of the rows."""
        k, q = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
        for r in self.rows:
            if not r.phase_kw:
                continue
            f = r.factor if r.factor is not None else 1.0
            for i in range(3):
                k[i] += r.phase_kw[i]
                q[i] += r.phase_kw[i] * f
        return k + q + [sum(k), sum(q)]


def split_phases(total, phase="RYB", typed=None, phases=3):
    """(R, Y, B) kW of a load: the Revit phase values scaled to the total
    when known, else on the way's phase ('R', 'Y', 'B'), else a third on
    each (all on R on a single-phase board)."""
    if total is None:
        return None
    if typed:
        parts = [max(v or 0.0, 0.0) for v in typed]
        if sum(parts) > 0:
            return tuple(total * p / sum(parts) for p in parts)
    if phases == 1:
        return (total, 0.0, 0.0)
    if phase in ("R", "Y", "B"):
        return tuple(total if p == phase else 0.0 for p in "RYB")
    return (total / 3.0, total / 3.0, total / 3.0)


def sheet_name(name, used):
    base = _BAD_SHEET.sub("-", name or "Board").strip("'") or "Board"
    base = base[:31]
    text, n = base, 2
    while text.lower() in used:
        suffix = " (%d)" % n
        text, n = base[:31 - len(suffix)] + suffix, n + 1
    used.add(text.lower())
    return text


def _label(w):
    label = u"%s" % (w.label or "")
    return u"RYB%s" % label if label.isdigit() and w.phase in ("RYB", "") else label


def _phase_count(w):
    return 1 if w.phase in ("R", "Y", "B") else 3


def _breaker_text(w):
    trip = w.breaker()[0]
    return u"%sA" % trim_number(trip, 1) if trip else u""


def incoming_text(spec, fallback=u""):
    """'4x4Cx240mm² XLPE/SWA/PVC + 1Cx120mm² ECC' (office header text)."""
    if spec is None or spec.size is None:
        return fallback or u""
    main = u"%dCx%smm²" % (int(spec.cores or 4), trim_number(spec.size, 1))
    if spec.runs and int(spec.runs) > 1:
        main = u"%dx%s" % (int(spec.runs), main)
    text = u"%s %s" % (main, spec.build())
    earth = spec.earth_size
    if earth is None and (spec.cores or 0) >= 3:
        earth = sizing.earth_size(spec.size)
    if earth:
        text += u" + 1Cx%smm² ECC" % trim_number(earth, 1)
    return text


def _ecc(spec):
    if spec is None or spec.size is None:
        return u""
    earth = spec.earth_size
    if earth is None:
        if (spec.cores or 0) < 3:
            return u""
        earth = sizing.earth_size(spec.size)
    return u"1Cx%s" % trim_number(earth, 1)


def _fed_from(editor, item):
    b = item.board
    if b.parent is not None and b.feed_way is not None:
        return b.parent.name
    if b.feed_pass_through is not None:
        return b.feed_pass_through.equipment.name
    for source in (b.transformer, b.ats, b.model_generator):
        if source is not None:
            return source.name
    if item.values.get("fed_by"):
        return item.values["fed_by"]
    return u"TRANSFORMER" if b.is_main else u""


def _board_info(editor, item):
    b, v = item.board, item.values
    feed = editor._feeding_way(item.id)
    if feed is None:
        feed = next((w for w in editor.ways(item.id) if w.incoming), None)
    spec = feed.cable() if feed is not None else None
    trip = v.get("incomer_at") or u""
    try:
        big = float(trip) >= 800
    except ValueError:
        big = False
    device = v.get("incomer_device") or (u"ACB" if b.is_main and big else u"MCCB")
    poles = u"TP" if b.phases == 3 else u"DP"
    location = (b.equipment.location or u"").strip()
    return {
        "fed_from": _fed_from(editor, item),
        "incoming": incoming_text(spec, b.equipment.incoming_cable),
        "ways": u"%sWAY" % b.way_count() if b.way_count() else u"",
        "breaker": u"%sA" % trip if trip else u"",
        "device": u"%s %s" % (poles, device),
        "location": location,
    }


def collect(editor):
    """Sheets of every MDB / SMDB / USMDB shown in Power Studio, in tree
    order, and the DBs found on their ways ({name: (CL, DL, (R, Y, B))})."""
    sheets, by_board, used, dbs = [], {}, set([SCHEDULE_SHEET.lower()]), {}
    for item in editor.boards:
        s = Sheet(item.id, sheet_name(item.name, used), item.name, _board_info(editor, item))
        sheets.append(s)
        by_board[item.id] = s

    for item in editor.boards:
        s, b = by_board[item.id], item.board
        ups_first = set()
        outputs = dict((pt.equipment.id, pt) for pt in b.pass_throughs)
        for w in editor.ways(item.id):
            if w.incoming or w.way.is_space:
                continue
            way = w.way
            row = Row(_label(w), w.feeds, _phase_count(w), _breaker_text(w),
                      None if w.spare else w.cable(), kind=load_type(w.feeds))
            target = way.target
            if w.spare:
                row.name = u"SPARE"
                if not row.breaker and item.values.get("spare_at"):
                    row.breaker = u"%sA" % item.values["spare_at"]
            elif w.kind == FEEDER and w.target_id in by_board:
                row.source, row.target = "link", w.target_id
            elif w.kind == TO_UPS and w.target_id in outputs:
                pt = outputs[w.target_id]
                out = next((o for o in pt.outputs if o.id in by_board), None)
                if out is not None and w.target_id not in ups_first:
                    ups_first.add(w.target_id)
                    row.source, row.target = "link", out.id
                    row.remark = u"via %s" % pt.equipment.name if pt.equipment.name != w.feeds \
                        else u""
            elif target is not None and target.connected_kw:
                row.source, row.target = "lookup", target.name
                row.phase_kw = split_phases(target.connected_kw, w.phase,
                                            getattr(target, "phase_kw", None), b.phases)
                row.demand_kw = target.demand_kw if target.demand_kw is not None \
                    else target.connected_kw
                if w.kind != DB_BOX:
                    row.source = "value"       # a single piece of equipment
                else:
                    dbs[target.name] = (target.connected_kw, row.demand_kw, row.phase_kw)
            elif w.kind != PFC:
                cl, dl = way.loads()
                if cl:
                    row.source = "value"
                    typed = getattr(way.circuit, "phase_kw", None)
                    row.phase_kw = split_phases(cl, w.phase, typed, b.phases)
                    row.demand_kw = dl if dl is not None else cl
            s.rows.append(row)

    # linked rows take the totals of their board's sheet (children first)
    done = set()

    def finish(s, stack=()):
        if s.board_id in done or s.board_id in stack:
            return
        for r in s.rows:
            if r.source == "link":
                child = by_board[r.target]
                finish(child, stack + (s.board_id,))
                t = child.totals()
                r.phase_kw = tuple(t[0:3]) if t[6] else None
                r.demand_kw = t[7] if t[6] else None
        done.add(s.board_id)

    for s in sheets:
        finish(s)
    return sheets, by_board, dbs


# ---------------------------------------------------------------- workbook

def _quote(name):
    return u"'%s'" % name.replace(u"'", u"''")


def _cells(s):
    """Where a sheet's totals are: {key: 'Sheet'!$X$n}."""
    t = s.total_row
    q = _quote(s.name)
    out = {}
    for key, col in (("kr", C_KR), ("ky", C_KY), ("kb", C_KB),
                     ("qr", C_QR), ("qy", C_QY), ("qb", C_QB)):
        out[key] = u"%s!%s%d" % (q, col_letter(col), t)
    out["tcl"] = u"%s!%s%d" % (q, col_letter(C_REM), t + 1)
    out["tdl"] = u"%s!%s%d" % (q, col_letter(C_REM), t + 2)
    out["df"] = u"%s!%s%d" % (q, col_letter(C_REM), t + 3)
    return out


def _r(col, row):
    return u"%s%d" % (col_letter(col), row)


def _header(ws, s, project):
    m = ws.merge
    m(1, 1, 1, 7, u"Project/Building Name : %s" % project.get("project", u""), _INFO_BOLD)
    m(1, 8, 1, 17, u"Main Contractor :   %s" % project.get("contractor", u""), _INFO_BOLD)
    m(1, 18, 1, 19, u"Date : ", _INFO_BOLD)
    m(1, 20, 1, 21, Formula("TODAY()", None), Style(bold=True, size=10, halign="left",
                                                     num_format="dd/mm/yyyy"))
    m(2, 1, 2, 7, u"Address/Location : %s" % project.get("location", u""), _INFO_BOLD)
    m(2, 8, 2, 17, u"Electrical Contractor :   %s" % project.get("electrical", u""), _INFO_BOLD)
    m(2, 18, 2, 19, u"Document No. :", _INFO_BOLD)
    m(2, 20, 2, 21, project.get("document", u""), _INFO_BOLD)
    ws.write(3, 1, u"Panel Ref : ", _INFO_BOLD)
    m(3, 2, 3, 7, s.title, _INFO_BOLD)
    m(3, 8, 3, 10, u"Incoming Cable Size/type :", _INFO_BOLD)
    m(3, 11, 3, 21, s.info["incoming"], _INFO_BOLD)
    ws.write(4, 1, u"Fed From :", _INFO_BOLD)
    m(4, 2, 4, 7, s.info["fed_from"], _INFO_BOLD)
    m(4, 8, 4, 10, u"Main Breaker rating&WAY :", _INFO_BOLD)
    ws.write(4, 11, s.info["ways"], _INFO_BOLD)
    ws.write(4, 12, s.info["breaker"], _INFO_BOLD)
    m(4, 13, 4, 17, s.info["device"], _INFO_BOLD)
    m(4, 18, 4, 21, u"Location : %s" % s.info["location"], _INFO_BOLD)

    for col, text in ((C_NO, u"SL NO."), (C_DESC, u"Description"),
                      (C_PH, u"Single/Three Phase"), (C_TYPE, u"Cable Type"),
                      (C_TCL, u"Total C.Load (kw)"), (C_DF, u"Diversity Factor"),
                      (C_DTYPE, u"Diversity Type"), (C_TDL, u"Total D.Load (kw)"),
                      (C_REM, u"Remarks")):
        m(5, col, 6, col, text, _HEAD)
    m(5, C_RCD, 5, C_CB, u"Rating (Amps)", _HEAD)
    m(5, C_RUNS, 5, C_ECC, u"Cable Type / Size", _HEAD)
    m(5, C_KR, 5, C_KB, u"Connected Load", _HEAD)
    m(5, C_QR, 5, C_QB, u"Diversified Load", _HEAD)
    for col, text in ((C_RCD, u"RCD (mA)"), (C_CB, u"MCCB / ACB"),
                      (C_RUNS, u"No.of Cables"), (C_CORES, u"No.of Cores"),
                      (C_SIZE, u"Size mm2"), (C_ECC, u"ECC mm2"),
                      (C_KR, u"R-Ph (kw)"), (C_KY, u"Y-Ph (kw)"), (C_KB, u"B-Ph (kw)"),
                      (C_QR, u"R-Ph (kw)"), (C_QY, u"Y-Ph (kw)"), (C_QB, u"B-Ph (kw)")):
        ws.write(6, col, text, _HEAD)
    m(7, 1, 7, LAST_COL, u"Outgoing Ways:", _HEAD_LEFT)


def _way_row(ws, n, r, by_board, schedule_rows):
    """Write one way on row n."""
    ws.write(n, C_NO, r.label, _CELL)
    ws.write(n, C_DESC, r.name, _NAME)
    ws.write(n, C_PH, r.phases, _CELL)
    ws.write(n, C_RCD, RCD_TEXT, _CELL)
    ws.write(n, C_CB, r.breaker, _CELL)
    spec = r.cable
    if spec is not None and spec.size is not None:
        ws.write(n, C_TYPE, u"/".join(p for p in (spec.insulation, spec.armour, spec.sheath)
                                      if p), _CELL)
        ws.write(n, C_RUNS, int(spec.runs or 1), _CELL)
        ws.write(n, C_CORES, int(spec.cores or 4), _CELL)
        ws.write(n, C_SIZE, spec.size, _CELL)
        ws.write(n, C_ECC, _ecc(spec), _CELL)
    else:
        for col in (C_TYPE, C_RUNS, C_CORES, C_SIZE, C_ECC):
            ws.write(n, col, None, _CELL)
    for col in (C_KR, C_KY, C_KB, C_TCL, C_DF, C_QR, C_QY, C_QB, C_TDL):
        ws.write(n, col, None, _NUM)
    ws.write(n, C_DTYPE, r.kind if r.source else u"", _CELL)
    ws.write(n, C_REM, r.remark, _CELL)
    if not r.source or not r.phase_kw:
        return
    k, f = r.phase_kw, r.factor if r.factor is not None else 1.0
    tcl, tdl = sum(k), sum(k) * f
    if r.source == "link":
        c = _cells(by_board[r.target])
        for col, key, value in ((C_KR, "kr", k[0]), (C_KY, "ky", k[1]), (C_KB, "kb", k[2]),
                                (C_QR, "qr", k[0] * f), (C_QY, "qy", k[1] * f),
                                (C_QB, "qb", k[2] * f), (C_TCL, "tcl", tcl),
                                (C_TDL, "tdl", tdl), (C_DF, "df", f)):
            ws.write(n, col, Formula(c[key], value), _NUM)
        return
    if r.source == "lookup":
        table = u"%s!$A$%d:$F$%d" % (_quote(SCHEDULE_SHEET), schedule_rows[0], schedule_rows[1])
        name = _r(C_DESC, n)
        for col, index, value in ((C_TCL, 2, tcl), (C_TDL, 3, tdl), (C_KR, 4, k[0]),
                                  (C_KY, 5, k[1]), (C_KB, 6, k[2])):
            ws.write(n, col, Formula(u"VLOOKUP(%s,%s,%d,FALSE)" % (name, table, index), value),
                     _NUM)
        ws.write(n, C_DF, Formula(u"IF(%s>0,%s/%s,0)" % (_r(C_TCL, n), _r(C_TDL, n),
                                                         _r(C_TCL, n)), f), _NUM)
    else:
        for col, value in ((C_KR, k[0]), (C_KY, k[1]), (C_KB, k[2])):
            ws.write(n, col, round(value, 3), _NUM)
        ws.write(n, C_TCL, Formula(u"SUM(%s:%s)" % (_r(C_KR, n), _r(C_KB, n)), tcl), _NUM)
        ws.write(n, C_DF, round(f, 3), _NUM)
        ws.write(n, C_TDL, Formula(u"%s*%s" % (_r(C_TCL, n), _r(C_DF, n)), tdl), _NUM)
    for col, src, value in ((C_QR, C_KR, k[0] * f), (C_QY, C_KY, k[1] * f),
                            (C_QB, C_KB, k[2] * f)):
        ws.write(n, col, Formula(u"%s*%s" % (_r(src, n), _r(C_DF, n)), value), _NUM)


def _totals(ws, s):
    t = s.total_row
    first, last = FIRST_ROW, t - 1
    totals = s.totals()
    m = ws.merge
    m(t, 1, t + 3, 3, None, _TOTAL)
    m(t, 4, t, 6, None, _TOTAL)
    m(t, 7, t, 10, u"Total Connected Phase Loads", _TOTAL)
    for i, col in enumerate((C_KR, C_KY, C_KB)):
        ws.write(t, col, Formula(u"SUM(%s:%s)" % (_r(col, first), _r(col, last)), totals[i]),
                 _TOTAL_NUM)
    m(t, C_TCL, t, C_DTYPE, u"Total Diversified Phase Loads", _TOTAL)
    for i, col in enumerate((C_QR, C_QY, C_QB)):
        ws.write(t, col, Formula(u"SUM(%s:%s)" % (_r(col, first), _r(col, last)),
                                 totals[3 + i]), _TOTAL_NUM)
    ws.write(t, C_TDL, None, _TOTAL)
    ws.write(t, C_REM, None, _TOTAL)

    # area, load types and the board totals
    tcl, tdl = totals[6], totals[7]
    m(t + 1, 4, t + 1, 6, u"Gross Area (m²)", _TOTAL_LEFT)
    m(t + 1, 7, t + 1, 9, None, _TOTAL_NUM)
    m(t + 2, 4, t + 2, 6, u"Floor Area Diversified Load (W/m²)", _TOTAL_LEFT)
    area = _r(7, t + 1)
    m(t + 2, 7, t + 2, 9, Formula(u'IF(N(%s)>0,%s*1000/%s,"")' % (area, _r(C_REM, t + 2), area),
                                  u""), _TOTAL_NUM)
    m(t + 3, 4, t + 3, 9, None, _TOTAL)
    m(t + 1, 10, t + 1, 12, u"Diversified Load Types", _TOTAL_LEFT)
    m(t + 2, 10, t + 2, 12, u"Board Load (kW)", _TOTAL_LEFT)
    m(t + 3, 10, t + 3, 12, u"W/sq m", _TOTAL_LEFT)
    for i, (title, code) in enumerate(TYPES):
        col = 13 + i
        ws.write(t + 1, col, title, _TOTAL)
        value = sum(r.connected_kw * (r.factor if r.factor is not None else 1.0)
                    for r in s.rows if r.source and r.phase_kw and r.kind == code)
        ws.write(t + 2, col, Formula(u'SUMIF(%s:%s,"%s",%s:%s)' % (
            _r(C_DTYPE, first), _r(C_DTYPE, last), code, _r(C_TDL, first), _r(C_TDL, last)),
            value), _TOTAL_NUM)
        ws.write(t + 3, col, Formula(u'IF(N(%s)>0,%s*1000/%s,"")' % (
            u"$G$%d" % (t + 1), _r(col, t + 2), u"$G$%d" % (t + 1)), u""), _TOTAL_NUM)
    m(t + 1, 18, t + 1, 20, u"TOTAL CONNECTED LOAD (KW)=", _TOTAL_LEFT)
    ws.write(t + 1, C_REM, Formula(u"SUM(%s:%s)" % (_r(C_TCL, first), _r(C_TCL, last)), tcl),
             _TOTAL_NUM)
    m(t + 2, 18, t + 2, 20, u"LOAD AFTER DIVERSITY (KW)=", _TOTAL_LEFT)
    ws.write(t + 2, C_REM, Formula(u"SUM(%s:%s)" % (_r(C_TDL, first), _r(C_TDL, last)), tdl),
             _TOTAL_NUM)
    m(t + 3, 18, t + 3, 20, u"OVERALL DIVERSITY", _TOTAL_LEFT)
    ws.write(t + 3, C_REM, Formula(u"IF(%s>0,%s/%s,0)" % (
        _r(C_REM, t + 1), _r(C_REM, t + 2), _r(C_REM, t + 1)), tdl / tcl if tcl else 0),
        _PERCENT)


def _board_sheet(wb, s, by_board, schedule_rows, project):
    ws = wb.add_sheet(s.name)
    for col, width in WIDTHS.items():
        ws.widths[col] = width
    ws.heights.update({1: 15.0, 2: 15.0, 3: 18.0, 4: 18.0, 5: 18.0, 6: 40.0, 7: 20.0})
    ws.paper = 9                       # A4
    ws.landscape = True
    ws.print_rows = (5, 6)
    ws.freeze = (FIRST_ROW, 3)
    _header(ws, s, project)
    if not s.rows:
        ws.merge(FIRST_ROW, 1, FIRST_ROW, LAST_COL, u"No outgoing ways", _CELL)
    for i, r in enumerate(s.rows):
        n = FIRST_ROW + i
        ws.heights[n] = 15.0
        _way_row(ws, n, r, by_board, schedule_rows)
    _totals(ws, s)
    ws.heights[s.total_row] = 26.0
    return ws


def _schedule_sheet(wb, dbs):
    """The Revit panel loads the DB rows look up (as the office schedule
    export: Panel Name, Total Connected, Total Demand, Phase A / B / C)."""
    ws = wb.add_sheet(SCHEDULE_SHEET)
    ws.landscape = False
    for col, width in ((1, 24.0), (2, 16.0), (3, 16.0), (4, 14.0), (5, 14.0), (6, 14.0)):
        ws.widths[col] = width
    ws.merge(1, 1, 1, 6, u"Electrical Equipment Schedule (kW)", _HEAD_LEFT)
    for col, text in enumerate((u"Panel Name", u"Total Connected Apparent Power",
                                u"Total Demand Apparent Power", u"Apparent Power Phase A",
                                u"Apparent Power Phase B", u"Apparent Power Phase C"), 1):
        ws.write(3, col, text, _HEAD)
    ws.heights[3] = 40.0
    names = sorted(dbs, key=natural_key)
    first = 5
    for i, name in enumerate(names):
        cl, dl, phases = dbs[name]
        n = first + i
        ws.write(n, 1, name, _NAME)
        for col, value in ((2, cl), (3, dl), (4, phases[0]), (5, phases[1]), (6, phases[2])):
            ws.write(n, col, round(value, 3), _NUM)
    return first, max(first, first + len(names) - 1)


def build(editor, project=None):
    """Workbook of the load schedules. project: dict of header texts
    (project, location, contractor, electrical, document)."""
    project = project or {}
    sheets, by_board, dbs = collect(editor)
    wb = Workbook()
    names = sorted(dbs, key=natural_key)
    schedule_rows = (5, max(5, 5 + len(names) - 1))
    for s in sheets:
        _board_sheet(wb, s, by_board, schedule_rows, project)
    _schedule_sheet(wb, dbs)
    return wb, sheets


def summary(sheets):
    """Message shown after saving."""
    lines = [u"%d board sheet(s):" % len(sheets)]
    for s in sheets:
        t = s.totals()
        if t[6]:
            lines.append(u"- %s: %s kW connected, %s kW after diversity (%d ways)" % (
                s.title, trim_number(t[6], 1), trim_number(t[7], 1), len(s.rows)))
        else:
            lines.append(u"- %s: no load found (%d ways)" % (s.title, len(s.rows)))
    return u"\n".join(lines)
