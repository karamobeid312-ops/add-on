# -*- coding: utf-8 -*-
"""Symbols of the office LV schematic standard, drawn into a Drawing.

All coordinates are paper millimetres, +Y up.
"""
from __future__ import division

import math

from sld import style
from sld.geometry import (BOTTOM, CENTER, LEFT, MIDDLE, RIGHT, TOP, VERTICAL,
                          line_length, text_width)

HALF_PI = math.pi / 2


def breaker(d, x, y0, r=None):
    """MCCB/MCB contact ')' from y0 up to y0 + 2r. Returns the top y."""
    r = r or style.BREAKER_RADIUS
    d.arc(x, y0 + r, r, -HALF_PI, HALF_PI)
    return y0 + 2 * r


def vertical_text(d, x, y, text, size, center=False):
    """Text reading bottom -> top, starting at y.

    center=False: text sits just left of x (its right edge at x).
    center=True : text is centred on x.
    """
    return d.text(x, y, text, size, align=LEFT,
                  valign=MIDDLE if center else BOTTOM, rotation=VERTICAL)


def vertical_length(text, size):
    return text_width(text, size) - size


def _db_load_texts(loads):
    cl, dl = loads or (None, None)
    return ("CL:%.1f kW" % cl if cl is not None else None,
            "DL:%.1f kW" % dl if dl is not None else None)


def db_box_height(name, loads=None):
    """Tall enough for the name inside and CL + DL beside it."""
    beside = [line_length(t, style.TEXT_DB_LOAD) for t in _db_load_texts(loads) if t]
    return max(style.DB_BOX_HEIGHT, vertical_length(name, style.TEXT_LOAD) + 4.0,
               sum(beside) + 1.0 * len(beside) + 1.0)


def db_box(d, x, y0, name, loads=None):
    """Final distribution board: tall box with its name inside, and its
    connected (CL) and demand (DL) loads reading up on its right."""
    h = db_box_height(name, loads)
    w = style.DB_BOX_WIDTH
    d.rect(x - w / 2, y0, x + w / 2, y0 + h)
    d.text(x, y0 + h / 2, name, style.TEXT_LOAD, align=CENTER, valign=MIDDLE,
           rotation=VERTICAL)
    cl, dl = _db_load_texts(loads)
    tx = x + w / 2 + 0.4
    if cl:
        d.text(tx, y0 + 0.5, cl, style.TEXT_DB_LOAD, align=LEFT, valign=TOP,
               rotation=VERTICAL)
    if dl:
        d.text(tx, y0 + h - 0.5, dl, style.TEXT_DB_LOAD, align=RIGHT, valign=TOP,
               rotation=VERTICAL)
    return y0 + h


def load_table_size(values):
    """(width, height) of the load table for (label, value) rows."""
    size, pad = style.TEXT_LOAD_TABLE, style.LOAD_TABLE_PAD
    label_w = max(line_length(l, size) for l, _ in values) + 2 * pad
    value_w = max(line_length(v, size) for _, v in values) + 2 * pad
    return label_w + value_w, len(values) * style.LOAD_TABLE_ROW


def load_table(d, right, bottom, values):
    """Two-column table (label | value) with its bottom-right corner at
    (right, bottom), e.g. CONNECTED LOAD | 61.30kW."""
    size, pad, row = style.TEXT_LOAD_TABLE, style.LOAD_TABLE_PAD, style.LOAD_TABLE_ROW
    width, height = load_table_size(values)
    value_w = max(line_length(v, size) for _, v in values) + 2 * pad
    left, split, top = right - width, right - value_w, bottom + height
    d.rect(left, bottom, right, top)
    d.line(split, bottom, split, top)
    for i, (label, value) in enumerate(values):
        y = top - (i + 1) * row
        if i < len(values) - 1:
            d.line(left, y, right, y)
        d.text(left + pad, y + row / 2, label, size, align=LEFT, valign=MIDDLE)
        d.text(right - pad, y + row / 2, value, size, align=RIGHT, valign=MIDDLE)


def isolator(d, x, y0, name):
    """Local isolator feeding a single piece of equipment, name above."""
    w, h = style.ISOLATOR_WIDTH, style.ISOLATOR_HEIGHT
    d.rect(x - w / 2, y0, x + w / 2, y0 + h)
    top = y0 + h + style.ISOLATOR_HOOK
    d.line(x, y0 + h, x, top)
    d.line(x, top, x + 1.0, top)
    y_text = top + 0.8
    vertical_text(d, x, y_text, name, style.TEXT_LOAD, center=True)
    return y_text + vertical_length(name, style.TEXT_LOAD)


def spare(d, x, y_end):
    y_text = y_end + 0.8
    vertical_text(d, x, y_text, "SPARE", style.TEXT_LOAD, center=True)
    return y_text + vertical_length("SPARE", style.TEXT_LOAD)


def pfc(d, x, y0):
    """Power factor correction capacitor bank; y0 is the bottom vertex."""
    s = style.PFC_SIZE
    top = y0 + s * 0.8
    gap = 0.35
    d.polyline([(x - gap, top), (x - s / 2, top), (x, y0), (x + s / 2, top), (x + gap, top)])
    d.line(x - gap, top - 0.8, x - gap, top + 0.8)
    d.line(x + gap, top - 0.8, x + gap, top + 0.8)
    # Label reads upward above the symbol, like the load names.
    vertical_text(d, x, top + 1.5, pfc_label(), style.TEXT_LOAD, center=True)
    return top + 1.5 + vertical_length(pfc_label(), style.TEXT_LOAD)


def pfc_label():
    return style.PFC_LABEL.replace("\n", " ")


def ups_box(d, left, right, y0, name):
    h = style.UPS_HEIGHT
    d.rect(left, y0, right, y0 + h)
    d.text((left + right) / 2, y0 + h / 2, name, style.TEXT_LOAD, align=CENTER, valign=MIDDLE)
    return y0 + h


def cable_mark(d, x, y, label=None):
    """Cable oval on a vertical line, with its description on a leader to
    the left: first line above the leader, the rest below it."""
    r, half = 0.6, 0.9
    d.arc(x - half, y, r, HALF_PI, 3 * HALF_PI)
    d.arc(x + half, y, r, -HALF_PI, HALF_PI)
    d.line(x - half, y + r, x + half, y + r)
    d.line(x - half, y - r, x + half, y - r)
    if label:
        lines = label.split("\n")
        end = x - half - r - 0.5
        length = max(line_length(l, style.TEXT_CABLE) for l in lines)
        d.line(end - length - 1.0, y, x - half - r, y)
        d.text(end, y + 0.5, lines[0], style.TEXT_CABLE, align=RIGHT, valign=BOTTOM)
        if len(lines) > 1:
            d.text(end, y - 0.5, "\n".join(lines[1:]), style.TEXT_CABLE, align=RIGHT, valign=TOP)


def earth(d, x, y_top):
    d.line(x, y_top, x, y_top - 1.5)
    for i, w in enumerate((3.0, 2.0, 1.0)):
        y = y_top - 1.5 - i * 0.7
        d.line(x - w / 2, y, x + w / 2, y)


def sealing_end(d, x, y):
    """Cable termination at the utility supply."""
    r = 0.8
    d.arc(x - r, y, r, math.pi, 2 * math.pi)
    d.arc(x + r, y, r, 0.0, math.pi)


def transformer(d, x, y_top, name, description):
    """Two-winding transformer; returns the bottom y."""
    r = style.TRANSFORMER_RADIUS
    c1 = y_top - r
    c2 = c1 - 1.4 * r
    d.circle(x, c1, r)
    d.circle(x, c2, r)
    text_x = x - r - 1.5
    d.text(text_x, y_top, name, style.TEXT_TRANSFORMER_NAME, align=RIGHT, valign=TOP)
    if description:
        d.text(text_x, y_top - style.TEXT_TRANSFORMER_NAME * 1.7, "\n".join(description),
               style.TEXT_TRANSFORMER_INFO, align=RIGHT, valign=TOP)
    return c2 - r


def small_transformer(d, x, y0, name):
    """Transformer fed from a board way, drawn on the way (name reads up on
    its right). y0 is the bottom; returns the top y."""
    r = style.PT_TRANSFORMER_RADIUS
    c1 = y0 + r
    c2 = c1 + 1.4 * r
    d.circle(x, c1, r)
    d.circle(x, c2, r)
    size = style.TEXT_LOAD
    d.text(x + r + 0.8 + size * 1.25, y0, name, size, align=LEFT, valign=BOTTOM,
           rotation=VERTICAL)
    return c2 + r


def lamp(d, x, y, r=0.8):
    d.circle(x, y, r)
    k = r * 0.7
    d.line(x - k, y - k, x + k, y + k)
    d.line(x - k, y + k, x + k, y - k)


def meter(d, x, y, letter="A", r=1.1):
    d.circle(x, y, r)
    d.text(x, y, letter, style.TEXT_SMALL, align=CENTER, valign=MIDDLE)


def chevrons(d, x, y_apex, up=True, count=2, w=1.0, pitch=0.8):
    s = 1 if up else -1
    for i in range(count):
        ya = y_apex - s * i * pitch
        d.polyline([(x - w, ya - s * w), (x, ya), (x + w, ya - s * w)])


def fuse(d, x0, x1, y, h=1.0):
    d.rect(x0, y - h / 2, x1, y + h / 2)
    d.line(x0, y - h / 2, x1, y + h / 2)


def dot(d, x, y):
    d.circle(x, y, 0.3)


def main_incomer(d, xi, bus_y, bottom, right, device=None):
    """Main board incomer between busbar and box bottom: CT and ammeters,
    indicator lamps, withdrawable ACB, busbar fuse, SPD and earth."""
    device = device or style.MAIN_INCOMER_DEVICE
    small = style.TEXT_SMALL
    # CT with three ammeters
    y_ct = bus_y - 3.2
    xs = [xi + 7.0, xi + 11.5, xi + 16.0]
    d.line(xi, bus_y, xi, y_ct + 0.6)
    cable_mark(d, xi, y_ct)
    d.text(xi - 2.0, y_ct, style.MAIN_CT_LABEL, small, align=RIGHT, valign=MIDDLE)
    prev = xi + 1.5
    for mx in xs:
        d.line(prev, y_ct, mx - 1.1, y_ct)
        meter(d, mx, y_ct)
        prev = mx + 1.1
    # indicator lamps across the incomer
    y_lamp = bus_y - 6.2
    d.line(xi, y_ct - 0.6, xi, y_lamp)
    dot(d, xi, y_lamp)
    prev = xi + 0.3
    for lx in xs:
        d.line(prev, y_lamp, lx - 0.8, y_lamp)
        lamp(d, lx, y_lamp)
        prev = lx + 0.8
    # withdrawable ACB
    y_upper = bus_y - 8.5
    d.line(xi, y_lamp, xi, y_upper)
    chevrons(d, xi, y_upper, up=True)
    d.arc(xi, bus_y - 12.0, 1.0, HALF_PI, 3 * HALF_PI)
    y_lower = bus_y - 15.8
    chevrons(d, xi, y_lower, up=False)
    d.text(xi + 2.5, y_lower + 0.4, device, small, align=LEFT, valign=MIDDLE)
    # busbar mounted fuse feeding the indicator lamps
    y_fuse = bus_y - 21.0
    d.line(xi, y_lower, xi, y_fuse + 1.1)
    d.rect(xi - 1.1, y_fuse - 1.1, xi + 1.1, y_fuse + 1.1)
    dot(d, xi, y_fuse)
    d.line(xi + 1.1, y_fuse, xi + 6.0, y_fuse)
    d.text(xi + 6.5, y_fuse, style.MAIN_BUSBAR_FUSE, small, align=LEFT, valign=MIDDLE)
    fuse_l, fuse_r = xi - 13.0, xi - 10.0
    d.line(xi - 1.1, y_fuse, fuse_r, y_fuse)
    fuse(d, fuse_l, fuse_r, y_fuse)
    d.text((fuse_l + fuse_r) / 2, y_fuse - 1.0, style.MAIN_LAMP_FUSE, small,
           align=CENTER, valign=TOP)
    lx = [xi - 24.0, xi - 21.0, xi - 18.0]
    d.line(lx[-1] + 0.6, y_fuse, fuse_l, y_fuse)
    for i, (x, tag) in enumerate(zip(lx, "BYR")):
        lamp(d, x, y_fuse, r=0.6)
        if i:
            d.line(lx[i - 1] + 0.6, y_fuse, x - 0.6, y_fuse)
        d.text(x, y_fuse - 1.0, tag, small, align=CENTER, valign=TOP)
    d.text(lx[0] - 0.6, y_fuse + 1.4, style.MAIN_LAMPS_LABEL, small, align=LEFT, valign=BOTTOM)
    # SPD to earth
    y_spd = bus_y - 26.5
    d.line(xi, y_fuse - 1.1, xi, bottom)
    dot(d, xi, y_spd)
    d.line(xi, y_spd, xi + 6.0, y_spd)
    d.rect(xi + 6.0, y_spd - 1.5, xi + 14.0, y_spd + 1.5)
    d.text(xi + 10.0, y_spd, style.MAIN_SPD_LABEL, small, align=CENTER, valign=MIDDLE)
    ex = max(xi + 26.0, right - 12.0)
    d.line(xi + 14.0, y_spd, ex, y_spd)
    d.line(ex, y_spd, ex, bottom - 2.0)
    dot(d, ex, bottom - 2.0)
    earth(d, ex, bottom - 2.0)
    d.text(ex - 2.5, bottom - 2.5, style.MAIN_EARTH_LABEL, style.TEXT_CABLE, align=RIGHT, valign=MIDDLE)


# The lamp group of the main incomer starts this far left of the incomer.
MAIN_LAMPS_LEFT = 24.6
