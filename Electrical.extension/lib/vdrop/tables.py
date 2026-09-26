# -*- coding: utf-8 -*-
"""Cable data of the office voltage drop sheet (ref_XLPE, DUCAB copper
XLPE cables): current ratings per installation, mV/A/m and the derating
factors Ca (temperature), Cb (laying depth) and Cr (soil thermal
resistivity).

The office sheet's ref_PVC tab is a copy of ref_XLPE, so there is no real
PVC data and only the XLPE cables are offered here.
"""
from __future__ import division

TRAY = "Cable Tray"
DUCT = "Duct Bank"
GROUND = "Ground"
INSTALLATIONS = (TRAY, DUCT, GROUND)

ARMOURED = "armoured"
UNARMOURED = "unarmoured"

# Cable names of the office sheet -> rating table.
INSULATIONS = (
    ("XLPE/SWA/PVC", ARMOURED),
    ("XLPE/SWA/LS0H", ARMOURED),
    ("MICA/XLPE/SWA/LS0H", ARMOURED),
    ("XLPE/PVC", UNARMOURED),
    ("XLPE/LS0H", UNARMOURED),
)
INSULATION_NAMES = tuple(name for name, _ in INSULATIONS)
DEFAULT_INSULATION = "XLPE/SWA/PVC"

# Current rating of one cable (A): size mm² -> (Ground, Duct Bank, Cable Tray).
# Keyed by (table, single core).
_COLUMNS = (GROUND, DUCT, TRAY)
AMPACITY = {
    (ARMOURED, False): {
        4: (49, 36, 36), 6: (62, 43, 45), 10: (60, 50, 55), 16: (115, 94, 99),
        25: (150, 125, 131), 35: (180, 150, 162), 50: (215, 175, 197),
        70: (265, 215, 251), 95: (315, 260, 304), 120: (360, 300, 353),
        150: (405, 335, 406), 185: (460, 380, 463), 240: (530, 440, 546),
        300: (590, 495, 628), 400: (667, 570, 728), 500: (720, 605, 800),
    },
    (ARMOURED, True): {
        50: (235, 235, 222), 70: (290, 280, 285), 95: (345, 330, 346),
        120: (390, 370, 402), 150: (435, 405, 436), 185: (490, 440, 529),
        240: (560, 500, 625), 300: (630, 550, 720), 400: (700, 580, 815),
        500: (770, 620, 918), 630: (840, 670, 1027),
    },
    (UNARMOURED, False): {
        16: (120, 93, 100), 25: (145, 125, 127), 35: (180, 145, 158),
        50: (215, 175, 192), 70: (265, 215, 246), 95: (315, 255, 298),
        120: (365, 300, 346), 150: (405, 330, 399), 185: (465, 380, 456),
        240: (540, 440, 538), 300: (600, 500, 621), 400: (675, 575, 741),
        500: (730, 610, 814),
    },
    (UNARMOURED, True): {
        50: (230, 240, 209), 70: (285, 295, 270), 95: (335, 345, 330),
        120: (385, 395, 385), 150: (435, 445, 445), 185: (490, 500, 511),
        240: (570, 580, 606), 300: (650, 650, 701), 400: (740, 750, 820),
        500: (840, 850, 936), 630: (960, 960, 1069),
    },
}

# Three phase voltage drop, mV/A/m, keyed by single core. The office sheet
# takes it from the armoured table for every cable.
MV_PER_A_M = {
    False: {
        4: 8.3, 6: 5.5, 10: 4.0, 16: 2.5, 25: 1.65, 35: 1.15, 50: 0.865,
        70: 0.607, 95: 0.446, 120: 0.366, 150: 0.303, 185: 0.255, 240: 0.211,
        300: 0.185, 400: 0.166, 500: 0.166,
    },
    True: {
        50: 0.87, 70: 0.62, 95: 0.47, 120: 0.39, 150: 0.33, 185: 0.28,
        240: 0.24, 300: 0.21, 400: 0.2, 500: 0.18, 630: 0.17,
    },
}

SIZES = sorted(set(s for table in AMPACITY.values() for s in table))

# Ca, ambient temperature (°C) -> (in air: Cable Tray, in ground / ducts).
TEMPERATURE_FACTORS = {
    30: (1.0, 0.89), 35: (0.96, 0.86), 40: (0.91, 0.82), 45: (0.87, 0.76),
    50: (0.82, 0.75),
}
TEMPERATURES = sorted(TEMPERATURE_FACTORS)

# Cb, laying depth (mm) -> factor for sizes up to 50 mm², up to 300 mm², larger.
# 0 means not applied. Cable trays are never derated for depth.
_DEPTH_GROUND = {
    0: (1.0, 1.0, 1.0), 500: (1.0, 1.0, 1.0), 600: (0.99, 0.98, 0.97),
    800: (0.97, 0.96, 0.94), 1000: (0.95, 0.93, 0.92), 1250: (0.94, 0.92, 0.89),
    1500: (0.93, 0.9, 0.87), 1750: (0.92, 0.89, 0.86), 2000: (0.91, 0.88, 0.85),
}
_DEPTH_DUCT = {
    0: (1.0, 1.0, 1.0), 500: (1.0, 1.0, 1.0), 600: (0.98, 0.98, 0.98),
    800: (0.95, 0.95, 0.95), 1000: (0.93, 0.93, 0.93), 1250: (0.91, 0.91, 0.91),
    1500: (0.89, 0.89, 0.89), 1750: (0.88, 0.88, 0.88), 2000: (0.87, 0.87, 0.87),
}
DEPTH_FACTORS = {
    (False, GROUND): _DEPTH_GROUND, (True, GROUND): _DEPTH_GROUND,
    (False, DUCT): _DEPTH_DUCT, (True, DUCT): _DEPTH_DUCT,
}
DEPTH_BANDS = (50, 300)
DEPTHS = sorted(_DEPTH_GROUND)

# Cr, soil thermal resistivity (K.m/W) -> factor per size band. 0 means not
# applied. Bands as the table headings: multicore up to 16 / 150 mm²,
# single core up to 150 / 300 mm².
RESISTIVITY_FACTORS = {
    (False, GROUND): {
        0: (1.0, 1.0, 1.0), 0.8: (1.12, 1.14, 1.015), 0.9: (1.08, 1.1, 1.1),
        1.0: (1.05, 1.06, 1.07), 1.5: (0.93, 0.92, 0.92), 2.0: (0.84, 0.82, 0.81),
        2.5: (0.77, 0.75, 0.74), 3.0: (0.72, 0.69, 0.67),
    },
    (False, DUCT): {
        0: (1.0, 1.0, 1.0), 0.8: (1.04, 1.06, 1.07), 0.9: (1.03, 1.04, 1.05),
        1.0: (1.02, 1.03, 1.03), 1.5: (0.97, 0.95, 0.95), 2.0: (0.92, 0.9, 0.88),
        2.5: (0.88, 0.85, 0.83), 3.0: (0.86, 0.81, 0.78),
    },
    (True, GROUND): {
        0: (1.0, 1.0, 1.0), 0.8: (1.16, 1.17, 1.17), 0.9: (1.12, 1.12, 1.12),
        1.0: (1.07, 1.07, 1.07), 1.5: (0.91, 0.91, 0.91), 2.0: (0.81, 0.8, 0.8),
        2.5: (0.73, 0.73, 0.73), 3.0: (0.66, 0.66, 0.66),
    },
    (True, DUCT): {
        0: (1.0, 1.0, 1.0), 0.8: (1.1, 1.11, 1.12), 0.9: (1.07, 1.08, 1.08),
        1.0: (1.04, 1.05, 1.05), 1.5: (0.94, 0.93, 0.93), 2.0: (0.86, 0.85, 0.84),
        2.5: (0.8, 0.79, 0.78), 3.0: (0.76, 0.75, 0.74),
    },
}
RESISTIVITY_BANDS = {False: (16, 150), True: (150, 300)}
RESISTIVITIES = sorted(RESISTIVITY_FACTORS[(False, GROUND)])

# Breaker ratings of the office sheet.
BREAKER_RATINGS = (16, 20, 25, 32, 40, 50, 63, 80, 100, 125, 150, 160, 200, 220,
                   250, 320, 400, 500, 630, 800, 1000, 1250, 1600, 2000, 2500,
                   3200, 4000, 5000)


def table_of(insulation):
    """ARMOURED / UNARMOURED for an office cable name, or None."""
    for name, table in INSULATIONS:
        if name == insulation:
            return table
    return None


def _band(size, bands):
    for i, limit in enumerate(bands):
        if size <= limit:
            return i
    return len(bands)


def _key(value, table):
    """The table key equal to `value` (tolerant to 35 vs 35.0), or None."""
    for key in table:
        if abs(key - value) < 1e-6:
            return key
    return None


def ampacity(insulation, single_core, size, installation):
    """Rating of one cable (A) or None when the table has no value."""
    table = AMPACITY.get((table_of(insulation), bool(single_core)), {})
    size_key = _key(size, table) if size is not None else None
    if size_key is None or installation not in _COLUMNS:
        return None
    return table[size_key][_COLUMNS.index(installation)]


def mv_per_a_m(single_core, size):
    """Three phase mV/A/m of one cable or None."""
    table = MV_PER_A_M[bool(single_core)]
    size_key = _key(size, table) if size is not None else None
    return table[size_key] if size_key is not None else None


def temperature_factor(temperature, installation):
    key = _key(temperature, TEMPERATURE_FACTORS)
    if key is None:
        return None
    air, ground = TEMPERATURE_FACTORS[key]
    return air if installation == TRAY else ground


def depth_factor(depth, single_core, installation, size):
    table = DEPTH_FACTORS.get((bool(single_core), installation))
    if table is None:
        return 1.0
    key = _key(depth, table)
    if key is None:
        return None
    return table[key][_band(size, DEPTH_BANDS)]


def resistivity_factor(resistivity, single_core, installation, size):
    table = RESISTIVITY_FACTORS.get((bool(single_core), installation))
    if table is None:
        return 1.0
    key = _key(resistivity, table)
    if key is None:
        return None
    return table[key][_band(size, RESISTIVITY_BANDS[bool(single_core)])]


def next_breaker(amps):
    """Smallest office breaker rating >= amps, or None."""
    for rating in BREAKER_RATINGS:
        if rating >= amps - 1e-9:
            return rating
    return None
