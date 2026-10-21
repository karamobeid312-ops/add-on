# -*- coding: utf-8 -*-
"""What Mirror Tower (Mechanical / Plumbing) does on a floor (no Revit needed).

Every element is a Thing: a point (a fitting, a terminal, a fixture, a
piece of equipment) or a run between two ends (a duct, a pipe, a flex).
On each floor:

- Tower 1's things are those in its scope box: a point inside it, a run
  with both ends inside it. A run with one end out of the box leaves
  Tower 1 (into the riser, the podium, the other tower): it is not
  mirrored and is listed;
- a thing whose mirrored spot is itself (on the mirror line) is shared
  by both towers and not mirrored;
- a Tower 1 thing that Tower 2 has already (same type at the mirrored
  spot: a run with both ends there) is not mirrored again, so running
  the tool twice makes no doubles. The rest is mirrored.

After mirroring, the open ends of the copies are joined to any open end
at the same spot (a copy beside a pipe Tower 2 had already).
"""
from __future__ import division

import math

from mirrortower import geometry

Z_TOLERANCE = 0.5 / 0.3048          # ft: a copy is at the same height, within this


class Thing(object):
    """An element: id, type, family, its point `a` (x, y, z) and, for a
    run, its other end `b`. level: the key of its own level, or None."""

    def __init__(self, key, type_key, a, b=None, family_key=None, level=None, label=u"",
                 grouped=False):
        self.key = key
        self.grouped = grouped          # in a model group: Revit mirrors groups whole
        self.type_key = type_key
        self.family_key = family_key
        self.a = a
        self.b = b
        self.level = level
        self.label = label

    @property
    def run(self):
        return self.b is not None

    @property
    def z(self):
        """Height it is on its floor by: a run's lower end."""
        return min(self.a[2], self.b[2]) if self.run else self.a[2]

    def ends(self):
        return (self.a, self.b) if self.run else (self.a,)


def pick_floor(thing, floors):
    """Key of the floor `thing` is on, or None. floors: [(key, low, high)]
    (high None: the top floor), heights in feet. Its own level when that
    floor's storey holds it; else the floor with the highest bottom under
    it (levels a little apart overlap); else its own level, if picked."""
    z = thing.z
    holds = [(low, key) for key, low, high in floors
             if z >= low and (high is None or z < high)]
    if thing.level is not None and any(key == thing.level for _, key in holds):
        return thing.level
    if holds:
        return max(holds, key=lambda p: p[0])[1]
    return None


def _inside(box, point, pad):
    return geometry.inside(box, point[0], point[1], pad)


def _moved(placement, point):
    x, y = placement.apply(point[0], point[1])
    return (x, y, point[2])


def _near(p, q, tolerance, z_tolerance):
    return math.hypot(p[0] - q[0], p[1] - q[1]) <= tolerance and \
        abs(p[2] - q[2]) <= z_tolerance


class Side(object):
    """One floor split by tower."""

    def __init__(self):
        self.tower1 = []            # Things to mirror (or found in Tower 2)
        self.leaves = []            # runs with one end out of Tower 1: skipped
        self.grouped = []           # Tower 1 things in a model group: skipped
        self.shared = []            # on the mirror line: not mirrored
        self.pool = []              # the rest of the floor: Tower 2's things...
        self.copies = {}            # Tower 1 key -> Tower 2 key found
        self.missing = []           # Tower 1 Things Tower 2 has not got


def split(things, box, placement, tolerance):
    """Side of one floor's Things, before pairing."""
    side = Side()
    for t in things:
        inside = [_inside(box, p, tolerance) for p in t.ends()]
        if all(inside) and t.grouped:
            side.grouped.append(t)
        elif all(inside):
            if all(_near(_moved(placement, p), p, tolerance, Z_TOLERANCE) for p in t.ends()):
                side.shared.append(t)
            else:
                side.tower1.append(t)
        elif any(inside) and not t.grouped:
            side.leaves.append(t)
        else:
            side.pool.append(t)
    return side


def _cell(point, size):
    return int(math.floor(point[0] / size)), int(math.floor(point[1] / size))


def pair(side, placement, tolerance, z_tolerance=Z_TOLERANCE):
    """Fill side.copies and side.missing: each Tower 1 Thing with the
    nearest pool Thing of its type (else, for a point, its family) at its
    mirrored spot; a run's two ends must both be at the mirrored ends (in
    either order). One to one."""
    size = max(tolerance, 1e-9)
    cells = {}
    for t in side.pool:
        cells.setdefault(_cell(t.a, size), []).append(t)
    pairs = []
    for s in side.tower1:
        a = _moved(placement, s.a)
        b = _moved(placement, s.b) if s.run else None
        cx, cy = _cell(a, size)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for t in cells.get((cx + dx, cy + dy), ()):
                    if t.run != s.run:
                        continue
                    if t.type_key == s.type_key:
                        rank = 0
                    elif not s.run and s.family_key is not None and \
                            t.family_key == s.family_key:
                        rank = 1
                    else:
                        continue
                    if s.run:
                        if not _near(t.a, a, tolerance, z_tolerance) or \
                                not _near(t.b, b, tolerance, z_tolerance):
                            continue
                    elif not _near(t.a, a, tolerance, z_tolerance):
                        continue
                    d = math.hypot(t.a[0] - a[0], t.a[1] - a[1])
                    pairs.append((rank, d, s.key, t.key))
        if s.run:       # the pool run may be drawn the other way: its a at our b
            cx, cy = _cell(b, size)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for t in cells.get((cx + dx, cy + dy), ()):
                        if t.run and t.type_key == s.type_key and \
                                _near(t.a, b, tolerance, z_tolerance) and \
                                _near(t.b, a, tolerance, z_tolerance):
                            pairs.append((0, math.hypot(t.a[0] - b[0], t.a[1] - b[1]),
                                          s.key, t.key))
    pairs.sort(key=lambda p: (p[0], p[1]))
    copies, taken = {}, set()
    for _, _, s, t in pairs:
        if s not in copies and t not in taken:
            copies[s] = t
            taken.add(t)
    side.copies = copies
    side.missing = [t for t in side.tower1 if t.key not in copies]
    return side


def landed(expected, made, placement, tolerance, z_tolerance=Z_TOLERANCE):
    """{Tower 1 key: new key} of the copies `made` (Things) found where
    the `expected` Tower 1 Things mirror to; the rest did not land."""
    probe = Side()
    probe.tower1 = list(expected)
    probe.pool = list(made)
    return pair(probe, placement, tolerance, z_tolerance).copies


JOIN = 5.0 / 304.8              # ft: open ends this near are the same joint


def joints(ends, tolerance=JOIN):
    """Pairs of open connector ends to join: [(end, end)], each end at most
    once, nearest first. ends: [(owner key, connector id, (x, y, z), domain)];
    only ends of different owners and the same domain (duct, pipe) join."""
    size = max(tolerance, 1e-9)
    cells = {}
    for e in ends:
        cells.setdefault(_cell(e[2], size), []).append(e)
    found = []
    for i, e in enumerate(ends):
        cx, cy = _cell(e[2], size)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for f in cells.get((cx + dx, cy + dy), ()):
                    if f[0] == e[0] or f[3] != e[3] or (f[0], f[1]) <= (e[0], e[1]):
                        continue
                    p, q = e[2], f[2]
                    d = math.sqrt((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)
                    if d <= tolerance:
                        found.append((d, e, f))
    found.sort(key=lambda x: x[0])
    used, out = set(), []
    for _, e, f in found:
        if (e[0], e[1]) in used or (f[0], f[1]) in used:
            continue
        used.add((e[0], e[1]))
        used.add((f[0], f[1]))
        out.append((e, f))
    return out
