# -*- coding: utf-8 -*-
"""Fire alarm riser diagram layout (pure Python, no Revit), in the office
format: floors bottom to top, the main panel on its floor, and for every
loop an OUT and a RETURN line from the panel to its floor(s).

A loop's floors are drawn from the one furthest from the panel: OUT along
that floor's row of symbols, across to the next floor at the right end,
back along its row, and so on; after the last row the RETURN line runs
back to the panel (just under the row when the row ends on the right).
Loops to the furthest floors take the outer riser lines, so no lines
cross. Symbols stand in columns in the order of the legend, with their
quantity (NO.x) above.

All sizes in millimetres on paper; the diagram is drawn 1:1. Keep
compatible with IronPython 2.7.
"""
from __future__ import division

from sld.geometry import (BOTTOM, CENTER, LEFT, MIDDLE, RIGHT, TOP, VERTICAL, Drawing,
                          line_length)
from firealarm.riser_symbols import ORDER, PANEL, symbol

WIRING = "FA Riser Wiring"          # line styles, made red the first time
SYMBOLS = "FA Riser Symbols"
RED = (255, 0, 0)
SYMBOL_RED = (230, 0, 80)

TEXT_FLOOR = 2.0            # floor names
TEXT_COUNT = 1.8            # NO.14 above a symbol
TEXT_LOOP = 1.5             # LOOP#3 OUT / RETURN
TEXT_PANEL = 2.5            # MAIN FIRE ALARM CONTROL PANEL
TEXT_PANEL_INFO = 1.8
TEXT_LEGEND_TITLE = 2.5
TEXT_LEGEND = 1.8

FLOOR_DASH, FLOOR_GAP = 12.0, 4.0
LABEL_X = 0.0               # floor names
RISER_X = 50.0              # first riser line
RISER_GAP = 3.0             # between riser lines
COLUMN_PITCH = 16.0         # between symbol columns
ROW_PITCH = 14.0            # between rows of one floor
ROW_TOP = 8.0               # band top -> first row
ROW_BOTTOM = 8.0            # last row -> floor line
MIN_BAND = 16.0
RETURN_BELOW = 4.5          # return line under a row (loops going up)
RETURN_ABOVE = 7.0          # ... over a row (loops going down), clear of the NO.x
COUNT_ABOVE = 3.2           # row -> bottom of the NO.x text
PANEL_HEIGHT = 20.0         # main panel box
BATTERY_WIDTH = 18.0
PANEL_MIN_WIDTH = 95.0
PANEL_CLEAR = 22.0          # panel -> first row, room for the vertical loop labels
PANEL_BELOW = 5.0           # floor line -> panel frame
FRAME = 3.0                 # dashed frame round the panel
LEGEND_GAP = 30.0
LEGEND_PITCH = 7.0

MAX_DEVICES = 120


class Segment(object):
    """The devices of one loop on one floor."""

    def __init__(self, loop, floor, counts):
        self.loop = loop            # loop number
        self.floor = floor          # floor name
        self.counts = counts        # {symbol code: how many}

    @property
    def devices(self):
        return sum(self.counts.values())


class RiserLoop(object):
    def __init__(self, number, segments):
        self.number = number
        self.segments = segments    # furthest from the panel first
        self.devices = sum(s.devices for s in segments)
        self.floors = [s.floor for s in segments]
        self.up = True


class Riser(object):
    def __init__(self, drawing, loops, bands, warnings):
        self.drawing = drawing
        self.loops = loops          # [RiserLoop] by number
        self.bands = bands          # [(floor name, floor line y)] bottom to top
        self.warnings = warnings


def _count_text(n):
    return "NO.%d" % n


def riser_layout(floors, segments, panel_floor, location="", max_devices=MAX_DEVICES):
    """floors: [(name, elevation)]; segments: [Segment]; panel_floor: the
    main panel's floor name. Returns a Riser."""
    d = Drawing()
    d.styles[WIRING] = RED
    d.styles[SYMBOLS] = SYMBOL_RED
    warnings = []

    floors = sorted(floors, key=lambda f: f[1])
    names = [f[0] for f in floors]
    if panel_floor not in names:
        names.insert(0, panel_floor)
    level = dict((n, k) for k, n in enumerate(names))
    panel_level = level[panel_floor]

    # ---- loops
    by_loop = {}
    for s in segments:
        if s.devices and s.floor in level:
            by_loop.setdefault(s.loop, []).append(s)
    loops = []
    for number in sorted(by_loop):
        segs = by_loop[number]
        above = [s for s in segs if level[s.floor] >= panel_level]
        below = [s for s in segs if level[s.floor] < panel_level]
        loop = RiserLoop(number, [])
        if above:
            loop.segments = sorted(above, key=lambda s: -level[s.floor]) + \
                sorted(below, key=lambda s: -level[s.floor])
            if below:
                warnings.append("LOOP#%d has floors above and below the panel; it is drawn "
                                "from the top of the panel." % number)
        else:
            loop.up = False
            loop.segments = sorted(below, key=lambda s: level[s.floor])
        loop.devices = sum(s.devices for s in loop.segments)
        loop.floors = [s.floor for s in loop.segments]
        if loop.devices > max_devices:
            warnings.append("LOOP#%d has %d devices, more than %d." % (number, loop.devices,
                                                                      max_devices))
        loops.append(loop)

    # ---- rows of each floor (by loop number) and the bands
    rows = dict((n, []) for n in names)
    for loop in loops:
        for s in loop.segments:
            rows[s.floor].append((loop.number, s))
    for n in names:
        rows[n].sort(key=lambda r: r[0])

    panel_top_pad = PANEL_BELOW + PANEL_HEIGHT + 2 * FRAME + PANEL_CLEAR
    below_panel = names[panel_level - 1] if panel_level > 0 else None
    any_down = any(level[s.floor] < panel_level for s in segments if s.floor in level)
    band_y, row_y, y = {}, {}, 0.0
    for n in names:
        count = len(rows[n])
        height = ROW_TOP + max(count - 1, 0) * ROW_PITCH + ROW_BOTTOM if count else MIN_BAND
        top_pad = PANEL_CLEAR if (n == below_panel and any_down) else 0.0
        if n == panel_floor:
            height += panel_top_pad
        height = max(height + top_pad, MIN_BAND)
        band_y[n] = y
        for k, (number, s) in enumerate(rows[n]):
            row_y[(number, n)] = y + height - top_pad - ROW_TOP - k * ROW_PITCH
        y += height
    top_y = y

    # ---- columns (symbols used, in legend order)
    codes = set()
    for loop in loops:
        for s in loop.segments:
            codes.update(c for c, v in s.counts.items() if v)
    codes = sorted(codes, key=lambda c: (ORDER.get(c, len(ORDER)), c))

    # riser lines: loops to the furthest floors outermost
    ups = sorted([l for l in loops if l.up],
                 key=lambda l: (-row_y[(l.number, l.segments[0].floor)], l.number))
    downs = sorted([l for l in loops if not l.up],
                   key=lambda l: (row_y[(l.number, l.segments[0].floor)], l.number))
    x_out = {}
    for group in (ups, downs):
        for k, loop in enumerate(group):
            x_out[loop.number] = RISER_X + 2 * k * RISER_GAP
    widest = max(len(ups), len(downs), 1)
    riser_end = RISER_X + (2 * widest - 1) * RISER_GAP
    label_room = line_length("LOOP#%d" % max([l.number for l in loops] or [0]), TEXT_LOOP) + 3.0
    turn_x = riser_end + label_room + 4.0
    first_col = turn_x + 6.0
    col_x = dict((c, first_col + k * COLUMN_PITCH) for k, c in enumerate(codes))
    right_x = first_col + max(len(codes) - 1, 0) * COLUMN_PITCH + COLUMN_PITCH * 0.6

    # ---- the panel
    base = band_y[panel_floor]
    main_left = RISER_X - 6.0
    main_right = max(riser_end + 8.0, main_left + PANEL_MIN_WIDTH)
    panel_bottom = base + PANEL_BELOW + FRAME
    panel_top = panel_bottom + PANEL_HEIGHT
    battery_right = main_left - 3.0
    battery_left = battery_right - BATTERY_WIDTH
    d.rect(battery_left, panel_bottom, battery_right, panel_top, SYMBOLS)
    d.text((battery_left + battery_right) / 2, (panel_bottom + panel_top) / 2,
           "BATTERY\n&\nCHARGER", TEXT_PANEL_INFO, align=CENTER, valign=MIDDLE)
    d.rect(main_left, panel_bottom, main_right, panel_top, SYMBOLS)
    info = ["MAIN FIRE ALARM CONTROL PANEL",
            "%d LOOP%s" % (len(loops), "" if len(loops) == 1 else "S")]
    d.text((main_left + main_right) / 2, panel_top - 4.0, info[0], TEXT_PANEL,
           align=CENTER, valign=BOTTOM)
    lines = [info[1]] + (["LOC. %s" % location.upper()] if location else [])
    d.text((main_left + main_right) / 2, panel_top - 6.0, "\n".join(lines),
           TEXT_PANEL_INFO, align=CENTER, valign=TOP)
    # dashed frame round battery and panel
    fl, fb, fr, ft = battery_left - FRAME, panel_bottom - FRAME, main_right + FRAME, panel_top + FRAME
    for x0, y0, x1, y1 in ((fl, fb, fr, fb), (fl, ft, fr, ft)):
        d.dashed_line(x0, x1, y0, 4.0, 2.0, SYMBOLS)
    for x in (fl, fr):
        yy = fb
        while yy < ft:
            d.line(x, yy, x, min(yy + 4.0, ft), SYMBOLS)
            yy += 6.0

    # ---- loops
    for loop in loops:
        _draw_loop(d, loop, x_out[loop.number], row_y, col_x, turn_x, right_x,
                   panel_top if loop.up else panel_bottom,
                   panel_top + FRAME + 1.5 if loop.up else base - 1.5)

    # ---- floors
    legend_x = right_x + LEGEND_GAP
    for n in names:
        yf = band_y[n]
        d.dashed_line(LABEL_X, right_x + 10.0, yf, FLOOR_DASH, FLOOR_GAP)
        d.text(LABEL_X, yf + 1.2, n.upper(), TEXT_FLOOR, align=LEFT, valign=BOTTOM)
    d.dashed_line(LABEL_X, right_x + 10.0, top_y, FLOOR_DASH, FLOOR_GAP)

    # ---- legend with totals
    totals = {}
    for loop in loops:
        for s in loop.segments:
            for c, v in s.counts.items():
                totals[c] = totals.get(c, 0) + v
    ly = top_y - 4.0
    d.text(legend_x, ly, "LEGEND", TEXT_LEGEND_TITLE, align=LEFT, valign=MIDDLE)
    ly -= LEGEND_PITCH * 1.2
    qty_x = legend_x + 14.0 + max([line_length(symbol(c).description, TEXT_LEGEND) for c in codes] +
                                  [line_length(PANEL.description, TEXT_LEGEND)]) + 6.0
    d.text(qty_x, ly + LEGEND_PITCH * 0.6, "QTY", TEXT_LEGEND, align=LEFT, valign=MIDDLE)
    for code in codes + [PANEL.code]:
        sym = PANEL if code == PANEL.code else symbol(code)
        sym.draw(d, legend_x + 5.0, ly, SYMBOLS)
        d.text(legend_x + 14.0, ly, sym.description, TEXT_LEGEND, align=LEFT, valign=MIDDLE)
        d.text(qty_x, ly, "%d" % (1 if code == PANEL.code else totals.get(code, 0)),
               TEXT_LEGEND, align=LEFT, valign=MIDDLE)
        ly -= LEGEND_PITCH

    bands = [(n, band_y[n]) for n in names]
    return Riser(d, loops, bands, warnings)


def _row(d, y, x_from, x_to, segment, col_x):
    """The loop line along a row, broken at its symbols, with NO.x above."""
    lo, hi = sorted((x_from, x_to))
    gaps = []
    for code, n in sorted(segment.counts.items(), key=lambda item: col_x[item[0]]):
        if not n:
            continue
        x = col_x[code]
        half = symbol(code).draw(d, x, y, SYMBOLS)
        gaps.append((x - half, x + half))
        d.text(x, y + COUNT_ABOVE, _count_text(n), TEXT_COUNT, align=CENTER, valign=BOTTOM)
    x = lo
    for g0, g1 in sorted(gaps):
        d.line(x, y, g0, y, WIRING)
        x = g1
    d.line(x, y, hi, y, WIRING)


def _draw_loop(d, loop, x_out, row_y, col_x, turn_x, right_x, panel_edge, label_y):
    x_ret = x_out + RISER_GAP
    sign = 1 if loop.up else -1
    ys = [row_y[(loop.number, s.floor)] for s in loop.segments]
    d.line(x_out, panel_edge, x_out, ys[0], WIRING)                 # OUT
    at_right = False
    for k, (s, y) in enumerate(zip(loop.segments, ys)):
        last = k == len(ys) - 1
        if k == 0:
            start, end = x_out, right_x
        elif at_right:
            d.line(right_x, ys[k - 1], right_x, y, WIRING)
            start, end = right_x, (x_ret if last else turn_x)
        else:
            d.line(turn_x, ys[k - 1], turn_x, y, WIRING)
            start, end = turn_x, right_x
        _row(d, y, start, end, s, col_x)
        d.text(turn_x - 1.5, y + 0.6, "LOOP#%d" % loop.number, TEXT_LOOP,
               align=RIGHT, valign=BOTTOM)
        at_right = end == right_x
    y_end = ys[-1]
    if at_right:                                                     # back under / over the row
        y_end = ys[-1] - sign * (RETURN_BELOW if loop.up else RETURN_ABOVE)
        d.line(right_x, ys[-1], right_x, y_end, WIRING)
        d.line(right_x, y_end, x_ret, y_end, WIRING)
    d.line(x_ret, y_end, x_ret, panel_edge, WIRING)                  # RETURN
    # labels up the riser lines, next to the panel
    for x, text in ((x_out, "LOOP#%d OUT" % loop.number), (x_ret, "LOOP#%d RETURN" % loop.number)):
        d.text(x - 0.4, label_y, text, TEXT_LOOP, align=LEFT if loop.up else RIGHT,
               valign=BOTTOM, rotation=VERTICAL)
