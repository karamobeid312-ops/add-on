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


def isolator_label(name, kw=None):
    """'CL:135.0kW' / 'FOR ELEC PUMP' above an isolator (office SLD)."""
    lines = []
    if kw is not None:
        lines.append("CL:%.1fkW" % kw)
    lines.append("FOR %s" % name if name else "")
    return "\n".join(l for l in lines if l)


def isolator_label_length(name, kw=None):
    label = isolator_label(name, kw)
    return max([vertical_length(l, style.TEXT_ISOLATOR) for l in label.split("\n")] or [0.0])


def isolator(d, x, y0, name, rating="", kw=None):
    """Local isolator feeding a single piece of equipment, as the office
    SLD: its rating ('300A,4P') reading up on the left, W.P on the right,
    the load ('CL:135.0kW' / 'FOR ELEC PUMP') above."""
    w, h = style.ISOLATOR_WIDTH, style.ISOLATOR_HEIGHT
    d.rect(x - w / 2, y0, x + w / 2, y0 + h)
    top = y0 + h + style.ISOLATOR_HOOK
    d.line(x, y0 + h, x, top)
    d.line(x, top, x + 1.0, top)
    if rating:
        vertical_text(d, x - w / 2 - 0.3, y0, rating, style.TEXT_WAY)
    if style.ISOLATOR_NOTE:
        d.text(x + w / 2 + 0.3, y0, style.ISOLATOR_NOTE, style.TEXT_ISOLATOR_NOTE, align=LEFT,
               valign=TOP, rotation=VERTICAL)
    y_text = top + 0.8
    label = isolator_label(name, kw)
    d.text(x, y_text, label, style.TEXT_ISOLATOR, align=LEFT, valign=MIDDLE, rotation=VERTICAL)
    return y_text + isolator_label_length(name, kw)


def spare(d, x, y_end, label="SPARE"):
    """SPARE (or SPACE) at the end of a way."""
    y_text = y_end + 0.8
    vertical_text(d, x, y_text, label, style.TEXT_SPARE, center=True)
    return y_text + vertical_length(label, style.TEXT_SPARE)


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
    """Two-winding transformer, name and description left of it (office
    SLD), earthed on the right (R<1Ω); returns the bottom y."""
    r = style.TRANSFORMER_RADIUS
    c1 = y_top - r
    c2 = c1 - 1.4 * r
    d.circle(x, c1, r)
    d.circle(x, c2, r)
    info = list(description or [])
    width = max([line_length(name, style.TEXT_TRANSFORMER_NAME)] +
                [line_length(l, style.TEXT_TRANSFORMER_INFO) for l in info])
    text_x = x - r - 1.5 - width
    d.text(text_x, y_top, name, style.TEXT_TRANSFORMER_NAME, align=LEFT, valign=TOP)
    if info:
        d.text(text_x, y_top - style.TEXT_TRANSFORMER_NAME * 1.7, "\n".join(info),
               style.TEXT_TRANSFORMER_INFO, align=LEFT, valign=TOP)
    ex = x + r + 2.5
    d.line(x + r, c2, ex, c2)
    d.line(ex, c2, ex, c2 - r - 1.0)
    earth(d, ex, c2 - r - 1.0)
    d.text(ex + 0.5, c2 - r - 4.3, style.MAIN_EARTH_LABEL, style.TEXT_CABLE,
           align=LEFT, valign=TOP)
    return c2 - r


def utility_meter(d, x, y_top, label, ratio):
    """Utility meter box on the incoming line ('ADDC METER', '1600A/5A' on
    its right); returns the bottom y."""
    lines = label.split()
    if len(lines) > 2:
        lines = [" ".join(lines[:-1]), lines[-1]]
    size = style.TEXT_SMALL
    w = max(line_length(l, size) for l in lines) + 1.6
    h = size * style.LINE_SPACING * len(lines) + 1.2
    d.rect(x - w / 2, y_top - h, x + w / 2, y_top)
    d.text(x, y_top - h / 2, "\n".join(lines), size, align=CENTER, valign=MIDDLE)
    if ratio:
        d.text(x + w / 2 + 0.8, y_top - h / 2, ratio, size, align=LEFT, valign=MIDDLE)
    return y_top - h


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


def breaker_label(d, x, y, lines, size):
    """Breaker rating to the right of x, middle at y: '100AT' above a bar,
    '100AF' and the type below it (the office style); other text as is."""
    lines = [l for l in lines if l]
    if not lines:
        return
    if len(lines) < 2 or not lines[0].upper().endswith("AT"):
        d.text(x, y, "\n".join(lines), size, align=LEFT, valign=MIDDLE)
        return
    gap = 0.25 * size
    d.text(x, y + gap, lines[0], size, align=LEFT, valign=BOTTOM)
    d.text(x, y - gap, "\n".join(lines[1:]), size, align=LEFT, valign=TOP)
    d.line(x, y, x + max(line_length(l, size) for l in lines[:2]), y)


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
    # rating beside the ACB body, clear of the busbar fuse text below it
    breaker_label(d, xi + 2.5, bus_y - 11.5, (device or "").split("\n"), small)
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


# ---------------------------------------------------------------- bus bar riser

def riser_bar(d, x, y0, y1, label):
    """Tall bus bar riser centred on x, its label reading up inside."""
    w = style.RISER_BAR_WIDTH
    d.rect(x - w / 2, y0, x + w / 2, y1)
    if label:
        d.text(x, y0 + 3.0, label, style.TEXT_RISER, align=LEFT, valign=MIDDLE,
               rotation=VERTICAL)


def riser_label_length(label):
    return text_width(label, style.TEXT_RISER) * style.FLOOR_LABEL_SLACK + 6.0 if label else 0.0


def tap_unit(d, x_bar, y, rating):
    """Tap-off unit on the right side of a bar (x_bar = bar's right edge),
    centred on y, with its rating above. Returns the unit's right x."""
    w, h = style.TAP_UNIT_W, style.TAP_UNIT_H
    d.rect(x_bar, y - h / 2, x_bar + w, y + h / 2)
    d.circle(x_bar + w / 2, y, 0.22)
    if rating:
        d.text(x_bar + 0.2, y + h / 2 + 0.6, rating, style.TEXT_TAP_INFO, align=LEFT,
               valign=BOTTOM)
    return x_bar + w


def typical_box_lines(name, master, floor):
    lines = [(name, style.TEXT_TAP), (style.TYPICAL_TEXT % master, style.TEXT_TAP_INFO)]
    if floor:
        lines.append(("@ %s" % floor.upper(), style.TEXT_TAP_INFO))
    return lines


def typical_box_size(lines):
    pad = style.TAP_BOX_PAD
    w = max(line_length(t, s) for t, s in lines) + 2 * pad
    h = sum(s * style.LINE_SPACING for _, s in lines) + pad
    return w, h


def typical_box(d, left, y_mid, lines, width=None):
    """'SMDB-T-6 / DB SAME AS SMDB-T-1 / @ 6TH FLOOR', right-aligned in a box
    whose left side meets the tap-off line at y_mid."""
    w, h = typical_box_size(lines)
    w = max(w, width or 0.0)
    top = y_mid + h / 2
    d.rect(left, y_mid - h / 2, left + w, top)
    y = top - style.TAP_BOX_PAD
    for text, size in lines:
        d.text(left + w - style.TAP_BOX_PAD, y, text, size, align=RIGHT, valign=TOP)
        y -= size * style.LINE_SPACING
    return left + w


def ats_info(equipment):
    """Lines beside an ATS: its rating and poles, location."""
    lines = []
    rating = equipment.mains_rating or equipment.incomer_rating
    from sld.model import parse_amps, trim_number
    amps = parse_amps(rating)
    if amps:
        lines.append("%sA,4P" % trim_number(amps, 1))
    if equipment.location:
        lines.append("LOCATION: %s" % equipment.location)
    return lines


def ats(d, x, y0, name, info=()):
    """Automatic transfer switch, as the office SLD: a box with the switch
    inside, the supply in at the bottom (x), the standby supply's contact
    beside it, out at the top (x). Name and info on the right. Returns the
    top y."""
    s = style.ATS_SIZE
    top = y0 + s
    d.rect(x - s / 2, y0, x + s / 2, top)
    a = (x, y0 + 1.6)                 # normal supply contact
    b = (x + 1.8, y0 + 1.6)           # standby supply contact
    c = (x, top - 1.6)                # common, out
    d.line(x, y0, a[0], a[1])
    d.line(b[0], y0, b[0], b[1])
    d.line(c[0], c[1], x, top)
    for px, py in (a, b, c):
        d.circle(px, py, 0.25)
    d.line(a[0] + 0.15, a[1] + 0.2, c[0] + 1.3, c[1] - 0.4)   # the blade, open towards C
    tx = x + s / 2 + 1.0
    d.text(tx, top, name, style.TEXT_ATS, align=LEFT, valign=TOP)
    if info:
        d.text(tx, top - style.TEXT_ATS * style.LINE_SPACING, "\n".join(info),
               style.TEXT_ATS_INFO, align=LEFT, valign=TOP)
    return top


def ats_standby(d, x, y0, name, info=()):
    """ATS under a board with a generator, as the office SLD: normal
    supply in from the left side, generator out of the bottom (standby
    contact on the right), out at the top (x). Returns
    (top, normal contact y, standby contact x)."""
    s = style.ATS_SIZE
    top = y0 + s
    d.rect(x - s / 2, y0, x + s / 2, top)
    a = (x - 1.4, y0 + 2.0)           # normal supply contact
    b = (x + 1.4, y0 + 2.0)           # standby (generator) contact
    c = (x, top - 1.5)                # common, out
    d.line(x - s / 2, a[1], a[0], a[1])
    d.line(b[0], y0, b[0], b[1])
    d.line(c[0], c[1], x, top)
    for px, py in (a, b, c):
        d.circle(px, py, 0.25)
    d.line(a[0] + 0.2, a[1] + 0.2, c[0] - 0.1, c[1] - 0.3)   # blade on the normal supply
    tx = x + s / 2 + 1.0
    d.text(tx, top, name, style.TEXT_ATS, align=LEFT, valign=TOP)
    if info:
        d.text(tx, top - style.TEXT_ATS * style.LINE_SPACING, "\n".join(info),
               style.TEXT_ATS_INFO, align=LEFT, valign=TOP)
    return top, a[1], b[0]


def earth_pit(d, x, y):
    """Earth pit: an oval on the line, the earth under it."""
    r, half = 0.6, 0.9
    d.arc(x - half, y, r, HALF_PI, 3 * HALF_PI)
    d.arc(x + half, y, r, -HALF_PI, HALF_PI)
    d.line(x - half, y + r, x + half, y + r)
    d.line(x - half, y - r, x + half, y - r)
    d.line(x - half - r, y, x + half + r, y)
    earth(d, x, y - r)


def generator_width(cable, lines=()):
    """Generator drawing right of the ATS standby contact, mm."""
    from sld.generator import EARTH_TEXT
    return (generator_offset(cable) + _earth_offsets(lines)[1] +
            max(style.GEN_EARTH_TAIL, line_length(EARTH_TEXT, style.TEXT_GEN_CABLE) + 3.0))


def _earth_offsets(lines):
    """Generator centre -> its two earth pits, clear of the text under it."""
    text_right = -style.GEN_RADIUS - 2.0 + max(
        [line_length(l, style.TEXT_GEN) for l in lines] or [0.0])
    e1 = max(style.GEN_EARTH_1, text_right + 4.0)
    return e1, e1 + style.GEN_EARTH_2 - style.GEN_EARTH_1


def generator_offset(cable):
    """Standby contact -> generator centre."""
    return max(style.GEN_FROM_ATS, line_length(cable or "", style.TEXT_GEN_CABLE) + 6.0) + \
        style.GEN_RADIUS


def generator_height():
    """ATS bottom -> lowest point of the generator drawing."""
    return style.GEN_BELOW_ATS + max(style.GEN_RADIUS + 1.5 + 3 * style.TEXT_GEN * style.LINE_SPACING,
                                     style.GEN_EARTH_DROP + 4.0)


def generator(d, x_contact, y_ats, cable, lines):
    """Generator below-right of the ATS standby contact, as the office SLD:
    the cable down then across into the 'G' circle (cable text above the
    line), name / voltage / kVA under it, earthed to two earth pits."""
    from sld.generator import EARTH_TEXT
    r = style.GEN_RADIUS
    cy = y_ats - style.GEN_BELOW_ATS
    cx = x_contact + generator_offset(cable)
    d.polyline([(x_contact, y_ats), (x_contact, cy), (cx - r, cy)])
    if cable:
        d.text((x_contact + cx - r) / 2, cy + 0.6, cable, style.TEXT_GEN_CABLE,
               align=CENTER, valign=BOTTOM)
    d.circle(cx, cy, r)
    d.text(cx, cy, "G", style.TEXT_GEN_LETTER, align=CENTER, valign=MIDDLE)
    d.text(cx - r - 2.0, cy - r - 1.5, "\n".join(lines), style.TEXT_GEN, align=LEFT, valign=TOP)
    o1, o2 = _earth_offsets(lines)
    e1, e2 = cx + o1, cx + o2
    y_pit = cy - style.GEN_EARTH_DROP
    d.polyline([(cx + r * 0.6, cy - r * 0.8), (e1, cy - r * 0.8), (e1, y_pit + 0.6)])
    d.polyline([(cx + r * 0.6, cy + r * 0.8), (e2, cy + r * 0.8), (e2, y_pit + 0.6)])
    earth_pit(d, e1, y_pit)
    earth_pit(d, e2, y_pit)
    d.line(e1 + 1.5, y_pit, e2 - 1.5, y_pit)
    tail = e2 + max(style.GEN_EARTH_TAIL, line_length(EARTH_TEXT, style.TEXT_GEN_CABLE) + 3.0)
    d.line(e2 + 1.5, y_pit, tail, y_pit)
    d.text(e2 + 2.5, y_pit + 0.5, EARTH_TEXT, style.TEXT_GEN_CABLE, align=LEFT, valign=BOTTOM)
