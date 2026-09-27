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
   Square loops (lines at right angles, along the grid the devices are
   laid out on) measure the distance along the grid, across plus up, so
   the route runs along rows and columns.
3. Loops are numbered anticlockwise round the start, beginning after the
   widest direction without devices (for a panel on a wall: from one
   side of the wall round to the other); the loop of the start device,
   when the start is a device, is the first.
4. Lines (loop_lines): straight from device to device, or square: one
   straight line between devices in line with each other, otherwise an
   L with one right-angle bend, the bend on the side that runs through
   no other device and crosses or overlaps the fewest lines drawn; when
   both Ls run through a device, a Z that jogs half way between them.
   Lines stop at the edge of each device.

Lengths are in any unit (the Revit side uses metres). Keep this module
compatible with IronPython 2.7.
"""
from __future__ import division

import math

MAX_DEVICES = 120
START = -1          # the start in a route when it is not one of the devices
EPS = 1e-9
TIE = 1e-3          # square loops: among routes as long along the grid, the shorter straight
BLOCKED = 10.0      # square loops: added for each device a line would run through


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


def _grid(a, b):
    """Distance along the grid (across plus up), ties to the straight one."""
    dx, dy = abs(a[0] - b[0]), abs(a[1] - b[1])
    return dx + dy + TIE * math.hypot(dx, dy)


def _grid_length(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _rotate(p, angle):
    c, s = math.cos(angle), math.sin(angle)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


def grid_angle(points, fallback=0.0):
    """Direction (radians, 0 <= a < pi/2) of the grid the devices are laid
    out on, from the direction to each one's nearest device; `fallback`
    when no direction stands out (scattered devices)."""
    quarter = math.pi / 2
    fallback = fallback % quarter
    if len(points) < 3:
        return fallback
    votes = []
    for i, p in enumerate(points):
        best, d2 = None, None
        for j, q in enumerate(points):
            if i != j:
                e = (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2
                if e > EPS and (d2 is None or e < d2):
                    best, d2 = q, e
        if best is not None:
            votes.append(math.atan2(best[1] - p[1], best[0] - p[0]) % quarter)
    if not votes:
        return fallback
    tol = math.radians(1.0)

    def near(a, b):
        d = abs(a - b) % quarter
        return min(d, quarter - d) <= tol
    top = max(votes, key=lambda a: (sum(1 for b in votes if near(a, b)), -a))
    agree = [b for b in votes if near(top, b)]
    if len(agree) < 0.4 * len(votes):
        return fallback
    # mean of the agreeing directions, measured from `top` (they may wrap at 90 degrees)
    mean = top + sum(((b - top + quarter / 2) % quarter) - quarter / 2 for b in agree) / len(agree)
    mean %= quarter
    if min(mean, quarter - mean) < math.radians(0.05):
        return 0.0
    return mean


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


def _split(ids, points, count, square=False):
    """Cut `ids` into `count` groups of equal size, each in one area; for
    square loops the cuts follow the grid."""
    if count <= 1 or len(ids) <= 1:
        return [ids]
    left = count // 2
    cut = int(round(len(ids) * left / count))
    if square:
        xs = [points[i][0] for i in ids]
        ys = [points[i][1] for i in ids]
        ax, ay = (1.0, 0.0) if max(xs) - min(xs) >= max(ys) - min(ys) else (0.0, 1.0)
    else:
        ax, ay = _principal_axis([points[i] for i in ids])
    ids = sorted(ids, key=lambda i: (points[i][0] * ax + points[i][1] * ay,
                                     points[i][1] * ax - points[i][0] * ay, i))
    return _split(ids[:cut], points, left, square) + \
        _split(ids[cut:], points, count - left, square)


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


def _lines(values, band):
    """Group the values into lines (rows or columns): sorted, and a new
    line wherever the next value is `band` or more further. Returns the
    line of each value."""
    order = sorted(range(len(values)), key=lambda k: values[k])
    line, found = 0, [0] * len(values)
    for u, k in enumerate(order):
        if u and values[k] - values[order[u - 1]] >= band:
            line += 1
        found[k] = line
    return found


def _blocked(pts, band, others=()):
    """{(i, j): n}: a square line from pts[i] to pts[j] runs through n
    devices (of pts and `others`) at least: the straight line when they
    are in a row or column (within `band`), otherwise the better of the
    two Ls (the device at the bend counts)."""
    import bisect
    m = len(pts)
    every = list(pts) + list(others)
    row, col = _lines([p[1] for p in every], band), _lines([p[0] for p in every], band)
    along_row, along_col, at = {}, {}, {}
    for k, (x, y) in enumerate(every):
        along_row.setdefault(row[k], []).append(x)
        along_col.setdefault(col[k], []).append(y)
        at[(row[k], col[k])] = at.get((row[k], col[k]), 0) + 1
    for values in list(along_row.values()) + list(along_col.values()):
        values.sort()

    def between(values, a, b):
        lo, hi = (a, b) if a <= b else (b, a)
        return bisect.bisect_left(values, hi - 1e-6) - bisect.bisect_right(values, lo + 1e-6)

    found = {}
    for i in range(m):
        (xi, yi) = pts[i]
        for j in range(i + 1, m):
            (xj, yj) = pts[j]
            if row[i] == row[j]:
                n = between(along_row[row[i]], xi, xj)
            elif col[i] == col[j]:
                n = between(along_col[col[i]], yi, yj)
            else:
                n = min(between(along_row[row[i]], xi, xj) + at.get((row[i], col[j]), 0) +
                        between(along_col[col[j]], yi, yj),
                        between(along_col[col[i]], yi, yj) + at.get((row[j], col[i]), 0) +
                        between(along_row[row[j]], xi, xj))
            if n:
                found[(i, j)] = found[(j, i)] = n
    return found


def _snake(ids, pts, band, axis, reverse=False):
    """`ids` row by row (axis 1: rows, 0: columns), every other row the
    other way round."""
    lines = _lines([pts[k][axis] for k in ids], band)
    groups = {}
    for k, line in zip(ids, lines):
        groups.setdefault(line, []).append(k)
    order = []
    for n, line in enumerate(sorted(groups, reverse=reverse)):
        row = sorted(groups[line], key=lambda k: pts[k][1 - axis])
        order.extend(row[::-1] if n % 2 else row)
    return order


def _grid_tours(pts, band):
    """Starting routes for devices on a grid, pts[0] first: snakes along the
    rows and the columns, and combs (a snake through all but one edge
    column or row, back along that one)."""
    m = len(pts)
    tours = []
    for axis in (0, 1):
        tours.append(_snake(list(range(m)), pts, band, axis))
        across = 1 - axis
        lines = _lines([p[across] for p in pts], band)
        for edge in (min(lines), max(lines)):
            spine = sorted((k for k in range(m) if lines[k] == edge), key=lambda k: pts[k][axis])
            rest = [k for k in range(m) if lines[k] != edge]
            if not rest or not spine:
                continue
            body = _snake(rest, pts, band, axis)
            # back along the spine, from the end of the snake to its start
            if abs(pts[spine[-1]][axis] - pts[body[-1]][axis]) < \
                    abs(pts[spine[0]][axis] - pts[body[-1]][axis]):
                spine = spine[::-1]
            tours.append(body + spine)
    found = []
    for tour in tours:
        k = tour.index(0)
        found.append(tour[k:] + tour[:k])
    return found


def _route(nodes, where, metric=_distance, measure=_distance, band=0.0, others=(), quick=False):
    """Shortest closed route found through `nodes`, nodes[0] first, its
    length and its cost. metric: the distance the route is made short in;
    measure: the one its length is given in; band > 0: square lines
    through another device (of the route or `others`) count BLOCKED more
    for each, and grid-shaped starting routes are tried too (unless
    quick)."""
    pts = [where(n) for n in nodes]
    m = len(nodes)
    d = [[metric(a, b) for b in pts] for a in pts]
    if band > 0:
        for (i, j), n in _blocked(pts, band, others).items():
            d[i][j] += BLOCKED * n
    order, left = [0], set(range(1, m))
    while left:
        last = order[-1]
        nearest = min(left, key=lambda k: (d[last][k], k))
        order.append(nearest)
        left.discard(nearest)
    starts = [order] + (_grid_tours(pts, band) if band > 0 and m > 4 and not quick else [])
    best, best_cost = None, None
    for order in starts:
        while True:
            _two_opt(order, d)
            if not _or_opt(order, d):
                break
        cost = sum(d[a][b] for a, b in zip(order, order[1:] + order[:1]))
        if best is None or cost < best_cost - EPS:
            best, best_cost = order, cost
    order = best
    if m > 2 and d[0][order[-1]] < d[0][order[1]] - EPS:
        order = [0] + order[:0:-1]          # the nearer device first
    length = sum(measure(pts[a], pts[b]) for a, b in zip(order, order[1:] + order[:1]))
    return [nodes[k] for k in order], length, best_cost


def plan_loops(points, start, max_devices=MAX_DEVICES, square=False, angle=0.0, band=0.25):
    """Loops through all `points` ([(x, y)] of the devices).

    start: the index of the start device, or the (x, y) of the start when
    it is not one of the devices (the panel). Every loop starts and ends
    there. max_devices: most devices on one loop (the start device
    included). square: routes along the grid turned by `angle` (radians),
    lengths measured along it; devices within `band` of a row or column
    are on it, and a line never runs past one without stopping there.
    Returns [Loop], loop 1 first."""
    n = len(points)
    if n == 0:
        return []
    max_devices = max(1, int(max_devices))
    if isinstance(start, tuple):
        first, origin = None, (float(start[0]), float(start[1]))
    else:
        first, origin = start, points[start]
    if square:                              # work in the grid's own frame
        points = [_rotate(p, -angle) for p in points]
        origin = _rotate(origin, -angle) if first is None else points[first]
    metric, measure = (_grid, _grid_length) if square else (_distance, _distance)

    def where(node):
        return origin if node == START else points[node]

    count = int(math.ceil(n / max_devices))
    ids = list(range(n))
    if count == 1:
        splits = [[ids]]
    else:
        splits = [_sweep(ids, points, origin, count), _split(ids, points, count, square)]

    # numbering: anticlockwise round the start, the start device's loop first
    offset = _angles(ids, points, origin)[0][0]

    def order(group):
        if first is not None and first in group:
            return (0, 0.0)
        cx, cy = _centroid([points[i] for i in group])
        return (1, (math.atan2(cy - origin[1], cx - origin[0]) - offset) % (2 * math.pi))

    def route(groups, quick):
        loops, cost = [], 0.0
        for group in sorted(groups, key=order):
            depot = first if first is not None and first in group else START
            members = set(group)
            stops, length, c = _route([depot] + [i for i in group if i != depot], where,
                                      metric, measure, band if square else 0.0,
                                      [points[k] for k in range(n) if k not in members], quick)
            loops.append(Loop(stops, length))
            cost += c
        return loops, cost

    # the split with the shorter quick routes, then its routes in full
    if len(splits) > 1:
        splits = [min(splits, key=lambda groups: route(groups, True)[1])]
    return route(splits[0], False)[0]


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


# ---------------------------------------------------------------- square lines

class _Box(object):
    """A device's box in the grid's frame, at least `gap` round its centre."""

    def __init__(self, centre, box, gap, angle):
        cx, cy = centre
        x0, y0, x1, y1 = cx - gap, cy - gap, cx + gap, cy + gap
        if box is not None:
            bx0, by0, bx1, by1 = box
            corners = [_rotate(p, -angle) for p in ((bx0, by0), (bx1, by0), (bx1, by1), (bx0, by1))]
            x0 = min([x0] + [p[0] for p in corners])
            x1 = max([x1] + [p[0] for p in corners])
            y0 = min([y0] + [p[1] for p in corners])
            y1 = max([y1] + [p[1] for p in corners])
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1

    def spans(self, axis, value):
        """The box reaches `value` along the axis (0: x, 1: y)."""
        lo, hi = (self.x0, self.x1) if axis == 0 else (self.y0, self.y1)
        return lo - 1e-9 <= value <= hi + 1e-9

    def bounds(self):
        return self.x0, self.y0, self.x1, self.y1

    def edge(self, direction):
        """Where a line leaving the box along +x, -x, +y or -y starts."""
        return {"+x": self.x1, "-x": self.x0, "+y": self.y1, "-y": self.y0}[direction]

    def hit(self, seg):
        """True when the (square) line runs through the box."""
        (ax, ay), (bx, by) = seg
        if abs(ay - by) < EPS:
            return self.y0 < ay < self.y1 and min(ax, bx) < self.x1 and max(ax, bx) > self.x0
        return self.x0 < ax < self.x1 and min(ay, by) < self.y1 and max(ay, by) > self.y0


def _clash(s, t):
    """0 apart, 1 crossing, 2 overlapping (square lines)."""
    (ax0, ay0), (ax1, ay1) = s
    (bx0, by0), (bx1, by1) = t
    s_flat, t_flat = abs(ay0 - ay1) < EPS, abs(by0 - by1) < EPS
    if s_flat != t_flat:
        h, v = (s, t) if s_flat else (t, s)
        hy, (hx0, hx1) = h[0][1], sorted((h[0][0], h[1][0]))
        vx, (vy0, vy1) = v[0][0], sorted((v[0][1], v[1][1]))
        return 1 if hx0 + EPS < vx < hx1 - EPS and vy0 + EPS < hy < vy1 - EPS else 0
    if s_flat:
        same, (a0, a1), (b0, b1) = abs(ay0 - by0) < 1e-6, sorted((ax0, ax1)), sorted((bx0, bx1))
    else:
        same, (a0, a1), (b0, b1) = abs(ax0 - bx0) < 1e-6, sorted((ay0, ay1)), sorted((by0, by1))
    return 2 if same and min(a1, b1) - max(a0, b0) > 1e-6 else 0


def _square_options(pa, pb, box_a, box_b):
    """Ways to join a to b at right angles, each [line, ...], trimmed at the
    boxes: one straight line when they are in line, else the two Ls."""
    (xa, ya), (xb, yb) = pa, pb
    ym = (ya + yb) / 2
    if box_a.spans(1, ym) and box_b.spans(1, ym) and abs(xb - xa) > EPS:
        go = "+x" if xb > xa else "-x"
        back = "-x" if go == "+x" else "+x"
        return [[((box_a.edge(go), ym), (box_b.edge(back), ym))]]
    xm = (xa + xb) / 2
    if box_a.spans(0, xm) and box_b.spans(0, xm) and abs(yb - ya) > EPS:
        go = "+y" if yb > ya else "-y"
        back = "-y" if go == "+y" else "+y"
        return [[((xm, box_a.edge(go)), (xm, box_b.edge(back)))]]
    options = []
    hx, vy = ("+x" if xb > xa else "-x"), ("+y" if yb > ya else "-y")
    # across first, then up/down; and up/down first, then across
    for first, second, corner in ((hx, vy, (xb, ya)), (vy, hx, (xa, yb))):
        if first in ("+x", "-x"):
            start, end = (box_a.edge(first), ya), (xb, box_b.edge(_back(second)))
        else:
            start, end = (xa, box_a.edge(first)), (box_b.edge(_back(second)), yb)
        legs = [(start, corner), (corner, end)]
        if all(_ahead(p, q, d) for (p, q), d in zip(legs, (first, second))):
            options.append(legs)
    return options


def _zigzag_options(pa, pb, box_a, box_b):
    """The two Zs from a to b: across, up/down half way, across; and
    up/down, across half way, up/down."""
    (xa, ya), (xb, yb) = pa, pb
    options = []
    hx, vy = ("+x" if xb > xa else "-x"), ("+y" if yb > ya else "-y")
    xm, ym = (xa + xb) / 2, (ya + yb) / 2
    start, end = (box_a.edge(hx), ya), (box_b.edge(_back(hx)), yb)
    legs = [(start, (xm, ya)), ((xm, ya), (xm, yb)), ((xm, yb), end)]
    if _ahead(start, (xm, ya), hx) and _ahead((xm, yb), end, hx):
        options.append(legs)
    start, end = (xa, box_a.edge(vy)), (xb, box_b.edge(_back(vy)))
    legs = [(start, (xa, ym)), ((xa, ym), (xb, ym)), ((xb, ym), end)]
    if _ahead(start, (xa, ym), vy) and _ahead((xb, ym), end, vy):
        options.append(legs)
    return options


def _back(direction):
    return {"+x": "-x", "-x": "+x", "+y": "-y", "-y": "+y"}[direction]


def _ahead(p, q, direction):
    """q lies beyond p along the direction (the leg has a length)."""
    axis, sign = (0 if direction[1] == "x" else 1), (1 if direction[0] == "+" else -1)
    return (q[axis] - p[axis]) * sign > EPS


def loop_lines(loop, points, start_xy, boxes=None, start_box=None, gap=0.0,
               square=False, angle=0.0, drawn=None):
    """The lines to draw for a loop: [((x0, y0), (x1, y1))].

    points: all devices (x, y); boxes: their boxes (x0, y0, x1, y1) as
    shown, or None; start_xy / start_box: the start when it is not a device.
    Lines stop at the boxes and at least `gap` from the centres. square:
    right-angle lines along the grid turned by `angle`; `drawn`, a list
    shared by the loops of a floor, collects the lines (in the grid's
    frame) the bends keep clear of."""
    boxes = boxes or [None] * len(points)
    if not square:
        found = []
        for a, b in loop.segments():
            pa, ba = (start_xy, start_box) if a == START else (points[a], boxes[a])
            pb, bb = (start_xy, start_box) if b == START else (points[b], boxes[b])
            line = line_between(pa, pb, ba, bb, gap)
            if line is not None:
                found.append(line)
        return found

    drawn = [] if drawn is None else drawn
    frame = [_rotate(p, -angle) for p in points]
    frame_boxes = [_Box(frame[i], boxes[i], gap, angle) for i in range(len(points))]
    start_frame = _rotate(start_xy, -angle)
    start_frame_box = _Box(start_frame, start_box, gap, angle)

    def at(stop):
        return (start_frame, start_frame_box) if stop == START else (frame[stop], frame_boxes[stop])

    found = []
    for a, b in loop.segments():
        (pa, ba), (pb, bb) = at(a), at(b)
        if a == b or _distance(pa, pb) < EPS:
            continue
        options = _square_options(pa, pb, ba, bb)
        if not options:                     # boxes overlap: a short straight line
            line = line_between(pa, pb, ba.bounds(), bb.bounds(), 0.0)
            options = [[line]] if line else []
        if not options:
            continue
        others = [k for k in range(len(points)) if k not in (a, b)]

        def cost(legs):
            hits = sum(1 for k in others for leg in legs if frame_boxes[k].hit(leg))
            clashes = [_clash(leg, old) for leg in legs for old in drawn]
            return 10 * hits + 6 * clashes.count(2) + 3 * clashes.count(1) + (len(legs) - 1)
        legs = min(options, key=cost)
        if cost(legs) >= 10 and len(legs) == 2:     # both Ls run through a device: try a Z
            legs = min([legs] + _zigzag_options(pa, pb, ba, bb), key=cost)
        drawn.extend(legs)
        found.extend(legs)
    return [(_rotate(p, angle), _rotate(q, angle)) for p, q in found]
