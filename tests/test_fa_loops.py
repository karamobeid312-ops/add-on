# -*- coding: utf-8 -*-
import math
import random

import pytest

from firealarm.layout import layout_detectors
from firealarm.loops import START, crossings, line_between, plan_loops
from sample_rooms import rect


def scatter(n, seed, w=60.0, h=40.0):
    rng = random.Random(seed)
    return [(rng.uniform(0, w), rng.uniform(0, h)) for _ in range(n)]


def check_loops(points, loops, start_xy, max_devices=120, square=False):
    """Every device on exactly one loop, loops within size, none crossing
    itself (straight lines), every loop starting from the start."""
    visited = sorted(i for loop in loops for i in loop.devices)
    assert visited == list(range(len(points)))
    for loop in loops:
        assert 1 <= len(loop.devices) <= max_devices
        if not square:
            assert crossings(loop, points, start_xy) == []
        where = [start_xy if s == START else points[s] for s in loop.stops]
        assert where[0] == start_xy
        length = sum(abs(a[0] - b[0]) + abs(a[1] - b[1]) if square else
                     math.hypot(a[0] - b[0], a[1] - b[1])
                     for a, b in zip(where, where[1:] + where[:1]))
        assert abs(length - loop.length) < 1e-6


def test_one_loop_from_the_start_device():
    points = scatter(120, 1)
    loops = plan_loops(points, 7)
    assert len(loops) == 1
    assert loops[0].stops[0] == 7 and START not in loops[0].stops
    check_loops(points, loops, points[7])


@pytest.mark.parametrize("seed", range(5))
def test_routes_never_cross(seed):
    points = scatter(100, seed)
    check_loops(points, plan_loops(points, (0.0, 0.0)), (0.0, 0.0))


def test_split_into_equal_loops_from_the_panel():
    points = scatter(250, 3, 80, 50)
    loops = plan_loops(points, (0.0, 0.0))
    assert sorted(len(l.devices) for l in loops) == [83, 83, 84]
    assert all(l.stops[0] == START for l in loops)
    check_loops(points, loops, (0.0, 0.0))
    # numbered anticlockwise round the panel (in the corner: from the x axis up)
    def direction(l):
        pts = [points[i] for i in l.devices]
        return math.atan2(sum(p[1] for p in pts), sum(p[0] for p in pts))
    assert [direction(l) for l in loops] == sorted(direction(l) for l in loops)


@pytest.mark.parametrize("count,sizes", [(120, [120]), (121, [60, 61]), (240, [120, 120]),
                                         (241, [80, 80, 81])])
def test_loop_sizes(count, sizes):
    points = scatter(count, 4, 90, 50)
    assert sorted(len(l.devices) for l in plan_loops(points, 0)) == sizes


def test_start_device_is_first_on_loop_one_only():
    points = scatter(300, 5, 90, 60)
    loops = plan_loops(points, 42)
    assert loops[0].stops[0] == 42
    assert all(l.stops[0] == START and 42 not in l.stops for l in loops[1:])
    check_loops(points, loops, points[42])


def test_devices_per_loop_setting():
    points = scatter(35, 6)
    loops = plan_loops(points, (0.0, 0.0), max_devices=10)
    assert sorted(len(l.devices) for l in loops) == [8, 9, 9, 9]
    check_loops(points, loops, (0.0, 0.0), max_devices=10)


def test_shortest_route_on_a_grid():
    # 4 x 4 devices 1 m apart: the best closed route is 16 m
    points = [(x, y) for y in range(4) for x in range(4)]
    loop = plan_loops(points, 0)[0]
    assert abs(loop.length - 16.0) < 1e-9


def test_devices_on_a_circle_go_round():
    rng = random.Random(7)
    points = [(10 * math.cos(a), 10 * math.sin(a))
              for a in sorted(rng.uniform(0, 2 * math.pi) for _ in range(40))]
    rng.shuffle(points)
    loop = plan_loops(points, 0)[0]
    ring = sorted(points, key=lambda p: math.atan2(p[1], p[0]))
    perimeter = sum(math.hypot(a[0] - b[0], a[1] - b[1]) for a, b in zip(ring, ring[1:] + ring[:1]))
    assert abs(loop.length - perimeter) < 1e-6


def test_detector_grid_splits_in_two():
    points = layout_detectors([rect(0, 0, 60, 40)], 4.5).points     # 126 heat detectors
    loops = plan_loops(points, (0.0, 20.0))
    assert sorted(len(l.devices) for l in loops) == [63, 63]
    check_loops(points, loops, (0.0, 20.0))


def test_every_loop_starts_at_a_panel_on_the_wall():
    # panel in the middle of the left wall: the loops are the lower and
    # upper halves, both beginning next to the panel (not left and right
    # halves, where loop 2 would run across loop 1 to reach the panel)
    points = layout_detectors([rect(0, 0, 60, 40)], 4.5).points
    panel = (0.0, 20.0)
    loops = plan_loops(points, panel)
    for loop in loops:
        assert min(math.hypot(points[i][0] - panel[0], points[i][1] - panel[1])
                   for i in loop.devices) < 5.0
    lower = [points[i][1] for i in loops[0].devices]
    assert max(lower) <= 20.0 + 1e-9                # anticlockwise: from below the panel up


def test_small_cases():
    assert plan_loops([], (0.0, 0.0)) == []
    one = plan_loops([(3.0, 4.0)], (0.0, 0.0))
    assert one[0].stops == [START, 0] and abs(one[0].length - 10.0) < 1e-9
    alone = plan_loops([(3.0, 4.0)], 0)
    assert alone[0].stops == [0] and alone[0].length == 0.0


def test_line_stops_at_the_symbols():
    box_a = (-0.3, -0.3, 0.3, 0.3)
    box_b = (9.8, -0.2, 10.2, 0.2)
    (a, b) = line_between((0.0, 0.0), (10.0, 0.0), box_a, box_b)
    assert a == pytest.approx((0.3, 0.0)) and b == pytest.approx((9.8, 0.0))
    # diagonal: leaves the square box through its corner side
    (a, _) = line_between((0.0, 0.0), (10.0, 10.0), box_a, None)
    assert a == pytest.approx((0.3, 0.3))
    # no box: the gap from the centre
    (a, b) = line_between((0.0, 0.0), (0.0, 5.0), None, None, gap=0.25)
    assert a == pytest.approx((0.0, 0.25)) and b == pytest.approx((0.0, 4.75))
    # the gap is at least the gap even with a small box
    (a, _) = line_between((0.0, 0.0), (10.0, 0.0), (-0.05, -0.05, 0.05, 0.05), None, gap=0.2)
    assert a == pytest.approx((0.2, 0.0))
    # devices very close: each end gives up at most 45 %
    (a, b) = line_between((0.0, 0.0), (0.5, 0.0), box_a, (0.2, -0.3, 0.8, 0.3))
    assert a == pytest.approx((0.225, 0.0)) and b == pytest.approx((0.275, 0.0))
    assert line_between((1.0, 1.0), (1.0, 1.0)) is None


# ---------------------------------------------------------------- square loops

from firealarm.loops import _Box, _clash, grid_angle, loop_lines  # noqa: E402


def square(points, start, boxes=None, gap=0.0, max_devices=120, band=0.3):
    angle = grid_angle(points)
    loops = plan_loops(points, start, max_devices, True, angle, band)
    start_xy = start if isinstance(start, tuple) else points[start]
    drawn, lines = [], []
    for loop in loops:
        lines.append(loop_lines(loop, points, start_xy, boxes, None, gap, True, angle, drawn))
    return angle, loops, lines, drawn


def box(p, r=0.25):
    return (p[0] - r, p[1] - r, p[0] + r, p[1] + r)


def check_square(points, drawn, boxes):
    """Every line along the grid (in its frame), none through a device,
    none crossing or lying on another."""
    frame_boxes = [_Box(p, b, 0.0, 0.0) for p, b in zip(points, boxes)]
    for s in drawn:
        (x0, y0), (x1, y1) = s
        assert abs(x0 - x1) < 1e-9 or abs(y0 - y1) < 1e-9
        assert not any(b.hit(s) for b in frame_boxes), s
    assert all(_clash(s, t) == 0 for i, s in enumerate(drawn) for t in drawn[i + 1:])


def test_square_loop_on_an_open_space_grid():
    # 3 columns x 4 rows, as the open space of the drawing, from a corner device
    points = [(x, y) for x in (0.0, 15.5, 30.8) for y in (0.0, 10.8, 23.2, 34.5)]
    boxes = [box(p) for p in points]
    angle, loops, lines, drawn = square(points, 0, boxes)
    assert angle == 0.0 and len(loops) == 1
    # up the first column, then a snake through the other two, as drawn by hand
    assert abs(loops[0].length - 161.2) < 1e-6
    assert [points[i] for i in loops[0].stops] == [
        (0.0, 0.0), (0.0, 10.8), (0.0, 23.2), (0.0, 34.5), (15.5, 34.5), (30.8, 34.5),
        (30.8, 23.2), (15.5, 23.2), (15.5, 10.8), (30.8, 10.8), (30.8, 0.0), (15.5, 0.0)]
    check_square(points, drawn, boxes)
    assert len(lines[0]) == 12          # one straight line per step, no bends needed


def test_square_loops_on_detector_grids_never_run_through_devices():
    for points, start in ((layout_detectors([rect(0, 0, 60, 40)], 4.5).points, (0.0, 20.0)),
                          (layout_detectors([[(0, 0), (70, 0), (70, 20), (30, 20), (30, 50),
                                              (0, 50)]], 5.0).points, 0)):
        boxes = [box(p, 0.45) for p in points]
        angle, loops, lines, drawn = square(points, start, boxes, band=0.45)
        check_loops(points, loops, start if isinstance(start, tuple) else points[start],
                    square=True)
        frame_boxes = [_Box(p, b, 0.0, 0.0) for p, b in zip(points, boxes)]
        assert not any(b.hit(s) for s in drawn for b in frame_boxes)


def test_grid_angle():
    grid = [(x * 5.0, y * 4.0) for x in range(6) for y in range(4)]
    assert grid_angle(grid) == 0.0
    turned = [(x * math.cos(0.5236) - y * math.sin(0.5236), x * math.sin(0.5236) + y * math.cos(0.5236))
              for x, y in grid]
    assert abs(grid_angle(turned) - 0.5236) < 1e-6
    assert grid_angle(scatter(80, 9), fallback=0.1) == pytest.approx(0.1)   # no grid: the view's
    assert grid_angle([(0, 0), (1, 1)], fallback=0.2) == pytest.approx(0.2)


def test_square_lines_follow_a_turned_grid():
    grid = [(x * 5.0, y * 4.0) for x in range(5) for y in range(3)]
    a = 0.5236
    turned = [(x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)) for x, y in grid]
    angle, loops, lines, _ = square(turned, 0)
    for (x0, y0), (x1, y1) in lines[0]:
        direction = math.atan2(y1 - y0, x1 - x0) % (math.pi / 2)
        assert min(abs(direction - a), abs(direction - a + math.pi / 2)) < 1e-6


def _pair(points, boxes, drawn=None):
    loop = plan_loops(points[:2], 0)[0]
    return loop_lines(loop, points, points[0], boxes, None, 0.0, True, 0.0, drawn)


def test_devices_nearly_in_line_get_one_straight_line():
    points = [(0.0, 0.0), (6.0, 0.08)]
    lines = _pair(points, [box(p) for p in points])
    # there and back: one horizontal line each way, at the middle height, box to box
    assert lines[0][0] == pytest.approx((0.25, 0.04)) and lines[0][1] == pytest.approx((5.75, 0.04))
    assert len(lines) == 2


def test_l_bends_on_the_free_side():
    points = [(0.0, 0.0), (5.0, 5.0), (5.0, 0.0)]         # a device where one L would bend
    lines = _pair(points, [box(p) for p in points])
    first = lines[:2]
    assert first[0][1] == pytest.approx((0.0, 5.0))       # up first, bend at (0, 5)
    assert first[1][0] == pytest.approx((0.0, 5.0))


def test_z_when_both_ls_are_blocked():
    points = [(0.0, 0.0), (5.0, 5.0), (5.0, 0.0), (0.0, 5.0)]
    boxes = [box(p) for p in points]
    loop = plan_loops(points[:2], 0)[0]
    drawn = []
    lines = loop_lines(loop, points, points[0], boxes, None, 0.0, True, 0.0, drawn)
    frame_boxes = [_Box(p, b, 0.0, 0.0) for p, b in zip(points, boxes)]
    assert len(lines) == 6                                 # a Z there and a Z back
    assert not any(frame_boxes[k].hit(s) for s in drawn for k in (2, 3))


def test_square_settings_switch():
    from firealarm.settings import _coerce
    assert _coerce("loop_square", False) is False
    assert _coerce("loop_square", "False") is False
    assert _coerce("loop_square", "True") is True
    assert _coerce("loop_devices", "80") == 80
    assert _coerce("loop_devices", "0") == 120
