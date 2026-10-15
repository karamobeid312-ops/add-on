# -*- coding: utf-8 -*-
"""Where the copies of a floor are: same spot, moved, turned, mirrored."""
import math

from copycircuits.placement import Placement, SAME_SPOT, find, from_pairs, moved, proposals
from copycircuits.plan import Item

TOL = 0.16      # about 50 mm in feet


def tower(start=1, flip=False, dx=0.0):
    """A floor of one tower: panels, a grid of floor boxes, sockets and
    lights, not symmetric."""
    items, key = [], start
    for i, (x, y, kind) in enumerate([(10, 5, "DB-A"), (40, 6, "DB-B"), (25, 30, "DB-C")]):
        items.append(Item(key, kind, x + dx, y, 0.0, "DB", flip)); key += 1
    for gx in range(6):
        for gy in range(4):
            items.append(Item(key, "FB1", 5 + gx * 7 + dx, 10 + gy * 5.5, 0.0, "FB", flip))
            key += 1
    for i in range(15):
        items.append(Item(key, "R01", 3 + i * 3.1 + dx, 2 + (i % 4) * 0.7, 1.0, "R", flip))
        key += 1
    for i in range(10):
        items.append(Item(key, "LT", 6 + i * 4.3 + dx, 35 + (i % 3) * 2.2, 9.0, "L", flip))
        key += 1
    return items


def placed(items, placement, start, dz=0.0, flip=False):
    found = []
    for n, i in enumerate(items):
        x, y = placement.apply(i.x, i.y)
        facing = placement.turn(*i.facing) if i.facing is not None else None
        found.append(Item(start + n, i.type_key, x, y, i.z + dz, i.family_key, flip, facing))
    return found


def test_placement_apply_and_describe():
    p = Placement(math.pi / 2, False, 10, 0)
    x, y = p.apply(1, 0)
    assert abs(x - 10) < 1e-9 and abs(y - 1) < 1e-9
    m = Placement(0, True, 0, 0)
    assert m.apply(3, 4) == (3, -4)
    assert SAME_SPOT.describe(TOL) == "same spot"
    assert Placement(0, False, 100 / 0.3048, 0).describe(TOL, 0.3048) == "moved 100 m"
    assert Placement(math.pi, False, 5, 5).describe(TOL) == "turned 180°"
    assert Placement(0.3, True, 5, 5).describe(TOL) == "mirrored"


def test_from_pairs_recovers_a_mirror():
    truth = Placement(math.radians(90), True, 120.0, -3.0)
    s1, s2 = (10.0, 5.0), (40.0, 6.0)
    t1, t2 = truth.apply(*s1), truth.apply(*s2)
    p = from_pairs(s1, s2, t1, t2, True)
    for pt in [(0, 0), (25, 30), (-7, 3)]:
        a, b = p.apply(*pt), truth.apply(*pt)
        assert math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-6


def test_typical_floor_is_the_same_spot():
    source = tower()
    target = placed(source, SAME_SPOT, 1000, dz=-13.0)
    copies = find(source, target, TOL, dz=-13.0, z_tolerance=1.6)
    assert len(copies) == 1
    assert copies[0].placement.is_same_spot(TOL)
    assert len(copies[0].copies) == len(source)


def test_mirrored_tower_on_the_same_floor():
    source = tower()
    truth = Placement(0, True, 0, 0)          # mirrored about the X axis...
    truth = Placement(math.pi, True, 160.0, 0)  # ...i.e. about x = 80: (x, y) -> (160 - x, y)
    target = placed(source, truth, 1000, flip=True)
    copies = find(source, target, TOL)
    assert len(copies) == 1
    assert copies[0].placement.mirrored
    assert len(copies[0].copies) == len(source)
    for s in source:
        t = target[[i.key for i in target].index(copies[0].copies[s.key])]
        x, y = truth.apply(s.x, s.y)
        assert math.hypot(t.x - x, t.y - y) < 1e-6


def test_both_towers_on_the_floor_below():
    source = tower()
    mirror = Placement(math.pi, True, 160.0, 0)
    target = placed(source, SAME_SPOT, 1000, dz=-13.0) + \
        placed(source, mirror, 2000, dz=-13.0, flip=True)
    copies = find(source, target, TOL, dz=-13.0, z_tolerance=1.6)
    assert len(copies) == 2
    assert copies[0].placement.is_same_spot(TOL)
    assert copies[1].placement.mirrored
    assert set(copies[0].copies.values()) == set(range(1000, 1000 + len(source)))
    assert set(copies[1].copies.values()) == set(range(2000, 2000 + len(source)))


def test_turned_and_moved_copy():
    source = tower()
    truth = Placement(math.radians(90), False, 200.0, 50.0)
    target = placed(source, truth, 1000)
    copies = find(source, target, TOL)
    assert len(copies) == 1
    assert not copies[0].placement.mirrored
    assert abs(math.degrees(copies[0].placement.angle) - 90) < 0.1
    assert len(copies[0].copies) == len(source)


def test_semi_typical_mirrored_copy():
    source = tower()
    truth = Placement(math.pi, True, 160.0, 0)
    target = placed(source, truth, 1000, flip=True)
    target = [t for n, t in enumerate(target) if n % 5 != 3]        # some removed
    target.append(Item(5000, "FB1", 999.0, 999.0, 0.0, "FB"))          # one added
    copies = find(source, target, TOL)
    assert len(copies) == 1 and copies[0].placement.mirrored
    assert len(copies[0].copies) == len(target) - 1


def test_symmetric_floor_told_by_the_way_the_fixtures_face():
    # a symmetric grid: its mirror image is also a shifted copy of it, and a
    # copy mirrored about the other axis; the fixtures facing +X tell which
    source = [Item(k, "FB1", (k % 6) * 7.0, (k // 6) * 5.0, 0.0, "FB", False, (1.0, 0.0))
              for k in range(24)]
    mirror = Placement(math.pi, True, 200.0, 0)
    target = placed(source, mirror, 1000, flip=True)
    copies = find(source, target, TOL)
    assert len(copies) == 1
    assert copies[0].placement.mirrored
    assert copies[0].copies == dict((s.key, 1000 + n) for n, s in enumerate(source))


def test_other_tower_on_the_source_floor_itself():
    source = tower()
    mirror = Placement(math.pi, True, 160.0, 0)
    spare = [Item(900, "FB1", 5.0, 10.0, 0.0, "FB")]           # at a source spot: not a copy
    target = placed(source, mirror, 1000, flip=True) + spare
    copies = find(source, target, TOL, same_floor=True)
    assert len(copies) == 1 and copies[0].placement.mirrored
    assert 900 not in copies[0].copies.values()
    assert find(source, spare, TOL, same_floor=True) == []


def test_panel_on_the_axis_feeds_both_towers():
    source = tower()
    axis = Item(99, "DB-X", 80.0, 20.0, 0.0, "DB")              # on x = 80, the mirror axis
    source.append(axis)
    panels = set([1, 2, 3, 99])
    mirror = Placement(math.pi, True, 160.0, 0)
    target = placed([s for s in source if s.key != 99], mirror, 1000, flip=True)
    copies = find(source, target, TOL, panels=panels, panel_targets=target + [axis],
                  same_floor=True)
    assert len(copies) == 1 and copies[0].placement.mirrored


def test_a_few_elements_alike_are_not_a_copy():
    source = tower()
    mirror = Placement(math.pi, True, 160.0, 0)
    target = placed(source, mirror, 1000, flip=True)[3:8]       # 5 floor boxes of 52
    assert find(source, target, TOL, same_floor=True) == []


def test_copies_leave_the_panels_to_the_next_copy():
    # the riser between the towers, on the mirror axis, feeds both copies
    source = [i for i in tower() if i.key > 3]
    source += [Item(k, "DB-%d" % k, 80.0, 6.0 * k, 0.0, "DB") for k in (1, 2, 3)]
    mirror = Placement(math.pi, True, 160.0, 0)
    below = placed(source, SAME_SPOT, 1000, dz=-13.0)
    risers = [t for t in below if t.type_key.startswith("DB")]
    other = [t for t in placed(source, mirror, 2000, dz=-13.0, flip=True)
             if not t.type_key.startswith("DB")]
    copies = find(source, below + other, TOL, dz=-13.0, z_tolerance=1.6, panels=[1, 2, 3])
    assert len(copies) == 2 and copies[1].placement.mirrored
    for copy in copies:
        assert set(copy.copies[k] for k in (1, 2, 3)) == set(t.key for t in risers)


def test_nothing_alike():
    source = tower()
    target = [Item(1000 + k, "OTHER", k * 3.0, 0, 0, "O") for k in range(20)]
    assert find(source, target, TOL) == []


def test_same_spot_kept_on_a_partly_matching_floor():
    source = tower()
    target = placed(source, SAME_SPOT, 1000)[:10]
    copies = find(source, target, TOL)
    assert len(copies) == 1 and copies[0].placement.is_same_spot(TOL)
    assert len(copies[0].copies) == 10


def test_proposals_include_the_truth():
    source = tower()
    truth = Placement(math.radians(-30), True, 55.0, 12.0)
    target = placed(source, truth, 1000)
    found = proposals(source, target, TOL)
    assert any(p.mirrored and abs(p.angle - truth.angle) < 0.01 for p in found)


def test_moved_items_keep_their_keys():
    source = tower()
    out = moved(source, Placement(0, False, 5, 0))
    assert [i.key for i in out] == [i.key for i in source]
    assert out[0].x == source[0].x + 5


def test_large_floor_is_quick():
    import time
    source = [Item(k, "FB1", (k % 40) * 3.0 + (k % 7) * 0.1, (k // 40) * 2.5, 0.0, "FB")
              for k in range(1200)]
    source += [Item(5000 + k, "DB%d" % (k % 3), k * 9.0, -5.0, 0.0, "DB") for k in range(12)]
    target = placed(source, Placement(math.pi, True, 300.0, 0), 10000, flip=True)
    started = time.time()
    copies = find(source, target, TOL)
    assert time.time() - started < 5
    assert copies[0].placement.mirrored and len(copies[0].copies) == len(source)
