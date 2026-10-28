# -*- coding: utf-8 -*-
"""Draw a sample fire alarm loop diagram (FA Riser from the addresses in
the devices' Comments) as SVG, without Revit.

    python tools/preview_loop_diagram.py [out.svg] [pixels per mm]
"""
from __future__ import print_function

import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "Electrical.extension", "lib"))
sys.path.insert(0, HERE)

from firealarm.loop_diagram import Device, loop_diagram  # noqa: E402
from firealarm.loop_symbols import dot  # noqa: E402
from preview_svg import to_svg  # noqa: E402

# the office drawing SUBSTATION2 FIRE ALARM SCHEMATIC (03 and 04 added)
LOOP1 = ("MCP MM MCP HD MCP HD MCP HD MM HD MCP SD SD HD MM HD HD MCP MCP MM FD HY HD HD HY FD "
         "MCP MM MCP MM FD HY HD MCP SD SD MM MM SD").split()
WP = (2, 6, 8, 10)          # weatherproof sounders with beacon


def sample():
    devices = [Device("L1/%s-%02d" % (c, k + 1)) for k, c in enumerate(LOOP1)]
    devices += [Device("L1/SB-%02d" % k, name="SOUNDER : W/P" if k in WP else "SOUNDER")
                for k in range(1, 14)]
    devices.append(Device(""))
    return devices


def main(argv):
    out = argv[1] if len(argv) > 1 else "loop_diagram.svg"
    scale = float(argv[2]) if len(argv) > 2 else 4.0
    diagram = loop_diagram(sample(), "SFACP-AUD-SS-02",
                           links="FROM TRAIN SERVICING SUPPORT AND FACILITIES; TO ENGINE SHED")
    with io.open(out, "w", encoding="utf-8") as f:
        drawing = diagram.drawing
        fills, drawing.fills = drawing.fills, None     # filled regions in Revit: rings here
        for cx, cy, r, style in fills:
            dot(drawing, cx, cy, r, style, step=0.03)
        f.write(to_svg(drawing, px_per_mm=scale))
    for w in diagram.warnings:
        print("warning:", w)
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv)
