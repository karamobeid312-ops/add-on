# -*- coding: utf-8 -*-
"""Reading the values typed in the VD parameters (no Revit needed)."""
from __future__ import division

import re

from vdrop.tables import DUCT, GROUND, INSULATION_NAMES, TRAY

_NUMBER_RE = re.compile(r"[-+]?\d+(?:[.,]\d+)?")
_LENGTH_UNITS = (
    ("km", 1000.0), ("mm", 0.001), ("cm", 0.01), ("ft", 0.3048), ("'", 0.3048),
    ("m", 1.0),
)
_INSTALLATION_WORDS = (
    (TRAY, ("TRAY", "LADDER", "AIR", "CT")),
    (DUCT, ("DUCT", "CONDUIT", "DB")),
    (GROUND, ("GROUND", "BURIED", "DIRECT", "SOIL")),
)
# 2x(4Cx300mm² ...), 4x4Cx300, 11 x 1C x 630, 4Cx16mm², 4C 16
_CABLE_RE = re.compile(
    r"(?:(\d+)\s*X\s*\(?\s*)?(\d+)\s*C\s*(?:X\s*)?(\d+(?:\.\d+)?)")


def number(text):
    """First number in the text (comma or dot decimals), or None."""
    match = _NUMBER_RE.search(u"%s" % (text or ""))
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


def length_m(text):
    """Cable length in metres from '175', '175 m', '17500 mm'... or None."""
    value = number(text)
    if value is None or value <= 0:
        return None
    unit = _NUMBER_RE.sub("", u"%s" % text).strip().lower()
    for suffix, factor in _LENGTH_UNITS:
        if unit.startswith(suffix):
            return value * factor
    return value


def installation(text):
    """'Cable Tray', 'Duct Bank' or 'Ground' from what was typed, or None."""
    words = re.findall(r"[A-Z]+", (text or "").upper())
    for name, keys in _INSTALLATION_WORDS:
        if any(w in keys for w in words):
            return name
    return None


def insulation(text):
    """Office cable name found in the text (XLPE/SWA/PVC...), or None."""
    upper = (text or "").upper().replace(" ", "")
    upper = upper.replace("LSOH", "LS0H").replace("LSZH", "LS0H").replace("AWA", "SWA")
    for name in sorted(INSULATION_NAMES, key=len, reverse=True):
        if name in upper:
            return name
    return None


class Cable(object):
    """Runs per phase, cores and size (mm²) of a cable, and its insulation."""

    def __init__(self, runs=1, cores=None, size=None, insulation=None):
        self.runs = runs
        self.cores = cores
        self.size = size
        self.insulation = insulation

    @property
    def single_core(self):
        return self.cores == 1

    def __eq__(self, other):
        return isinstance(other, Cable) and self.__dict__ == other.__dict__

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return "Cable(%r, %r, %r, %r)" % (self.runs, self.cores, self.size, self.insulation)


def cable(text):
    """Cable from text such as '4x4Cx300', '1Cx630 XLPE/SWA/PVC' or the SLD
    format '2x(4Cx300mm² Cu/XLPE/SWA/PVC + 1Cx150mm² ...)'. None if no
    size can be read."""
    upper = (text or "").upper().replace(u"×", "X").replace("*", "X")
    match = _CABLE_RE.search(upper)
    if not match:
        return None
    runs = int(match.group(1)) if match.group(1) else 1
    size = float(match.group(3))
    return Cable(runs=max(runs, 1), cores=int(match.group(2)),
                 size=int(size) if size == int(size) else size,
                 insulation=insulation(upper))


_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:mm²|mm2|mm\^2|sq\.?\s*mm|mm)", re.IGNORECASE)


def metric_size(wire_size_text):
    """First conductor size (mm²) in Revit's wire size text, e.g.
    '3-16 mm², 1-16 mm², 1-16 mm²' -> 16. None for imperial sizes."""
    match = _SIZE_RE.search(wire_size_text or "")
    if not match:
        return None
    size = float(match.group(1))
    return int(size) if size == int(size) else size


REVIT_UNIT_TO_VOLTS = 0.3048 ** 2   # Revit's internal unit of voltage, in V


def volts(value):
    """Voltage in V from a Revit value, which is in Revit's internal unit
    (400 V = 4305.6) for circuits but already in volts for voltage types.
    The one that gives a low voltage (100 to 1100 V) is taken; None if
    neither does."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    for candidate in (value * REVIT_UNIT_TO_VOLTS, value):
        if 100 <= candidate <= 1100:
            return candidate
    return None


def format_number(value, decimals=2):
    """'175', '0.85', '2.5' - no trailing zeros."""
    if value is None:
        return ""
    text = ("%." + str(decimals) + "f") % value
    return text.rstrip("0").rstrip(".") if "." in text else text
