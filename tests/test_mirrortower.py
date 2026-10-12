# -*- coding: utf-8 -*-
import math

from copycircuits.plan import Item
from mirrortower.geometry import (
    centre, from_points, hull, inside, mirror_placement, own_images, revit_steps, swap_name,
)


def close(a, b, tol=1e-6):
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


def test_mirror_about_vertical_line():
    p = mirror_placement((10, 0), (10, 5))
    assert close(p.apply(4, 7), (16, 7))
    assert close(p.apply(10, 3), (10, 3))
    assert p.mirrored


def test_mirror_about_horizontal_line():
    p = mirror_placement((0, 2), (8, 2))
    assert close(p.apply(3, 5), (3, -1))


def test_mirror_about_slanted_line_is_its_own_inverse():
    p = mirror_placement((1, 1), (4, 3))
    for x, y in [(0, 0), (7, -2), (3.5, 9)]:
        assert close(p.apply(*p.apply(x, y)), (x, y))
    # a point on the line stays
    assert close(p.apply(7, 5), (7, 5))


def test_mirror_turns_directions():
    p = mirror_placement((0, 0), (0, 1))     # about the Y axis
    assert close(p.turn(1, 0), (-1, 0))
    assert close(p.turn(0, 1), (0, 1))


def test_same_points_give_no_line():
    assert mirror_placement((1, 1), (1, 1)) is None
    assert from_points((2, 2), (2, 2), (5, 5), (6, 6)) == (None, 0.0)


def _mirror_then_move(placement, x, y, about=(12.0, -7.0)):
    """What Revit does: mirror about the line through `about`, then move."""
    angle, (ax, ay), (dx, dy) = revit_steps(placement, about)
    line = mirror_placement((ax, ay), (ax + math.cos(angle), ay + math.sin(angle)))
    mx, my = line.apply(x, y)
    return mx + dx, my + dy


def test_diagonal_tower_from_two_point_pairs():
    # Tower 2 is Tower 1 flipped left-right, then moved up and right (the
    # user's site: no single mirror line does it)
    def tower2(x, y):
        return 200 - x + 30, y + 60
    s1, s2 = (10, 5), (40, 12)
    t1, t2 = tower2(*s1), tower2(*s2)
    p, stretch = from_points(s1, s2, t1, t2)
    assert abs(stretch) < 1e-9
    for x, y in [(0, 0), (25, 18), (55, -3)]:
        assert close(p.apply(x, y), tower2(x, y))
        assert close(_mirror_then_move(p, x, y), tower2(x, y))
    # facing directions flip left-right too
    assert close(p.turn(1, 0), (-1, 0))
    assert close(p.turn(0, 1), (0, 1))


def test_revit_steps_for_a_plain_mirror():
    p = mirror_placement((1, 1), (4, 3))
    for x, y in [(0, 0), (7, -2), (3.5, 9)]:
        assert close(_mirror_then_move(p, x, y), p.apply(x, y))


def test_points_not_the_same_distance_apart():
    _, stretch = from_points((0, 0), (10, 0), (100, 0), (88, 0))
    assert abs(stretch - 2) < 1e-9


def test_own_images_are_on_a_plain_mirror_line():
    p = mirror_placement((0, 0), (0, 10))
    items = [Item(1, "a", -5, 0), Item(2, "a", 0.01, 3), Item(3, "a", 4, 0)]
    assert own_images(items, p, 0.16) == set([2])


def test_hull_and_inside_rotated_box():
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    corners = [(x * c - y * s, x * s + y * c) for x, y in [(0, 0), (10, 0), (10, 4), (0, 4)]]
    # scope box lines give each corner twice, at two heights
    outline = hull(corners + corners)
    assert len(outline) == 4
    assert inside(outline, *(5 * c - 2 * s, 5 * s + 2 * c))
    assert not inside(outline, 10, 0)            # inside the axis box but not the rotated one
    assert inside(outline, -0.05, 0.0, pad=0.1)
    assert close(centre(hull([(0, 0), (4, 0), (4, 2), (0, 2)])), (2, 1))


def test_swap_name():
    assert swap_name(u"DB-B1-L4-01", u"B1", u"B2") == u"DB-B2-L4-01"
    assert swap_name(u"smdb-b1", u"B1", u"B2") == u"smdb-B2"
    assert swap_name(u"DB-B1-B1", u"b1", u"B2") == u"DB-B2-B2"
    assert swap_name(u"DB-L4-01", u"B1", u"B2") is None
    assert swap_name(u"DB-B1", u"", u"B2") is None


# ---------------------------------------------------------------- pairing

from mirrortower.pairing import BY_NAME, BY_SPOT, FALLBACK, ITSELF, board_for, pair_up  # noqa: E402

TOL = 0.16


def test_pair_up_finds_copies_at_the_mirrored_spot():
    line = mirror_placement((0, 0), (0, 10))         # Tower 2 is at -x
    tower1 = [Item(1, "light", 5, 2, 9.0), Item(2, "socket", 6, 3, 1.0),
              Item(3, "light", 7, 4, 9.0)]
    pool = [Item(11, "light", -5.02, 2, 9.0),        # 1's copy
            Item(12, "socket", -6, 3, 9.0),          # at the spot but at ceiling height
            Item(13, "socket", 6, 3, 1.0)]           # Tower 1 side, not a copy
    copies, missing = pair_up(tower1, pool, line, TOL, 0.5)
    assert copies == {1: 11}
    assert sorted(missing) == [2, 3]


def test_pair_up_boards_by_name_win():
    line = mirror_placement((0, 0), (0, 10))
    tower1 = [Item(1, "DB", 5, 2), Item(2, "DB", 8, 2)]
    pool = [Item(21, "DB", -5, 2), Item(22, "DB", -8, 2)]
    copies, missing = pair_up(tower1, pool, line, TOL, 0.5, by_name={1: 22})
    assert copies[1] == 22
    assert missing == [2]          # 22, its spot copy, is taken by name


def test_board_for():
    assert board_for(5, {5: 50}, None, None) == (50, BY_SPOT)
    assert board_for(5, {5: 50}, None, None, named={5}) == (50, BY_NAME)
    assert board_for(5, {5: 5}, None, None) == (5, ITSELF)
    assert board_for(5, {}, 70, 80) == (70, BY_NAME)
    assert board_for(5, {}, None, 80) == (80, BY_SPOT)
    assert board_for(5, {}, None, 5) == (5, ITSELF)
    assert board_for(5, {}, None, None) == (5, FALLBACK)
