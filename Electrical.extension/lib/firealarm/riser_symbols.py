# -*- coding: utf-8 -*-
"""Fire alarm riser symbols, as in the office legend, and which symbol a
Revit family / type gets (pure Python, no Revit).

Each symbol is drawn in paper millimetres, centred on the loop line, with
the `style` line style (red). Keep compatible with IronPython 2.7.
"""
from __future__ import division

import math
import re

from sld.geometry import CENTER, MIDDLE, line_length

TEXT = 1.3              # letters inside a symbol (mm)
R = 2.2                 # half the height of a detector diamond (mm)


class Symbol(object):
    def __init__(self, code, description, draw):
        self.code = code
        self.description = description
        self.draw = draw        # draw(drawing, x, y, style) -> half width


# ---------------------------------------------------------------- shapes

def _diamond(d, x, y, r, style):
    d.polyline([(x - r, y), (x, y + r), (x + r, y), (x, y - r), (x - r, y)], style)


def _box(d, x, y, w, h, style):
    d.rect(x - w / 2, y - h / 2, x + w / 2, y + h / 2, style)


def _cross_circle(d, x, y, r, style):
    d.circle(x, y, r, style)
    k = r * math.sqrt(0.5)
    d.line(x - k, y - k, x + k, y + k, style)
    d.line(x - k, y + k, x + k, y - k, style)


def _letters(d, x, y, text, size=TEXT):
    d.text(x, y, text, size, align=CENTER, valign=MIDDLE)


def _detector(letter=None, circle=True):
    def draw(d, x, y, style):
        _diamond(d, x, y, R, style)
        if circle:
            d.circle(x, y, 0.75, style)
        if letter:
            _letters(d, x, y, letter)
        return R
    return draw


def _raised_floor(d, x, y, style):
    _box(d, x, y, 2 * R, 2 * R, style)
    _diamond(d, x, y, R, style)
    d.circle(x, y, 0.75, style)
    return R


def _trench(d, x, y, style):
    _box(d, x, y - 0.4, 4.4, 1.3, style)
    d.circle(x, y + 1.25, 0.6, style)
    return 2.2


def _beam(letters):
    def draw(d, x, y, style):
        w, h = 3.6, 3.0
        top = y + h / 2
        d.polyline([(x - w / 2, top), (x - w / 2, y - h / 2), (x + w / 2, y - h / 2),
                    (x + w / 2, top), (x - w / 2, top)], style)
        # a low dome on top
        rise = 0.6
        radius = ((w / 2) ** 2 + rise ** 2) / (2 * rise)
        a = math.asin((w / 2) / radius)
        d.arc(x, top + rise - radius, radius, math.pi / 2 - a, math.pi / 2 + a, style)
        _letters(d, x, y - 0.1, letters, 1.1)
        return w / 2
    return draw


def _text_box(letters, size=TEXT):
    def draw(d, x, y, style):
        w = max(line_length(letters, size) + 1.4, 3.2)
        _box(d, x, y, w, 2.6, style)
        _letters(d, x, y, letters, size)
        return w / 2
    return draw


def _bell(strobe):
    def draw(d, x, y, style):
        _box(d, x, y - 0.5, 2.4, 2.8, style)
        top = y - 0.5 + 1.4
        if strobe:
            _cross_circle(d, x, top + 0.8, 0.8, style)
        else:
            d.circle(x, top + 0.75, 0.75, style)
        return 1.2
    return draw


def _strobe(wall):
    def draw(d, x, y, style):
        _box(d, x, y, 3.4, 3.4, style)
        _cross_circle(d, x, y, 0.9, style)
        if wall:
            d.line(x, y - 1.7, x, y - 3.0, style)
            d.line(x - 1.1, y - 3.0, x + 1.1, y - 3.0, style)
        return 1.7
    return draw


def _horn_strobe(d, x, y, style):
    left = x - 2.6
    _box(d, left + 1.2, y - 0.4, 2.4, 2.2, style)               # body
    _cross_circle(d, left + 1.2, y + 1.5, 0.7, style)            # strobe on top
    # horn to the right of the body
    d.polyline([(left + 2.4, y - 0.1), (left + 2.4, y - 0.7), (x + 2.6, y - 1.3),
                (x + 2.6, y + 0.5), (left + 2.4, y - 0.1)], style)
    return 2.6


def _flow_switch(d, x, y, style):
    d.circle(x, y, 1.8, style)
    d.circle(x, y, 1.55, style)
    _diamond(d, x, y, 1.0, style)
    return 1.8


def _tamper(d, x, y, style):
    w, h = 1.5, 1.9
    d.polyline([(x - w, y + h), (x + w, y + h), (x - w, y - h), (x + w, y - h),
                (x - w, y + h)], style)
    return w


def _linear_heat(d, x, y, style):
    for dx in (-1.6, 1.6):
        _letters(d, x + dx, y, "H", TEXT)
    return 2.4


# In the order of the office legend; the riser columns follow it.
SYMBOLS = [
    Symbol("SD", "PHOTOELECTRIC SMOKE DETECTOR", _detector()),
    Symbol("SDF", "ABOVE FALSE CEILING PHOTOELECTRIC SMOKE DETECTOR", _detector()),
    Symbol("SDR", "UNDER RAISED FLOOR PHOTOELECTRIC SMOKE DETECTOR", _raised_floor),
    Symbol("HD", "HEAT DETECTOR", _detector("H", circle=False)),
    Symbol("BTX", "OPTICAL BEAM SMOKE DETECTOR - TRANSMITTER", _beam("TX")),
    Symbol("BRX", "OPTICAL BEAM SMOKE DETECTOR - RECEIVER", _beam("RX")),
    Symbol("MCP", "MANUAL STATION", _text_box("F")),
    Symbol("BELL", "FIRE ALARM BELL", _bell(strobe=False)),
    Symbol("BELLS", "FIRE ALARM BELL WITH STROBE LIGHT", _bell(strobe=True)),
    Symbol("STC", "CEILING MOUNTED STROBE LIGHT", _strobe(wall=False)),
    Symbol("STW", "WALL MOUNTED STROBE LIGHT", _strobe(wall=True)),
    Symbol("HS", "FIRE ALARM HORN WITH STROBE LIGHT", _horn_strobe),
    Symbol("SDT", "PHOTOELECTRIC SMOKE DETECTOR INSIDE TRENCHES", _trench),
    Symbol("J", "FIRE TELEPHONE JACK", _text_box("J")),
    Symbol("FARP", "FIRE ALARM REPEATER PANEL", _text_box("FARP")),
    Symbol("WFS", "WATER FLOW SWITCH", _flow_switch),
    Symbol("TS", "TAMPER SWITCH", _tamper),
    Symbol("CM", "CONTROL MODULE", _text_box("CM")),
    Symbol("MM", "MONITOR MODULE", _text_box("MM")),
    Symbol("ZM", "ZONE MODULE", _text_box("ZM")),
    Symbol("LHD", "LINEAR HEAT DETECTOR", _linear_heat),
    Symbol("DD", "DUCT DETECTOR", _detector("D", circle=False)),
    Symbol("EOL", "END OF LINE", _text_box("EOL")),
    Symbol("LHDP", "LINEAR HEAT DETECTOR PANEL", _text_box("LHD")),
    Symbol("HSSD", "HIGH SENSITIVITY SMOKE DETECTION SYSTEM", _text_box("HSSD")),
    Symbol("ISO", "ISOLATOR", _text_box("ISO")),
]
BY_CODE = dict((s.code, s) for s in SYMBOLS)
ORDER = dict((s.code, k) for k, s in enumerate(SYMBOLS))
PANEL = Symbol("MFACP", "MAIN FIRE ALARM CONTROL PANEL", _text_box("MFACP"))


def initials(name):
    """Up to four initials of a name: 'Mystery Gadget : Type 1' -> 'MGT1'."""
    words = re.findall(r"[A-Z0-9]+", name.upper())
    return "".join(w[0] for w in words)[:4] or "?"


def other_symbol(name):
    """A box with the initials of a type no legend symbol fits."""
    return Symbol(u"?" + name, name.upper(), _text_box(initials(name)))


def symbol(code):
    if code in BY_CODE:
        return BY_CODE[code]
    return other_symbol(code[1:] if code.startswith("?") else code)


# ---------------------------------------------------------------- which symbol

def _has(text, *words):
    """Any of the words (whole words or phrases) in the text."""
    return any(re.search(r"(?<![A-Z0-9])" + re.escape(w) + r"(?![A-Z0-9])", text) for w in words)


def _part(text, *parts):
    """Any of the parts anywhere in the text (PHOTO in PHOTOELECTRIC)."""
    return any(p in text for p in parts)


VISUAL = ("STROBE", "BEACON", "VAD", "FLASH", "VISUAL ALARM")
SMOKE = ("SMOKE", "OPTICAL", "PHOTO", "IONI", "MULTI")

_RULES = [
    ("FARP", lambda t: _part(t, "REPEATER")),
    ("HSSD", lambda t: _has(t, "HSSD", "VESDA") or _part(t, "ASPIRAT", "HIGH SENSITIVITY")),
    ("LHDP", lambda t: (_part(t, "LINEAR HEAT") or _has(t, "LHD")) and _part(t, "PANEL", "CONTROL", "INTERFACE")),
    ("LHD", lambda t: _part(t, "LINEAR HEAT") or _has(t, "LHD")),
    ("BRX", lambda t: _part(t, "BEAM") and (_part(t, "RECEIV") or _has(t, "RX"))),
    ("BTX", lambda t: _part(t, "BEAM")),
    ("DD", lambda t: _part(t, "DUCT")),
    ("SDT", lambda t: _part(t, "TRENCH")),
    ("SDR", lambda t: _part(t, "RAISED FLOOR", "UNDER FLOOR", "UNDERFLOOR", "FLOOR VOID")),
    ("SDF", lambda t: _part(t, *SMOKE) and _part(t, "ABOVE", "FALSE CEILING", "CEILING VOID")),
    ("SD", lambda t: _part(t, *SMOKE)),
    ("HD", lambda t: _part(t, "HEAT", "THERMAL") or _has(t, "ROR")),
    ("MCP", lambda t: _part(t, "MANUAL", "CALL POINT", "BREAK GLASS", "PULL STATION") or _has(t, "MCP")),
    ("J", lambda t: _part(t, "TELEPHONE", "PHONE", "JACK")),
    ("WFS", lambda t: _part(t, "FLOW")),
    ("TS", lambda t: _part(t, "TAMPER", "SUPERVISORY")),
    ("HS", lambda t: _part(t, "HORN")),
    ("BELLS", lambda t: _part(t, "BELL", "SOUNDER") and _part(t, *VISUAL)),
    ("BELL", lambda t: _part(t, "BELL", "SOUNDER")),
    ("STC", lambda t: _part(t, *VISUAL) and _part(t, "CEILING")),
    ("STW", lambda t: _part(t, *VISUAL)),
    ("MM", lambda t: _part(t, "MONITOR", "INPUT")),
    ("ZM", lambda t: _part(t, "ZONE")),
    ("CM", lambda t: _part(t, "CONTROL", "OUTPUT", "RELAY")),
    ("EOL", lambda t: _part(t, "END OF LINE") or _has(t, "EOL")),
    ("ISO", lambda t: _part(t, "ISOLAT")),
]


def is_panel_name(name):
    """A fire alarm control panel (main or not), not a repeater."""
    t = name.upper()
    return not _part(t, "REPEATER") and (
        _has(t, "FACP", "MFACP", "CIE") or _part(t, "CONTROL PANEL", "FIRE ALARM PANEL", "FA PANEL"))


def guess(name):
    """Symbol code for a 'Family : Type' name; '?<name>' when none fits."""
    t = name.upper()
    for code, test in _RULES:
        if test(t):
            return code
    return u"?" + name


def resolve(name, override=None, chosen=None):
    """The symbol code of a type: its 'FA Symbol' parameter (a code or a
    description), else the one chosen in FA Settings, else the guess."""
    for value in (override, chosen):
        if value:
            value = value.strip().upper()
            if value in BY_CODE:
                return value
            for s in SYMBOLS:
                if s.description == value:
                    return s.code
    return guess(name)
