# -*- coding: utf-8 -*-
"""Fire alarm loops (pure Python, no Revit).

Every loop leaves the start (the panel, or the device clicked first),
passes each of its devices once and comes back to the start.

1. More devices than a loop takes (120) are split into as few loops as
   possible, of equal size, each one area. Two splits are tried and the
   one with the shorter lines kept:
   - by direction from the start, like slices of a pie, so every loop
     begins right at the start (best with the panel at the edge),
   - by cutting the devices in two across their longer direction, in
     proportion to the loops each side gets, and again until every part
     is one loop (best for long floors with the panel inside).
2. Each loop's route runs from the start to the nearest device, and so
   on, and is then improved until no change shortens it: 2-opt (turn a
   stretch of the route round) and or-opt (move one to three devices
   elsewhere). A route that no 2-opt move shortens never crosses itself.
3. Loops are numbered anticlockwise round the start, beginning after the
   widest direction without devices (for a panel on a wall: from one
   side of the wall round to the other); the loop of the start device,
   when the start is a device, is the first.

Lengths are in any unit (the Revit side uses metres). Keep this module
compatible with IronPython 2.7.
"""
from __future__ import division

import math

MAX_DEVICES = 120
START = -1          # the start in a route when it is not one of the devices
EPS = 1e-9


class Loop(object):
    """One loop: `stops` is the closed route, the start first."""

    def __init__(self, stops, length):
        self.stops = stops          # [START or device index], back to stops[0] at the end
        self.length = length        # of the closed route

    @property
    def devices(self):
        """Device indices in route order (the start device included)."""
        return [s for s in self.stops if s != START]

    def segments(self):
        """(from, to) stops of every line, the last one back to the start."""
        return list(zip(self.stops, self.stops[1:] + self.stops[:1]))


def _distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _centroid(points):
    n = len(points)
    return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n)


def _principal_axis(points):
    """Unit vector along which the points spread the most."""
    mx, my = _centroid(points)
    sxx = sum((x - mx) ** 2 for x, _ in points)
    syy = sum((y - my) ** 2 for _, y in points)
    sxy = sum((x - mx) * (y - my) for x, y in points)
    angle = 0.5 * math.atan2(2 * sxy, sxx - syy)
    return math.cos(angle), math.sin(angle)


def _angles(ids, points, origin):
    """[(angle, id)] round the origin, anticlockwise, beginning after the
    widest direction without devices."""
    found = sorted((math.atan2(points[i][1] - origin[1], points[i][0] - origin[0]),
                    _distance(points[i], origin), i) for i in ids)
    n = len(found)
    turn = 2 * math.pi
    widest = max(range(n), key=lambda k: ((found[(k + 1) % n][0] - found[k][0]) % turn
                                          if n > 1 else turn, -k))
    return [(found[(widest + 1 + j) % n][0], found[(widest + 1 + j) % n][2]) for j in range(n)]


def _sweep(ids, points, origin, count):
    """Cut `ids` into `count` groups of equal size by direction from the
    origin."""
    ordered = [i for _, i in _angles(ids, points, origin)]
    n = len(ordered)
    cuts = [int(round(n * k / count)) for k in range(count + 1)]
    return [ordered[a:b] for a, b in zip(cuts, cuts[1:])]


def _split(ids, points, count):
    """Cut `ids` into `count` groups of equal size, each in one area."""
    if count <= 1 or len(ids) <= 1:
        return [ids]
    left = count // 2
    cut = int(round(len(ids) * left / count))
    ax, ay = _principal_axis([points[i] for i in ids])
    ids = sorted(ids, key=lambda i: (points[i][0] * ax + points[i][1] * ay,
                                     points[i][1] * ax - points[i][0] * ay, i))
    return _split(ids[:cut], points, left) + _split(ids[cut:], points, count - left)


# ---------------------------------------------------------------- routes

def _two_opt(order, d):
    """Turn stretches of the closed route round while that shortens it;
    order[0] (the start) stays first. True when anything changed."""
    m = len(order)
    changed = False
    improved = True
    while improved:
        improved = False
        for i in range(m - 2):
            a, b = order[i], order[i + 1]
            for j in range(i + 2, m if i > 0 else m - 1):
                c, e = order[j], order[(j + 1) % m]
                if d[a][c] + d[b][e] < d[a][b] + d[c][e] - EPS:
                    order[i + 1:j + 1] = order[i + 1:j + 1][::-1]
                    b = order[i + 1]
                    improved = changed = True
    return changed


def _or_opt(order, d):
    """Move stretches of one to three devices to where they add least,
    either way round; order[0] stays first. True when anything changed."""
    m = len(order)
    changed = False
    if m < 4:
        return changed
    for size in (1, 2, 3):
        i = 1
        while i + size <= m:
            seg = order[i:i + size]
            prev, nxt = order[i - 1], order[(i + size) % m]
            gain = d[prev][seg[0]] + d[seg[-1]][nxt] - d[prev][nxt]
            rest = order[:i] + order[i + size:]
            best = None
            for k in range(len(rest)):
                p, q = rest[k], rest[(k + 1) % len(rest)]
                if p == prev and q == nxt:
                    continue
                for s in (seg, seg[::-1]):
                    cost = d[p][s[0]] + d[s[-1]][q] - d[p][q]
                    if cost < gain - EPS and (best is None or cost < best[0] - EPS):
                        best = (cost, k, s)
            if best is not None:
                _, k, s = best
                order[:] = rest[:k + 1] + s + rest[k + 1:]
                changed = True
            i += 1
    return changed


def _route(nodes, where):
    """Shortest closed route found through `nodes`, nodes[0] first."""
    pts = [where(n) for n in nodes]
    m = len(nodes)
    d = [[_distance(a, b) for b in pts] for a in pts]
    order, left = [0], set(range(1, m))
    while left:
        last = order[-1]
        nearest = min(left, key=lambda k: (d[last][k], k))
        order.append(nearest)
        left.discard(nearest)
    while True:
        _two_opt(order, d)
        if not _or_opt(order, d):
            break
    if m > 2 and d[0][order[-1]] < d[0][order[1]] - EPS:
        order = [0] + order[:0:-1]          # the nearer device first
    length = sum(d[a][b] for a, b in zip(order, order[1:] + order[:1]))
    return [nodes[k] for k in order], length


def plan_loops(points, start, max_devices=MAX_DEVICES):
    """Loops through all `points` ([(x, y)] of the devices).

    start: the index of the start device, or the (x, y) of the start when
    it is not one of the devices (the panel). Every loop starts and ends
    there. max_devices: most devices on one loop (the start device
    included). Returns [Loop], loop 1 first."""
    n = len(points)
    if n == 0:
        return []
    max_devices = max(1, int(max_devices))
    if isinstance(start, tuple):
        first, origin = None, (float(start[0]), float(start[1]))
    else:
        first, origin = start, points[start]

    def where(node):
        return origin if node == START else points[node]

    count = int(math.ceil(n / max_devices))
    ids = list(range(n))
    if count == 1:
        splits = [[ids]]
    else:
        splits = [_sweep(ids, points, origin, count), _split(ids, points, count)]

    # numbering: anticlockwise round the start, the start device's loop first
    offset = _angles(ids, points, origin)[0][0]

    def order(group):
        if first is not None and first in group:
            return (0, 0.0)
        cx, cy = _centroid([points[i] for i in group])
        return (1, (math.atan2(cy - origin[1], cx - origin[0]) - offset) % (2 * math.pi))

    best, best_length = None, None
    for groups in splits:
        loops = []
        for group in sorted(groups, key=order):
            depot = first if first is not None and first in group else START
            stops, length = _route([depot] + [i for i in group if i != depot], where)
            loops.append(Loop(stops, length))
        length = sum(loop.length for loop in loops)
        if best is None or length < best_length - EPS:
            best, best_length = loops, length
    return best


def crossings(loop, points, start=None):
    """Pairs of lines of the loop that cross (for checks)."""
    def where(node):
        return start if node == START else points[node]

    def side(p, q, r):
        v = (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        return 0 if abs(v) < 1e-9 else (1 if v > 0 else -1)

    segs = [(where(a), where(b)) for a, b in loop.segments()]
    found = []
    for i in range(len(segs)):
        for j in range(i + 2, len(segs)):
            if i == 0 and j == len(segs) - 1:
                continue                    # the two lines at the start
            (p1, p2), (p3, p4) = segs[i], segs[j]
            if side(p1, p2, p3) * side(p1, p2, p4) < 0 and side(p3, p4, p1) * side(p3, p4, p2) < 0:
                found.append((i, j))
    return found


# ---------------------------------------------------------------- lines

def _exit(p, u, box):
    """How far from p, going along the unit vector u, the edge of `box`
    (x0, y0, x1, y1) is; 0 when p is outside it."""
    x0, y0, x1, y1 = box
    t = None
    for pv, uv, lo, hi in ((p[0], u[0], x0, x1), (p[1], u[1], y0, y1)):
        if uv > EPS:
            reach = (hi - pv) / uv
        elif uv < -EPS:
            reach = (lo - pv) / uv
        else:
            continue
        t = reach if t is None else min(t, reach)
    return max(t or 0.0, 0.0)


def line_between(a, b, box_a=None, box_b=None, gap=0.0):
    """The line from device a to device b, stopped at the edge of each
    one's box (x0, y0, x1, y1) and at least `gap` from its centre. Each end
    gives up at most 45 % of the length. None when a and b coincide."""
    length = _distance(a, b)
    if length < EPS:
        return None
    u = ((b[0] - a[0]) / length, (b[1] - a[1]) / length)
    ta = max(_exit(a, u, box_a) if box_a else 0.0, gap)
    tb = max(_exit(b, (-u[0], -u[1]), box_b) if box_b else 0.0, gap)
    ta, tb = min(ta, 0.45 * length), min(tb, 0.45 * length)
    return ((a[0] + u[0] * ta, a[1] + u[1] * ta), (b[0] - u[0] * tb, b[1] - u[1] * tb))
