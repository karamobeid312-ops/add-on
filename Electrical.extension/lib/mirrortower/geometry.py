# -*- coding: utf-8 -*-
"""Plan geometry of Mirror Tower (no Revit needed).

Tower 1 is the area of a scope box (any shape it has in plan: its corners'
outline). Tower 2 is Tower 1 mirrored about a line in plan: a grid or line
picked in Revit, two points, or the line halfway between Tower 1's and
Tower 2's scope boxes. The mirror is a copycircuits Placement (mirrored,
turned and shifted), so Copy Circuits' matching and wire drawing take it
as they are.

Elements of Tower 1 are those in the scope box on Tower 1's side of the
line. Those on the line itself (a shared riser board in the core) are
their own mirror: they are not mirrored, and feed both towers.
"""
from __future__ import division

import math

from copycircuits.placement import Placement


def mirror_placement(p1, p2):
    """The Placement mirroring plan points about the line through p1 and p2
    ((x, y) each). None when the points are the same."""
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    if math.hypot(dx, dy) < 1e-9:
        return None
    angle = 2 * math.atan2(dy, dx)      # reflection = turn(2 * line angle) after a Y flip
    p = Placement(angle, True)
    x, y = p.apply(p1[0], p1[1])
    return Placement(angle, True, p1[0] - x, p1[1] - y)


def halfway_line(c1, c2):
    """Two points of the line halfway between c1 and c2 (the mirror line
    that takes one to the other), or None when they are the same point."""
    dx, dy = c2[0] - c1[0], c2[1] - c1[1]
    if math.hypot(dx, dy) < 1e-9:
        return None
    mx, my = (c1[0] + c2[0]) / 2, (c1[1] + c2[1]) / 2
    return (mx, my), (mx - dy, my + dx)


def side(p1, p2, x, y):
    """Signed distance of (x, y) from the line p1-p2 (+ on its left)."""
    dx, dy = p2[0] - p1[0], p2[1] - p1[1]
    length = math.hypot(dx, dy)
    return (dx * (y - p1[1]) - dy * (x - p1[0])) / length


def hull(points):
    """Convex outline (counter-clockwise) of plan points (x, y)."""
    pts = sorted(set((round(x, 6), round(y, 6)) for x, y in points))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def inside(outline, x, y, pad=0.0):
    """(x, y) is in the convex outline, or within `pad` of it."""
    if len(outline) < 3:
        return False
    n = len(outline)
    for i in range(n):
        a, b = outline[i], outline[(i + 1) % n]
        ex, ey = b[0] - a[0], b[1] - a[1]
        length = math.hypot(ex, ey)
        if length < 1e-12:
            continue
        if (ex * (y - a[1]) - ey * (x - a[0])) / length < -pad:
            return False
    return True


def centre(outline):
    xs = [p[0] for p in outline]
    ys = [p[1] for p in outline]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def swap_name(name, old, new):
    """`name` with `old` replaced by `new` (case does not matter), or None
    when `old` is empty or not in it."""
    if not old or not name:
        return None
    low, find = name.lower(), old.lower()
    at = low.find(find)
    if at < 0:
        return None
    out, start = [], 0
    while at >= 0:
        out.append(name[start:at])
        out.append(new)
        start = at + len(old)
        at = low.find(find, start)
    out.append(name[start:])
    return u"".join(out)


ON_LINE = "line"        # on the mirror line: its own mirror, shared by both towers
TOWER_1 = "tower1"
OTHER_SIDE = "other"    # in the box but past the line: Tower 2's


def where(items, p1, p2, tolerance, home):
    """{key: ON_LINE / TOWER_1 / OTHER_SIDE} of plan.Items, by the side of
    the line they are on. home: a point on Tower 1's side (its box centre)."""
    sign = 1 if side(p1, p2, home[0], home[1]) >= 0 else -1
    found = {}
    for i in items:
        d = side(p1, p2, i.x, i.y) * sign
        found[i.key] = ON_LINE if abs(d) <= tolerance else (TOWER_1 if d > 0 else OTHER_SIDE)
    return found
