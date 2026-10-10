# -*- coding: utf-8 -*-
"""A cable as the LV Schematic Editor shows it, and its office text:

    (4X120)mm² CU/XLPE/SWA/PVC +(1X70)mm² CU/PVC(E)
    2X(4X240)mm² CU/XLPE/SWA/PVC +(1X120)mm² CU/PVC(E)     parallel runs
    4X(1X300)mm² CU/XLPE/AWA/PVC                           single core, runs per phase

The same text is written to SLD Cable and VD Cable; the Voltage Drop tool
reads it too (vdrop.parse.cable).
"""
from __future__ import division

import re

MM2 = u"mm²"
MATERIALS = ("CU", "AL")
INSULATIONS = ("XLPE", "PVC", "LSZH")
ARMOURS = ("SWA", "AWA", "STA")
SHEATHS = ("PVC", "LSZH")
EARTH_BUILD = "CU/PVC(E)"

_NUM = r"(\d+(?:[.,]\d+)?)"
_OFFICE_RE = re.compile(r"(?:(\d+)\s*X\s*)?\(\s*(\d+)\s*X\s*" + _NUM + r"\s*\)")
_OLD_RE = re.compile(r"(?:(\d+)\s*X\s*\(?\s*)?(\d+)\s*C\s*(?:X\s*)?" + _NUM)
_EARTH_RE = re.compile(r"\+\s*\(?\s*(\d+)\s*C?\s*X\s*" + _NUM)


def _size(text):
    value = float(text.replace(",", "."))
    return int(value) if value == int(value) else value


def _trim(value):
    text = "%.2f" % value
    return text.rstrip("0").rstrip(".") if "." in text else text


class CableSpec(object):
    def __init__(self, cores=4, size=None, runs=1, material="CU", insulation="XLPE",
                 armour="SWA", sheath="PVC", earth_size=None):
        self.cores = cores
        self.size = size
        self.runs = runs or 1
        self.material = material
        self.insulation = insulation
        self.armour = armour or ""
        self.sheath = sheath
        self.earth_size = earth_size

    def build(self):
        return "/".join(p for p in (self.material, self.insulation, self.armour, self.sheath)
                        if p)

    def text(self):
        """Office text; '' when the size is unknown."""
        if self.size is None:
            return ""
        main = u"(%dX%s)%s" % (int(self.cores or 4), _trim(self.size), MM2)
        if self.runs and int(self.runs) > 1:
            main = u"%dX%s" % (int(self.runs), main)
        text = u"%s %s" % (main, self.build())
        if self.earth_size:
            text += u" +(1X%s)%s %s" % (_trim(self.earth_size), MM2, EARTH_BUILD)
        return text

    def vd_cable(self):
        """The cable as the Voltage Drop tool sees it."""
        from vdrop import parse
        return parse.cable(self.text())

    def copy(self, **changes):
        values = dict(self.__dict__)
        values.update(changes)
        return CableSpec(**values)

    def __eq__(self, other):
        return isinstance(other, CableSpec) and self.__dict__ == other.__dict__

    def __ne__(self, other):
        return not self == other

    def __repr__(self):
        return "CableSpec(%r)" % self.text()


def parse(text):
    """CableSpec from the office text, the old SLD text ('4Cx16mm²
    Cu/XLPE/PVC + 1Cx16mm² Cu/XLPE/PVC') or a VD Cable ('4x4Cx300
    XLPE/SWA/PVC'); None when no size can be read. Parts not given take the
    defaults (CU, XLPE, PVC sheath; no armour unless named)."""
    upper = (text or "").upper().replace(u"×", "X").replace("*", "X")
    match = _OFFICE_RE.search(upper) or _OLD_RE.search(upper)
    if not match:
        return None
    rest = upper[match.end():]
    main, _, earth = rest.partition("+")
    words = re.findall(r"[A-Z0]+", main.replace("LS0H", "LSZH").replace("LSOH", "LSZH"))
    material = next((w for w in words if w in MATERIALS), "CU")
    insulation = next((w for w in words if w in ("XLPE", "LSZH", "PVC", "EPR")), "XLPE")
    armour = next((w for w in words if w in ARMOURS), "")
    after = words[words.index(insulation) + 1:] if insulation in words else words
    sheath = next((w for w in after if w in SHEATHS), "PVC")
    earth_size = None
    e = _EARTH_RE.search(upper[match.end() - 1:] if "+" in rest else "")
    if e:
        earth_size = _size(e.group(2))
    return CableSpec(cores=int(match.group(2)), size=_size(match.group(3)),
                     runs=int(match.group(1)) if match.group(1) else 1, material=material,
                     insulation=insulation, armour=armour, sheath=sheath,
                     earth_size=earth_size)


def from_vd(cable):
    """CableSpec from a vdrop.parse.Cable (its insulation name gives the
    build), None for None."""
    if cable is None or cable.size is None:
        return None
    spec = parse(u"%dCx%s %s" % (cable.cores or 4, _trim(cable.size), cable.insulation or ""))
    spec.runs = cable.runs or 1
    if not cable.insulation:
        spec.armour = ""
    return spec
