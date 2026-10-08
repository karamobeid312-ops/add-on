# -*- coding: utf-8 -*-
"""A cable tray run routed around what is in its way (no Revit needed).

All lengths in metres, points (x, y, z). A run is one straight, level
piece of tray from `start` to `end`, of a width and height, its points on
the tray's centre line (Revit's middle elevation). Its ends stay where
they are: a clash on the way is dodged inside the run by going over it,
under it, or round it to the left or right, with two bends out and two
bends back.

An obstacle is a prism: a convex footprint in plan from `bottom` to `top`.
A pipe, duct, beam or wall is cut into short prisms along its length
(linear_obstacles), so a sloping pipe keeps its slope.

Walls are only dodged over or under (a low wall, a bulkhead). A wall the
tray cannot pass over or under within the limits is crossed straight
through, and the crossing is reported as an opening to make.
"""
from __future__ import division

import math

OVER, UNDER, LEFT, RIGHT = "over", "under", "left", "right"
KINDS = (OVER, UNDER, LEFT, RIGHT)
SIDEWAYS = (LEFT, RIGHT)

CLEARANCE = 0.05            # m, tray to anything in its way
CHUNK = 1.0                 # m, length of the prisms a linear element is cut into
EPS = 1e-6
MAX_STEPS = 60              # tries to grow a dodge before giving up

# why a clash was left as it is (Unsolved.reason)
NO_ROOM = "no_room"         # no dodge fits within the limits or the run
AT_END = "at_end"           # the clash is at the run's end, where it joins something
NOT_LEVEL = "not_level"     # sloping or vertical runs are not rerouted


class Obstacle(object):
    def __init__(self, key, label, footprint, bottom, top, wall=False):
        self.key = key              # element id, (link id, element id) for a linked element
        self.label = label          # "Pipes : Standard"
        self.footprint = footprint  # convex [(x, y)], either winding
        self.bottom = bottom
        self.top = top
        self.wall = wall            # walls are dodged over or under only, else crossed

    def __repr__(self):
        return "Obstacle(%r, %r)" % (self.key, self.label)


def box_obstacle(key, label, points, wall=False):
    """An upright box around points (a column, an equipment, a fitting)."""
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    footprint = [(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))]
    return Obstacle(key, label, footprint, min(zs), max(zs), wall)


def linear_obstacles(key, label, a, b, points, wall=False, chunk=CHUNK):
    """Prisms along a straight element from a to b (its location line)
    holding its geometry points, chunk long, each following the line's
    slope. Points are measured across the line and above it, so a
    sloping pipe gets sloping prisms. Returns [] for a vertical line."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length < EPS:
        return []
    ux, uy = dx / length, dy / length
    slope = (b[2] - a[2]) / length
    us, vs, hs = [], [], []
    for p in points:
        px, py = p[0] - a[0], p[1] - a[1]
        u = px * ux + py * uy
        us.append(u)
        vs.append(-px * uy + py * ux)
        hs.append(p[2] - (a[2] + slope * u))
    u0, u1 = min(us + [0.0]), max(us + [length])
    v0, v1 = min(vs), max(vs)
    h0, h1 = min(hs), max(hs)
    pieces = max(1, int(math.ceil((u1 - u0) / chunk - EPS)))
    step = (u1 - u0) / pieces
    found = []
    for i in range(pieces):
        s0, s1 = u0 + i * step, u0 + (i + 1) * step
        footprint = [(a[0] + s * ux - v * uy, a[1] + s * uy + v * ux)
                     for s, v in ((s0, v0), (s1, v0), (s1, v1), (s0, v1))]
        z0, z1 = a[2] + slope * s0, a[2] + slope * s1
        found.append(Obstacle(key, label, footprint, min(z0, z1) + h0, max(z0, z1) + h1, wall))
    return found


# ---------------------------------------------------------------- results

class Dodge(object):
    """One clash dodged: `kind` by `offset` (up/down in z, left/right across)."""

    def __init__(self, kind, offset, obstacles, at, extra):
        self.kind = kind
        self.offset = offset        # m, signed: + up or left
        self.obstacles = obstacles  # [Obstacle], one per element
        self.at = at                # (x, y, z) where the dodge is, on the original line
        self.extra = extra          # m of tray added


class Crossing(object):
    """A wall the tray goes through: an opening or sleeve to make."""

    def __init__(self, obstacle, at):
        self.obstacle = obstacle
        self.at = at


class Unsolved(object):
    """Clashes left in place: the run goes straight through them."""

    def __init__(self, obstacles, at, reason):
        self.obstacles = obstacles
        self.at = at
        self.reason = reason


class Run(object):
    def __init__(self, start, end, points=None):
        self.start = start
        self.end = end
        self.points = points or [start, end]    # the routed centre line
        self.dodges = []
        self.crossings = []
        self.unsolved = []

    @property
    def changed(self):
        return len(self.points) > 2


# ---------------------------------------------------------------- geometry

def _clip(poly, axis, bound, keep_above):
    """The part of a polygon on one side of the line coordinate[axis] = bound."""
    def inside(p):
        return p[axis] >= bound if keep_above else p[axis] <= bound
    found = []
    n = len(poly)
    for i in range(n):
        p, q = poly[i], poly[(i + 1) % n]
        if inside(p):
            found.append(p)
        if inside(p) != inside(q):
            t = (bound - p[axis]) / (q[axis] - p[axis])
            found.append(tuple(p[k] + t * (q[k] - p[k]) for k in (0, 1)))
    return found


def _area(poly):
    return abs(sum(p[0] * q[1] - q[0] * p[1]
                   for p, q in zip(poly, poly[1:] + poly[:1]))) / 2.0


def _clip_box(poly, u0, u1, v0, v1):
    for axis, bound, above in ((0, u0, True), (0, u1, False), (1, v0, True), (1, v1, False)):
        if not poly:
            return []
        poly = _clip(poly, axis, bound, above)
    return poly if len(poly) >= 3 and _area(poly) > 1e-9 else []


def _dedupe(obstacles):
    """One obstacle per element (a pipe is many prisms)."""
    seen, found = set(), []
    for o in obstacles:
        if o.key not in seen:
            seen.add(o.key)
            found.append(o)
    return found


class _Frame(object):
    """The run's own coordinates: u along it, v to its left, z up."""

    def __init__(self, start, end):
        self.ox, self.oy, self.z = start[0], start[1], start[2]
        dx, dy = end[0] - start[0], end[1] - start[1]
        self.length = math.hypot(dx, dy)
        self.ux, self.uy = dx / self.length, dy / self.length

    def local(self, x, y):
        px, py = x - self.ox, y - self.oy
        return (px * self.ux + py * self.uy, -px * self.uy + py * self.ux)

    def world(self, u, v, dz=0.0):
        return (self.ox + u * self.ux - v * self.uy, self.oy + u * self.uy + v * self.ux,
                self.z + dz)


class _Local(object):
    """An obstacle in the run's coordinates, z relative to the run."""

    def __init__(self, obstacle, frame):
        self.obstacle = obstacle
        self.poly = [frame.local(x, y) for x, y in obstacle.footprint]
        self.bottom = obstacle.bottom - frame.z
        self.top = obstacle.top - frame.z
        us = [p[0] for p in self.poly]
        vs = [p[1] for p in self.poly]
        self.u0, self.u1, self.v0, self.v1 = min(us), max(us), min(vs), max(vs)


class _Hit(object):
    def __init__(self, local, part):
        self.local = local
        self.u0 = min(p[0] for p in part)
        self.u1 = max(p[0] for p in part)


# ---------------------------------------------------------------- routing

class _Router(object):
    def __init__(self, frame, width, height, obstacles, limits, clearance, bends,
                 start_free, end_free):
        self.f = frame
        self.c = clearance
        self.hw = width / 2.0 + clearance       # half the corridor, across
        self.hz = height / 2.0 + clearance      # half the corridor, up
        self.w, self.h = width, height
        self.bends = bends
        self.margin = clearance + max(width, height)    # room for the bends
        self.u_min = 0.0 if start_free else max(width, height)
        self.u_max = frame.length - (0.0 if end_free else max(width, height))
        bottom, top = limits
        self.low = None if bottom is None else bottom - frame.z + height / 2.0
        self.high = None if top is None else top - frame.z - height / 2.0
        self.locals = [_Local(o, frame) for o in obstacles]

    # -- queries

    def hits(self, u0, u1, v0, v1, z0, z1, among=None):
        """Obstacles in the box (local coordinates)."""
        found = []
        for lo in (self.locals if among is None else among):
            if lo.top <= z0 + EPS or lo.bottom >= z1 - EPS:
                continue
            if lo.u1 <= u0 or lo.u0 >= u1 or lo.v1 <= v0 or lo.v0 >= v1:
                continue
            part = _clip_box(lo.poly, u0, u1, v0, v1)
            if part:
                found.append(_Hit(lo, part))
        return found

    def line_hits(self, u0, u1, v=0.0, dz=0.0):
        """Obstacles along a level piece of tray from u0 to u1, at v, dz."""
        return self.hits(u0, u1, v - self.hw, v + self.hw, dz - self.hz, dz + self.hz)

    def leg_hits(self, u, kind, offset, run):
        """Obstacles in a bend leg leaving the line at u for the offset,
        reaching it at u + run (0 for square bends)."""
        found = []
        pieces = 1 if run < EPS else max(2, int(math.ceil(run / 0.1)))
        for i in range(pieces):
            t0, t1 = i / pieces, (i + 1) / pieces
            ua, ub = u + run * t0, u + run * t1
            if kind in (OVER, UNDER):
                za, zb = offset * t0, offset * t1
                found += self.hits(min(ua, ub) - self.h / 2.0 - self.c,
                                   max(ua, ub) + self.h / 2.0 + self.c,
                                   -self.hw, self.hw,
                                   min(za, zb) - self.hz, max(za, zb) + self.hz)
            else:
                va, vb = offset * t0, offset * t1
                found += self.hits(min(ua, ub) - self.hw, max(ua, ub) + self.hw,
                                   min(va, vb) - self.hw, max(va, vb) + self.hw,
                                   -self.hz, self.hz)
        return found

    # -- one dodge

    def _offset(self, kind, group, g0, g1):
        if kind == OVER:
            return max(lo.top for lo in group) + self.hz
        if kind == UNDER:
            return min(lo.bottom for lo in group) - self.hz
        spans = []
        for lo in group:
            part = _clip(_clip(lo.poly, 0, g0 - self.margin, True), 0, g1 + self.margin, False)
            vs = [p[1] for p in (part or lo.poly)]
            spans.append((min(vs), max(vs)))
        if kind == LEFT:
            return max(s[1] for s in spans) + self.hw
        return min(s[0] for s in spans) - self.hw

    def dodge(self, kind, hits, lower):
        """(offset, enter, exit, [locals]) of a dodge clear of the hits, or None."""
        group = {}
        for hit in hits:
            group[id(hit.local)] = hit.local
        g0 = min(h.u0 for h in hits)
        g1 = max(h.u1 for h in hits)
        for _ in range(MAX_STEPS):
            locals_ = list(group.values())
            if kind in SIDEWAYS and any(lo.obstacle.wall for lo in locals_):
                return None
            offset = self._offset(kind, locals_, g0, g1)
            if kind == OVER and self.high is not None and offset > self.high + EPS:
                return None
            if kind == UNDER and self.low is not None and offset < self.low - EPS:
                return None
            run = abs(offset) if self.bends == 45 else 0.0
            enter = g0 - self.margin - run
            leave = g1 + self.margin + run
            if enter < max(lower, self.u_min) - EPS or leave > self.u_max + EPS:
                return None
            changed = False
            for h in self.line_hits(enter, leave):      # passed by the dodge
                if id(h.local) not in group:
                    group[id(h.local)] = h.local
                    g0, g1, changed = min(g0, h.u0), max(g1, h.u1), True
            if kind in (OVER, UNDER):
                detour = self.line_hits(enter + run, leave - run, dz=offset)
                v0, v1 = -self.hw, self.hw
            else:
                detour = self.line_hits(enter + run, leave - run, v=offset)
                v0, v1 = min(0.0, offset) - self.hw, max(0.0, offset) + self.hw
            detour += self.leg_hits(enter, kind, offset, run)
            detour += self.leg_hits(leave, kind, offset, -run)
            if not detour and not changed:
                return offset, enter, leave, locals_
            for h in detour:                # in the way of the dodge: dodge it too
                lo = h.local
                if id(lo) not in group:
                    group[id(lo)] = lo
                    changed = True
                part = _clip_box(lo.poly, -1e9, 1e9, v0, v1) or lo.poly
                u0, u1 = min(p[0] for p in part), max(p[0] for p in part)
                if u0 < g0 - EPS or u1 > g1 + EPS:
                    g0, g1, changed = min(g0, u0), max(g1, u1), True
            if not changed:
                return None
        return None

    def points(self, kind, offset, enter, leave):
        run = abs(offset) if self.bends == 45 else 0.0
        out = [(enter, 0.0, 0.0)]
        for u in (enter + run, leave - run):
            out.append((u, 0.0, offset) if kind in (OVER, UNDER) else (u, offset, 0.0))
        out.append((leave, 0.0, 0.0))
        return out


def _extra(local_points):
    total = 0.0
    for p, q in zip(local_points, local_points[1:]):
        total += math.sqrt(sum((p[k] - q[k]) ** 2 for k in range(3)))
    return total - (local_points[-1][0] - local_points[0][0])


def _choose(options, prefer):
    """The dodge to use: the preferred kind when it fits, else the shortest."""
    if not options:
        return None
    if prefer in KINDS:
        for option in options:
            if option[0] == prefer:
                return option
    if prefer == "side":
        sideways = [o for o in options if o[0] in SIDEWAYS]
        if sideways:
            options = sideways
    return min(options, key=lambda o: (round(o[4], 6), KINDS.index(o[0])))


def through_walls(obstacles, z, height, limits, clearance=CLEARANCE):
    """Walls in the tray's way at elevation z that it cannot pass over or
    under within the limits: it goes through them."""
    bottom, top = limits
    hz = height / 2.0 + clearance
    found = []
    for o in obstacles:
        if not o.wall or o.top <= z - hz + EPS or o.bottom >= z + hz - EPS:
            continue
        over = top is None or o.top + clearance + height <= top + EPS
        under = bottom is None or o.bottom - clearance - height >= bottom - EPS
        if not over and not under:
            found.append(o)
    return found


def route(start, end, width, height, obstacles, limits=(None, None), clearance=CLEARANCE,
          bends=90, prefer="shortest", start_free=True, end_free=True):
    """The Run from start to end, dodging the obstacles.

    limits: (lowest, highest) the tray may go (its bottom and its top), or
    None for no limit. bends: 90 or 45 degrees. prefer: "shortest", a
    kind (over, under, left, right) or "side" (left or right). start_free
    / end_free: False when the run's end joins another tray or fitting,
    which then keeps room for its bend.
    """
    result = Run(start, end)
    if math.hypot(end[0] - start[0], end[1] - start[1]) < EPS:
        return result
    frame = _Frame(start, end)
    if abs(end[2] - start[2]) > EPS:
        router = _Router(frame, width, height, obstacles, limits, clearance, bends, True, True)
        dz = end[2] - start[2]
        hits = [h for h in router.hits(0, frame.length, -router.hw, router.hw,
                                       min(0.0, dz) - router.hz, max(0.0, dz) + router.hz)]
        if hits:
            result.unsolved.append(Unsolved(_dedupe([h.local.obstacle for h in hits]),
                                            start, NOT_LEVEL))
        return result

    through = through_walls(obstacles, start[2], height, limits, clearance)
    passed = set(id(o) for o in through)
    router = _Router(frame, width, height, [o for o in obstacles if id(o) not in passed],
                     limits, clearance, bends, start_free, end_free)

    dodges = []         # (kind, offset, enter, exit, locals)
    cursor = 0.0
    while True:
        hits = router.line_hits(cursor, frame.length)
        if not hits:
            break
        first = min(hits, key=lambda h: h.u0)
        # every obstacle the line meets before the first one is passed
        group = [h for h in hits if h.u0 <= first.u1 + EPS]
        g1 = max(h.u1 for h in group)
        while True:
            more = [h for h in hits if h not in group and h.u0 <= g1 + EPS]
            if not more:
                break
            group += more
            g1 = max(h.u1 for h in group)

        options = []
        for kind in KINDS:
            found = router.dodge(kind, group, cursor)
            if found:
                offset, enter, leave, locals_ = found
                options.append((kind, offset, enter, leave,
                                _extra(router.points(kind, offset, enter, leave)), locals_))
        chosen = _choose(options, prefer)

        if chosen is None and dodges:
            # too near the last dodge: try both as one
            last = dodges[-1]
            merged = [_Hit(lo, _clip_box(lo.poly, last[2], last[3], -router.hw, router.hw)
                           or lo.poly) for lo in last[5]]
            lower = dodges[-2][3] if len(dodges) > 1 else 0.0
            options = []
            for kind in KINDS:
                found = router.dodge(kind, merged + group, lower)
                if found:
                    offset, enter, leave, locals_ = found
                    options.append((kind, offset, enter, leave,
                                    _extra(router.points(kind, offset, enter, leave)), locals_))
            chosen = _choose(options, prefer)
            if chosen is not None:
                dodges.pop()

        if chosen is None:
            g0 = min(h.u0 for h in group)
            at_end = g0 - router.margin < router.u_min or g1 + router.margin > router.u_max
            reason = AT_END if at_end and not (start_free and end_free) else NO_ROOM
            result.unsolved.append(Unsolved(_dedupe([h.local.obstacle for h in group]),
                                            frame.world(g0, 0.0), reason))
            cursor = g1 + EPS
            continue
        dodges.append(chosen)
        cursor = chosen[3]

    local_points = [(0.0, 0.0, 0.0)]
    for kind, offset, enter, leave, extra, locals_ in dodges:
        local_points += router.points(kind, offset, enter, leave)
        result.dodges.append(Dodge(kind, offset, _dedupe([lo.obstacle for lo in locals_]),
                                   frame.world((enter + leave) / 2.0, 0.0), extra))
    local_points.append((frame.length, 0.0, 0.0))
    result.points = [frame.world(u, v, dz) for u, v, dz in local_points]

    _cross(result, through, width, height, clearance)
    return result


def _cross(result, walls, width, height, clearance):
    """The walls the routed tray goes through, once each, where it does."""
    if not walls:
        return
    seen = set()
    for p, q in zip(result.points, result.points[1:]):
        if math.hypot(q[0] - p[0], q[1] - p[1]) < EPS:
            continue
        frame = _Frame(p, q)
        router = _Router(frame, width, height, walls, (None, None), clearance, 90, True, True)
        for hit in router.line_hits(0.0, frame.length, dz=0.0):
            wall = hit.local.obstacle
            if wall.key in seen:
                continue
            seen.add(wall.key)
            result.crossings.append(Crossing(wall, frame.world((hit.u0 + hit.u1) / 2.0, 0.0)))


def route_path(points, width, height, obstacles, **options):
    """Runs along a picked path, one per leg. Its corners stay put, and
    keep room for their bends; its two ends are free."""
    last = len(points) - 2
    return [route(a, b, width, height, obstacles, start_free=i == 0, end_free=i == last,
                  **options)
            for i, (a, b) in enumerate(zip(points, points[1:]))]
