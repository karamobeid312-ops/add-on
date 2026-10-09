# -*- coding: utf-8 -*-
"""Where the copies of a floor are (no Revit needed).

A copied floor is usually right above or below its source (Paste >
Aligned to Selected Levels): every copy is at the same spot in plan. A
second tower built as a mirror of the first, or turned or moved, has its
copies somewhere else, by one placement in plan:

    copy = turn(mirror(source)) + shift

mirror flips Y (any mirror is that flip, then a turn), turn is about the
origin. The placements are found from the elements themselves:

- a few source elements of the rarest family types, spread over the
  floor, are the anchors;
- each pair of anchors is paired with target elements of the same types
  the same distance apart, and each pairing proposes a placement, as it
  is and mirrored;
- each proposal is checked on all the anchors (how many land on an
  element of their type), and the best checked ones, mirrored and not,
  are tried on every element;
- the placement matching the most elements wins. The same spot is kept
  when it matches nearly as many; between placements matching about as
  many (a symmetric floor), the one the elements' own orientation and
  Revit's Mirrored flag agree with wins.

A floor can hold more than one copy (both towers on L3): once the best
copy has taken its elements, the next is looked for among those left.
Panels are not taken: two copies can share one (a DB on the mirror axis).
A copy that is not at the same spot must match a good share of the
source, and the source floor's panels must land on panels, so a grid
that happens to line up with itself is not taken for a copy.
"""
from __future__ import division

import math

from copycircuits.plan import Item, match

ANGLE_STEP = math.radians(0.5)      # proposals this near in angle count together
ANGLE_BINS = int(round(2 * math.pi / ANGLE_STEP))
MIN_SHARE = 0.3                     # a copy elsewhere needs this share of the source matched
MIN_COUNT = 3                       # and at least this many elements
PANEL_SHARE = 0.5                   # and this share of the source floor's panels on panels
TYPE_SHARE = 0.5                    # and elements of this share of the source's family types
TIE = 0.97                          # placements matching this share of the best one tie
SAME_SPOT_WINS = 0.9                # the same spot is kept when it matches this share of the best
ANCHORS = 6                         # source elements whose pairs propose placements
PER_TYPE = 2                        # anchors of one family type, while other types are left
PAIR_CHECKS = 60000                 # target pairs compared for one anchor pair, at most
CHECKS = 400000                     # target pairs compared in all, about at most
TRIED = 12                          # proposals tried on every element: half mirrored
MAX_COPIES = 4                      # copies looked for on one floor, at most
FACING = 0.98                       # orientations this near (cosine) agree


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

    def turn(self, x, y):
        """A direction (x, y) as the copy has it."""
        if self.mirrored:
            y = -y
        return x * self._cos - y * self._sin, x * self._sin + y * self._cos

    def apply(self, x, y):
        x, y = self.turn(x, y)
        return x + self.tx, y + self.ty

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
        return (self.mirrored, int(round(self.angle / ANGLE_STEP)) % ANGLE_BINS,
                int(round(self.tx / step)), int(round(self.ty / step)))

    def near(self, other, tolerance, reach):
        """Both put every point within `reach` of the origin at about the same spot."""
        if self.mirrored != other.mirrored:
            return False
        turn = abs(_normal(self.angle - other.angle))
        return turn * reach + math.hypot(self.tx - other.tx, self.ty - other.ty) <= 2 * tolerance


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

    def __init__(self, placement, copies, by_family, score=0, agree=0):
        self.placement = placement
        self.copies = copies            # {source key: target key}
        self.by_family = by_family      # source keys matched to another type of the family
        self.score = score              # source elements matched, panels left out
        self.agree = agree              # pairs whose orientation agrees with the placement


def moved(items, placement):
    """The items where `placement` puts them."""
    found = []
    for s in items:
        x, y = placement.apply(s.x, s.y)
        facing = placement.turn(*s.facing) if s.facing is not None else None
        found.append(Item(s.key, s.type_key, x, y, s.z, s.family_key, s.flip, facing))
    return found


def _by_type(items):
    groups = {}
    for i in items:
        groups.setdefault(i.type_key, []).append(i)
    return groups


class _Grid(object):
    """Target items by family type (and family) and plan cell, to look up
    what is at a spot."""

    def __init__(self, items, tolerance):
        self.size = max(tolerance, 1e-9)
        self.cells = {}
        for t in items:
            for group in (("t", t.type_key), ("f", t.family_key)):
                if group[1] is None:
                    continue
                self.cells.setdefault(group + self._cell(t.x, t.y), []).append(t)

    def _cell(self, x, y):
        return int(math.floor(x / self.size)), int(math.floor(y / self.size))

    def at(self, item, x, y, tolerance, dz, z_tolerance):
        """A target item of the item's type (else family) within tolerance of (x, y)."""
        cx, cy = self._cell(x, y)
        for group in (("t", item.type_key), ("f", item.family_key)):
            if group[1] is None:
                continue
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for t in self.cells.get(group + (cx + dx, cy + dy), ()):
                        if z_tolerance is not None and abs(t.z - item.z - dz) > z_tolerance:
                            continue
                        if math.hypot(t.x - x, t.y - y) <= tolerance:
                            return t
        return None


def _anchors(source, targets_by_type, tolerance):
    """Up to ANCHORS source elements, of the family types rarest on both
    floors first (at most PER_TYPE of a type while other types are left),
    each as far as can be from those already chosen."""
    spread = 20 * tolerance
    by_type = _by_type([s for s in source if targets_by_type.get(s.type_key)])
    types = sorted(by_type, key=lambda t: (max(len(by_type[t]), len(targets_by_type[t])),
                                           str(t)))
    if not types:
        return []
    cx = sum(s.x for s in source) / len(source)
    cy = sum(s.y for s in source) / len(source)
    chosen = []

    def farthest(candidates):
        best, best_d = None, None
        for s in candidates:
            if chosen:
                d = min(math.hypot(s.x - a.x, s.y - a.y) for a in chosen)
                if d < spread:
                    continue
            else:
                d = math.hypot(s.x - cx, s.y - cy)
            if best is None or d > best_d or (d == best_d and str(s.key) < str(best.key)):
                best, best_d = s, d
        return best

    for limit in (PER_TYPE, ANCHORS):
        for t in types:
            taken = len([a for a in chosen if a.type_key == t])
            while taken < limit and len(chosen) < ANCHORS:
                s = farthest([c for c in by_type[t] if c not in chosen])
                if s is None:
                    break
                chosen.append(s)
                taken += 1
        if len(chosen) >= ANCHORS:
            break
    return chosen


def _thin(items, keep):
    """Every n-th item, so at most about `keep` are left."""
    if len(items) <= keep:
        return items
    step = int(math.ceil(len(items) / float(max(keep, 1))))
    return items[::step]


def proposals(source, target, tolerance, dz=0.0, z_tolerance=None):
    """[Placement], the best checked first: at most TRIED, half of them
    mirrored when there are enough of both."""
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
        if checks >= CHECKS:
            break
        a, b = anchors[i], anchors[j]
        near_a, near_b = near[a.key], near[b.key]
        if not near_a or not near_b:
            continue
        if len(near_a) * len(near_b) > PAIR_CHECKS:
            # thin both alike: the copy of each anchor may then be missed for this
            # pair, but other pairs (rarer types first) still propose it
            keep = int(math.sqrt(PAIR_CHECKS))
            near_a, near_b = _thin(near_a, keep), _thin(near_b, keep)
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
    if not votes:
        return []
    grid = _Grid(target, tolerance)
    checked = {}
    for k in votes:
        p = best[k][1]
        landed = 0
        for a in anchors:
            x, y = p.apply(a.x, a.y)
            if grid.at(a, x, y, tolerance, dz, z_tolerance) is not None:
                landed += 1
        checked[k] = landed
    order = sorted(votes, key=lambda k: (-checked[k], -votes[k], k))
    flat = [k for k in order if not k[0]]
    flipped = [k for k in order if k[0]]
    half = TRIED // 2
    keys = flat[:half] + flipped[:half]
    keys += [k for k in order if k not in keys][:TRIED - len(keys)]
    keys.sort(key=lambda k: (-checked[k], -votes[k], k))
    return [best[k][1] for k in keys]


def _try(placement, source, target, tolerance, dz, z_tolerance, panels=()):
    by_family = set()
    copies = match(moved(source, placement), target, tolerance, dz, z_tolerance, by_family)
    targets = dict((t.key, t) for t in target)
    sources = dict((s.key, s) for s in source)
    agree = 0
    for s, t in copies.items():
        si, ti = sources[s], targets[t]
        # Revit's Mirrored flag flips the way the placement says
        if (si.flip != ti.flip) == placement.mirrored:
            agree += 1
        # the element faces the way the placement turns it
        if si.facing is not None and ti.facing is not None:
            fx, fy = placement.turn(*si.facing)
            if fx * ti.facing[0] + fy * ti.facing[1] >= FACING:
                agree += 1
    fixtures = len([k for k in copies if k not in panels])
    only_panels = all(s.key in panels for s in source)
    score = len(copies) if only_panels else fixtures
    return Copy(placement, copies, by_family, score, agree)


def _ranked(source, target, tolerance, dz, z_tolerance, panels, same_floor, done):
    """[Copy] of the placements worth trying, the best first."""
    same_spot = not same_floor and not any(p.is_same_spot(tolerance) for p in done)
    tried = [SAME_SPOT] if same_spot else []
    reach = max([math.hypot(s.x, s.y) for s in source] or [0.0])
    for p in proposals(source, target, tolerance, dz, z_tolerance):
        if p.is_same_spot(tolerance):
            continue                # tried as SAME_SPOT, or not wanted
        if any(p.near(d, tolerance, reach) for d in done):
            continue
        tried.append(p)
    found = [_try(p, source, target, tolerance, dz, z_tolerance, panels) for p in tried]
    found = [c for c in found if c.score]
    if not found:
        return []
    top = max(c.score for c in found)
    first = []
    if found[0].placement is SAME_SPOT and found[0].score >= SAME_SPOT_WINS * top:
        first = [found.pop(0)]
    tied = [c for c in found if c.score >= TIE * top]
    rest = [c for c in found if c.score < TIE * top]
    # among placements matching about as many, the one the orientations agree with
    tied.sort(key=lambda c: (-c.agree, -c.score))
    rest.sort(key=lambda c: -c.score)
    return first + tied + rest


def _panels_land(copy, source, panel_targets, panels, tolerance, dz, z_tolerance):
    """How many of the source floor's panels land on a panel of their type
    (or family) where the copy puts them: any of the floor, taken or not."""
    if not panels:
        return 0
    grid = _Grid(panel_targets, tolerance)
    landed = 0
    for s in source:
        if s.key not in panels:
            continue
        x, y = copy.placement.apply(s.x, s.y)
        if grid.at(s, x, y, tolerance, dz, z_tolerance) is not None:
            landed += 1
    return landed


def find(source, target, tolerance, dz=0.0, z_tolerance=None, panels=(),
         panel_targets=None, same_floor=False):
    """[Copy] of the source on the target floor, the best first.

    panels: source keys of the source floor's panels; they are not taken by
    a copy, so the next copy can use them too. panel_targets: the target
    floor's panels, those left out of `target` too (the source's own on the
    same floor); by default `target`. same_floor: the target is the source
    floor, where only copies elsewhere (the other tower) are looked for.

    The same spot is kept when it matches anything. A copy elsewhere must
    match MIN_SHARE of the source (at least MIN_COUNT, or all of a smaller
    source), elements of TYPE_SHARE of its family types, and PANEL_SHARE of
    the source floor's panels must land on panels."""
    panels = set(panels)
    if panel_targets is None:
        panel_targets = target
    count = len([s for s in source if s.key not in panels]) or len(source)
    need = min(count, max(MIN_COUNT, int(math.ceil(MIN_SHARE * count))))
    need_panels = int(math.ceil(PANEL_SHARE * len(panels))) if panels else 0
    kinds = dict((s.key, s.type_key) for s in source if s.key not in panels)
    need_kinds = int(math.ceil(TYPE_SHARE * len(set(kinds.values()))))
    copies, done = [], []
    left = list(target)
    while left and len(copies) < MAX_COPIES:
        chosen = None
        for c in _ranked(source, left, tolerance, dz, z_tolerance, panels, same_floor, done):
            if c.placement is SAME_SPOT:
                chosen = c
                break
            if c.score < need:
                continue
            if len(set(kinds[k] for k in c.copies if k in kinds)) < need_kinds:
                continue
            if _panels_land(c, source, panel_targets, panels, tolerance, dz,
                            z_tolerance) < need_panels:
                continue
            chosen = c
            break
        if chosen is None:
            break
        copies.append(chosen)
        done.append(chosen.placement)
        taken = set(t for s, t in chosen.copies.items() if s not in panels)
        left = [t for t in left if t.key not in taken]
    return copies
