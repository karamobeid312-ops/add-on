# -*- coding: utf-8 -*-
"""Dimension strings for devices in a plan (pure Python, no Revit).

Each device is dimensioned along its own axes, the normals of its centre
reference planes, so devices turned with a rotated room get strings
square to that room. Devices whose axes point the same way are
dimensioned together, in rows along one axis and columns along the other:

1. Devices at the same position across (within ALIGN_TOL) are one row,
   in order along it.
2. A row is cut where a wall runs between two of its devices, so each
   piece stays in one room.
3. Each piece is a string from the nearest wall face: the one before its
   first device or the one after its last device, whichever is nearer
   (walls BOTH: from wall to wall; NONE: between the devices only). A wall
   face that is not square to the string cannot be dimensioned.

With every_row False, a piece is left out when its devices only repeat
positions that another piece in the same room already dimensions: one
row and one column then fix a whole regular grid. Devices joined by rows
and columns with no wall between them are one room.

Walls come from find_wall(device, (dx, dy)): the first wall face from
the device in that direction, as a Hit, or None.

Lengths are in metres, angles in radians. Keep this module compatible
with IronPython 2.7.
"""
from __future__ import division

import math

ALIGN_TOL = 0.02        # m: devices this close across a string are one row
ANGLE_TOL = 1e-4        # rad: axes and walls this close are parallel
WALL_GAP = 0.01         # m: a wall face closer than this to the device is not dimensioned
QUARTER = math.pi / 2
EPS = 1e-9

NEAREST = "nearest"             # walls in a string: the nearest one
BOTH = "both"                   # from wall to wall
NONE = "none"                   # between the devices only

NO_WALL = "no wall"             # why a string end has no wall
SKEW = "not square"


class Device(object):
    """A device to dimension.

    axes: [(angle, ref)] for each centre plane that can be dimensioned in
    the plan: the direction of the plane's normal (radians) and the
    caller's reference to the plane."""

    def __init__(self, key, x, y, axes, z=0.0, label=""):
        self.key = key
        self.x, self.y, self.z = x, y, z
        self.axes = list(axes)
        self.label = label


class Hit(object):
    """The first wall from a device along a string."""

    def __init__(self, distance, ref=None, square=True):
        self.distance = distance    # m from the device
        self.ref = ref              # the caller's reference to the wall face
        self.square = square        # the face is square to the string


class Stop(object):
    """A point of a dimension string: a wall face or a device."""

    def __init__(self, at, ref, device=None):
        self.at = at                # m along the string
        self.ref = ref
        self.device = device        # None for a wall face

    @property
    def is_wall(self):
        return self.device is None


class Chain(object):
    """One dimension string."""

    def __init__(self, angle, across, stops, side, members, ends):
        self.angle = angle          # direction of the string (radians)
        self.across = across        # position across the string (m, string frame)
        self.stops = stops          # [Stop] in order along the string
        self.side = side            # +1 / -1: side across the string that has the text
        self.members = members      # [Device] in the string (repeats share a stop)
        self.ends = ends            # [start, end]: None, NO_WALL or SKEW

    @property
    def walls(self):
        return sum(1 for s in self.stops if s.is_wall)

    def point(self, along, across):
        """Plan (x, y) of a point given along and across the string."""
        c, s = math.cos(self.angle), math.sin(self.angle)
        return (along * c - across * s, along * s + across * c)

    def line(self, offset=0.0):
        """End points of the dimension line, `offset` from the devices on
        the side of the text."""
        across = self.across + self.side * offset
        return self.point(self.stops[0].at, across), self.point(self.stops[-1].at, across)


class Plan(object):
    """Result of plan()."""

    def __init__(self):
        self.chains = []            # [Chain]
        self.alone = []             # [(Device, angle)]: nothing to dimension to along angle
        self.no_wall = 0            # string ends where no wall was found
        self.skew = 0               # string ends at a wall not square to the string


def text_side(dx, dy, right=(1.0, 0.0), up=(0.0, 1.0)):
    """Unit normal to a string along (dx, dy), on the side Revit writes
    the text: above strings that read left to right, left of strings
    that read bottom to top, as seen in the view (right / up)."""
    r = dx * right[0] + dy * right[1]
    u = dx * up[0] + dy * up[1]
    if r < -EPS or (abs(r) <= EPS and u < 0):
        r, u = -r, -u
    # a quarter turn anticlockwise, in the view
    return (-u * right[0] + r * up[0], -u * right[1] + r * up[1])


def _turn(a, b, period):
    """Angle between directions a and b, modulo period."""
    d = (a - b) % period
    return min(d, period - d)


def _groups(devices):
    """[(angle, [(Device, [ref along angle, ref across])])] for devices
    whose axes are parallel; angle in [0, 90 degrees)."""
    groups = []
    for device in devices:
        if not device.axes:
            continue
        base = device.axes[0][0] % QUARTER
        for angle, members in groups:
            if _turn(base, angle, QUARTER) <= ANGLE_TOL:
                break
        else:
            angle, members = base, []
            groups.append((angle, members))
        refs = [None, None]
        for axis, ref in device.axes:
            for k in (0, 1):
                if refs[k] is None and _turn(axis, angle + k * QUARTER, math.pi) <= ANGLE_TOL:
                    refs[k] = ref
        members.append((device, refs))
    return groups


class _Item(object):
    """A device in a string's frame."""

    def __init__(self, device, ref, along, across):
        self.device = device
        self.ref = ref
        self.along = along
        self.across = across


def _rows(items, tol):
    """Items at the same position across (within tol of the next one) as
    rows, each in order along."""
    rows, row = [], []
    for item in sorted(items, key=lambda i: i.across):
        if row and item.across - row[-1].across > tol:
            rows.append(row)
            row = []
        row.append(item)
    if row:
        rows.append(row)
    return [sorted(r, key=lambda i: i.along) for r in rows]


def _clusters(items, tol):
    """{id(item): number}, the same number for positions along within tol."""
    found, number, last = {}, -1, None
    for item in sorted(items, key=lambda i: i.along):
        if last is None or item.along - last > tol:
            number += 1
        found[id(item)] = number
        last = item.along
    return found


def _rooms(pieces):
    """find(device) -> room number: devices joined by pieces of rows and
    columns share a room."""
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for _, piece in pieces:
        for a, b in zip(piece, piece[1:]):
            ra, rb = find(id(a.device)), find(id(b.device))
            if ra != rb:
                parent[ra] = rb
    return lambda device: find(id(device))


_NO_END = (None, None, None)


def _end(hit, along, sign):
    """(wall Stop or None, distance or None, why no wall) at one end of a
    string. A wall at the device (nearer than WALL_GAP) has a distance but
    no stop: the device is on it."""
    if hit is None:
        return None, None, NO_WALL
    if not hit.square:
        return None, None, SKEW
    if hit.distance < WALL_GAP:
        return None, hit.distance, None
    return Stop(along + sign * hit.distance, hit.ref), hit.distance, None


def _chain(piece, alpha, ray, walls, tol, side):
    """The string of a piece of row, or None when it has fewer than two stops."""
    first, last = piece[0], piece[-1]
    stops, ends = [], [None, None]
    at = None
    for item in piece:
        if at is not None and item.along - at <= tol:
            continue            # devices at the same place share a stop
        stops.append(Stop(item.along, item.ref, item.device))
        at = item.along
    if walls != NONE:
        start = _end(ray(first.device, -1), first.along, -1)
        end = _end(ray(last.device, 1), last.along, 1)
        if walls == NEAREST and (start[1] is not None or end[1] is not None):
            # keep the nearer wall, the start one when they are as near
            if end[1] is None or (start[1] is not None and start[1] <= end[1] + tol):
                end = _NO_END
            else:
                start = _NO_END
        if start[0] is not None:
            stops.insert(0, start[0])
        if end[0] is not None:
            stops.append(end[0])
        ends = [start[2], end[2]]
    if len(stops) < 2:
        return None
    across = sum(i.across for i in piece) / len(piece)
    return Chain(alpha, across, stops, side, [i.device for i in piece], ends)


def _pick(k, candidates, tol, every_row):
    """(chosen chains, items left alone) in one room along one direction.

    candidates: [(piece, chain or None)]. Every chain, or the fewest that
    dimension every position along (greedy). An item is alone when no
    chosen chain has a device at its position along."""
    items = [i for piece, _ in candidates for i in piece]
    cluster = _clusters(items, tol)
    covers = [set(cluster[id(i)] for i in piece) for piece, _ in candidates]
    uncovered = set(cluster.values())
    pool = [n for n, (_, chain) in enumerate(candidates) if chain is not None]
    if every_row:
        for n in pool:
            uncovered -= covers[n]
        return [candidates[n][1] for n in pool], [i for i in items if cluster[id(i)] in uncovered]
    chosen = []
    while pool:
        best, best_key = None, None
        for n in pool:
            gain = len(covers[n] & uncovered)
            if not gain:
                continue
            chain = candidates[n][1]
            # most new positions, then most walls, most devices, bottom row / left column
            key = (gain, chain.walls, len(chain.members),
                   -chain.across if k == 0 else chain.across)
            if best_key is None or key > best_key:
                best, best_key = n, key
        if best is None:
            break
        chosen.append(candidates[best][1])
        uncovered -= covers[best]
        pool.remove(best)
    return chosen, [i for i in items if cluster[id(i)] in uncovered]


def plan(devices, find_wall, every_row=True, walls=NEAREST, right=(1.0, 0.0), up=(0.0, 1.0),
         tol=ALIGN_TOL):
    """Dimension strings for `devices` ([Device]).

    find_wall(device, (dx, dy)) -> Hit or None. every_row False: only the
    strings needed to fix every position. walls: NEAREST, BOTH or NONE
    (walls still cut the rows). right / up: the view's directions, to know
    which side of a string has the text."""
    result = Plan()
    for angle, members in _groups(devices):
        cache, rays, sides, pieces = {}, {}, {}, []
        for k in (0, 1):
            alpha = angle + k * QUARTER
            c, s = math.cos(alpha), math.sin(alpha)
            rays[k] = _rays(find_wall, cache, k, c, s)
            nx, ny = text_side(c, s, right, up)
            sides[k] = 1 if -nx * s + ny * c >= 0 else -1
            items = [_Item(d, refs[k], d.x * c + d.y * s, -d.x * s + d.y * c)
                     for d, refs in members if refs[k] is not None]
            for row in _rows(items, tol):
                piece = [row[0]]
                for a, b in zip(row, row[1:]):
                    hit = rays[k](a.device, 1)
                    if hit is not None and WALL_GAP <= hit.distance < b.along - a.along - EPS:
                        pieces.append((k, piece))       # a wall between a and b
                        piece = [b]
                    else:
                        piece.append(b)
                pieces.append((k, piece))

        room = _rooms(pieces)
        found = {}                                      # (k, room) -> [(piece, chain)]
        for k, piece in pieces:
            chain = _chain(piece, angle + k * QUARTER, rays[k], walls, tol, sides[k])
            found.setdefault((k, room(piece[0].device)), []).append((piece, chain))

        chosen = []
        for (k, _), candidates in found.items():
            picked, alone = _pick(k, candidates, tol, every_row)
            chosen.extend((k, chain) for chain in picked)
            result.alone.extend((i.device, angle + k * QUARTER) for i in alone)
        chosen.sort(key=lambda kc: (kc[0], kc[1].across, kc[1].stops[0].at))
        for _, chain in chosen:
            result.chains.append(chain)
            result.no_wall += chain.ends.count(NO_WALL)
            result.skew += chain.ends.count(SKEW)
    return result


def _rays(find_wall, cache, k, c, s):
    """ray(device, sign): find_wall() along the string (sign 1) or back
    (sign -1), each asked once."""
    def ray(device, sign):
        key = (k, sign, id(device))
        if key not in cache:
            cache[key] = find_wall(device, (sign * c, sign * s))
        return cache[key]
    return ray


def segment_walls(segments):
    """find_wall() for walls given as segments ((x0, y0), (x1, y1)) in
    metres: the first segment a ray crosses. For previews and tests; in
    Revit the walls are found with rays through the model."""
    def find_wall(device, direction):
        dx, dy = direction
        best = None
        for (ax, ay), (bx, by) in segments:
            ex, ey = bx - ax, by - ay
            denom = dx * ey - dy * ex
            if abs(denom) < EPS:
                continue                    # ray along the wall
            wx, wy = ax - device.x, ay - device.y
            t = (wx * ey - wy * ex) / denom
            u = (wx * dy - wy * dx) / denom
            if t < -EPS or u < -EPS or u > 1 + EPS:
                continue
            if best is None or t < best[0]:
                square = abs(dx * ex + dy * ey) / math.hypot(ex, ey) <= math.sin(ANGLE_TOL)
                best = (max(t, 0.0), square, ((ax, ay), (bx, by)))
        if best is None:
            return None
        return Hit(best[0], best[2], best[1])
    return find_wall
