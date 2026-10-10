# -*- coding: utf-8 -*-
"""Auto Size: the feeder cable and breaker of an SMDB or DB from its
connected load, by the office XLPE/SWA/PVC 4-core table:

    cable 4c mm²   max load kW   CB A
    10             15            40
    16             18 to 36      60 to 80
    ...
    4 x 300        801 to 1000   2000

A load goes on the first row whose top kW covers it. Where the table gives
a breaker range (60 to 80, 225 to 250) the lower standard rating is taken
for the lower half of the row's kW range, the upper one for the rest.
Earth: the phase size up to 16 mm², 16 mm² for 25 and 35, else half the
phase size rounded up to a standard size (120 -> 70).

Kept free of Revit so it runs under IronPython 2.7, CPython 3 and pytest.
"""
from __future__ import division

from sld import style
from sld.cablespec import CableSpec
from sld.model import frame_rating

# (top kW, runs, size mm², breaker A, upper breaker A or None, kW splitting them)
TABLE = (
    (15, 1, 10, 40, None, None),
    (36, 1, 16, 63, 80, 27),
    (52, 1, 25, 100, None, None),
    (62, 1, 35, 125, None, None),
    (80, 1, 50, 160, None, None),
    (100, 1, 70, 200, None, None),
    (128, 1, 95, 225, 250, 114.5),
    (130, 1, 120, 250, None, None),
    (150, 1, 150, 300, None, None),
    (175, 1, 185, 350, None, None),
    (200, 1, 240, 400, None, None),
    (250, 1, 300, 500, None, None),
    (300, 2, 150, 600, None, None),
    (400, 2, 240, 800, None, None),
    (500, 2, 300, 1000, None, None),
    (600, 3, 240, 1200, None, None),
    (800, 4, 240, 1600, None, None),
    (1000, 4, 300, 2000, None, None),
)
MAX_KW = TABLE[-1][0]
SIZES = (1.5, 2.5, 4, 6, 10, 16, 25, 35, 50, 70, 95, 120, 150, 185, 240, 300, 400)


def earth_size(size):
    if size <= 16:
        return size
    if size <= 35:
        return 16
    half = size / 2
    return next((s for s in SIZES if s >= half), SIZES[-1])


def breaker_for(trip):
    """(frame AF, device): an MCCB on the smallest standard frame, an ACB
    above the largest MCCB frame."""
    if trip > style.MCCB_FRAMES[-1]:
        return frame_rating(trip, style.ACB_FRAMES), style.MAIN_INCOMER_DEVICE
    return frame_rating(trip), style.WAY_DEVICE


class Sizing(object):
    def __init__(self, kw, cable, trip, frame, device=style.WAY_DEVICE):
        self.kw = kw
        self.cable = cable          # CableSpec
        self.trip = trip
        self.frame = frame
        self.device = device

    def __repr__(self):
        return "Sizing(%s kW: %s, %sAT/%sAF)" % (self.kw, self.cable.text(), self.trip,
                                                 self.frame)


def size_for(kw):
    """Sizing for a connected load in kW; None when it is not known (or 0)
    or more than the table covers."""
    if kw is None or kw <= 0 or kw > MAX_KW:
        return None
    for top, runs, size, trip, upper, split in TABLE:
        if kw <= top:
            if upper is not None and kw > split:
                trip = upper
            cable = CableSpec(cores=4, size=size, runs=runs, material="CU",
                              insulation="XLPE", armour="SWA", sheath="PVC",
                              earth_size=earth_size(size))
            frame, device = breaker_for(trip)
            return Sizing(kw, cable, trip, frame, device)
    return None
