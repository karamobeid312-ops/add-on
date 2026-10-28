# -*- coding: utf-8 -*-
"""Device symbols of the office fire alarm loop diagram, copied from the
office drawing SUBSTATION2 FIRE ALARM SCHEMATIC.dxf (drawn there at 1:100;
here in paper millimetres, centred where the loop line meets the device).

Each shape is a list of
    ("L", x1, y1, x2, y2, pattern)          line
    ("A", cx, cy, r, from_deg, to_deg, pattern)   arc
    ("D", cx, cy, r)                        filled dot
    ("T", x, y, text, size)                 text centred at x, y
with pattern "solid", "hidden" (dashed) or "center" (dash dot), as in the
office drawing. Keep compatible with IronPython 2.7.
"""
from __future__ import division

import math

from sld.geometry import CENTER, MIDDLE

# dash patterns in paper mm: dash, gap, dash, gap...
PATTERNS = {
    "hidden": (0.6, 0.3),
    "center": (1.6, 0.35, 0.3, 0.35),
}
MIN_DASHED = 1.0    # shorter edges are drawn solid: a dash would be all of them anyway


def _diamond(letter, pattern="solid"):
    r = 2.556
    return [("L", -r, 0.0, 0.0, -r, pattern), ("L", 0.0, -r, r, 0.0, pattern),
            ("L", r, 0.0, 0.0, r, pattern), ("L", 0.0, r, -r, 0.0, pattern),
            ("T", 0.0, 0.0, letter, 1.81)]


def _box(w, h, pattern):
    x, y = w / 2, h / 2
    return [("L", -x, -y, x, -y, pattern), ("L", x, -y, x, y, pattern),
            ("L", x, y, -x, y, pattern), ("L", -x, y, -x, -y, pattern)]


def _rays(cx, cy, pattern):
    """The sounder's sound rays, from the dome (radius 1.86) out 0.75."""
    out = []
    right = (12.4, 18.1, 24.8, 32.5, 40.0, 49.8, 60.0, 70.0, 78.0)
    for deg in right + (90.0,) + tuple(180.0 - d for d in right):
        a = math.radians(deg)
        c, s = math.cos(a), math.sin(a)
        r0, r1 = 1.86, 2.61
        out.append(("L", cx + r0 * c, cy + r0 * s, cx + r1 * c, cy + r1 * s, pattern))
    return out


# sounder on its base: dome over a 3.72 x 1.2 base
_SOUNDER = (_box(3.718, 1.2, "hidden") + [("L", -1.859, -0.6, 1.859, -0.6, "solid"),
                                          ("A", 0.0, 0.6, 1.859, 0.0, 180.0, "hidden")]
            + _rays(0.0, 0.6, "hidden"))

# weatherproof sounder with beacon: W/P base, sounder and beacon on stalks
_SOUNDER_WP = (_box(8.164, 1.5, "center")
               + [("T", 0.0, -0.09, "W/P", 1.0),
                  ("L", 2.1, 0.75, 2.1, 2.27, "center"),          # sounder stalk
                  ("L", 0.05, 2.27, 3.77, 2.27, "center"), ("L", 3.77, 2.27, 3.77, 3.48, "center"),
                  ("L", 3.77, 3.48, 0.05, 3.48, "center"), ("L", 0.05, 3.48, 0.05, 2.27, "center"),
                  ("A", 1.91, 3.48, 1.859, 0.0, 180.0, "center")]
               + _rays(1.91, 3.48, "center")
               + [("L", -2.75, 0.75, -2.75, 4.32, "center"),       # beacon stalk
                  ("L", -2.75, 2.27, -1.54, 4.32, "center"), ("L", -1.54, 4.32, -3.98, 4.32, "center"),
                  ("L", -3.98, 4.32, -2.75, 2.27, "center")])

# hexagon with a small triangle and H: HY
_HEX_R = 2.231
_HY = ([("L", _HEX_R * math.cos(math.radians(a)), _HEX_R * math.sin(math.radians(a)),
         _HEX_R * math.cos(math.radians(a + 60)), _HEX_R * math.sin(math.radians(a + 60)),
         "center") for a in range(0, 360, 60)]
       + [("L", 0.0, 0.7, -0.574, -0.014, "center"), ("L", -0.574, -0.014, 0.579, -0.014, "center"),
          ("L", 0.579, -0.014, 0.0, 0.7, "center"), ("T", 2.21, -1.73, "H", 1.0)])

_MCP = _box(3.718, 3.08, "center") + [("D", 0.0, 0.0, 0.62)]
_MM = _box(5.058, 2.604, "hidden") + [("T", 0.0, 0.0, "MM", 1.81)]


class LoopSymbol(object):
    def __init__(self, code, shape, half):
        self.code = code
        self.shape = shape
        self.half = half        # the loop line stops this far either side
        ys = []
        for op in shape:
            if op[0] == "L":
                ys += [op[2], op[4]]
            elif op[0] in "AD":
                ys.append(op[2] - (op[3] if op[0] == "D" else 0.0))
        self.bottom = -min(ys)  # how far the symbol reaches under the line

    def draw(self, d, x, y, style):
        for op in self.shape:
            kind = op[0]
            # drawn solid: the office drawing's dashed outlines read as hatching
            if kind == "L":
                d.line(x + op[1], y + op[2], x + op[3], y + op[4], style)
            elif kind == "A":
                d.arc(x + op[1], y + op[2], op[3], math.radians(op[4]), math.radians(op[5]),
                      style)
            elif kind == "D":
                dot(d, x + op[1], y + op[2], op[3], style)
            elif kind == "T":
                d.text(x + op[1], y + op[2], op[3], op[4], align=CENTER, valign=MIDDLE)
        return self.half


LOOP_SYMBOLS = dict((s.code, s) for s in (
    LoopSymbol("SD", _diamond("S"), 2.556),
    LoopSymbol("HD", _diamond("H"), 2.556),
    LoopSymbol("FD", _diamond("F"), 2.556),
    LoopSymbol("HY", _HY, 2.231),
    LoopSymbol("MCP", _MCP, 1.859),
    LoopSymbol("MM", _MM, 2.529),
    LoopSymbol("SB", _SOUNDER, 1.859),
    LoopSymbol("SBW", _SOUNDER_WP, 4.082),
))


# ---------------------------------------------------------------- patterns

def _dashes(length, pattern):
    """[(from, to)] along a length for a pattern name."""
    steps = PATTERNS.get(pattern)
    if not steps or length < MIN_DASHED:
        return [(0.0, length)]
    out, at, k = [], 0.0, 0
    while at < length - 1e-9:
        step = steps[k % len(steps)]
        if k % 2 == 0:
            out.append((at, min(at + step, length)))
        at += step
        k += 1
    return out


def patterned_line(d, x1, y1, x2, y2, pattern, style=None):
    length = math.hypot(x2 - x1, y2 - y1)
    if length < 1e-9:
        return
    ux, uy = (x2 - x1) / length, (y2 - y1) / length
    for a, b in _dashes(length, pattern):
        d.line(x1 + ux * a, y1 + uy * a, x1 + ux * b, y1 + uy * b, style)


def patterned_arc(d, cx, cy, r, a0, a1, pattern, style=None):
    for a, b in _dashes(r * (a1 - a0), pattern):
        d.arc(cx, cy, r, a0 + a / r, a0 + b / r, style)


def dot(d, cx, cy, r, style=None, step=0.06):
    """A filled dot: rings close enough to print solid."""
    rr = r
    while rr > step / 2:
        d.circle(cx, cy, rr, style)
        rr -= step
