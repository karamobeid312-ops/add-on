# -*- coding: utf-8 -*-
"""Where the copies of a floor are (no Revit needed).

A copied floor is usually right above or below its source (Paste >
Aligned to Selected Levels): every copy is at the same spot in plan. A
second tower built as a mirror of the first, or turned or moved, has its
copies somewhere else, by one placement in plan:

    copy = turn(mirror(source)) + shift

mirror flips Y (any mirror is that flip, then a turn), turn is about the
origin. The placements are found from the elements themselves: pairs of
source elements of rare family types are paired with target elements of
the same types the same distance apart, each pairing proposes a
placement (as it is, and mirrored), the proposals are counted, and the
best ones are tried on every element. A floor can hold more than one copy
(both towers on L3): once the best placement has taken its copies, the
next best is looked for among the elements left.
"""
from __future__ import division

import math

from copycircuits.plan import Item, match

ANGLE_STEP = math.radians(0.5)      # proposals this near in angle count together
MIN_SHARE = 0.3                     # a second copy needs this share of the source matched
MIN_COUNT = 3                       # and at least this many elements
TIE = 0.97                          # placements matching this share of the best one tie
SAME_SPOT_WINS = 0.9                # the same spot is kept when it matches this share of the best
ANCHORS = 6                         # source elements whose pairs propose placements
CHECKS = 300000                     # target pairs compared for proposals, about at most
TRIED = 12                          # proposals tried on every element, the most counted first
MAX_COPIES = 4                      # copies looked for on one floor, at most


def _normal(angle):
    angle = math.fmod(angle, 2 * math.pi)
    if angle <= -math.pi:
        angle += 2 * math.pi
    elif angle > math.pi:
        angle -= 2 * math.pi
    return angle


class Placement(object):
    """Where a copy is: mirrored (Y flipped), turned by `angle` (radians,
    about the origin), then shifted by (tx, ty)."""

    def __init__(self, angle=0.0, mirrored=False, tx=0.0, ty=0.0):
        self.angle = _normal(angle)
        self.mirrored = mirrored
        self.tx = tx
        self.ty = ty
        self._cos = math.cos(self.angle)
        self._sin = math.sin(self.angle)

    def apply(self, x, y):
        if self.mirrored:
            y = -y
        return (x * self._cos - y * self._sin + self.tx,
                x * self._sin + y * self._cos + self.ty)

    def turned(self):
        return abs(self.angle) > ANGLE_STEP / 2

    def is_same_spot(self, tolerance):
        return not self.mirrored and not self.turned() and \
            math.hypot(self.tx, self.ty) <= tolerance

    def describe(self, tolerance, unit=1.0):
        """'same spot', 'moved 42.5 m', 'turned 90°' or 'mirrored'. unit: metres
        per model unit."""
        if self.mirrored:
            return u"mirrored"
        if self.turned():
            return u"turned %d°" % int(round(math.degrees(self.angle)))
        d = math.hypot(self.tx, self.ty)
        if d <= tolerance:
            return u"same spot"
        return u"moved %s m" % ("%.1f" % (d * unit)).rstrip("0").rstrip(".")

    def key(self, tolerance):
        """Proposals with the same key are the same placement."""
        step = max(4 * tolerance, 1e-9)
        return (self.mirrored, int(round(self.angle / ANGLE_STEP)),
                int(round(self.tx / step)), int(round(self.ty / step)))


SAME_SPOT = Placement()


def from_pairs(s1, s2, t1, t2, mirrored):
    """The placement taking s1 to t1 and s2 to t2 (points (x, y)), turning
    the s1-s2 direction onto the t1-t2 one."""
    sx, sy = s2[0] - s1[0], s2[1] - s1[1]
    if mirrored:
        sy = -sy
    angle = math.atan2(t2[1] - t1[1], t2[0] - t1[0]) - math.atan2(sy, sx)
    p = Placement(angle, mirrored)
    x, y = p.apply(s1[0], s1[1])
    return Placement(angle, mirrored, t1[0] - x, t1[1] - y)


class Copy(object):
    """One copy of the source on the target floor."""

    def __init__(self, placement, copies, by_family, score=0):
        self.placement = placement
        self.copies = copies            # {source key: target key}
        self.by_family = by_family      # source keys matched to another type of the family
        self.score = score


def moved(items, placement):
    """The items where `placement` puts them."""
    found = []
    for s in items:
        x, y = placement.apply(s.x, s.y)
        found.append(Item(s.key, s.type_key, x, y, s.z, s.family_key, s.flip))
    return found


def _by_type(items):
    groups = {}
    for i in items:
        groups.setdefault(i.type_key, []).append(i)
    return groups


def _anchors(source, targets_by_type, tolerance):
    """Up to ANCHORS source elements of the rarest types on the target floor,
    far enough apart to give a placement a clear direction."""
    spread = 20 * tolerance
    ranked = [s for s in source if targets_by_type.get(s.type_key)]
    ranked.sort(key=lambda s: (len(targets_by_type[s.type_key]), s.key))
    chosen = []
    for s in ranked:
        if all(math.hypot(s.x - a.x, s.y - a.y) >= spread for a in chosen):
            chosen.append(s)
            if len(chosen) >= ANCHORS:
                break
    return chosen


def proposals(source, target, tolerance, dz=0.0, z_tolerance=None):
    """[Placement], the most proposed first (at most TRIED)."""
    targets_by_type = _by_type(target)
    anchors = _anchors(source, targets_by_type, tolerance)
    near = {}
    for a in anchors:
        near[a.key] = [t for t in targets_by_type[a.type_key]
                       if z_tolerance is None or abs(t.z - a.z - dz) <= z_tolerance]
    votes, best = {}, {}
    checks = 0
    pairs = [(i, j) for i in range(len(anchors)) for j in range(i + 1, len(anchors))]
    for i, j in pairs:
        a, b = anchors[i], anchors[j]
        near_a, near_b = near[a.key], near[b.key]
        if checks and checks + len(near_a) * len(near_b) > CHECKS:
            continue
        checks += len(near_a) * len(near_b)
        gap = math.hypot(b.x - a.x, b.y - a.y)
        for ta in near_a:
            for tb in near_b:
                if ta.key == tb.key:
                    continue
                if abs(math.hypot(tb.x - ta.x, tb.y - ta.y) - gap) > 2 * tolerance:
                    continue
                for mirrored in (False, True):
                    p = from_pairs((a.x, a.y), (b.x, b.y), (ta.x, ta.y), (tb.x, tb.y),
                                   mirrored)
                    k = p.key(tolerance)
                    votes[k] = votes.get(k, 0) + 1
                    # the widest pair in a bin gives its most exact placement
                    if k not in best or gap > best[k][0]:
                        best[k] = (gap, p)
    ranked = sorted(votes, key=lambda k: (-votes[k], k))[:TRIED]
    return [best[k][1] for k in ranked]


def _try(placement, source, target, tolerance, dz, z_tolerance):
    by_family = set()
    copies = match(moved(source, placement), target, tolerance, dz, z_tolerance, by_family)
    flips = dict((t.key, t.flip) for t in target)
    flipped = dict((s.key, s.flip) for s in source)
    # how many pairs are flipped the way the placement says (Revit's Mirrored)
    agree = sum(1 for s, t in copies.items()
                if (flipped[s] != flips[t]) == placement.mirrored)
    return Copy(placement, copies, by_family, len(copies)), agree


def _best(source, target, tolerance, dz, z_tolerance):
    """The Copy that matches the most elements, or None."""
    tried = [SAME_SPOT] + [p for p in proposals(source, target, tolerance, dz, z_tolerance)
                           if not p.is_same_spot(tolerance)]
    found = [_try(p, source, target, tolerance, dz, z_tolerance) for p in tried]
    top = max(c.score for c, _ in found) if found else 0
    if not top:
        return None
    same = found[0][0]
    if same.score >= SAME_SPOT_WINS * top:
        return same
    tied = [(c, agree) for c, agree in found if c.score >= TIE * top]
    # among placements matching about as many, the one Revit's Mirrored agrees with
    tied.sort(key=lambda ca: (-ca[1], -ca[0].score))
    return tied[0][0]


def find(source, target, tolerance, dz=0.0, z_tolerance=None):
    """[Copy] of the source on the target floor, the best first. The first
    copy is kept when it matches MIN_COUNT elements (or all of them, when
    fewer); each next one needs MIN_SHARE of the source too."""
    copies = []
    left = list(target)
    need_first = min(MIN_COUNT, len(source))
    need_next = max(MIN_COUNT, int(math.ceil(MIN_SHARE * len(source))))
    while left and len(copies) < MAX_COPIES:
        best = _best(source, left, tolerance, dz, z_tolerance)
        if best is None or best.score < (need_next if copies else max(need_first, 1)):
            break
        copies.append(best)
        taken = set(best.copies.values())
        left = [t for t in left if t.key not in taken]
    return copies
