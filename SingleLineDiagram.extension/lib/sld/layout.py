# -*- coding: utf-8 -*-
"""Lays a Diagram out as plain drawing primitives (lines and text).

All coordinates are paper inches with +Y up; the diagram grows downward from
y = 0. The Revit renderer only has to turn these primitives into detail lines
and text notes, so everything geometric is testable without Revit.
"""
from __future__ import division

from sld.model import EQUIPMENT

LEFT = "left"
CENTER = "center"


class LayoutOptions(object):
    def __init__(self, **kwargs):
        self.box_width = 1.75          # equipment rectangle
        self.box_height = 0.75
        self.circuit_width = 1.1       # branch circuit text block
        self.horizontal_gap = 0.35     # between sibling subtrees
        self.root_gap = 0.75           # between separate sources
        self.level_gap = 1.4           # box bottom -> next row top
        self.bus_drop = 0.35           # box bottom -> horizontal bus
        self.breaker_offset = 0.15     # bus -> top of breaker symbol
        self.breaker_size = 0.12
        self.text_padding = 0.06
        self.title_height = 0.6        # space above the first row
        for k, v in kwargs.items():
            if not hasattr(self, k):
                raise TypeError("Unknown layout option: %s" % k)
            setattr(self, k, v)

    @property
    def row_pitch(self):
        return self.box_height + self.level_gap


class Line(object):
    def __init__(self, x1, y1, x2, y2):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2

    def length(self):
        return ((self.x2 - self.x1) ** 2 + (self.y2 - self.y1) ** 2) ** 0.5

    def __repr__(self):
        return "Line(%.3f, %.3f, %.3f, %.3f)" % (self.x1, self.y1, self.x2, self.y2)


class Text(object):
    """Text anchored at its top edge; x is the left edge (LEFT) or the
    centre (CENTER)."""

    def __init__(self, x, y, width, text, align):
        self.x, self.y, self.width = x, y, width
        self.text = text
        self.align = align

    def __repr__(self):
        return "Text(%r @ %.3f, %.3f)" % (self.text, self.x, self.y)


class Placement(object):
    def __init__(self, node, center_x, top_y, width, height):
        self.node = node
        self.center_x = center_x
        self.top_y = top_y
        self.width = width
        self.height = height

    @property
    def left(self):
        return self.center_x - self.width / 2

    @property
    def right(self):
        return self.center_x + self.width / 2

    @property
    def bottom(self):
        return self.top_y - self.height


class Drawing(object):
    def __init__(self):
        self.lines = []
        self.texts = []
        self.placements = {}  # node id -> Placement

    def add_line(self, x1, y1, x2, y2):
        self.lines.append(Line(x1, y1, x2, y2))

    def add_rect(self, left, top, right, bottom):
        self.add_line(left, top, right, top)
        self.add_line(right, top, right, bottom)
        self.add_line(right, bottom, left, bottom)
        self.add_line(left, bottom, left, top)


def layout_diagram(diagram, title=None, subtitle=None, options=None):
    opts = options or LayoutOptions()
    drawing = Drawing()
    widths = {}

    def node_size(node):
        if node.kind == EQUIPMENT:
            return opts.box_width, opts.box_height
        return opts.circuit_width, opts.box_height

    def subtree_width(node):
        key = id(node)
        if key not in widths:
            own = node_size(node)[0]
            if node.children:
                kids = sum(subtree_width(c) for c in node.children)
                kids += opts.horizontal_gap * (len(node.children) - 1)
                widths[key] = max(own, kids)
            else:
                widths[key] = own
        return widths[key]

    def place(node, left, depth):
        w, h = node_size(node)
        top = -depth * opts.row_pitch
        total = subtree_width(node)
        if node.children:
            span = sum(subtree_width(c) for c in node.children)
            span += opts.horizontal_gap * (len(node.children) - 1)
            x = left + (total - span) / 2
            kids = []
            for child in node.children:
                kids.append(place(child, x, depth + 1))
                x += subtree_width(child) + opts.horizontal_gap
            cx = (kids[0].center_x + kids[-1].center_x) / 2
        else:
            cx = left + total / 2
        p = Placement(node, cx, top, w, h)
        drawing.placements[node.id] = p
        return p

    left = 0.0
    for root in diagram.roots:
        place(root, left, 0)
        left += subtree_width(root) + opts.root_gap

    for root in diagram.roots:
        _draw_subtree(root, drawing, opts)

    if title:
        text = title if not subtitle else title + "\n" + subtitle
        drawing.texts.append(Text(0.0, opts.title_height, max(left, 3.0), text, LEFT))
    return drawing


def _draw_subtree(node, drawing, opts):
    p = drawing.placements[node.id]
    pad = opts.text_padding
    body = "\n".join([node.title] + node.details)

    if node.kind == EQUIPMENT:
        drawing.add_rect(p.left, p.top_y, p.right, p.bottom)
        drawing.texts.append(Text(p.center_x, p.top_y - pad, p.width - 2 * pad, body, CENTER))
    else:
        drawing.texts.append(Text(p.center_x, p.top_y, p.width - pad, body, CENTER))

    if not node.children:
        return

    bus_y = p.bottom - opts.bus_drop
    drawing.add_line(p.center_x, p.bottom, p.center_x, bus_y)
    kids = [drawing.placements[c.id] for c in node.children]
    xs = [k.center_x for k in kids] + [p.center_x]
    if max(xs) - min(xs) > 1e-9:
        drawing.add_line(min(xs), bus_y, max(xs), bus_y)

    for child, k in zip(node.children, kids):
        _draw_feeder(child, k, bus_y, drawing, opts)
        _draw_subtree(child, drawing, opts)


def _draw_feeder(child, k, bus_y, drawing, opts):
    """Vertical drop from the bus to `child` with a breaker symbol on it."""
    x = k.center_x
    b_top = bus_y - opts.breaker_offset
    b_bot = b_top - opts.breaker_size
    half = opts.breaker_size / 2
    drawing.add_line(x, bus_y, x, b_top)
    drawing.add_rect(x - half, b_top, x + half, b_bot)
    drawing.add_line(x, b_bot, x, k.top_y)

    # Branch circuits carry their breaker info in their own text block.
    if child.kind == EQUIPMENT and child.feeder is not None:
        lines = child.feeder.feeder_label_lines()
        if lines:
            label_x = x + half + 0.05
            width = max(k.width / 2 - half - 0.1, 0.5)
            drawing.texts.append(Text(label_x, b_top + 0.02, width, "\n".join(lines), LEFT))
