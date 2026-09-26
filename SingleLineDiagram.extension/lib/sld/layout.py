# -*- coding: utf-8 -*-
"""Lays a Diagram out as plain drawing primitives (lines and text).

All coordinates are paper inches with +Y up. By default the diagram grows
upward: sources (e.g. the main switchboard) sit on the bottom row at y = 0
and each downstream level is drawn one row higher (direction=UP). With
direction=DOWN the sources are on top and the diagram grows downward.

The Revit renderer only has to turn these primitives into detail lines and
text notes, so everything geometric is testable without Revit.
"""
from __future__ import division

from sld.model import EQUIPMENT

LEFT = "left"
CENTER = "center"
TOP = "top"
BOTTOM = "bottom"

UP = "up"      # sources at the bottom, loads above (default)
DOWN = "down"  # sources at the top, loads below


class LayoutOptions(object):
    def __init__(self, **kwargs):
        self.direction = UP
        self.box_width = 2.0           # equipment rectangle
        self.box_height = 0.75
        self.circuit_width = 1.6       # branch circuit text block
        self.horizontal_gap = 0.4      # between sibling subtrees
        self.root_gap = 0.75           # between separate sources
        self.level_gap = 1.4           # box edge -> next row box edge
        self.bus_drop = 0.35           # box edge -> horizontal bus
        self.breaker_offset = 0.15     # bus -> breaker symbol
        self.breaker_size = 0.12
        self.label_width = 1.6         # feeder label next to the breaker
        self.text_padding = 0.06
        self.title_gap = 0.4           # diagram edge -> title
        for k, v in kwargs.items():
            if not hasattr(self, k):
                raise TypeError("Unknown layout option: %s" % k)
            setattr(self, k, v)
        if self.direction not in (UP, DOWN):
            raise ValueError("direction must be 'up' or 'down'")

    @property
    def row_pitch(self):
        return self.box_height + self.level_gap

    @property
    def sign(self):
        """+1 when children are drawn above their parent, -1 when below."""
        return 1 if self.direction == UP else -1


class Line(object):
    def __init__(self, x1, y1, x2, y2):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2

    def length(self):
        return ((self.x2 - self.x1) ** 2 + (self.y2 - self.y1) ** 2) ** 0.5

    def __repr__(self):
        return "Line(%.3f, %.3f, %.3f, %.3f)" % (self.x1, self.y1, self.x2, self.y2)


class Text(object):
    """x is the left edge (align LEFT) or the centre (align CENTER);
    y is the top edge (valign TOP) or the bottom edge (valign BOTTOM)."""

    def __init__(self, x, y, width, text, align, valign=TOP):
        self.x, self.y, self.width = x, y, width
        self.text = text
        self.align = align
        self.valign = valign

    def __repr__(self):
        return "Text(%r @ %.3f, %.3f)" % (self.text, self.x, self.y)


class Placement(object):
    def __init__(self, node, center_x, top_y, width, height, sign):
        self.node = node
        self.center_x = center_x
        self.top_y = top_y
        self.width = width
        self.height = height
        self.sign = sign

    @property
    def left(self):
        return self.center_x - self.width / 2

    @property
    def right(self):
        return self.center_x + self.width / 2

    @property
    def bottom(self):
        return self.top_y - self.height

    @property
    def near_y(self):
        """Edge facing the parent (where the feeder arrives)."""
        return self.bottom if self.sign > 0 else self.top_y

    @property
    def far_y(self):
        """Edge facing the children (where outgoing feeders leave)."""
        return self.top_y if self.sign > 0 else self.bottom


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
    s = opts.sign
    drawing = Drawing()
    widths = {}

    def node_width(node):
        return opts.box_width if node.kind == EQUIPMENT else opts.circuit_width

    def subtree_width(node):
        key = id(node)
        if key not in widths:
            own = node_width(node)
            if node.children:
                kids = sum(subtree_width(c) for c in node.children)
                kids += opts.horizontal_gap * (len(node.children) - 1)
                widths[key] = max(own, kids)
            else:
                widths[key] = own
        return widths[key]

    def place(node, left, depth):
        near = s * depth * opts.row_pitch  # edge facing the parent
        top = near + opts.box_height if s > 0 else near
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
        p = Placement(node, cx, top, node_width(node), opts.box_height, s)
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
        # Title sits under the sources: below the bottom row when growing up,
        # above the top row when growing down.
        if s > 0:
            drawing.texts.append(Text(0.0, -opts.title_gap, max(left, 3.0), text, LEFT, TOP))
        else:
            drawing.texts.append(Text(0.0, opts.title_gap, max(left, 3.0), text, LEFT, BOTTOM))
    return drawing


def _draw_subtree(node, drawing, opts):
    s = opts.sign
    p = drawing.placements[node.id]
    pad = opts.text_padding
    body = "\n".join([node.title] + node.details)

    if node.kind == EQUIPMENT:
        drawing.add_rect(p.left, p.top_y, p.right, p.bottom)
        drawing.texts.append(Text(p.center_x, p.top_y - pad, p.width - 2 * pad, body, CENTER))
    else:
        # Branch circuit: text only, hugging the end of its feeder line.
        valign = BOTTOM if s > 0 else TOP
        drawing.texts.append(Text(p.center_x, p.near_y, p.width - pad, body, CENTER, valign))

    if not node.children:
        return

    bus_y = p.far_y + s * opts.bus_drop
    drawing.add_line(p.center_x, p.far_y, p.center_x, bus_y)
    kids = [drawing.placements[c.id] for c in node.children]
    xs = [k.center_x for k in kids] + [p.center_x]
    if max(xs) - min(xs) > 1e-9:
        drawing.add_line(min(xs), bus_y, max(xs), bus_y)

    for child, k in zip(node.children, kids):
        _draw_feeder(child, k, bus_y, drawing, opts)
        _draw_subtree(child, drawing, opts)


def _draw_feeder(child, k, bus_y, drawing, opts):
    """Line from the bus to `child` with a breaker symbol next to the bus."""
    s = opts.sign
    x = k.center_x
    b_start = bus_y + s * opts.breaker_offset
    b_end = b_start + s * opts.breaker_size
    half = opts.breaker_size / 2
    drawing.add_line(x, bus_y, x, b_start)
    drawing.add_rect(x - half, max(b_start, b_end), x + half, min(b_start, b_end))
    drawing.add_line(x, b_end, x, k.near_y)

    # Branch circuits carry their breaker/cable info in their own text block.
    if child.kind == EQUIPMENT and child.feeder is not None:
        lines = child.feeder.feeder_label_lines()
        if lines:
            label_x = x + half + 0.05
            # Label runs along the feeder, starting at the breaker.
            if s > 0:
                y, valign = min(b_start, b_end), BOTTOM
            else:
                y, valign = max(b_start, b_end), TOP
            drawing.texts.append(Text(label_x, y, opts.label_width, "\n".join(lines), LEFT, valign))
