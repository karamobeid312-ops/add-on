# -*- coding: utf-8 -*-
import math

import pytest

from firealarm.layout import (layout_detectors, main_direction, point_in_loops,
                              reach, segments, wall_distance)
from sample_rooms import ROOMS, circle, rect, rotated

SMOKE, HEAT = 9.0, 4.5


def worst_gap(loops, points, step):
    """Farthest any point of the ceiling is from its nearest detector,
    checked independently of the layout's own checking grid."""
    segs = segments(loops)
    xs = [p[0] for loop in loops for p in loop]
    ys = [p[1] for loop in loops for p in loop]
    probes = []
    y = min(ys)
    while y <= max(ys):
        x = min(xs)
        while x <= max(xs):
            if point_in_loops(x, y, loops):
                probes.append((x, y))
            x += step
        y += step
    for (ax, ay), (bx, by) in segs:
        for k in range(40):
            t = k / 40.0
            probes.append((ax + t * (bx - ax), ay + t * (by - ay)))
    return max(min(math.hypot(px - x, py - y) for x, y in points) for px, py in probes)


@pytest.mark.parametrize("width,depth,spacing,count", [
    (20, 12, SMOKE, 6),
    (9, 9, SMOKE, 1),
    (18, 9, SMOKE, 2),
    (18.01, 9, SMOKE, 3),
    (60, 40, SMOKE, 35),
    (9, 9, HEAT, 4),
    (20, 12, HEAT, 15),
    (3, 4, SMOKE, 1),
    (3, 4, HEAT, 1),
])
def test_rectangle_counts(width, depth, spacing, count):
    lay = layout_detectors([rect(0, 0, width, depth)], spacing)
    assert len(lay.points) == count
    assert lay.added == 0 and lay.uncovered == 0


def test_rectangle_is_even_grid_half_a_bay_from_the_walls():
    lay = layout_detectors([rect(0, 0, 20, 12)], SMOKE)
    xs = sorted(set(round(x, 3) for x, _ in lay.points))
    ys = sorted(set(round(y, 3) for _, y in lay.points))
    assert xs == [3.333, 10.0, 16.667]
    assert ys == [3.0, 9.0]
    # spacing: at most S apart, at most S/2 from the walls
    assert max(b - a for a, b in zip(xs, xs[1:])) <= SMOKE
    assert max(b - a for a, b in zip(ys, ys[1:])) <= SMOKE
    assert xs[0] <= SMOKE / 2 and 20 - xs[-1] <= SMOKE / 2
    assert ys[0] <= SMOKE / 2 and 12 - ys[-1] <= SMOKE / 2


@pytest.mark.parametrize("spacing", [SMOKE, HEAT])
@pytest.mark.parametrize("name,loops", ROOMS)
def test_sample_rooms_fully_covered(name, loops, spacing):
    lay = layout_detectors(loops, spacing)
    assert lay.points and lay.uncovered == 0
    assert worst_gap(loops, lay.points, spacing / 60.0) <= reach(spacing) + 1e-6
    for x, y in lay.points:
        assert point_in_loops(x, y, loops), (x, y)


@pytest.mark.parametrize("name,loops", ROOMS)
def test_detectors_clear_of_walls(name, loops):
    segs = segments(loops)
    for spacing in (SMOKE, HEAT):
        lay = layout_detectors(loops, spacing, clearance=0.5)
        for x, y in lay.points:
            assert wall_distance(x, y, segs) >= 0.5 - 1e-6, (name, spacing, x, y)


def test_rotated_room_gets_the_same_grid_turned():
    plain = layout_detectors([rect(0, 0, 15, 10)], SMOKE)
    turned = layout_detectors([rotated(rect(0, 0, 15, 10), 30)], SMOKE)
    assert len(turned.points) == len(plain.points) == 4
    assert abs(math.degrees(turned.angle) - 30) < 1e-6
    expected = sorted((round(x, 6), round(y, 6)) for x, y in rotated(plain.points, 30))
    assert sorted((round(x, 6), round(y, 6)) for x, y in turned.points) == expected


def test_main_direction():
    assert main_direction([rect(0, 0, 10, 5)]) == 0.0
    assert abs(math.degrees(main_direction([rotated(rect(0, 0, 10, 5), 120)])) - 30) < 1e-6
    assert main_direction([circle(8)]) == 0.0     # no main wall: model axes


def test_t_shape_cut_into_rectangles():
    loops = dict(ROOMS)["T-shaped lobby"]
    heat = layout_detectors(loops, HEAT)
    assert len(heat.points) == 26 and heat.added == 0   # bar 7 x 2 + stem 2 x 6
    assert len(layout_detectors(loops, SMOKE).points) == 7


def test_l_shaped_corridor_on_the_centreline():
    loops = dict(ROOMS)["L-shaped corridor, 2 m wide"]
    segs = segments(loops)
    for spacing, count in ((SMOKE, 6), (HEAT, 11)):
        lay = layout_detectors(loops, spacing)
        assert len(lay.points) == count
        for x, y in lay.points:
            assert abs(wall_distance(x, y, segs) - 1.0) < 1e-6


def test_narrow_space_keeps_to_the_middle():
    lay = layout_detectors([rect(0, 0, 5, 0.6)], SMOKE, clearance=0.5)
    assert len(lay.points) == 1
    x, y = lay.points[0]
    assert abs(y - 0.3) < 1e-6 and lay.uncovered == 0


def test_no_detector_in_shaft():
    loops = [rect(0, 0, 24, 16), rect(10, 6, 14, 10)]
    for spacing in (SMOKE, HEAT):
        for x, y in layout_detectors(loops, spacing).points:
            assert not (10 <= x <= 14 and 6 <= y <= 10)


def test_loop_direction_and_closing_point_do_not_matter():
    ccw = [(0, 0), (20, 0), (20, 10), (10, 10), (10, 20), (0, 20)]
    cw = list(reversed(ccw)) + [ccw[-1]]
    a = sorted(layout_detectors([ccw], SMOKE).points)
    b = sorted(layout_detectors([cw], SMOKE).points)
    assert [(round(x, 6), round(y, 6)) for x, y in a] == [(round(x, 6), round(y, 6)) for x, y in b]


def test_nothing_to_lay_out():
    assert layout_detectors([], SMOKE).points == []
    assert layout_detectors([[(0, 0), (1, 0)]], SMOKE).points == []
    assert layout_detectors([rect(0, 0, 5, 5)], 0).points == []


def test_single_detector_in_middle_of_main_rectangle():
    # bedroom 4.5 x 4.5 with its entrance passage beside the bathroom
    room = [(0, 3), (1.8, 3), (1.8, 0), (6.3, 0), (6.3, 4.5), (0, 4.5)]
    points = layout_detectors([room], SMOKE).points
    assert len(points) == 1
    assert abs(points[0][0] - 4.05) < 1e-6 and abs(points[0][1] - 2.25) < 1e-6
    assert worst_gap([room], points, 0.1) <= reach(SMOKE) + 1e-6


def test_single_detector_in_biggest_rectangle_of_stepped_room():
    # bedroom with a step on one side and a passage along the top
    room = [(1.8, 0), (6.0, 0), (6.0, 4.2), (4.2, 4.2), (4.2, 5.3), (1.4, 5.3),
            (1.4, 1.9), (1.8, 1.9)]
    points = layout_detectors([room], SMOKE).points
    assert len(points) == 1
    assert abs(points[0][0] - 3.9) < 1e-6 and abs(points[0][1] - 2.1) < 1e-6
    assert worst_gap([room], points, 0.1) <= reach(SMOKE) + 1e-6
