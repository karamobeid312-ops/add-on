# -*- coding: utf-8 -*-
"""Fire alarm loop diagram from the device addresses (pure Python, no
Revit), drawn like the office drawing SUBSTATION2 FIRE ALARM SCHEMATIC:
the control panel at the bottom and, for every loop, a START line up from
the panel to a row of its devices in address order, each with its address
under it, and an END line back down to the panel.

    END START END START
     |    |    |    |          row 2 <- ... <- L1/SD-39   (a long loop comes
     |    |    |    +-- row 1 -> L1/MCP-01 ... L1/MM-20 -+  back on a second
     |    |    +-------------------------------------- row 2  row)
     |    +-- L1/SB-01 ... L1/SB-13 --+    sounders of the loop (SB...): their
     +--------------------------------+    own magenta line above, own numbers
    [ SUB MAIN FIRE ALARM CONTROL PANEL ]

Each loop's sounders (L1/SB-01...) are a circuit of their own, drawn in
magenta above the loop's detection devices. The first circuit takes the
lowest rows and the lines nearest the rows, so no lines cross. Detection
devices are joined by red dash-dot lines, as in the office drawing.

All sizes in millimetres on paper; the office drawing is 1:100, so the
diagram is drawn in Revit at 1:100 (DRAW_SCALE) to keep its small dashes.
Keep compatible with IronPython 2.7.
"""
from __future__ import division

import math

from sld.geometry import BOTTOM, CENTER, LEFT, MIDDLE, TOP, VERTICAL, Drawing, line_length, wrap
from firealarm.addresses import parse_address
from firealarm.loop_symbols import LOOP_SYMBOLS, patterned_line
from firealarm.riser_symbols import SYMBOLS as ALL_SYMBOLS, Symbol, _text_box, symbol

DETECTION_STYLE = "FA Riser Wiring"         # red: loop lines, panel
SOUNDER_STYLE = "FA Riser Sounder Wiring"   # magenta
SYMBOL_STYLE = "FA Riser Symbols"           # red
BMS_STYLE = "FA Riser BMS"                  # green
POWER_STYLE = "FA Riser Power"              # blue
NETWORK_STYLE = "FA Riser Network"          # magenta box
RED = (255, 0, 0)
MAGENTA = (255, 0, 255)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)

DRAW_SCALE = 100            # Revit view scale, as the office drawing

TEXT_ADDRESS = 1.5          # L1/SD-01 under a device
TEXT_LINE = 1.88            # START / END
TEXT_CABLE = 1.88           # SLC LOOP,2X1.5 mm2 CU, / FIRE RATED CABLE
TEXT_PANEL = 1.88
TEXT_NOTE = 1.8             # INTERFACE WITH BMS ...
TEXT_LINK = 2.25            # FROM ... / TO ... on the panel's right

# measured on the office drawing (its units / 100)
ADDRESS_GAP = 1.2           # symbol bottom -> top of the address text
PITCH_MIN = 12.0            # between devices along a row
PITCH_PAD = 1.0             # address width + this, at least
ROW_PITCH = 11.86           # between the rows of a circuit
CIRCUIT_GAP = 10.3          # last row of a circuit -> first row of the next
RETURN_ABOVE = 11.86        # a circuit ending on the right comes back this far over its row
LINE_GAP = 7.5              # START -> END line of a circuit
CIRCUIT_LINES_GAP = 9.4     # END line -> START line of the next circuit
FIRST_DEVICE = 34.65        # innermost START line -> first device
TURN_PAD = 7.6              # last device's side -> where the line turns up
PANEL_GAP = 46.06           # panel top -> first row
LABEL_Y = 33.4              # START / END texts, centred this far above the panel
NOTE_LOW, NOTE_HIGH = 11.5, 25.0    # cable notes: on the END line, on the START line
NOTE_STEP = 27.0            # more circuits on one side: the next pair this much higher
NOTE_TEXT = 7.1             # innermost START line -> note text, notes to the right
NOTE_LEFT = 39.4            # outer END line -> end of the notes to the left
ELLIPSE_W, ELLIPSE_H = 4.5, 1.88
PANEL_RIGHT = 7.07          # innermost START line -> panel right side
PANEL_LEFT = 8.61           # outer END line -> panel left side
PANEL_WIDTH = 40.07
PANEL_TEXT_IN = 3.8
ARROW_LONG = 26.5           # BMS / power arrows
ARROW_HEAD = 1.05
NOTE_X = 50.0               # panel left -> BMS / power texts
LINK_LONG = 26.7            # FROM ... / TO ... lines on the right

SIRENS_AND_FLASHERS = frozenset(["SB", "B", "BS", "ST", "HS", "BELL", "BELLS", "STC", "STW"])

DEFAULT_CABLE = "SLC LOOP,2X1.5 mm2 CU, FIRE RATED CABLE"
DEFAULT_PANEL_LINES = ("IP NETWORK INTERFACE MODULE; BACNET GATEWAY; "
                       "POWER UNIT WITH BACKUP BATTERY FOR 24 HRS")
DEFAULT_NETWORK = "Multi Service Network; (Operational Communication Network)"
DEFAULT_LINKS = ""
DEFAULT_PER_ROW = 20

# address type -> office loop symbol
_LOOP_BY_ADDRESS = {"SD": "SD", "HD": "HD", "FD": "FD", "HY": "HY", "MCP": "MCP", "MM": "MM",
                    "SB": "SB", "B": "SB", "BS": "SBW"}
# address type -> riser symbol, for the types the office drawing has no symbol of
_BY_ADDRESS = {
    "DD": "DD", "TX": "BTX", "RX": "BRX", "ST": "STW", "HS": "HS", "J": "J",
    "FS": "WFS", "TS": "TS", "CM": "CM", "ZM": "ZM", "LHD": "LHD",
    "HSSD": "HSSD", "EOL": "EOL", "ISO": "ISO", "FARP": "FARP",
}
_KNOWN = set(s.code for s in ALL_SYMBOLS)
# a sounder whose family or type says one of these is the W/P sounder with beacon
_WEATHERPROOF = ("W/P", "WP", "WEATHER", "STROBE", "BEACON", "FLASH")


class _RiserSymbol(object):
    """A floor riser symbol, where the office loop drawing has none."""

    bottom = 1.5

    def __init__(self, sym):
        self.code = sym.code
        self.sym = sym

    def draw(self, d, x, y, style):
        return self.sym.draw(d, x, y, style)


class Device(object):
    def __init__(self, address, code=None, element_id=None, name=""):
        parsed = parse_address(address)
        self.address = (address or "").strip().upper()
        self.loop, self.kind, self.number = parsed if parsed else (None, None, None)
        self.code = code            # riser symbol code of the family, for unknown address types
        self.element_id = element_id
        self.name = (name or "").upper()    # family : type

    def symbol(self):
        loop_code = _LOOP_BY_ADDRESS.get(self.kind)
        if loop_code == "SB" and (self.code in ("BELLS", "HS", "STW", "STC") or
                                  any(w in self.name for w in _WEATHERPROOF)):
            loop_code = "SBW"
        if loop_code:
            return LOOP_SYMBOLS[loop_code]
        code = _BY_ADDRESS.get(self.kind) or (self.code if self.code in _KNOWN else None)
        if code:
            return _RiserSymbol(symbol(code))
        return _RiserSymbol(Symbol(self.kind, self.kind, _text_box(self.kind or "?")))


class Loop(object):
    """One circuit: a loop's detection devices, or its sounders."""

    def __init__(self, number, devices, sounder=None):
        self.number = number
        self.devices = sorted(devices, key=lambda d: d.number)
        self.sounder = (all(d.kind in SIRENS_AND_FLASHERS for d in devices)
                        if sounder is None else sounder)
        self.rows = []              # [[Device]] in drawing order
        self.duplicates = []        # addresses used twice


class LoopDiagram(object):
    def __init__(self, drawing, loops, unaddressed, warnings):
        self.drawing = drawing
        self.loops = loops
        self.unaddressed = unaddressed      # [Device] without an address
        self.warnings = warnings


def group_loops(devices):
    """([Loop] by loop number, detection before sounders; [Device] without
    an address)."""
    by_loop, bad = {}, []
    for d in devices:
        if d.loop is None:
            bad.append(d)
        else:
            by_loop.setdefault(d.loop, []).append(d)
    loops = []
    for number in sorted(by_loop):
        items = by_loop[number]
        detection = [d for d in items if d.kind not in SIRENS_AND_FLASHERS]
        sounders = [d for d in items if d.kind in SIRENS_AND_FLASHERS]
        for part, sounder in ((detection, False), (sounders, True)):
            if not part:
                continue
            loop = Loop(number, part, sounder)
            seen = set()
            for d in loop.devices:
                if d.number in seen:
                    loop.duplicates.append(d.address)
                seen.add(d.number)
            loops.append(loop)
    return loops, bad


def panel_title(panel_name):
    name = (panel_name or "").upper()
    if name.startswith("SFACP") or "SUB" in name:
        return "SUB MAIN FIRE ALARM CONTROL PANEL"
    if name.startswith("MFACP") or "MAIN" in name:
        return "MAIN FIRE ALARM CONTROL PANEL"
    return "FIRE ALARM CONTROL PANEL"


def _split(items, per_row):
    per_row = max(1, int(per_row))
    return [items[k:k + per_row] for k in range(0, len(items), per_row)] or [[]]


def _parts(text):
    return [p.strip() for p in (text or "").replace("\n", ";").split(";") if p.strip()]


def _ellipse(d, cx, cy, w, h, style=None, n=24):
    d.polyline([(cx + w / 2 * math.cos(2 * math.pi * k / n),
                 cy + h / 2 * math.sin(2 * math.pi * k / n)) for k in range(n + 1)], style)


def _arrow(d, x, y, towards, style, half=0.37, rows=7):
    """Filled arrowhead, tip at x, y, pointing left (-1) or right (+1)."""
    base = x - towards * ARROW_HEAD
    for i in range(rows):
        yy = y - half + 2 * half * i / (rows - 1)
        d.line(base, yy, base + towards * ARROW_HEAD * (1 - abs(yy - y) / half), yy, style)
    d.polyline([(base, y - half), (x, y), (base, y + half), (base, y - half)], style)


def loop_diagram(devices, panel_name="", panel_lines=DEFAULT_PANEL_LINES, cable=DEFAULT_CABLE,
                 per_row=DEFAULT_PER_ROW, network=DEFAULT_NETWORK, links=DEFAULT_LINKS):
    """devices: [Device]. Returns a LoopDiagram."""
    d = Drawing()
    for name, colour in ((DETECTION_STYLE, RED), (SOUNDER_STYLE, MAGENTA), (SYMBOL_STYLE, RED),
                         (BMS_STYLE, GREEN), (POWER_STYLE, BLUE), (NETWORK_STYLE, MAGENTA)):
        d.styles[name] = colour
    warnings = []

    loops, bad = group_loops(devices)
    for loop in loops:
        loop.rows = _split(loop.devices, per_row)
        if loop.duplicates:
            warnings.append(u"L%d: %s used twice" % (loop.number, ", ".join(loop.duplicates)))

    # vertical lines, from the innermost (right) out: START, END of each circuit
    start_x, end_x = {}, {}
    x = 0.0
    for k in range(len(loops)):
        if k:
            x -= CIRCUIT_LINES_GAP
        start_x[k], end_x[k] = x, x - LINE_GAP
        x -= LINE_GAP
    lines_left = x

    labels = [dv.address for l in loops for dv in l.devices]
    pitch = max([PITCH_MIN] + [line_length(t, TEXT_ADDRESS) + PITCH_PAD for t in labels])
    first_x = FIRST_DEVICE

    # cable notes: the innermost circuit's to the right, the others' to the left
    right_notes = [0] if loops else []
    left_notes = list(range(1, len(loops)))
    levels = max(len(right_notes), len(left_notes), 1)

    # rows bottom up
    panel_top = 0.0
    y = PANEL_GAP + (levels - 1) * NOTE_STEP
    row_y = {}
    for k, loop in enumerate(loops):
        if k:
            y += CIRCUIT_GAP
        for r in range(len(loop.rows)):
            if r:
                y += ROW_PITCH
            row_y[(k, r)] = y
        if len(loop.rows) % 2 == 1:         # ends on the right: room for the return line
            y += RETURN_ABOVE

    for k, loop in enumerate(loops):
        lead = SOUNDER_STYLE if loop.sounder else DETECTION_STYLE
        pattern = "solid" if loop.sounder else "center"
        xs, xe = start_x[k], end_x[k]
        widest = max(len(r) for r in loop.rows)
        syms = [dv.symbol() for dv in loop.devices]
        turn_x = first_x + (widest - 1) * pitch + getattr(syms[-1], "half", 2.5) + TURN_PAD
        address_top = max(s.bottom for s in syms) + ADDRESS_GAP

        def wire(x1, y1, x2, y2):
            patterned_line(d, x1, y1, x2, y2, pattern, lead)

        d.line(xs, panel_top, xs, row_y[(k, 0)], lead)              # START up
        at = xs
        for r, row in enumerate(loop.rows):
            yr = row_y[(k, r)]
            forward = r % 2 == 0
            if r:                                                   # up to the next row
                wire(at, row_y[(k, r - 1)], at, yr)
            for i, dev in enumerate(row):       # a row coming back fills from the right
                x = first_x + (i if forward else widest - 1 - i) * pitch
                half = dev.symbol().draw(d, x, yr, SYMBOL_STYLE)
                near, far = (x - half, x + half) if forward else (x + half, x - half)
                if at == xs:
                    d.line(at, yr, near, yr, lead)                  # lead from START
                else:
                    wire(at, yr, near, yr)
                at = far
                d.text(x, yr - address_top, dev.address, TEXT_ADDRESS, align=CENTER, valign=TOP)
            if r < len(loop.rows) - 1:
                turn = turn_x if forward else first_x - pitch / 2
                wire(at, yr, turn, yr)
                at = turn
            elif forward:                                           # back over the row
                y_ret = yr + RETURN_ABOVE
                wire(at, yr, turn_x, yr)
                wire(turn_x, yr, turn_x, y_ret)
                d.polyline([(turn_x, y_ret), (xe, y_ret), (xe, panel_top)], lead)
            else:                                                   # lead back to END
                d.polyline([(at, yr), (xe, yr), (xe, panel_top)], lead)
        for x, text in ((xs, "START"), (xe, "END")):
            d.text(x - 0.6, panel_top + LABEL_Y + (levels - 1) * NOTE_STEP, text, TEXT_LINE,
                   align=CENTER, valign=BOTTOM, rotation=VERTICAL)

    # cable notes: an ellipse on each line and the note beside it
    parts = [p.strip() for p in (cable or "").split(",") if p.strip()]
    first_line = ",".join(parts[:-1]) + "," if len(parts) > 1 else (parts[0] if parts else "")
    second_line = parts[-1] if len(parts) > 1 else ""
    note_w = max(line_length(first_line, TEXT_CABLE), line_length(second_line, TEXT_CABLE))
    for side, members in ((1, right_notes), (-1, left_notes)):
        for j, k in enumerate(members):
            for x, yn in ((start_x[k], NOTE_HIGH), (end_x[k], NOTE_LOW)):
                yn = panel_top + yn + j * NOTE_STEP
                _ellipse(d, x, yn, ELLIPSE_W, ELLIPSE_H)
                if side > 0:
                    tx = start_x[0] + NOTE_TEXT
                    d.line(x + ELLIPSE_W / 2, yn, tx + note_w + 0.5, yn)
                else:
                    tx = lines_left - NOTE_LEFT
                    d.line(x - ELLIPSE_W / 2, yn, tx, yn)
                d.text(tx, yn + 0.6, first_line, TEXT_CABLE, align=LEFT, valign=BOTTOM)
                if second_line:
                    d.text(tx, yn - 0.6, second_line, TEXT_CABLE, align=LEFT, valign=TOP)

    # the panel
    p_right = (start_x[0] if loops else 0.0) + PANEL_RIGHT
    p_left = min(lines_left - PANEL_LEFT, p_right - PANEL_WIDTH)
    inner = p_right - p_left - PANEL_TEXT_IN - 1.0     # the office text runs close to the side
    title = wrap(panel_title(panel_name), TEXT_PANEL, inner)
    n_title = len(title.split("\n"))
    y_top = panel_top
    name_top = 3.1 + n_title * 2.55 + 1.9
    title_h = (name_top + TEXT_PANEL + 2.2) if panel_name else (3.1 + n_title * 2.55 + 1.6)
    d.text(p_left + PANEL_TEXT_IN, y_top - 3.1, title, TEXT_PANEL, align=LEFT, valign=TOP)
    if panel_name:
        d.text(p_left + PANEL_TEXT_IN, y_top - name_top, panel_name, TEXT_PANEL, align=LEFT,
               valign=TOP)
    y = y_top - title_h
    d.rect(p_left, y, p_right, y_top, DETECTION_STYLE)
    rows = []                       # (text, middle y)
    for text in _parts(panel_lines):
        text = wrap(text, TEXT_PANEL, p_right - p_left - 2.0)
        h = 4.27 + (len(text.split("\n")) - 1) * 3.14
        d.rect(p_left, y - h, p_right, y, DETECTION_STYLE)
        d.text((p_left + p_right) / 2, y - h / 2, text, TEXT_PANEL, align=CENTER, valign=MIDDLE)
        rows.append((text, y - h / 2))
        y -= h
    bottom = y

    # BMS and mains power arrows on the left
    note_end = p_left - NOTE_X + max(line_length(t, TEXT_NOTE) for t in
                                     ("INTERFACE WITH BMS", "230V AC MAIN POWER")) + 1.5
    arrow_x = max(p_left - ARROW_LONG, note_end)
    bms = [m for t, m in rows if "BACNET" in t.upper() or "BMS" in t.upper()][:1]
    y_bms = bms[0] if bms else (rows[1][1] if len(rows) > 1 else (y_top + bottom) / 2)
    d.line(p_left, y_bms, arrow_x + ARROW_HEAD, y_bms, BMS_STYLE)
    _arrow(d, arrow_x, y_bms, -1, BMS_STYLE)
    d.text(p_left - NOTE_X, y_bms, "INTERFACE WITH BMS", TEXT_NOTE, align=LEFT, valign=MIDDLE)
    y_pwr = bottom + 2.17
    d.line(arrow_x, y_pwr, p_left - ARROW_HEAD, y_pwr, POWER_STYLE)
    _arrow(d, p_left, y_pwr, 1, POWER_STYLE)
    d.text(p_left - NOTE_X, y_pwr, "230V AC MAIN POWER", TEXT_NOTE, align=LEFT, valign=MIDDLE)

    # network box beside the panel's title
    net = _parts(network)
    if net:
        bx0 = p_left - 50.4
        bx1 = max(p_left - 9.5, bx0 + max(line_length(t, TEXT_NOTE) for t in net) + 5.0)
        by1 = y_top - 1.6
        by0 = by1 - max(10.95, 4.3 + len(net) * 2.5 + 2.0)
        d.rect(bx0, by0, bx1, by1, NETWORK_STYLE)
        d.text(bx0 + 3.6, by1 - 2.8, "\n".join(net), TEXT_NOTE, align=LEFT, valign=TOP)
        d.line(bx1, (by0 + by1) / 2, p_left, (by0 + by1) / 2, BMS_STYLE)

    # links on the right (FROM ... / TO ...): by the panel name, then the BMS row
    link_y = ([y_top - name_top - TEXT_PANEL / 2] if panel_name else []) + bms + \
        [m for t, m in rows if m not in bms]
    for text, yl in zip(_parts(links), link_y):
        patterned_line(d, p_right, yl, p_right + LINK_LONG, yl, "center", DETECTION_STYLE)
        d.text(p_right + LINK_LONG + 1.5, yl, text, TEXT_LINK, align=LEFT, valign=MIDDLE)

    return LoopDiagram(d, loops, bad, warnings)
