# -*- coding: utf-8 -*-
"""Loop lines -> wire paths: the straight lines of a loop joined end to
end into runs, and the runs' straight legs (one wire a leg). A run goes
on through a point where exactly two lines meet (a bend) and stops where a line ends at nothing (at a device,
the lines stop at its edge) or where more than two meet. Points in the
middle of a straight stretch are dropped. Keep compatible with IronPython 2.7.
"""
from __future__ import division

TOLERANCE = 0.01        # ft: line ends closer than this are one point


def _node(nodes, p, tol):
    for i, q in enumerate(nodes):
        if abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol:
            return i
    nodes.append(p)
    return len(nodes) - 1


def _straight(a, b, c, tol):
    """b lies on the straight line a-c, between them."""
    cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    length = max(abs(c[0] - a[0]), abs(c[1] - a[1]), tol)
    dot = (b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1])
    return abs(cross) / length <= tol and dot > 0


def runs(segments, tol=TOLERANCE):
    """[[(x, y), ...]]: the lines ((x0, y0), (x1, y1)) joined into runs,
    each at least two points."""
    nodes, ends = [], []
    for a, b in segments:
        i, j = _node(nodes, a, tol), _node(nodes, b, tol)
        if i != j:
            ends.append((i, j))
    at = {}
    for k, (i, j) in enumerate(ends):
        at.setdefault(i, []).append(k)
        at.setdefault(j, []).append(k)
    used = [False] * len(ends)

    def walk(node, came):
        """Nodes on from `node`, having arrived by line `came`."""
        path = []
        while len(at[node]) == 2:
            nxt = at[node][0] if at[node][1] == came else at[node][1]
            if used[nxt]:
                break
            used[nxt] = True
            i, j = ends[nxt]
            node = j if i == node else i
            path.append(node)
            came = nxt
        return path

    found = []
    for k, (i, j) in enumerate(ends):
        if used[k]:
            continue
        used[k] = True
        back = walk(i, k)
        ahead = walk(j, k)
        order = list(reversed(back)) + [i, j] + ahead
        points = [nodes[n] for n in order]
        found.append(_simplify(points, tol))
    return found


def legs(segments, tol=TOLERANCE):
    """[((x0, y0), (x1, y1))]: the straight legs of the runs, lines in line
    joined. A wire with a bend in it is drawn with the corner cut (chamfer)
    or rounded (arc), so each leg is its own two-point wire, and the
    corners stay square."""
    return [(a, b) for run in runs(segments, tol) for a, b in zip(run, run[1:])]


def _simplify(points, tol):
    """Without the points in the middle of straight stretches."""
    out = list(points[:1])
    for k in range(1, len(points) - 1):
        if not _straight(out[-1], points[k], points[k + 1], tol):
            out.append(points[k])
    out.append(points[-1])
    return out
