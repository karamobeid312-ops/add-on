# -*- coding: utf-8 -*-
"""What the Power Studio window shows besides the ways grid: board status
and totals, the voltage drop table of every cable, and the settings form
(SLD drawing + voltage drop + report). Kept free of Revit and WPF, so it
runs under pytest.

States are 'ok' (green), 'warn' (amber), 'bad' (red) or '' (nothing to say).
"""
from __future__ import division

from sld import style
from sld.model import is_sub_main, way_positions
from vdrop import calc
from vdrop import settings as vd_settings
from vdrop.parse import format_number

OK, WARN, BAD, NONE = "ok", "warn", "bad", ""


# ---------------------------------------------------------------- boards

def _kw(value):
    return u"%s kW" % format_number(value, 1) if value is not None else u"–"


def board_state(editor, board_id):
    """Red when a way is over the V.D limit or has a wrong value, amber for
    a board warning (too many ways, spares), else green."""
    b = editor.board(board_id)
    ways = editor.ways(board_id)
    if any(w.vd_over or w.errors for w in ways):
        return BAD
    if b.warnings or (is_sub_main(b.board) and
                      way_positions(b.board.ways, b.board.phases) > style.MAX_WAYS):
        return WARN
    return OK


def _incomer_text(values):
    at, af, device = values.get("incomer_at"), values.get("incomer_af"), \
        values.get("incomer_device")
    if not at:
        return u"–"
    text = u"%s A" % at
    if af:
        text += u" / %s AF" % af
    return text + (u" %s" % device if device else u"")


def worst_vd(editor, board_id):
    """(text, state) of the highest V.D % among the board's ways."""
    best, over = None, False
    for w in editor.ways(board_id):
        try:
            value = float(w.vd)
        except (TypeError, ValueError):
            continue
        if best is None or value > best:
            best = value
        over = over or w.vd_over
    if best is None:
        return u"–", NONE
    return u"%.2f %%" % best, BAD if over else OK


def board_summary(editor, board_id):
    """The four tiles above the ways grid."""
    b = editor.board(board_id)
    totals = b.board.load_totals()
    connected = totals[0] if totals else None
    demand = totals[2] if totals else None
    vd_text, vd_state = worst_vd(editor, board_id)
    ways = [w for w in editor.ways(board_id)]
    return {
        "connected": _kw(connected),
        "demand": _kw(demand),
        "incomer": _incomer_text(b.values),
        "worst_vd": vd_text,
        "worst_state": vd_state,
        "ways": u"%d ways, %d spare" % (len(ways), sum(1 for w in ways if w.spare)),
        "state": board_state(editor, board_id),
    }


def way_state(way):
    """State of a way's V.D chip."""
    if way.vd_over:
        return BAD
    if way.vd in ("", None):
        return NONE
    if way.vd == "n/a":
        return WARN
    return OK


# ---------------------------------------------------------------- voltage drop

VD_COLUMNS = (
    # (data column, header, width)
    ("number", "S.N", 50), ("source", "From", 110), ("target", "To", 150),
    ("length", "Length m", 70), ("cable", "Cable", 110), ("breaker", "In A", 55),
    ("current", "Ib A", 60), ("vd", "V.D %", 60), ("total", "Total V.D %", 85),
    ("limit", "Max %", 55), ("status", "Result", 95), ("remarks", "Remarks", 380),
)
STATUS_TEXT = {"OK": "OK", "FAIL": "Failed", "INCOMPLETE": "Incomplete"}
STATUS_STATE = {"OK": OK, "FAIL": BAD, "INCOMPLETE": WARN}


def vd_rows(editor, problems_only=False, search=u""):
    """Rows of the Voltage drop tab, in report order."""
    if editor.result is None:
        return []
    search = (search or u"").strip().upper()
    out = []
    for r in editor.result.rows():
        status = r.status()
        if problems_only and status == "OK":
            continue
        f = r.feeder
        if search and search not in (u"%s %s" % (f.source, f.target)).upper():
            continue
        out.append({
            "key": u"%s" % f.id,
            "number": u"%s" % r.number,
            "source": f.source, "target": f.target,
            "length": format_number(f.length, 1),
            "cable": r.cable_text(),
            "breaker": format_number(f.breaker, 0),
            "current": format_number(r.current, 1),
            "vd": format_number(r.vd_percent),
            "total": format_number(r.total_percent),
            "limit": format_number(r.limit),
            "status": STATUS_TEXT.get(status, status),
            "state": STATUS_STATE.get(status, NONE),
            "remarks": r.remarks(),
        })
    return out


def vd_summary(editor):
    """Tiles of the Voltage drop tab and the 'to fix' lines."""
    from vdrop import report
    if editor.result is None:
        return {"cables": u"–", "ok": u"–", "failed": u"–", "incomplete": u"–",
                "worst": u"–", "worst_where": u"", "worst_state": NONE,
                "fixes": [u"The voltage drop could not be read from the model."],
                "state": NONE}
    rows, failed, incomplete = report.counts(editor.result)
    top = report.worst(editor.result)
    fixes = report.to_fix(editor.result) + list(editor.result.warnings)
    return {
        "cables": u"%d" % len(rows),
        "ok": u"%d" % (len(rows) - len(failed) - len(incomplete)),
        "failed": u"%d" % len(failed),
        "incomplete": u"%d" % len(incomplete),
        "worst": u"%s %%" % format_number(top.total_percent) if top else u"–",
        "worst_where": (u"%s → %s" % (top.feeder.source, top.feeder.target)) if top else u"",
        "worst_state": (BAD if top.vd_ok is False else OK) if top else NONE,
        "fixes": fixes,
        "state": BAD if failed else WARN if incomplete else OK,
    }


def vd_tab_header(editor):
    """Text on the Voltage drop tab, with its state."""
    s = vd_summary(editor)
    if editor.result is None:
        return u"Voltage drop", NONE
    if s["failed"] not in (u"0", u"–"):
        return u"Voltage drop  ·  %s failed" % s["failed"], BAD
    return u"Voltage drop", s["state"]


# ---------------------------------------------------------------- settings

# (group, key, label, unit, kind) kind: text, number, choice, check
SLD = "sld"
VD = "vd"
SETTINGS = (
    (SLD, "utility", "Utility / supply authority (FROM ...)", "", "text"),
    (SLD, "substation_label", "Bottom band label", "", "text"),
    (SLD, "show_ratings", "Print breaker rating and cable along each way", "", "check"),
    (SLD, "numbering", "Way numbering", "", "choice"),
    (VD, "voltage_3ph", "Three phase voltage", "V", "number"),
    (VD, "voltage_1ph", "Single phase voltage", "V", "number"),
    (VD, "voltage_source", "Voltage used", "", "choice"),
    (VD, "power_factor", "Power factor", "", "number"),
    (VD, "pf_source", "Power factor used", "", "choice"),
    (VD, "load_basis", "Load for the current", "", "choice"),
    (VD, "limit_transformer", "Max V.D transformer to main board", "%", "number"),
    (VD, "limit_total", "Max V.D to the final load", "%", "number"),
    (VD, "insulation", "Cable (when VD Cable doesn't say)", "", "choice"),
    (VD, "installation", "Installation (when VD Installation is empty)", "", "choice"),
    (VD, "air_temperature", u"Air temperature, cable tray", u"°C", "choice"),
    (VD, "ground_temperature", u"Ground temperature, ground and duct bank", u"°C", "choice"),
    (VD, "depth", "Laying depth, ground and duct bank (0 = not applied)", "mm", "choice"),
    (VD, "soil_resistivity", "Soil thermal resistivity (0 = not applied)", "K.m/W", "choice"),
    (VD, "grouping", "Grouping factor Cg", "", "number"),
    (VD, "company", "Report: company name", "", "text"),
    (VD, "revision", "Report: revision", "", "text"),
    (VD, "issue", "Report: issue (empty = Revit project status)", "", "text"),
)
# settings that change what is read from Revit: the window reads the model again
RELOAD_KEYS = ("numbering", "voltage_source", "pf_source", "power_factor", "load_basis")

NUMBERING = (("slots", "Ways numbered in order (1, 2, R9, Y9, B9)"),
             ("revit", "Revit circuit numbers"))
_LABELS = {
    "numbering": dict(NUMBERING),
    "voltage_source": {"settings": "The voltages above (as the office sheet)",
                       "model": "Each panel's distribution system in Revit"},
    "pf_source": {"settings": "The power factor above on every cable (as the office sheet)",
                  "model": "The loads in Revit (the one above when they have none)"},
    "load_basis": {calc.MDL: "MDL - demand load of the fed board",
                   calc.TCL: "TCL - connected load"},
}


def choices(key):
    """[(value, text shown)] of a 'choice' setting."""
    if key == "numbering":
        values = [k for k, _ in NUMBERING]
    else:
        values = list(vd_settings.CHOICES[key])
    labels = _LABELS.get(key, {})
    return [(v, labels.get(v) or (format_number(v, 3) if isinstance(v, float) else u"%s" % v))
            for v in values]


def shown(key, value):
    """A setting's value as the form shows it."""
    kind = next(k for _, name, _, _, k in SETTINGS if name == key)
    if kind == "check":
        return bool(value)
    if kind == "choice":
        return next((text for v, text in choices(key) if v == value), u"%s" % value)
    if isinstance(value, float):
        return format_number(value, 3)
    return u"%s" % (value if value is not None else u"")


def read(key, shown_value):
    """The setting's value from what the form holds; raises ValueError."""
    kind = next(k for _, name, _, _, k in SETTINGS if name == key)
    if kind == "check":
        return bool(shown_value)
    if kind == "choice":
        for v, text in choices(key):
            if text == shown_value or u"%s" % v == u"%s" % shown_value:
                return v
        raise ValueError(u"'%s' is not one of the choices" % shown_value)
    text = (u"%s" % (shown_value or u"")).strip()
    if key in ("utility", "substation_label"):
        return text.upper()
    if group_of(key) == SLD:
        return text
    if kind == "number":
        text = text.replace(",", ".")
    value = vd_settings.valid(key, text)
    if value is None:
        raise ValueError(u"'%s' is not valid" % text)
    return value


def group_of(key):
    return next(g for g, name, _, _, _ in SETTINGS if name == key)


def apply_settings(sld_values, vd_values, form):
    """New (sld values, vd values, errors) from the form {key: shown value}."""
    sld_values, vd_values, errors = dict(sld_values), dict(vd_values), []
    for group, key, label, _, _ in SETTINGS:
        if key not in form:
            continue
        try:
            value = read(key, form[key])
        except ValueError as error:
            errors.append(u"%s: %s" % (label, error))
            continue
        if key in ("utility", "substation_label") and not value:
            continue
        (sld_values if group == SLD else vd_values)[key] = value
    return sld_values, vd_values, errors


def needs_reload(old_sld, old_vd, new_sld, new_vd):
    return any((old_sld.get(k), old_vd.get(k)) != (new_sld.get(k), new_vd.get(k))
               for k in RELOAD_KEYS)


def model_text(project, boards, ways):
    name = project or u"This model"
    return u"%s\n%d boards · %d ways" % (name, boards, ways)

