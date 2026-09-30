# -*- coding: utf-8 -*-
"""The route of a loop drawn with detail lines (pure Python, no Revit).

Given the lines of one loop and the devices of the plan, finds the devices
the loop passes and their order: the line ends at a device (within its
reach) belong to it, line ends meeting at a bend join, and the ends at
nothing are the start (the panel). From the start the route follows the
lines device after device back to the start, anticlockwise round what
the loop encloses, as Draw FA Loop routes it (firealarm.loops); the
nearer way first when it encloses nothing (out along a row and back).
A loop starting at a device (no free ends) starts at `first`, e.g. the
device nearest the panel.

Keep compatible with IronPython 2.7.
"""
from __future__ import division

import math

from firealarm.loops import turning

JOIN = 0.005            # line ends this close meet (ft, about 1.5 mm)


class Route(object):
    def __init__(self, order, loose, closed, from_device=False):
        self.order = order      # device indices in route order
        self.loose = loose      # devices on the loop the route does not reach
        self.closed = closed    # the lines go round and back to the start
        self.from_device = from_device      # it starts at a device, order[0]


def _angle(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


def route_order(segments, devices, panels=(), first=None):
    """segments: [((x, y), (x, y))] of the loop; devices: [(x, y, reach)];
    panels: [(x, y, reach)] of the panels shown. The route starts at the
    line ends at a panel, else at the free line ends, else at device
    `first`: an index, or (x, y) for the device nearest that point (None:
    the first device the lines reach). Returns a Route."""
    def device_at(p, q):
        """The device a line ending at p (and going on to q) leaves: within
        reach of p and behind it, straight on from the line."""
        length = math.hypot(p[0] - q[0], p[1] - q[1]) or 1.0
        ux, uy = (p[0] - q[0]) / length, (p[1] - q[1]) / length
        best = None
        for k, (x, y, r) in enumerate(devices):
            vx, vy = x - p[0], y - p[1]
            if math.hypot(vx, vy) > r:
                continue
            behind = vx * ux + vy * uy >= -1e-6
            off = abs(vx * uy - vy * ux)            # how far off the line's own line
            # behind the end first (devices packed closer than their symbols
            # may have none), then the least off the line, then the nearest
            key = (not behind, round(off, 3) if behind else 0.0, math.hypot(vx, vy))
            if best is None or key < best[0]:
                best = (key, k)
        return best[1] if best else None

    joins = []                  # points of bends and free ends

    def join_at(p):
        for k, q in enumerate(joins):
            if math.hypot(p[0] - q[0], p[1] - q[1]) <= JOIN:
                return k
        joins.append(p)
        return len(joins) - 1

    # line ends meeting other line ends at an angle are bends, even next
    # to a device; ends on their own (or overlapping, a U-turn) are at a
    # device when within its reach, else free
    ends = [(p, q) for a, b in segments for p, q in ((a, b), (b, a))]
    bends = set()
    for i, (p, q) in enumerate(ends):
        for j, (p2, q2) in enumerate(ends):
            if j <= i or math.hypot(p[0] - p2[0], p[1] - p2[1]) > JOIN:
                continue
            d = abs(_angle(p, q) - _angle(p2, q2)) % (2 * math.pi)
            if min(d, 2 * math.pi - d) > 0.02:
                bends.add(i)
                bends.add(j)

    def node(p, q, end_index):
        k = None if end_index in bends else device_at(p, q)
        return ("d", k) if k is not None else ("j", join_at(p))

    def where(n):
        return (devices[n[1]][0], devices[n[1]][1]) if n[0] == "d" else joins[n[1]]

    edges = []                  # (node, node, length)
    for s, (a, b) in enumerate(segments):
        na, nb = node(a, b, 2 * s), node(b, a, 2 * s + 1)
        if na != nb:
            edges.append((na, nb, math.hypot(b[0] - a[0], b[1] - a[1])))
    by_node = {}
    for k, (na, nb, _) in enumerate(edges):
        by_node.setdefault(na, []).append(k)
        by_node.setdefault(nb, []).append(k)
    on_loop = sorted(set(n[1] for n in by_node if n[0] == "d"))
    if not on_loop:
        return Route([], [], False)

    starts = [n for n in by_node if n[0] == "j" and any(
        math.hypot(where(n)[0] - x, where(n)[1] - y) <= r for x, y, r in panels)]
    if not starts:
        starts = [n for n, ks in by_node.items() if n[0] == "j" and len(ks) == 1]
    if not starts:
        if isinstance(first, tuple):
            first = min(on_loop, key=lambda k: math.hypot(devices[k][0] - first[0],
                                                          devices[k][1] - first[1]))
        starts = [("d", first if first in on_loop else on_loop[0])]
    stops = set(starts)

    def walk(start, edge):
        """Follow the lines from `start` along `edge` to a start again:
        ([(device, length so far)], where it ended)."""
        used, seen, found = set(), set(), []
        here, length, heading = start, 0.0, None
        while edge is not None:
            used.add(edge)
            na, nb, l = edges[edge]
            there = nb if na == here else na
            length += l
            heading = _angle(where(here), where(there))
            here = there
            if here[0] == "d" and here[1] not in seen:
                seen.add(here[1])
                found.append((here[1], length))
            if here in stops:
                break
            left = [k for k in by_node[here] if k not in used]
            if not left:
                break

            def turn(k):            # where lines cross or overlap, go straight on
                na, nb, _ = edges[k]
                other = nb if na == here else na
                d = abs(_angle(where(here), where(other)) - heading) % (2 * math.pi)
                return min(d, 2 * math.pi - d)
            edge = min(left, key=turn)
        return found, here

    ways = []                   # the most devices, anticlockwise, the nearer way first
    for start in starts:
        for edge in by_node[start]:
            found, end = walk(start, edge)
            if start[0] == "d":
                found = [(start[1], 0.0)] + [f for f in found if f[0] != start[1]]
                soon = found[1][1] if len(found) > 1 else float("inf")
                corners = [where(("d", k)) for k, _ in found]
            else:
                soon = found[0][1] if found else float("inf")
                x, y = where(start)
                at = [(x0, y0) for x0, y0, r in panels if math.hypot(x - x0, y - y0) <= r]
                corners = [(at or [(x, y)])[0]] + [where(("d", k)) for k, _ in found]
            ways.append((-len(found), -turning(corners), soon, len(ways), found, end, start))
    found, end, start = min(ways)[4:]
    order = [k for k, _ in found]
    loose = [k for k in on_loop if k not in set(order)]
    return Route(order, loose, end in stops and not loose, start[0] == "d")
