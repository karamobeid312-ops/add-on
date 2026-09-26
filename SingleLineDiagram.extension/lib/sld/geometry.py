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
    def __init__(self, x1, y1, x2, y2):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2

    def length(self):
        return math.hypot(self.x2 - self.x1, self.y2 - self.y1)

    def __repr__(self):
        return "Line(%.2f, %.2f, %.2f, %.2f)" % (self.x1, self.y1, self.x2, self.y2)


class Arc(object):
    """Counter-clockwise arc from angle a0 to a1 (radians), a1 > a0."""

    def __init__(self, cx, cy, r, a0, a1):
        self.cx, self.cy, self.r, self.a0, self.a1 = cx, cy, r, a0, a1

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


def text_width(text, size):
    """Width needed so no line of `text` wraps."""
    longest = max(len(line) for line in text.split("\n")) if text else 1
    return longest * size * style.CHAR_WIDTH + size


def text_height(text, size):
    return len(text.split("\n")) * size * 1.6


class Drawing(object):
    def __init__(self):
        self.lines = []
        self.arcs = []
        self.texts = []

    # -- basic shapes
    def line(self, x1, y1, x2, y2):
        if abs(x1 - x2) > 1e-9 or abs(y1 - y2) > 1e-9:
            self.lines.append(Line(x1, y1, x2, y2))

    def polyline(self, points):
        for (x1, y1), (x2, y2) in zip(points, points[1:]):
            self.line(x1, y1, x2, y2)

    def rect(self, left, bottom, right, top):
        self.polyline([(left, bottom), (right, bottom), (right, top),
                       (left, top), (left, bottom)])

    def arc(self, cx, cy, r, a0, a1):
        self.arcs.append(Arc(cx, cy, r, a0, a1))

    def circle(self, cx, cy, r):
        # Two halves: Revit refuses closed curves as detail lines.
        self.arc(cx, cy, r, 0.0, math.pi)
        self.arc(cx, cy, r, math.pi, 2 * math.pi)

    def dashed_line(self, x1, x2, y, dash, gap):
        x = x1
        while x < x2:
            self.line(x, y, min(x + dash, x2), y)
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
