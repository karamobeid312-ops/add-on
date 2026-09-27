# -*- coding: utf-8 -*-
"""A sample building for the fire alarm riser preview and tests: podiums,
typical floors and a roof, loops as they would be drawn with Draw FA Loop
(some loops going on over two floors)."""
from firealarm.riser import Segment

TYPICAL = {"SD": 14, "SDF": 7, "HD": 9, "MCP": 7, "BELLS": 2, "STW": 2}


def build():
    """(floors [(name, elevation m)], segments, panel floor, panel location)"""
    names = ["GROUND FLOOR", "PODIUM 01", "PODIUM 02", "PODIUM 03", "PODIUM 04",
             "FIRST FLOOR", "SECOND FLOOR"] + \
        ["TYPICAL FLOOR %02d" % k for k in range(1, 12)] + ["ROOF FLOOR"]
    floors = [(n, 4.0 * k) for k, n in enumerate(names)]
    segments = [
        Segment(1, "PODIUM 01", {"SD": 16, "HD": 3, "SDF": 14, "CM": 5, "MCP": 6, "STW": 6,
                                 "HS": 5, "WFS": 4, "TS": 2}),
        Segment(2, "PODIUM 02", {"SD": 6, "HD": 2, "MCP": 2, "BELLS": 6}),
        Segment(2, "PODIUM 03", {"SD": 6, "HD": 2, "MCP": 2, "BELLS": 6}),
        Segment(3, "PODIUM 04", {"SD": 5, "HD": 1, "MCP": 2, "CM": 2, "STW": 6}),
        Segment(4, "FIRST FLOOR", {"SD": 13, "SDF": 6, "HD": 8, "MCP": 6, "BELLS": 2, "STW": 2}),
        Segment(4, "SECOND FLOOR", {"SD": 12, "SDF": 7, "HD": 9, "MCP": 7, "BELLS": 2, "STW": 2}),
    ]
    number = 5
    for k in range(1, 12, 2):           # typical floors in pairs, the roof with floor 11
        upper = "TYPICAL FLOOR %02d" % (k + 1) if k < 11 else "ROOF FLOOR"
        segments.append(Segment(number, "TYPICAL FLOOR %02d" % k, dict(TYPICAL)))
        segments.append(Segment(number, upper, dict(TYPICAL) if k < 11 else
                                {"SD": 4, "HD": 1, "SDF": 1, "CM": 2, "MCP": 4, "HS": 4}))
        number += 1
    return floors, segments, "GROUND FLOOR", "FIRE COMMAND ROOM (GF-154)"
