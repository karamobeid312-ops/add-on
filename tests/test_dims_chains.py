# -*- coding: utf-8 -*-
import math

import pytest

from dims.chains import BOTH, NEAREST, NONE, Device, Hit, plan, segment_walls, text_side
from firealarm.layout import layout_detectors, point_in_loops, segments
from sample_rooms import ROOMS, rect, rotated

QUARTER = math.pi / 2


def devices(points, angle=0.0, axes=(0, 1)):
    """Devices at points, turned by angle, with the centre planes of `axes`."""
    return [Device(n, x, y, [(angle + k * QUARTER, (n, k)) for k in axes])
            for n, (x, y) in enumerate(points)]


def run(points, segs, angle=0.0, **options):
    return plan(devices(points, angle), segment_walls(segs), **options)


def along(chain):
    return [round(s.at, 3) for s in chain.stops]


def kinds(chain):
    return "".join("W" if s.is_wall else "D" for s in chain.stops)


def horizontal(result):
    return [c for c in result.chains if abs(math.sin(c.angle)) < 1e-9]


def vertical(result):
    return [c for c in result.chains if abs(math.cos(c.angle)) < 1e-9]


OFFICE = [(x, y) for y in (3.0, 9.0) for x in (10 / 3.0, 10.0, 50 / 3.0)]


def test_every_row_and_column_from_wall_to_wall():
    result = run(OFFICE, segments([rect(0, 0, 20, 12)]), walls=BOTH)
    rows, columns = horizontal(result), vertical(result)
    assert len(rows) == 2 and len(columns) == 3
    for chain in rows:
        assert kinds(chain) == "WDDDW"
        assert along(chain) == [0.0, 3.333, 10.0, 16.667, 20.0]
    for chain in columns:
        assert kinds(chain) == "WDDW"
        assert along(chain) == [0.0, 3.0, 9.0, 12.0]
    assert not result.alone and result.no_wall == 0 and result.skew == 0


def test_only_what_is_needed_fixes_a_grid_with_one_row_and_one_column():
    result = run(OFFICE, segments([rect(0, 0, 20, 12)]), every_row=False)
    rows, columns = horizontal(result), vertical(result)
    assert len(rows) == 1 and len(columns) == 1
    assert rows[0].across == pytest.approx(3.0)            # the bottom row
    assert columns[0].members[0].x == pytest.approx(10 / 3.0)   # the left column
    assert not result.alone


def test_dimension_lines_sit_on_the_text_side():
    result = run(OFFICE, segments([rect(0, 0, 20, 12)]), walls=BOTH)
    for chain in horizontal(result):
        (x0, y0), (x1, y1) = chain.line(0.5)
        assert y0 == pytest.approx(chain.members[0].y + 0.5)    # above the row
        assert (x0, x1) == (pytest.approx(0.0), pytest.approx(20.0))
    for chain in vertical(result):
        (x0, y0), (x1, y1) = chain.line(0.5)
        assert x0 == pytest.approx(chain.members[0].x - 0.5)    # left of the column
        assert (y0, y1) == (pytest.approx(0.0), pytest.approx(12.0))


def test_strings_start_at_the_nearest_wall():
    result = run(OFFICE, segments([rect(0, 0, 20, 12)]))
    for chain in horizontal(result):
        assert kinds(chain) == "WDDD" and along(chain)[0] == 0.0    # as near: the start wall
    for chain in vertical(result):
        assert kinds(chain) == "WDD" and along(chain)[0] == 0.0
    assert not result.alone and result.no_wall == 0


# as the first test drawing: a room with a fixture in its middle, and a long
# corridor (225 mm wall between them) with one fixture near each end
ROOM = rect(0, 0, 6.0, 4.35)
CORRIDOR = rect(6.225, 0, 8.625, 10.0)


def test_each_fixture_is_dimensioned_from_its_nearest_walls():
    result = run([(3.0, 2.175), (7.88, 8.045), (7.335, 2.385)], segments([ROOM, CORRIDOR]))
    found = sorted((kinds(c), round(c.stops[-1].at - c.stops[0].at, 3), round(c.angle, 3))
                   for c in result.chains)
    assert found == sorted([
        ("WD", 3.0, 0.0), ("WD", 2.175, 1.571),         # room: as near both ways, start wall
        ("DW", 0.745, 0.0), ("DW", 1.955, 1.571),       # corridor, top: right and top walls
        ("WD", 1.11, 0.0), ("WD", 2.385, 1.571),        # corridor, bottom: left and bottom walls
    ])
    assert not result.alone and result.no_wall == 0
    assert result.other_no_wall == 0 and result.other_skew == 0


def test_nearest_wall_takes_the_other_end_when_one_is_open():
    walls = [((0, 0), (0, 10))]                         # only a wall on the left
    result = run([(8.0, 5.0)], walls)
    row = horizontal(result)[0]
    assert kinds(row) == "WD" and along(row) == [0.0, 8.0]
    assert result.no_wall == 0                          # the open end is not needed
    assert result.other_no_wall == 1                    # but it is why the far wall is used


def test_nearest_wall_passes_over_a_wall_that_is_not_square():
    walls = [((0, 0), (0, 10)), ((9, 0), (10, 10))]    # the right wall is slanted
    result = run([(7.0, 5.0)], walls)
    row = horizontal(result)[0]
    assert kinds(row) == "WD" and along(row) == [0.0, 7.0]
    assert result.skew == 0 and result.other_skew == 1


# two offices side by side, 200 mm wall between them, rows lined up
TWO_OFFICES = segments([rect(0, 0, 6, 5), rect(6.2, 0, 12.2, 5)])
TWO_POINTS = [(1.5, 2.5), (4.5, 2.5), (7.7, 2.5), (10.7, 2.5)]


def test_a_wall_between_two_devices_cuts_the_row():
    result = run(TWO_POINTS, TWO_OFFICES, walls=BOTH)
    rows = sorted(horizontal(result), key=lambda c: c.stops[0].at)
    assert [along(c) for c in rows] == [[0.0, 1.5, 4.5, 6.0], [6.2, 7.7, 10.7, 12.2]]
    assert len(vertical(result)) == 4
    assert not result.alone


def test_each_room_gets_its_own_strings_when_only_what_is_needed():
    # two rooms one above the other, columns lined up: the upper room's
    # row cannot fix the lower room's devices across the wall
    walls = segments([rect(0, 0, 9, 4), rect(0, 4.2, 9, 8.2)])
    points = [(3.0, 2.0), (6.0, 2.0), (3.0, 6.2), (6.0, 6.2)]
    result = run(points, walls, every_row=False)
    rows = sorted(horizontal(result), key=lambda c: c.across)
    assert [c.across for c in rows] == [pytest.approx(2.0), pytest.approx(6.2)]
    assert len(vertical(result)) == 2                      # one per room
    assert not result.alone


def test_rotated_room_gets_rotated_strings():
    angle = math.radians(30)
    outline = rotated(rect(0, 0, 15, 10), 30)
    points = rotated([(3.75, 2.5), (11.25, 2.5), (3.75, 7.5), (11.25, 7.5)], 30)
    result = run(points, segments([outline]), angle=angle, walls=BOTH)
    assert len(result.chains) == 4
    for chain in result.chains:
        assert kinds(chain) == "WDDW"
        assert _turn(chain.angle, angle) < 1e-9
    lengths = sorted(round(c.stops[-1].at - c.stops[0].at, 3) for c in result.chains)
    assert lengths == [10.0, 10.0, 15.0, 15.0]


def _turn(a, b):
    d = (a - b) % QUARTER
    return min(d, QUARTER - d)


def test_devices_not_turned_with_the_room_cannot_take_its_walls():
    outline = rotated(rect(0, 0, 15, 10), 30)
    points = [(2.0, 5.0), (6.0, 5.0)]                       # on the model axes, room at 30 degrees
    assert all(point_in_loops(x, y, [outline]) for x, y in points)
    result = run(points, segments([outline]))
    assert len(result.chains) == 1 and kinds(result.chains[0]) == "DD"
    assert result.skew == 2 and result.no_wall == 0
    assert len(result.alone) == 2                           # nothing across: walls are skew


def test_round_room_walls_are_never_square():
    loops = [ROOMS[6][1][0]]
    lay = layout_detectors(loops, 9.0)
    result = run(lay.points, segments(loops), angle=lay.angle)
    assert result.skew > 0
    assert all(not s.is_wall for c in result.chains for s in c.stops)


def test_no_walls_found_leaves_the_ends_open():
    result = run([(0, 0), (4, 0)], [])
    assert len(horizontal(result)) == 1 and kinds(horizontal(result)[0]) == "DD"
    assert result.no_wall == 2
    # the two single-device columns have nothing to dimension to
    assert len(result.alone) == 2 and not vertical(result)


def test_between_devices_only():
    result = run(OFFICE, segments([rect(0, 0, 20, 12)]), walls=NONE)
    assert all(kinds(c) in ("DDD", "DD") for c in result.chains)
    assert result.no_wall == 0 and result.skew == 0


def test_between_devices_only_leaves_single_devices_alone():
    points = [(3.0, 3.0), (3.0, 9.0), (17.0, 6.0)]     # a column of two, one on its own
    result = run(points, segments([rect(0, 0, 20, 12)]), walls=NONE)
    assert len(result.chains) == 1 and kinds(result.chains[0]) == "DD"
    # rows: each device is alone along x; the lone device is alone both ways
    assert len(result.alone) == 4


def test_family_with_one_centre_plane_is_dimensioned_one_way():
    walls = segments([rect(0, 0, 10, 10)])
    result = plan(devices([(3, 5), (7, 5)], axes=(0,)), segment_walls(walls))
    assert len(result.chains) == 1
    assert kinds(horizontal(result)[0]) == "WDD"


def test_devices_turned_a_quarter_turn_are_dimensioned_together():
    walls = segments([rect(0, 0, 10, 10)])
    a = Device("a", 3, 5, [(0.0, "a-x"), (QUARTER, "a-y")])
    b = Device("b", 7, 5, [(QUARTER, "b-x"), (math.pi, "b-y")])   # turned 90 degrees
    result = plan([a, b], segment_walls(walls))
    row = horizontal(result)[0]
    assert [s.ref for s in row.stops if not s.is_wall] == ["a-x", "b-y"]


def test_devices_at_the_same_place_share_a_stop():
    walls = segments([rect(0, 0, 10, 10)])
    result = run([(3, 5), (3.005, 5), (7, 5)], walls, walls=BOTH)
    row = horizontal(result)[0]
    assert kinds(row) == "WDDW" and len(row.members) == 3
    assert not result.alone


def test_device_on_the_wall_is_not_dimensioned_to_it():
    walls = segments([rect(0, 0, 10, 10)])
    result = run([(0.0, 5.0), (4.0, 5.0)], walls, walls=BOTH)
    row = horizontal(result)[0]
    assert kinds(row) == "DDW" and along(row) == [0.0, 4.0, 10.0]
    assert result.no_wall == 0
    # the wall it is on is the nearest: nothing to add
    row = horizontal(run([(0.0, 5.0), (4.0, 5.0)], walls))[0]
    assert kinds(row) == "DD" and along(row) == [0.0, 4.0]


@pytest.mark.parametrize("name,loops", [r for r in ROOMS if not r[0].startswith("Round")])
@pytest.mark.parametrize("spacing", [9.0, 4.5])
@pytest.mark.parametrize("every_row", [True, False])
@pytest.mark.parametrize("walls", [NEAREST, BOTH])
def test_sample_rooms_every_detector_is_dimensioned_both_ways(name, loops, spacing, every_row,
                                                              walls):
    lay = layout_detectors(loops, spacing)
    result = run(lay.points, segments(loops), angle=lay.angle, every_row=every_row, walls=walls)
    assert not result.alone and result.no_wall == 0 and result.skew == 0
    positions = {0: set(), 1: set()}
    for chain in result.chains:
        k = 0 if abs(math.sin(chain.angle - lay.angle)) < 1e-9 else 1
        ats = [s.at for s in chain.stops]
        assert ats == sorted(ats) and len(set(round(a, 6) for a in ats)) == len(ats)
        assert chain.walls == (2 if walls == BOTH else 1)
        for device in chain.members:
            c, s = math.cos(chain.angle), math.sin(chain.angle)
            positions[k].add(round(device.x * c + device.y * s, 3))
    # every detector's position along each axis is on a string
    for x, y in lay.points:
        for k in (0, 1):
            a = lay.angle + k * QUARTER
            p = round(x * math.cos(a) + y * math.sin(a), 3)
            assert any(abs(p - q) <= 0.021 for q in positions[k])


def test_only_what_is_needed_is_never_more():
    for _, loops in ROOMS:
        lay = layout_detectors(loops, 4.5)
        walls = segments(loops)
        every = run(lay.points, walls, angle=lay.angle)
        needed = run(lay.points, walls, angle=lay.angle, every_row=False)
        assert len(needed.chains) <= len(every.chains)


def test_segment_walls_finds_the_first_wall():
    find = segment_walls(segments([rect(0, 0, 10, 10), rect(4, 4, 6, 6)]))
    here = Device(0, 1.0, 5.0, [])
    hit = find(here, (1.0, 0.0))
    assert hit.distance == pytest.approx(3.0) and hit.square
    assert find(here, (-1.0, 0.0)).distance == pytest.approx(1.0)
    slanted = find(here, (math.cos(0.3), math.sin(0.3)))
    assert not slanted.square
    assert find(Device(0, 20.0, 5.0, []), (1.0, 0.0)) is None


def test_hit_defaults():
    hit = Hit(2.0)
    assert hit.square and hit.ref is None


@pytest.mark.parametrize("direction,right,up,normal", [
    ((1, 0), (1, 0), (0, 1), (0, 1)),       # reads left to right: text above
    ((-1, 0), (1, 0), (0, 1), (0, 1)),
    ((0, 1), (1, 0), (0, 1), (-1, 0)),      # reads bottom to top: text on the left
    ((0, -1), (1, 0), (0, 1), (-1, 0)),
    ((1, 0), (0, 1), (-1, 0), (0, -1)),     # view turned: model x reads bottom to top
])
def test_text_side(direction, right, up, normal):
    assert text_side(direction[0], direction[1], right, up) == \
        (pytest.approx(normal[0]), pytest.approx(normal[1]))


def test_text_side_of_a_slanted_string():
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    nx, ny = text_side(c, s)
    assert (nx, ny) == (pytest.approx(-s), pytest.approx(c))
