# -*- coding: utf-8 -*-
"""Draw sample fire alarm loops as SVG, without Revit.

    python tools/preview_loops.py [out.svg] [devices per loop]

Devices are circles, the start a square; each loop has its colour.
"""
from __future__ import division, print_function

import io
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "Electrical.extension", "lib"))
sys.path.insert(0, HERE)

from firealarm.layout import layout_detectors  # noqa: E402
from firealarm.loops import START, line_between, plan_loops  # noqa: E402
from sample_rooms import rect  # noqa: E402

PX = 7.0                # pixels per metre
SYMBOL = 0.45           # device symbol radius (m)
COLOURS = ["#e03131", "#1c7ed6", "#2f9e44", "#ae3ec9", "#f08c00", "#0c8599"]


def samples():
    rng = random.Random(3)
    office = layout_detectors([rect(0, 0, 60, 40)], 4.5).points
    scattered = [(rng.uniform(0, 90), rng.uniform(0, 55)) for _ in range(250)]
    floor = layout_detectors([[(0, 0), (70, 0), (70, 20), (30, 20), (30, 50), (0, 50)]], 5.0).points
    return [
        ("Open office, %d heat detectors, panel at the entrance" % len(office),
         office, (0.0, 20.0), (60, 40)),
        ("%d devices, panel at the bottom" % len(scattered), scattered, (45.0, 0.0), (90, 55)),
        ("L-shaped floor, %d devices, loop from the first device" % len(floor),
         floor, 0, (70, 50)),
    ]


def _panel(name, points, start, size, max_devices):
    w, h = size
    loops = plan_loops(points, start, max_devices)
    start_xy = start if isinstance(start, tuple) else points[start]
    margin = 4.0

    def pt(p):
        return (p[0] + margin) * PX, (h + margin - p[1]) * PX + 40

    out = ['<svg x="0" y="0" width="%d" height="%d">' % ((w + 2 * margin) * PX,
                                                          (h + 2 * margin) * PX + 40)]
    out.append('<text x="8" y="18" class="t">%s</text>' % name)
    out.append('<text x="8" y="34" class="s">%s</text>' % ", ".join(
        "Loop %d: %d devices, %.0f m" % (k + 1, len(l.devices), l.length) for k, l in enumerate(loops)))
    for k, loop in enumerate(loops):
        colour = COLOURS[k % len(COLOURS)]
        for a, b in loop.segments():
            pa = start_xy if a == START else points[a]
            pb = start_xy if b == START else points[b]
            box_a = None if a == START and isinstance(start, tuple) else \
                (pa[0] - SYMBOL, pa[1] - SYMBOL, pa[0] + SYMBOL, pa[1] + SYMBOL)
            box_b = None if b == START and isinstance(start, tuple) else \
                (pb[0] - SYMBOL, pb[1] - SYMBOL, pb[0] + SYMBOL, pb[1] + SYMBOL)
            line = line_between(pa, pb, box_a, box_b, 0.8 if START in (a, b) else 0.0)
            if line:
                (x0, y0), (x1, y1) = pt(line[0]), pt(line[1])
                out.append('<line x1="%.1f" y1="%.1f" x2="%.1f" y2="%.1f" stroke="%s" '
                           'stroke-width="1.6"/>' % (x0, y0, x1, y1, colour))
    for p in points:
        x, y = pt(p)
        out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" class="d"/>' % (x, y, SYMBOL * PX))
    if isinstance(start, tuple):
        x, y = pt(start)
        out.append('<rect x="%.1f" y="%.1f" width="16" height="11" class="p"/>' % (x - 8, y - 5.5))
    else:
        x, y = pt(points[start])
        out.append('<circle cx="%.1f" cy="%.1f" r="%.1f" class="f"/>' % (x, y, SYMBOL * PX + 1.5))
    out.append('</svg>')
    return out, (w + 2 * margin) * PX, (h + 2 * margin) * PX + 40


def to_svg(max_devices=120):
    parts, x, height = [], 0.0, 0.0
    for name, points, start, size in samples():
        body, w, h = _panel(name, points, start, size, max_devices)
        parts.append('<g transform="translate(%.1f 0)">' % x)
        parts.extend(body)
        parts.append('</g>')
        x += w + 10
        height = max(height, h)
    return "\n".join(['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
                      'style="background:#fff">' % (x, height),
                      '<style>.t{font:bold 13px Arial;fill:#222}.s{font:12px Arial;fill:#555}'
                      '.d{fill:#fff;stroke:#333;stroke-width:1.2}'
                      '.f{fill:#fff;stroke:#111;stroke-width:2.4}'
                      '.p{fill:#333}</style>'] + parts + ['</svg>'])


def main(argv):
    out = argv[1] if len(argv) > 1 else "loops.svg"
    max_devices = int(argv[2]) if len(argv) > 2 else 120
    with io.open(out, "w", encoding="utf-8") as f:
        f.write(to_svg(max_devices))
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv)
