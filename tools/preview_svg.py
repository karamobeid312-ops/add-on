# -*- coding: utf-8 -*-
"""Draw the LV schematic of the sample model (or any model data) as SVG,
without Revit, to check the layout.

    python tools/preview_svg.py [out.svg] [pixels per mm]

Open the SVG in a browser. Text is approximated with Arial.
"""
from __future__ import division, print_function

import io
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "Electrical.extension", "lib"))
sys.path.insert(0, HERE)

from sld.geometry import BOTTOM, CENTER, MIDDLE, RIGHT, TOP  # noqa: E402
from sld.layout import layout_schematic  # noqa: E402
from sld.model import build_schematic  # noqa: E402


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def to_svg(drawing, margin=20.0, px_per_mm=4.0):
    x0, y0, x1, y1 = drawing.bounds()
    x0, y0, x1, y1 = x0 - margin, y0 - margin, x1 + margin, y1 + margin
    w, h = (x1 - x0), (y1 - y0)
    out = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
           'viewBox="%f %f %f %f" style="background:#fff">' % (w * px_per_mm, h * px_per_mm, x0, -y1, w, h),
           '<g stroke="#000" stroke-width="0.18" fill="none">']
    styles = getattr(drawing, "styles", {})

    def colour(item):
        rgb = styles.get(getattr(item, "style", None))
        return ' stroke="#%02x%02x%02x"' % tuple(rgb) if rgb else ""
    for l in drawing.lines:
        out.append('<line x1="%.3f" y1="%.3f" x2="%.3f" y2="%.3f"%s/>'
                   % (l.x1, -l.y1, l.x2, -l.y2, colour(l)))
    for a in drawing.arcs:
        sx, sy = a.point(a.a0)
        ex, ey = a.point(a.a1)
        large = 1 if (a.a1 - a.a0) > math.pi else 0
        out.append('<path d="M %.3f %.3f A %.3f %.3f 0 %d 0 %.3f %.3f"%s/>'
                   % (sx, -sy, a.r, a.r, large, ex, -ey, colour(a)))
    out.append('</g><g font-family="Arial" fill="#000">')
    for t in drawing.texts:
        lines = t.lines
        lh = t.size * 1.6
        anchor = {CENTER: "middle", RIGHT: "end"}.get(t.align, "start")
        # y of the first baseline in the text's own frame (y down)
        # (text size = capital height, as in Revit)
        cap = t.size
        span = cap + lh * (len(lines) - 1)
        first = {TOP: cap, MIDDLE: -span / 2 + cap, BOTTOM: -span + cap}[t.valign]
        rot = -math.degrees(t.rotation)
        out.append('<text transform="translate(%.3f %.3f) rotate(%.2f)" font-size="%.2f" text-anchor="%s">'
                   % (t.x, -t.y, rot, t.size / 0.716, anchor))
        for i, line in enumerate(lines):
            out.append('<tspan x="0" y="%.3f">%s</tspan>' % (first + i * lh, _esc(line)))
        out.append('</text>')
    out.append('</g></svg>')
    return "\n".join(out)


def main(argv):
    import sample_al_yasat
    out = argv[1] if len(argv) > 1 else "preview.svg"
    scale = float(argv[2]) if len(argv) > 2 else 4.0
    equipment, circuits = sample_al_yasat.build()
    schematic = build_schematic(equipment, circuits)
    layout = layout_schematic(schematic)
    with io.open(out, "w", encoding="utf-8") as f:
        f.write(to_svg(layout.drawing, px_per_mm=scale))
    for w in schematic.warnings:
        print("warning:", w)
    print("wrote", out)


if __name__ == "__main__":
    main(sys.argv)
