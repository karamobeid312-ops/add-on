# -*- coding: utf-8 -*-
"""Sample room outlines (metres) for the detector layout preview and tests."""
from __future__ import division

import math


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def rotated(loop, degrees):
    a = math.radians(degrees)
    c, s = math.cos(a), math.sin(a)
    return [(x * c - y * s, x * s + y * c) for x, y in loop]


def circle(r, n=48):
    return [(r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n)) for k in range(n)]


# name -> loops (outline first, then holes)
ROOMS = [
    ("Office 20 x 12 m", [rect(0, 0, 20, 12)]),
    ("L-shaped hall", [[(0, 0), (20, 0), (20, 10), (10, 10), (10, 20), (0, 20)]]),
    ("Rotated 30 deg, 15 x 10 m", [rotated(rect(0, 0, 15, 10), 30)]),
    ("Open office with shaft", [rect(0, 0, 24, 16), rect(10, 6, 14, 10)]),
    ("T-shaped lobby", [[(0, 10), (30, 10), (30, 16), (18, 16), (18, 40),
                         (12, 40), (12, 16), (0, 16)]]),
    ("L-shaped corridor, 2 m wide", [[(0, 0), (30, 0), (30, 2), (2, 2), (2, 20), (0, 20)]]),
    ("Round meeting room", [circle(8)]),
    ("Store 3 x 4 m", [rect(0, 0, 3, 4)]),
]
