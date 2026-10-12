# -*- coding: utf-8 -*-
import math

from copycircuits.plan import Item
from mirrortower.geometry import (
    ON_LINE, OTHER_SIDE, TOWER_1, centre, halfway_line, hull, inside, mirror_placement, side,
    swap_name, where,
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
    assert halfway_line((2, 2), (2, 2)) is None


def test_halfway_line_takes_one_centre_to_the_other():
    a, b = (0, 0), (30, 10)
    p1, p2 = halfway_line(a, b)
    p = mirror_placement(p1, p2)
    assert close(p.apply(*a), b)
    assert close(p.apply(*b), a)


def test_side_sign():
    assert side((0, 0), (0, 1), -2, 5) > 0
    assert side((0, 0), (0, 1), 3, 5) < 0
    assert abs(side((0, 0), (0, 1), 3, 5) + 3) < 1e-9


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


def test_where_by_side_of_line():
    items = [Item(1, "a", -5, 0), Item(2, "a", 0.01, 3), Item(3, "a", 4, 0)]
    found = where(items, (0, 0), (0, 10), 0.16, home=(-20, 5))
    assert found == {1: TOWER_1, 2: ON_LINE, 3: OTHER_SIDE}
    # the same with the line drawn the other way
    assert where(items, (0, 10), (0, 0), 0.16, home=(-20, 5)) == found


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
