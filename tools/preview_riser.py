# -*- coding: utf-8 -*-
"""Draw the fire alarm riser of the sample building as SVG, without Revit.

    python tools/preview_riser.py [out.svg] [pixels per mm]
"""
from __future__ import print_function

import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "Electrical.extension", "lib"))
sys.path.insert(0, HERE)

from firealarm.riser import riser_layout  # noqa: E402
from preview_svg import to_svg  # noqa: E402
import sample_riser  # noqa: E402


def main(argv):
    out = argv[1] if len(argv) > 1 else "riser.svg"
    scale = float(argv[2]) if len(argv) > 2 else 4.0
    floors, segments, panel_floor, location = sample_riser.build()
    riser = riser_layout(floors, segments, panel_floor, location)
    with io.open(out, "w", encoding="utf-8") as f:
        f.write(to_svg(riser.drawing, px_per_mm=scale))
    for w in riser.warnings:
        print("warning:", w)
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv)
