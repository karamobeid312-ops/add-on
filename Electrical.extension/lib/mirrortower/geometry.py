# -*- coding: utf-8 -*-
"""Plan geometry of Mirror Tower (no Revit needed).

Tower 1 is the area of a scope box (any shape it has in plan: its corners'
outline). Tower 2 is Tower 1 mirrored, and usually also shifted: towers
that sit diagonally from each other are not the mirror of each other about
any one line. The user shows where Tower 2 is with two points of Tower 1
and the same two points of Tower 2 (two core corners), or, for a plain
mirror, with a grid or line. Either way the result is a copycircuits
Placement (mirrored, turned and shifted), so Copy Circuits' matching and
wire drawing take it as they are.

In Revit it is done as a mirror about a line through Tower 1's centre at
half the placement's angle, then a move (`revit_steps`).

An element whose mirrored spot is itself (on the mirror line of a plain
mirror: a shared riser board in the core) is not mirrored; it feeds both
towers.
"""
from __future__ import division

import math

from copycircuits import placement as placing
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


def from_points(s1, s2, t1, t2):
    """The mirrored Placement taking Tower 1's points s1, s2 to Tower 2's
    t1, t2 ((x, y) each), and how much longer t1-t2 is than s1-s2 (0 when
    they are the same two points). None when s1 and s2 are the same point."""
    a = math.hypot(s2[0] - s1[0], s2[1] - s1[1])
    if a < 1e-9:
        return None, 0.0
    b = math.hypot(t2[0] - t1[0], t2[1] - t1[1])
    return placing.from_pairs(s1, s2, t1, t2, True), b - a


def revit_steps(placement, about):
    """(angle of the mirror line, the line's point, (dx, dy) move after it)
    doing `placement` in Revit. The line goes through `about` (Tower 1's
    centre), so the mirrored copies stay near the model until moved."""
    x, y = placement.apply(about[0], about[1])
    return placement.angle / 2, about, (x - about[0], y - about[1])


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


def own_images(items, placement, tolerance):
    """Keys of the plan.Items whose mirrored spot is themselves."""
    found = set()
    for i in items:
        x, y = placement.apply(i.x, i.y)
        if math.hypot(x - i.x, y - i.y) <= tolerance:
            found.add(i.key)
    return found
