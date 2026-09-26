# -*- coding: utf-8 -*-
"""Draw the dimension strings of the sample rooms as SVG, without Revit.

    python tools/preview_dims.py [out.svg] [spacing]

Each room gets smoke detectors as the Smoke Detectors button lays them
out (9 m spacing), and is drawn twice: a string along every row and
column, and only the strings needed to fix every detector. The last
rooms have sockets on their walls instead. Lengths are in millimetres, as
on the drawings.
"""
from __future__ import division, print_function

import io
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "Electrical.extension", "lib"))
sys.path.insert(0, HERE)

from dims.chains import Device, plan, segment_walls, text_side  # noqa: E402
from firealarm.layout import layout_detectors, segments  # noqa: E402
from sample_rooms import ROOMS, rect  # noqa: E402

PX = 9.0            # pixels per metre
PANEL = 44.0        # panel size (m)
COLUMNS = 4
OFFSET = 0.5        # m, dimension line from the devices (5 mm on paper at 1:100)
EXTRA = 0.4         # m, more when the text would face the devices (4 mm at 1:100)
TICK = 0.3          # m, tick mark length

# name -> rooms, each room its loops (outline first, then holes)
SAMPLES = [(name, [loops]) for name, loops in ROOMS] + [
    ("Two offices, 200 mm wall", [[rect(0, 0, 12, 9)], [rect(12.2, 0, 24.2, 9)]]),
]

# name -> rooms, sockets on their walls: (x, y, facing into the room)
WALL_SAMPLES = [
    ("Bedroom, sockets on the walls", [[rect(0, 0, 4.5, 4.0)]],
     [(0.6, 0.0, (0, 1)), (3.9, 0.0, (0, 1)), (2.25, 4.0, (0, -1)), (0.0, 2.8, (1, 0)),
      (4.5, 1.2, (-1, 0))]),
    ("Two offices, sockets on one wall line", [[rect(0, 0, 5, 4)], [rect(5.2, 0, 10.2, 4)]],
     [(1.2, 0.0, (0, 1)), (3.6, 0.0, (0, 1)), (6.4, 0.0, (0, 1)), (9.0, 0.0, (0, 1)),
      (2.5, 4.0, (0, -1)), (7.7, 4.0, (0, -1))]),
]


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _devices(rooms, spacing):
    """Detectors of every room, turned with the room's layout."""
    found = []
    for loops in rooms:
        lay = layout_detectors(loops, spacing)
        for x, y in lay.points:
            n = len(found)
            found.append(Device(n, x, y, [(lay.angle, (n, 0)), (lay.angle + math.pi / 2, (n, 1))]))
    return found


def _sockets(points):
    """Devices on walls: one centre plane, along the wall."""
    return [Device(n, x, y, [(math.atan2(f[0], -f[1]), (n, 0))], facing=f)
            for n, (x, y, f) in enumerate(points)]


def _panel(name, rooms, spacing, every_row, sockets=None, zoom=1.0):
    loops = [loop for room in rooms for loop in room]
    xs = [p[0] for loop in loops for p in loop]
    ys = [p[1] for loop in loops for p in loop]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2

    def pt(p):
        return (PANEL / 2 * PX + (p[0] - cx) * PX * zoom,
                (PANEL / 2 + 2) * PX - (p[1] - cy) * PX * zoom)

    devices = _devices(rooms, spacing) if sockets is None else _sockets(sockets)
    result = plan(devices, segment_walls(segments(loops)), every_row=every_row)
    out = []
    d = " ".join("M " + " L ".join("%.1f %.1f" % pt(p) for p in loop) + " Z" for loop in loops)
    out.append('<path d="%s" class="room"/>' % d)
    for chain in result.chains:
        out.extend(_chain(chain, pt))
    for device in devices:
        x, y = pt((device.x, device.y))
        out.append('<circle cx="%.1f" cy="%.1f" r="4" class="dev"/>' % (x, y))
    mode = "every row and column" if every_row else "only what is needed"
    notes = []
    if result.alone:
        notes.append("%d not dimensioned one way" % len(set(id(d) for d, _ in result.alone)))
    if result.skew:
        notes.append("%d ends at walls not square" % result.skew)
    out.append('<text x="8" y="16" class="t">%s</text>' % _esc(name))
    out.append('<text x="8" y="32" class="s">%s: %d strings, %d %s%s</text>'
               % (mode, len(result.chains), len(devices), "sockets" if sockets else "detectors",
                  (", " + ", ".join(notes)) if notes else ""))
    return out


def _chain(chain, pt):
    out = []
    c, s = math.cos(chain.angle), math.sin(chain.angle)
    nx, ny = text_side(c, s)
    across = chain.across + chain.side * (OFFSET + (0.0 if chain.text_away else EXTRA))
    (x0, y0), (x1, y1) = chain.line(OFFSET, EXTRA)
    out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" class="dim"/>' % (pt((x0, y0)) + pt((x1, y1))))
    # reading direction of the text, and its angle on screen
    rx, ry = (c, s) if (c > 1e-9 or (abs(c) <= 1e-9 and s > 0)) else (-c, -s)
    rotate = -math.degrees(math.atan2(ry, rx))
    for stop in chain.stops:
        if stop.is_wall:
            base = chain.point(stop.at, chain.across)
        else:
            base = (stop.device.x, stop.device.y)
        on = chain.point(stop.at, across)
        out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" class="wit"/>' % (pt(base) + pt(on)))
        # tick: a short slash at 45 degrees to the string
        tx, ty = (c - s) * TICK / 2 / math.sqrt(2), (s + c) * TICK / 2 / math.sqrt(2)
        out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" class="tick"/>'
                   % (pt((on[0] - tx, on[1] - ty)) + pt((on[0] + tx, on[1] + ty))))
    for a, b in zip(chain.stops, chain.stops[1:]):
        mx, my = chain.point((a.at + b.at) / 2, across)
        x, y = pt((mx + nx * 0.25, my + ny * 0.25))
        out.append('<text x="%.1f" y="%.1f" transform="rotate(%.1f %.1f %.1f)" class="v">%d</text>'
                   % (x, y, rotate, x, y, round((b.at - a.at) * 1000)))
    return out


def to_svg(spacing=9.0):
    panels = []
    for name, rooms in SAMPLES:
        for every_row in (True, False):
            panels.append(_panel(name, rooms, spacing, every_row))
    for name, rooms, sockets in WALL_SAMPLES:
        panels.append(_panel(name, rooms, spacing, True, sockets, zoom=3.0))
    size = PANEL * PX
    rows = int(math.ceil(len(panels) / COLUMNS))
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" style="background:#fff">'
           % (size * COLUMNS, size * rows),
           '<style>.room{fill:none;stroke:#222;stroke-width:2;fill-rule:evenodd}'
           '.dev{fill:#d9480f}'
           '.dim{stroke:#1c7ed6;stroke-width:1}.wit{stroke:#1c7ed6;stroke-width:0.6;opacity:0.6}'
           '.tick{stroke:#1c7ed6;stroke-width:1.6}'
           '.v{font:8px Arial;fill:#1c7ed6;text-anchor:middle}'
           '.t{font:bold 13px Arial;fill:#222}.s{font:12px Arial;fill:#555}</style>']
    for k, body in enumerate(panels):
        x, y = (k % COLUMNS) * size, (k // COLUMNS) * size
        out.append('<g transform="translate(%.1f %.1f)">' % (x, y))
        out.append('<rect x="1" y="1" width="%.1f" height="%.1f" fill="none" stroke="#e5e5e5"/>'
                   % (size - 2, size - 2))
        out.extend(body)
        out.append('</g>')
    out.append('</svg>')
    return "\n".join(out)


def main(argv):
    out = argv[1] if len(argv) > 1 else "dims.svg"
    spacing = float(argv[2]) if len(argv) > 2 else 9.0
    with io.open(out, "w", encoding="utf-8") as f:
        f.write(to_svg(spacing))
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv)
