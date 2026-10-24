# -*- coding: utf-8 -*-
"""Cable descriptions in the office format, e.g.

    (4X4)mm² CU/XLPE/PVC +(1X4)mm² CU/PVC(E)

Revit-independent so it can be unit tested.
"""
from __future__ import division

import re

MM2 = u"mm²"  # mm²

DEFAULT_CONDUCTOR = "Cu"
DEFAULT_INSULATION = "XLPE"
DEFAULT_SHEATH = "PVC"
EARTH_BUILD = "CU/PVC(E)"

_MATERIALS = {
    "copper": "Cu", "cu": "Cu",
    "aluminum": "Al", "aluminium": "Al", "al": "Al",
}
_INSULATIONS = ("XLPE", "PVC", "EPR", "LSZH", "LSF", "MICC", "SWA")

_SIZE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:mm²|mm2|mm\^2|sq\.?\s*mm|mm)",
                      re.IGNORECASE)


def parse_metric_sizes(wire_size_text):
    """All conductor sizes (mm²) in Revit's wire size text, in order.

    '4x4mm², 1x2.5mm²' -> ['4', '2.5']. Returns [] for imperial text such as
    '3-#12, 1-#12' so the caller can fall back to the raw value.
    """
    return [_clean_number(m) for m in _SIZE_RE.findall(wire_size_text or "")]


def _clean_number(text):
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def conductor_code(material_name):
    """'Copper' -> 'Cu', 'Aluminum' -> 'Al', unknown -> default."""
    key = (material_name or "").strip().lower()
    for name, code in _MATERIALS.items():
        if key == name or key.startswith(name):
            return code
    return DEFAULT_CONDUCTOR


def insulation_code(insulation_name):
    """Keeps recognised IEC insulation names (XLPE, PVC...), else default."""
    upper = (insulation_name or "").upper()
    for code in _INSULATIONS:
        if code in upper:
            return code
    return DEFAULT_INSULATION


def construction(conductor=DEFAULT_CONDUCTOR, insulation=DEFAULT_INSULATION,
                 sheath=DEFAULT_SHEATH):
    return "/".join(p for p in (conductor, insulation, sheath) if p)


def format_cable(cores, size, earth_cores=0, earth_size=None, build=None,
                 runs=1):
    """Build the cable description.

    cores       number of live cores (phases + neutral)
    size        live conductor size in mm², e.g. '4' or 4
    earth_cores number of separate earth cores (0 = no earth)
    earth_size  earth size in mm² (defaults to `size`)
    build       e.g. 'Cu/XLPE/PVC' (defaults to Cu/XLPE/PVC), printed upper case
    runs        parallel runs; >1 gives '2X(4X95)mm² ...'
    """
    if not cores or size in (None, ""):
        return ""
    build = (build or construction()).upper()
    text = u"(%dX%s)%s" % (int(cores), _clean_number(str(size)), MM2)
    if runs and int(runs) > 1:
        text = u"%dX%s" % (int(runs), text)
    text += u" " + build
    if earth_cores:
        text += u" +(%dX%s)%s %s" % (
            int(earth_cores),
            _clean_number(str(earth_size if earth_size not in (None, "") else size)),
            MM2, EARTH_BUILD)
    return text


def cable_from_revit_values(hots, neutrals, grounds, wire_size_text,
                            build=None, runs=1):
    """Cable text from the values Revit stores on a circuit.

    Falls back to the raw wire size text when no metric size can be read.
    """
    sizes = parse_metric_sizes(wire_size_text)
    cores = (hots or 0) + (neutrals or 0)
    if not sizes or not cores:
        return wire_size_text or ""
    earth_size = sizes[-1] if len(sizes) > 1 else sizes[0]
    return format_cable(cores, sizes[0], grounds or 0, earth_size, build, runs)
