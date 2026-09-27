# -*- coding: utf-8 -*-
"""Drawing primitives in paper millimetres (+Y up).

The Revit renderer turns these into detail lines, detail arcs and text
notes; tools/preview_svg.py turns them into an SVG for checking layouts
without Revit.
"""
from __future__ import division

import math

from sld import style

LEFT = "left"
CENTER = "center"
RIGHT = "right"
TOP = "top"
MIDDLE = "middle"
BOTTOM = "bottom"

VERTICAL = math.pi / 2  # text rotation: reads bottom -> top


class Line(object):
    def __init__(self, x1, y1, x2, y2, style=None):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        self.style = style      # line style name (Drawing.styles), None: the default

    def length(self):
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    def __repr__(self):
        return "Line(%.2f, %.2f, %.2f, %.2f)" % (self.x1, self.y1, self.x2, self.y2)


class Arc(object):
    """Counter-clockwise arc from angle a0 to a1 (radians), a1 > a0."""

    def __init__(self, cx, cy, r, a0, a1, style=None):
        self.cx, self.cy, self.r, self.a0, self.a1 = cx, cy, r, a0, a1
        self.style = style

    def point(self, a):
        return (self.cx + self.r * math.cos(a), self.cy + self.r * math.sin(a))

    def __repr__(self):
        return "Arc(%.2f, %.2f, r=%.2f)" % (self.cx, self.cy, self.r)


class Text(object):
    """A text note.

    (x, y) is the anchor. `align` (LEFT/CENTER/RIGHT) and `valign`
    (TOP/MIDDLE/BOTTOM) say which point of the text box the anchor is, in
    the text's own frame, exactly like Revit's text note alignment. With
    rotation=VERTICAL the text reads bottom -> top and its "top" edge faces
    left.
    """

    def __init__(self, x, y, text, size, align=LEFT, valign=BOTTOM,
                 rotation=0.0, width=None):
        self.x, self.y = x, y
        self.text = text
        self.size = size
        self.align = align
        self.valign = valign
        self.rotation = rotation
        self.width = width if width is not None else text_width(text, size)

    @property
    def lines(self):
        return self.text.split("\n")

    def __repr__(self):
        return "Text(%r @ %.2f, %.2f)" % (self.text, self.x, self.y)


# Arial advance widths in em. Text size is the capital height (0.716 em).
_ARIAL = {}
for _chars, _w in (("ABEKPSVXY&", 0.667), ("CDHNRUw", 0.722), ("GOQ", 0.778),
                   ("FTZ", 0.611), ("I", 0.278), ("J", 0.5), ("L", 0.556),
                   ("Mm", 0.833), ("W", 0.944), ("0123456789#_abdeghnopqu", 0.556),
                   (" .,:;/!|fijlt\u00a0", 0.278), ("-()r\u00b2", 0.333),
                   ("+<=>~", 0.584), ("@", 1.015), ("%", 0.889),
                   ("ckvxyzs\"*", 0.5), ("\u03a9", 0.768)):
    for _c in _chars:
        _ARIAL[_c] = _w
_CAP_HEIGHT = 0.716


def line_length(line, size):
    """Estimated printed length of one line of text (Arial)."""
    em = sum(_ARIAL.get(c, 0.6) for c in line)
    return em / _CAP_HEIGHT * size * style.CHAR_WIDTH


def text_width(text, size):
    """Width needed so no line of `text` wraps."""
    longest = max(line_length(line, size) for line in text.split("\n")) if text else size
    return longest + size


def text_height(text, size):
    """From the top of the first line's capitals to the last baseline."""
    return size * (1.25 + style.LINE_SPACING * (len(text.split("\n")) - 1))


def wrap(text, size, max_length):
    """Break lines at spaces so each fits in max_length (if possible)."""
    out = []
    for line in text.split("\n"):
        words = line.split(" ")
        current = words[0]
        for word in words[1:]:
            if line_length(current + " " + word, size) <= max_length:
                current += " " + word
            else:
                out.append(current)
                current = word
        out.append(current)
    return "\n".join(out)


class Drawing(object):
    def __init__(self):
        self.lines = []
        self.arcs = []
        self.texts = []
        self.styles = {}        # line style name -> (r, g, b) colour, for styled lines

    # -- basic shapes
    def line(self, x1, y1, x2, y2, style=None):
        if abs(x1 - x2) > 1e-9 or abs(y1 - y2) > 1e-9:
            self.lines.append(Line(x1, y1, x2, y2, style))

    def polyline(self, points, style=None):
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            self.line(x1, y1, x2, y2, style)

    def rect(self, left, bottom, right, top, style=None):
        self.polyline([(left, bottom), (right, bottom), (right, top),
                       (left, top), (left, bottom)], style)

    def arc(self, cx, cy, r, a0, a1, style=None):
        self.arcs.append(Arc(cx, cy, r, a0, a1, style))

    def circle(self, cx, cy, r, style=None):
        # Two halves: Revit refuses closed curves as detail lines.
        self.arc(cx, cy, r, 0.0, math.pi, style)
        self.arc(cx, cy, r, math.pi, 2 * math.pi, style)

    def dashed_line(self, x1, x2, y, dash, gap, style=None):
        x = x1
        while x < x2:
            self.line(x, y, min(x + dash, x2), y, style)
            x += dash + gap

    def text(self, x, y, text, size, **kwargs):
        t = Text(x, y, text, size, **kwargs)
        self.texts.append(t)
        return t

    # -- bounds
    def bounds(self):
        xs, ys = [], []
        for l in self.lines:
            xs += [l.x1, l.x2]
            ys += [l.y1, l.y2]
        for a in self.arcs:
            xs += [a.cx - a.r, a.cx + a.r]
            ys += [a.cy - a.r, a.cy + a.r]
        for t in self.texts:
            x0, y0, x1, y1 = text_box(t)
            xs += [x0, x1]
            ys += [y0, y1]
        if not xs:
            return 0.0, 0.0, 0.0, 0.0
        return min(xs), min(ys), max(xs), max(ys)


def text_box(t):
    """Approximate axis-aligned box (x0, y0, x1, y1) covered by a text."""
    w = text_width(t.text, t.size) - t.size
    h = text_height(t.text, t.size)
    # box in the text's own frame, relative to the anchor
    fx0 = {LEFT: 0.0, CENTER: -w / 2, RIGHT: -w}[t.align]
    fy0 = {TOP: -h, MIDDLE: -h / 2, BOTTOM: 0.0}[t.valign]
    corners = [(fx0, fy0), (fx0 + w, fy0), (fx0, fy0 + h), (fx0 + w, fy0 + h)]
    c, s = math.cos(t.rotation), math.sin(t.rotation)
    pts = [(t.x + u * c - v * s, t.y + u * s + v * c) for u, v in corners]
    return (min(p[0] for p in pts), min(p[1] for p in pts),
            max(p[0] for p in pts), max(p[1] for p in pts))
