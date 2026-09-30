# -*- coding: utf-8 -*-
"""Draws the ribbon button icons (icon.png, and icon.dark.png for Revit's
dark theme) into every pushbutton folder. Standard library only.

    python tools/make_icons.py

Shapes are drawn in a 32 x 32 grid, scaled to SIZE pixels, with 4 x 4
anti-aliasing.
"""
from __future__ import division

import math
import os
import struct
import zlib

SIZE = 96          # pixels; pyRevit scales it down for the ribbon
SCALE = SIZE / 32.0
AA = 4             # samples per pixel along each axis

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")

# colours that read on the light (#F0F0F0) and dark (#3B4453) ribbons
BLUE = (30, 136, 229)
AMBER = (255, 179, 0)
RED = (229, 57, 53)
GREEN = (67, 160, 71)
GRAY = (120, 144, 156)
LIGHT = (207, 216, 220)
WHITE = (255, 255, 255)
INK = {"light": (55, 71, 79), "dark": (225, 230, 235)}


# ---------------------------------------------------------------- canvas

class Canvas(object):
    def __init__(self):
        self.px = [[(0, 0, 0, 0)] * SIZE for _ in range(SIZE)]

    def fill(self, paths, color, even_odd=False):
        """Fill closed paths (lists of (x, y) in the 32 grid)."""
        paths = [[(x * SCALE * AA, y * SCALE * AA) for x, y in p] for p in paths]
        ys = [y for p in paths for _, y in p]
        xs = [x for p in paths for x, _ in p]
        n = SIZE * AA
        y0, y1 = max(int(min(ys)), 0), min(int(max(ys)) + 1, n)
        cover = {}
        for sy in range(y0, y1):
            yc = sy + 0.5
            hits = []
            for p in paths:
                for (ax, ay), (bx, by) in zip(p, p[1:] + p[:1]):
                    if (ay <= yc < by) or (by <= yc < ay):
                        x = ax + (yc - ay) * (bx - ax) / (by - ay)
                        hits.append((x, 1 if by > ay else -1))
            hits.sort()
            wind = 0
            for i, (x, d) in enumerate(hits[:-1]):
                wind = wind + 1 if even_odd else wind + d
                inside = (wind % 2 == 1) if even_odd else wind != 0
                if not inside:
                    continue
                xa, xb = max(int(round(x)), 0), min(int(round(hits[i + 1][0])), n)
                row = sy // AA
                for sx in range(xa, xb):
                    key = (row, sx // AA)
                    cover[key] = cover.get(key, 0) + 1
        for (row, col), count in cover.items():
            self._blend(row, col, color, min(count / float(AA * AA), 1.0))

    def _blend(self, row, col, color, alpha):
        r, g, b, a = self.px[row][col]
        a0 = a / 255.0
        out = alpha + a0 * (1 - alpha)
        if out <= 0:
            return
        mix = [(c * alpha + d * a0 * (1 - alpha)) / out for c, d in zip(color, (r, g, b))]
        self.px[row][col] = tuple(int(round(v)) for v in mix) + (int(round(out * 255)),)

    def save(self, path):
        raw = b"".join(b"\x00" + b"".join(struct.pack("4B", *p) for p in row) for row in self.px)

        def chunk(kind, data):
            body = kind + data
            return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
        png = (b"\x89PNG\r\n\x1a\n" +
               chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0)) +
               chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
        with open(path, "wb") as f:
            f.write(png)


# ---------------------------------------------------------------- shapes

def circle(cx, cy, r, steps=48):
    return [(cx + r * math.cos(2 * math.pi * i / steps), cy + r * math.sin(2 * math.pi * i / steps))
            for i in range(steps)]


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def rounded(x0, y0, x1, y1, r, steps=8):
    pts = []
    for cx, cy, start in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90),
                          (x0 + r, y0 + r, 180)):
        for i in range(steps + 1):
            a = math.radians(start + 90.0 * i / steps)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def stroke(canvas, points, width, color, closed=False):
    """A polyline with round joints and ends."""
    pts = points + points[:1] if closed else points
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        length = math.hypot(bx - ax, by - ay) or 1
        nx, ny = -(by - ay) / length * width / 2, (bx - ax) / length * width / 2
        canvas.fill([[(ax + nx, ay + ny), (bx + nx, by + ny), (bx - nx, by - ny), (ax - nx, ay - ny)]],
                    color)
    for x, y in pts:
        canvas.fill([circle(x, y, width / 2, 16)], color)


def gear(cx, cy, outer, inner, hole, teeth=8):
    pts = []
    for i in range(teeth * 4):
        a = 2 * math.pi * (i - 0.5) / (teeth * 4)
        r = outer if i % 4 in (1, 2) else inner
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return [pts, circle(cx, cy, hole)]


def bolt(x, y, s=1.0):
    """Lightning bolt with its top at (x, y), s = scale."""
    shape = [(3.5, 0), (-1.5, 8.5), (1.5, 8.5), (-1, 15), (6.5, 5.5), (3, 5.5), (6, 0)]
    return [(x + px * s, y + py * s) for px, py in shape]


_FLAME = [(0, 0), (0.30, -0.05), (0.40, -0.22), (0.36, -0.45), (0.24, -0.64), (0.13, -0.80),
          (0.05, -1.0), (-0.05, -0.85), (-0.21, -0.70), (-0.35, -0.50), (-0.40, -0.28),
          (-0.32, -0.07)]


def flame(cx, cy, h):
    """Flame with its base centre at (cx, cy), h high."""
    return [(cx + x * h, cy + y * h) for x, y in _FLAME]


def wave(x, y0, y1, amplitude=1.6, turns=1.5):
    pts = []
    for i in range(25):
        t = i / 24.0
        pts.append((x + amplitude * math.sin(t * turns * 2 * math.pi), y0 + (y1 - y0) * t))
    return pts


def badge(canvas, color):
    canvas.fill([circle(24, 24, 7.6)], color)


# ---------------------------------------------------------------- icons

def calculate_vd(c, ink):
    stroke(c, [(5, 4), (5, 27), (28, 27)], 2.0, ink)
    stroke(c, [(8, 9), (13.5, 12), (19, 16.5), (25.5, 23)], 2.4, BLUE)
    for x, y in [(8, 9), (13.5, 12), (19, 16.5), (25.5, 23)]:
        c.fill([circle(x, y, 2.3)], BLUE)
    c.fill([bolt(20.5, 1.2, 0.95)], AMBER)


def vd_report(c, ink):
    page = [(5, 2.5), (18.5, 2.5), (24, 8), (24, 29.5), (5, 29.5)]
    c.fill([page], WHITE)
    c.fill([[(18.5, 2.5), (18.5, 8), (24, 8)]], LIGHT)
    stroke(c, page, 1.4, ink, closed=True)
    for y in (12, 15.5, 19, 22.5):
        stroke(c, [(8.5, y), (15.5, y)], 1.2, GRAY)
    stroke(c, [(11.5, 11), (11.5, 23.5)], 1.0, GRAY)
    c.fill([rounded(16.5, 17, 30.5, 31, 2.5)], RED)
    stroke(c, [(23.5, 19.8), (23.5, 27.2)], 2.0, WHITE)
    stroke(c, [(20.3, 24.2), (23.5, 27.4), (26.7, 24.2)], 2.0, WHITE)


def settings_gear(c, ink, color, glyph):
    c.fill(gear(13.5, 13.5, 12.5, 9.8, 4.2), GRAY, even_odd=True)
    badge(c, color)
    glyph(c)


def vd_settings(c, ink):
    settings_gear(c, ink, AMBER, lambda c: c.fill([bolt(21.2, 18.2, 0.8)], WHITE))


def generate_sld(c, ink):
    stroke(c, circle(16, 5.8, 4.2), 1.6, ink, closed=True)
    stroke(c, circle(16, 11.2, 4.2), 1.6, ink, closed=True)
    stroke(c, [(16, 15.4), (16, 19)], 1.6, ink)
    for x in (7, 16, 25):
        stroke(c, [(x, 19), (x, 28)], 1.6, ink)
        c.fill([rect(x - 2, 21.8, x + 2, 25.8)], BLUE)
        c.fill([circle(x, 28.6, 1.9)], ink)
    stroke(c, [(4, 19), (28, 19)], 2.8, BLUE)


def sld_settings(c, ink):
    def glyph(c):
        stroke(c, [(19.5, 21.5), (28.5, 21.5)], 1.6, WHITE)
        for x in (21, 24, 27):
            stroke(c, [(x, 21.5), (x, 27)], 1.3, WHITE)
    settings_gear(c, ink, BLUE, glyph)


def detector(c, ink):
    stroke(c, [(3, 4), (29, 4)], 1.6, ink)
    c.fill([rounded(8, 4.6, 24, 11, 3)], WHITE)
    stroke(c, rounded(8, 4.6, 24, 11, 3), 1.3, ink, closed=True)
    c.fill([circle(16, 8, 1.3)], RED)


def smoke_detectors(c, ink):
    detector(c, ink)
    for x, top in ((10, 16), (16, 14), (22, 16)):
        stroke(c, wave(x, 29, top), 2.0, GRAY)


def heat_detectors(c, ink):
    detector(c, ink)
    c.fill([flame(16, 30, 16)], RED)
    c.fill([flame(16, 30, 9)], AMBER)


def fa_loop(c, ink):
    c.fill([rounded(2, 12, 9, 21, 1.5)], ink)                   # panel
    c.fill([rect(3.8, 14, 7.2, 16.5)], RED)
    stops = [(9, 14), (15, 5), (25, 6), (28, 16), (24, 27), (14, 26), (9, 19)]
    stroke(c, stops, 1.6, RED)                                   # the loop, out and back
    for x, y in stops[1:-1]:                                     # devices
        c.fill([circle(x, y, 3.3)], WHITE)
        stroke(c, circle(x, y, 3.3, 24), 1.2, ink, closed=True)
        c.fill([circle(x, y, 1.1)], RED)


def fa_riser(c, ink):
    for y in (6, 13, 20):                                        # floors
        stroke(c, [(2, y), (30, y)], 1.0, GRAY)
    c.fill([rounded(3, 24, 17, 30, 1.2)], ink)                   # panel
    for x, top in ((6, 3.5), (9, 10.5), (12, 17.5)):             # loops up the riser
        stroke(c, [(x, 24), (x, top), (28, top)], 1.4, RED)
    for x, y in ((18, 3.5), (24, 10.5), (21, 17.5)):             # devices
        c.fill([[(x - 2.3, y), (x, y - 2.3), (x + 2.3, y), (x, y + 2.3)]], WHITE)
        stroke(c, [(x - 2.3, y), (x, y - 2.3), (x + 2.3, y), (x, y + 2.3)], 1.0, RED, closed=True)


def address_devices(c, ink):
    stroke(c, [(1.5, 25), (30.5, 25)], 1.6, RED)                 # loop line
    for x in (8, 22):                                            # devices
        c.fill([circle(x, 25, 4.2)], WHITE)
        stroke(c, circle(x, 25, 4.2, 24), 1.2, ink, closed=True)
        c.fill([circle(x, 25, 1.4)], RED)
    tag = [(11, 3), (28.5, 3), (28.5, 16), (11, 16), (7.5, 9.5)]    # address tag
    c.fill([tag], BLUE)
    c.fill([circle(10.6, 9.5, 1.1)], WHITE)
    stroke(c, [(15.5, 6.5), (15.5, 12.5), (18.5, 12.5)], 1.5, WHITE)     # L
    stroke(c, [(22.5, 7.6), (24.3, 6.3), (24.3, 12.7)], 1.5, WHITE)      # 1
    stroke(c, [(22.3, 12.7), (26.3, 12.7)], 1.5, WHITE)
    stroke(c, [(14, 16), (10.5, 20.8)], 1.1, ink)                # to its device


def bell(c):
    c.fill([[(24, 18.3), (25.9, 19.1), (26.8, 21.2), (27.2, 24.3), (28.7, 26.2), (19.3, 26.2),
             (20.8, 24.3), (21.2, 21.2), (22.1, 19.1)]], WHITE)
    c.fill([circle(24, 27.4, 1.3)], WHITE)


def fa_settings(c, ink):
    settings_gear(c, ink, RED, bell)


def dimension_devices(c, ink):
    c.fill([rect(1.5, 3, 4.5, 30)], ink)                # walls
    c.fill([rect(27.5, 3, 30.5, 30)], ink)
    stroke(c, [(4.5, 10), (27.5, 10)], 1.6, GREEN)      # dimension line
    for x in (12, 20):
        stroke(c, [(x, 10), (x, 19)], 1.1, GREEN)       # witness lines
        c.fill([circle(x, 22.5, 3.6)], RED)             # devices
        c.fill([circle(x, 22.5, 1.2)], WHITE)
    for x in (4.5, 12, 20, 27.5):
        stroke(c, [(x - 1.9, 11.9), (x + 1.9, 8.1)], 1.6, GREEN)   # ticks


def dim_settings(c, ink):
    def glyph(c):
        stroke(c, [(19.8, 24), (28.2, 24)], 1.4, WHITE)
        for x in (19.8, 28.2):
            stroke(c, [(x, 20.5), (x, 27.5)], 1.0, WHITE)
            stroke(c, [(x - 1.3, 25.3), (x + 1.3, 22.7)], 1.4, WHITE)
    settings_gear(c, ink, GREEN, glyph)


TAB = "Electrical.extension/Electrical.tab/"
ICONS = [
    (TAB + "SLD.panel/Generate SLD.pushbutton", generate_sld),
    (TAB + "SLD.panel/Settings.pushbutton", sld_settings),
    (TAB + "Fire Alarm.panel/Smoke Detectors.pushbutton", smoke_detectors),
    (TAB + "Fire Alarm.panel/Heat Detectors.pushbutton", heat_detectors),
    (TAB + "Fire Alarm.panel/Draw FA Loop.pushbutton", fa_loop),
    (TAB + "Fire Alarm.panel/Address Devices.pushbutton", address_devices),
    (TAB + "Fire Alarm.panel/FA Riser.pushbutton", fa_riser),
    (TAB + "Fire Alarm.panel/Settings.pushbutton", fa_settings),
    (TAB + "Voltage Drop.panel/Calculate VD.pushbutton", calculate_vd),
    (TAB + "Voltage Drop.panel/VD Report.pushbutton", vd_report),
    (TAB + "Voltage Drop.panel/Settings.pushbutton", vd_settings),
    (TAB + "Dimensions.panel/Dimension Devices.pushbutton", dimension_devices),
    (TAB + "Dimensions.panel/Settings.pushbutton", dim_settings),
]


def main():
    for folder, draw in ICONS:
        for theme, name in (("light", "icon.png"), ("dark", "icon.dark.png")):
            canvas = Canvas()
            draw(canvas, INK[theme])
            path = os.path.join(ROOT, folder, name)
            canvas.save(path)
            print(path)


if __name__ == "__main__":
    main()
