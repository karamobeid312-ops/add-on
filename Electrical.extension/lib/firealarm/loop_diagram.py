# -*- coding: utf-8 -*-
"""Fire alarm loop diagram from the device addresses (pure Python, no
Revit), in the style of the office sample: the control panel at the
bottom and, for every loop, a START line up from the panel to a row of
all its devices in address order, each with its address under it, and an
END line back down to the panel.

    END START END START
     |    |    |    |      row 2 <- ... <- L1/SD-39 (a long loop comes back
     |    |    |    +----- row 1 -> L1/MCP-01 ...      on a second row)
     |    |    +----------------------------------+
     |    +-- L2/SB-01 ... L2/SB-13 --------------+   (one row: back over it)
    [ FIRE ALARM CONTROL PANEL ]

The first loop takes the lowest rows and the lines nearest the rows, so
no lines cross. Loops of sirens and flashers only (SB, B, BS, ST, HS) are
drawn in magenta, the others in red.

All sizes in millimetres on paper; the diagram is drawn 1:1. Keep
compatible with IronPython 2.7.
"""
from __future__ import division

from sld.geometry import BOTTOM, CENTER, LEFT, MIDDLE, RIGHT, TOP, VERTICAL, Drawing, line_length
from firealarm.addresses import parse_address
from firealarm.riser_symbols import SYMBOLS as ALL_SYMBOLS, Symbol, _text_box, symbol

DETECTION_STYLE = "FA Riser Wiring"         # red, shared with the floor riser
SOUNDER_STYLE = "FA Riser Sounder Wiring"   # magenta
SYMBOL_STYLE = "FA Riser Symbols"
RED = (255, 0, 0)
MAGENTA = (255, 0, 255)
SYMBOL_RED = (230, 0, 80)

TEXT_ADDRESS = 1.5          # L1/SD-01 under a device
TEXT_LINE = 1.8             # START / END
TEXT_CABLE = 1.8            # SLC LOOP, 2X1.5 mm2 CU...
TEXT_PANEL = 2.0
TEXT_NOTE = 1.8             # INTERFACE WITH BMS ...

ADDRESS_GAP = 3.2           # loop line -> top of the address text
PITCH_MIN = 16.0            # between devices along a row
PITCH_PAD = 4.0             # address width + this, at least
ROW_PITCH = 14.0            # between the rows of a loop and between loops
LINE_GAP = 8.0              # between the vertical START / END lines
FIRST_LINE = 20.0           # the nearest vertical line -> first device
RETURN_ABOVE = 7.0          # a loop ending on the right comes back this far over its row
RIGHT_PAD = 10.0            # last device -> where the line turns
PANEL_GAP = 45.0            # panel top -> lowest row (room for the cable notes)
CABLE_STEP = 9.0            # between the cable notes
PANEL_ROW = 6.0             # height of a line in the panel box
PANEL_PAD = 10.0            # panel box beyond the outer lines

SIRENS_AND_FLASHERS = frozenset(["SB", "B", "BS", "ST", "HS", "BELL", "BELLS", "STC", "STW"])

DEFAULT_CABLE = "SLC LOOP, 2X1.5 mm2 CU, FIRE RATED CABLE"
DEFAULT_PANEL_LINES = ("IP NETWORK INTERFACE MODULE; BACNET GATEWAY; "
                       "POWER UNIT WITH BACKUP BATTERY FOR 24 HRS")
DEFAULT_PER_ROW = 25

# address type -> riser symbol, when the device's own symbol is not known
_BY_ADDRESS = {
    "SD": "SD", "HD": "HD", "DD": "DD", "TX": "BTX", "RX": "BRX", "MCP": "MCP",
    "B": "BELL", "SB": "BELLS", "BS": "BELLS", "ST": "STW", "HS": "HS", "J": "J",
    "FS": "WFS", "TS": "TS", "CM": "CM", "MM": "MM", "ZM": "ZM", "LHD": "LHD",
    "HSSD": "HSSD", "EOL": "EOL", "ISO": "ISO", "FARP": "FARP",
}
_KNOWN = set(s.code for s in ALL_SYMBOLS)


class Device(object):
    def __init__(self, address, code=None, element_id=None):
        parsed = parse_address(address)
        self.address = (address or "").strip().upper()
        self.loop, self.kind, self.number = parsed if parsed else (None, None, None)
        self.code = code            # riser symbol code of the family, for unknown address types
        self.element_id = element_id

    def symbol(self):
        # the type in the address wins; the family's own symbol for types like FD, HY
        code = _BY_ADDRESS.get(self.kind) or (self.code if self.code in _KNOWN else None)
        if code:
            return symbol(code)
        return Symbol(self.kind, self.kind, _text_box(self.kind or "?"))


class Loop(object):
    def __init__(self, number, devices):
        self.number = number
        self.devices = sorted(devices, key=lambda d: d.number)
        self.sounder = all(d.kind in SIRENS_AND_FLASHERS for d in devices)
        self.rows = []              # [[Device]] in drawing order
        self.duplicates = []        # addresses used twice


class LoopDiagram(object):
    def __init__(self, drawing, loops, unaddressed, warnings):
        self.drawing = drawing
        self.loops = loops
        self.unaddressed = unaddressed      # [(element id, comments text)]
        self.warnings = warnings


def group_loops(devices):
    """([Loop] by number, [Device] without an address)."""
    by_loop, bad = {}, []
    for d in devices:
        if d.loop is None:
            bad.append(d)
        else:
            by_loop.setdefault(d.loop, []).append(d)
    loops = []
    for number in sorted(by_loop):
        loop = Loop(number, by_loop[number])
        seen = set()
        for d in loop.devices:
            if d.number in seen:
                loop.duplicates.append(d.address)
            seen.add(d.number)
        loops.append(loop)
    return loops, bad


def _split(items, per_row):
    per_row = max(1, int(per_row))
    return [items[k:k + per_row] for k in range(0, len(items), per_row)] or [[]]


def loop_diagram(devices, panel_name="", panel_lines=DEFAULT_PANEL_LINES, cable=DEFAULT_CABLE,
                 per_row=DEFAULT_PER_ROW):
    """devices: [Device]. Returns a LoopDiagram."""
    d = Drawing()
    d.styles[DETECTION_STYLE] = RED
    d.styles[SOUNDER_STYLE] = MAGENTA
    d.styles[SYMBOL_STYLE] = SYMBOL_RED
    warnings = []

    loops, bad = group_loops(devices)
    loops = [l for l in loops if l.devices]
    for loop in loops:
        loop.rows = _split(loop.devices, per_row)
        if loop.duplicates:
            warnings.append(u"L%d: %s used twice" % (loop.number, ", ".join(loop.duplicates)))

    # vertical lines: loop k has START at -(2k+1) and END at -(2k+2) line gaps
    # left of the lines' right edge; the first loop is nearest the rows
    n = len(loops)
    lines_right = 0.0
    start_x = dict((l.number, lines_right - (2 * k) * LINE_GAP) for k, l in enumerate(loops))
    end_x = dict((l.number, lines_right - (2 * k + 1) * LINE_GAP) for k, l in enumerate(loops))
    lines_left = lines_right - max(2 * n - 1, 1) * LINE_GAP

    widest = max([len(r) for l in loops for r in l.rows] + [1])
    labels = [dv.address for l in loops for dv in l.devices]
    pitch = max([PITCH_MIN] + [line_length(t, TEXT_ADDRESS) + PITCH_PAD for t in labels])
    first_x = lines_right + FIRST_LINE
    last_x = first_x + (widest - 1) * pitch
    turn_x = last_x + RIGHT_PAD

    # rows bottom up
    panel_top = 0.0
    y = panel_top + PANEL_GAP
    row_y = {}
    for loop in loops:
        for k in range(len(loop.rows)):
            row_y[(loop.number, k)] = y
            y += ROW_PITCH
        if len(loop.rows) % 2 == 1:         # ends on the right: room for the return line
            y += RETURN_ABOVE
        y += ROW_PITCH * 0.4

    for loop in loops:
        style = SOUNDER_STYLE if loop.sounder else DETECTION_STYLE
        xs, xe = start_x[loop.number], end_x[loop.number]
        y0 = row_y[(loop.number, 0)]
        d.line(xs, panel_top, xs, y0, style)                       # START up
        at = xs
        for k, row in enumerate(loop.rows):
            yk = row_y[(loop.number, k)]
            forward = k % 2 == 0
            if k:                                                   # up to the next row
                d.line(turn_x if not forward else first_x - pitch / 2, row_y[(loop.number, k - 1)],
                       turn_x if not forward else first_x - pitch / 2, yk, style)
                at = turn_x if not forward else first_x - pitch / 2
            for i, dev in enumerate(row):       # a row coming back fills from the right
                x = first_x + (i if forward else widest - 1 - i) * pitch
                half = dev.symbol().draw(d, x, yk, SYMBOL_STYLE)
                near, far = (x - half, x + half) if forward else (x + half, x - half)
                d.line(at, yk, near, yk, style)
                at = far
                d.text(x, yk - ADDRESS_GAP, dev.address, TEXT_ADDRESS, align=CENTER, valign=TOP)
            last = k == len(loop.rows) - 1
            if not last:
                d.line(at, yk, turn_x if forward else first_x - pitch / 2, yk, style)
            elif forward:                                           # back over the row
                y_ret = yk + RETURN_ABOVE
                d.polyline([(at, yk), (turn_x, yk), (turn_x, y_ret), (xe, y_ret),
                            (xe, panel_top)], style)
            else:
                d.polyline([(at, yk), (xe, yk), (xe, panel_top)], style)
        # START / END up the lines, under the first row
        for x, text in ((xs, "START"), (xe, "END")):
            d.text(x - 0.6, panel_top + PANEL_GAP * 0.55, text, TEXT_LINE, align=CENTER,
                   valign=BOTTOM, rotation=VERTICAL)

    # cable notes: one per loop, from its lines out to the left
    parts = [p.strip() for p in (cable or "").split(",") if p.strip()]
    first = ", ".join(parts[:-1]) + "," if len(parts) > 1 else (parts[0] if parts else "")
    second = parts[-1] if len(parts) > 1 else ""
    note_w = max(line_length(u"L%d %s" % (max([l.number for l in loops] or [1]), first),
                             TEXT_CABLE), line_length(second, TEXT_CABLE)) + 2.0
    note_x = lines_left - PANEL_PAD - 4.0 - note_w        # where the note text starts
    for k, loop in enumerate(loops):
        yc = panel_top + 8.0 + (k % 4) * CABLE_STEP
        xs, xe = start_x[loop.number], end_x[loop.number]
        for x in (xs, xe):
            d.circle(x, yc, 1.0)
        d.line(xe - 1.0, yc, note_x, yc)
        d.text(note_x, yc + 0.8, u"L%d %s" % (loop.number, first), TEXT_CABLE,
               align=LEFT, valign=BOTTOM)
        if second:
            d.text(note_x, yc - 0.8, second, TEXT_CABLE, align=LEFT, valign=TOP)

    # the panel
    rows = [p.strip() for p in (panel_lines or "").replace("\n", ";").split(";") if p.strip()]
    title = u"FIRE ALARM CONTROL PANEL" + (u"\n%s" % panel_name if panel_name else "")
    title_h = PANEL_ROW * (2.2 if panel_name else 1.4)
    p_left = lines_left - PANEL_PAD
    p_right = lines_right + PANEL_PAD + 30.0
    widest_text = max([line_length(t, TEXT_PANEL) for t in rows + title.split("\n")] + [0])
    p_right = max(p_right, p_left + widest_text + 8.0)
    y_top = panel_top
    y = y_top - title_h
    d.rect(p_left, y, p_right, y_top)
    d.text(p_left + 3.0, y_top - 1.5, title, TEXT_PANEL, align=LEFT, valign=TOP)
    row_mid = {}
    for k, text in enumerate(rows):
        d.rect(p_left, y - PANEL_ROW, p_right, y)
        d.text((p_left + p_right) / 2, y - PANEL_ROW / 2, text, TEXT_PANEL, align=CENTER,
               valign=MIDDLE)
        row_mid[k] = y - PANEL_ROW / 2
        y -= PANEL_ROW
    bottom = y
    # BMS and mains power arrows on the left
    arrow_x = p_left - 40.0
    y_bms = row_mid.get(1, row_mid.get(0, (y_top + bottom) / 2))
    d.line(p_left, y_bms, arrow_x, y_bms)
    d.polyline([(arrow_x + 2.0, y_bms + 0.8), (arrow_x, y_bms), (arrow_x + 2.0, y_bms - 0.8)])
    d.text(arrow_x - 2.0, y_bms, "INTERFACE WITH BMS", TEXT_NOTE, align=RIGHT, valign=MIDDLE)
    y_pwr = bottom + PANEL_ROW / 2 if rows else bottom + 2.0
    d.line(arrow_x, y_pwr, p_left, y_pwr)
    d.polyline([(p_left - 2.0, y_pwr + 0.8), (p_left, y_pwr), (p_left - 2.0, y_pwr - 0.8)])
    d.text(arrow_x - 2.0, y_pwr, "230V AC MAIN POWER", TEXT_NOTE, align=RIGHT, valign=MIDDLE)

    return LoopDiagram(d, loops, bad, warnings)
