# -*- coding: utf-8 -*-
"""Is each wall fixture on its wall? (no Revit needed)

A fixture on a wall (a face-based family on a wall face, or a wall-hosted
family) is measured against each side face of its wall, in metres:

- gap: its insertion point in front of the face (+) or behind it (-).
  Face-based families have their insertion point on the face they are
  placed on. Wall-hosted families are measured by their body only.
- front, back: the farthest and the nearest point of its body (the
  family's 3D geometry) in front of the face.
- on_face: the insertion point is over the face, not past the end or the
  top of the wall, nor in a door or window opening.
- square: how square the fixture is to the face (cosine of the angle
  between its out direction and the face's normal, < 0 facing into the
  wall), for face-based families.

The fixture's own side is the face its insertion point is nearest (for
face-based families) or the face its body sticks out of most.
"""
from __future__ import division

import math

TOLERANCE = 0.010           # m: a fixture this near its wall face is on it
SQUARE = math.cos(math.radians(2.0))    # a fixture turned more than this is not square

# where the fixture is hosted (Fixture.host)
WALL = "wall"               # a wall, in this model or a linked model: checked
NO_HOST = "no_host"         # a hosted family that lost its host
LINK_MISSING = "link_missing"   # hosted by a wall in a link not loaded, or no longer in it
NOT_WALL = "not_wall"       # face-based on a vertical work plane (level, reference plane)
UNHOSTED = "unhosted"       # a family not hosted by anything: not checked
FLAT = "flat"               # on a ceiling, floor or roof: not checked
OTHER_HOST = "other_host"   # on a column, furniture, curtain panel...: not checked

# results (Finding.status)
OK = "ok"
OFF_WALL = "off_wall"
FLOATING = "floating"
EMBEDDED = "embedded"
INSIDE = "inside"
FACES_IN = "faces_in"
TILTED = "tilted"
UNREADABLE = "unreadable"

# problems, in the order they are reported
PROBLEMS = (NO_HOST, LINK_MISSING, OFF_WALL, FLOATING, EMBEDDED, INSIDE, FACES_IN, TILTED,
            NOT_WALL)
# not checked, in the order they are reported
SKIPPED = (UNREADABLE, UNHOSTED, FLAT, OTHER_HOST)


class Side(object):
    """One side face of the fixture's wall, measured from the fixture (m)."""

    def __init__(self, gap=None, on_face=True, front=None, back=None, square=None):
        self.gap = gap              # insertion point in front of the face, None: not used
        self.on_face = on_face      # the insertion point is over the face
        self.front = front          # farthest point of the body in front of the face
        self.back = back            # nearest point of the body in front of the face
        self.square = square        # cosine to the face's normal, None: not known


class Fixture(object):
    """A family instance to check."""

    def __init__(self, key, label="", category="", level="", host=WALL, sides=()):
        self.key = key              # element id
        self.label = label          # family : type
        self.category = category
        self.level = level
        self.host = host            # WALL, NO_HOST, LINK_MISSING, NOT_WALL, UNHOSTED...
        self.sides = list(sides)    # [Side] of its wall


class Finding(object):
    """The result for one fixture. distance: m (degrees for TILTED), or None."""

    def __init__(self, fixture, status, distance=None):
        self.fixture = fixture
        self.status = status
        self.distance = distance


def _own_side(sides):
    """The side face the fixture is on."""
    with_gap = [s for s in sides if s.gap is not None]
    if with_gap:
        return min(with_gap, key=lambda s: abs(s.gap))
    with_body = [s for s in sides if s.front is not None]
    if with_body:
        return max(with_body, key=lambda s: s.front)
    return None


def check(fixture, tolerance=TOLERANCE):
    """The Finding of one fixture."""
    if fixture.host != WALL:
        return Finding(fixture, fixture.host)
    if not fixture.sides:
        return Finding(fixture, UNREADABLE)
    on = [s for s in fixture.sides if s.on_face]
    if not on:
        side = _own_side(fixture.sides)
        gap = side.gap if side is not None else None
        return Finding(fixture, OFF_WALL, abs(gap) if gap is not None else None)
    side = _own_side(on)
    if side is None:
        return Finding(fixture, UNREADABLE)
    if side.front is not None and side.front < -tolerance:
        return Finding(fixture, INSIDE, -side.front)
    if side.gap is not None and side.gap < -tolerance:
        return Finding(fixture, EMBEDDED, -side.gap)
    off = side.back if side.back is not None else side.gap
    if off is not None and off > tolerance:
        return Finding(fixture, FLOATING, off)
    if side.square is not None:
        if side.square < 0:
            return Finding(fixture, FACES_IN)
        if side.square < SQUARE:
            angle = math.degrees(math.acos(max(min(side.square, 1.0), -1.0)))
            return Finding(fixture, TILTED, angle)
    return Finding(fixture, OK)


class Result(object):
    """All the findings of a run."""

    def __init__(self, findings, tolerance=TOLERANCE):
        self.findings = list(findings)
        self.tolerance = tolerance

    def of(self, status):
        return [f for f in self.findings if f.status == status]

    def problems(self):
        return [f for f in self.findings if f.status in PROBLEMS]

    def checked(self):
        """Findings of fixtures on walls (or that should be): all but those skipped."""
        return [f for f in self.findings if f.status not in SKIPPED]


def check_all(fixtures, tolerance=TOLERANCE):
    return Result([check(f, tolerance) for f in fixtures], tolerance)
