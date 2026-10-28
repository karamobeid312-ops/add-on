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
from preview_svg import to_svg  # noqa: E402

LOOP1 = ("MCP MM HD HD MCP HD MCP HD MM HD MCP SD SD HD SD MCP MM HD SD HD MCP MM HD SD SD "
         "MCP MM MCP MM MCP FD HY HD MCP SD SD MM MM SD").split()
LOOP2 = ["SB"] * 13


def sample():
    devices = [Device("L1/%s-%02d" % (c, k + 1)) for k, c in enumerate(LOOP1)]
    devices += [Device("L2/%s-%02d" % (c, k + 1)) for k, c in enumerate(LOOP2)]
    devices.append(Device(""))
    return devices


def main(argv):
    out = argv[1] if len(argv) > 1 else "loop_diagram.svg"
    scale = float(argv[2]) if len(argv) > 2 else 4.0
    diagram = loop_diagram(sample(), "SFACP-AUD-SS-02")
    with io.open(out, "w", encoding="utf-8") as f:
        f.write(to_svg(diagram.drawing, px_per_mm=scale))
    for w in diagram.warnings:
        print("warning:", w)
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv)
