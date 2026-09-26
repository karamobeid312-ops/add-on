# -*- coding: utf-8 -*-
"""Draw the detector layout of the sample rooms as SVG, without Revit.

    python tools/preview_detectors.py [out.svg] [smoke spacing] [heat spacing]

Each room is drawn twice (smoke, heat): outline, grid bays (dashed),
detectors and the circle each one covers.
"""
from __future__ import division, print_function

import io
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "Electrical.extension", "lib"))
sys.path.insert(0, HERE)

from firealarm.layout import layout_detectors  # noqa: E402
from sample_rooms import ROOMS  # noqa: E402

PX = 9.0            # pixels per metre
PANEL = 44.0        # panel size (m)
COLUMNS = 4


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _rot(p, a):
    c, s = math.cos(a), math.sin(a)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


def _panel(name, loops, lay, colour, kind):
    xs = [p[0] for loop in loops for p in loop]
    ys = [p[1] for loop in loops for p in loop]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    off = (PANEL / 2 - cx, PANEL / 2 - 2 - cy)

    def pt(p):
        return (p[0] + off[0]) * PX, (PANEL - (p[1] + off[1])) * PX

    out = []
    for g in lay.grids:
        for i in range(g.nx + 1):
            a = pt(_rot((g.x0 + i * g.px, g.y0), lay.angle))
            b = pt(_rot((g.x0 + i * g.px, g.y0 + g.ny * g.py), lay.angle))
            out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" class="grid"/>' % (a + b))
        for j in range(g.ny + 1):
            a = pt(_rot((g.x0, g.y0 + j * g.py), lay.angle))
            b = pt(_rot((g.x0 + g.nx * g.px, g.y0 + j * g.py), lay.angle))
            out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" class="grid"/>' % (a + b))
    d = " ".join("M " + " L ".join("%.1f %.1f" % pt(p) for p in loop) + " Z" for loop in loops)
    out.append('<path d="%s" class="room"/>' % d)
    for p in lay.points:
        x, y = pt(p)
        out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" fill="%s" fill-opacity="0.07" '
                   'stroke="%s" stroke-opacity="0.35" stroke-width="0.8"/>' % (x, y, lay.reach * PX, colour, colour))
    for p in lay.points:
        x, y = pt(p)
        out.append('<circle cx="%.1f" cy="%.1f" r="4" fill="%s"/>' % (x, y, colour))
    status = "covered" if lay.uncovered == 0 else "%d points NOT covered" % lay.uncovered
    out.append('<text x="8" y="16" class="t">%s</text>' % _esc(name))
    out.append('<text x="8" y="32" class="s">%d %s detectors, %.1f m spacing, %s</text>'
               % (len(lay.points), kind, lay.spacing, status))
    return out


def to_svg(smoke=9.0, heat=4.5):
    panels = []
    for name, loops in ROOMS:
        for spacing, colour, kind in ((smoke, "#d9480f", "smoke"), (heat, "#1c7ed6", "heat")):
            panels.append(_panel(name, loops, layout_detectors(loops, spacing), colour, kind))
    size = PANEL * PX
    rows = int(math.ceil(len(panels) / COLUMNS))
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" style="background:#fff">'
           % (size * COLUMNS, size * rows),
           '<style>.room{fill:none;stroke:#222;stroke-width:2;fill-rule:evenodd}'
           '.grid{stroke:#999;stroke-width:0.7;stroke-dasharray:4 3}'
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
    out = argv[1] if len(argv) > 1 else "detectors.svg"
    smoke = float(argv[2]) if len(argv) > 2 else 9.0
    heat = float(argv[3]) if len(argv) > 3 else 4.5
    with io.open(out, "w", encoding="utf-8") as f:
        f.write(to_svg(smoke, heat))
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv)
