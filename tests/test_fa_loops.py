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
    # a snake through the last two columns, then down the first, as drawn
    # by hand; anticlockwise
    assert abs(loops[0].length - 161.2) < 1e-6
    assert [points[i] for i in loops[0].stops] == [
        (0.0, 0.0), (15.5, 0.0), (30.8, 0.0), (30.8, 10.8), (15.5, 10.8), (15.5, 23.2),
        (30.8, 23.2), (30.8, 34.5), (15.5, 34.5), (0.0, 34.5), (0.0, 23.2), (0.0, 10.8)]
    check_square(points, drawn, boxes)
    assert len(lines[0]) == 12          # one straight line per step, no bends needed


@pytest.mark.parametrize("square", [True, False])
def test_every_loop_runs_anticlockwise(square):
    from firealarm.loops import turning
    points = layout_detectors([rect(0, 0, 60, 40)], 4.5).points
    for start in ((30.0, 0.0), 5):
        start_xy = start if isinstance(start, tuple) else points[start]
        for loop in plan_loops(points, start, 40, square):
            corners = [start_xy if s == START else points[s] for s in loop.stops]
            assert turning(corners) == 1
            if not isinstance(start, tuple) and start in loop.devices:
                assert loop.stops[0] == start
    row = [(float(x), 0.0) for x in (8, 2, 6, 4)]           # a row: the nearer end first
    assert plan_loops(row, (0.0, 0.0), 120, square)[0].devices == [1, 3, 2, 0]


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
    boxes = [box(p) for p in points]
    lines = _pair(points, boxes)
    third = _Box(points[2], boxes[2], 0.0, 0.0)
    assert not any(third.hit(s) for s in lines)            # never through (5, 0)
    assert not any(_clash(s, t) == 2 for i, s in enumerate(lines) for t in lines[i + 1:])


def _overlaps(lines):
    return [(s, t) for i, s in enumerate(lines) for t in lines[i + 1:] if _clash(s, t) == 2]


def test_address_order_lines_do_not_run_back_over_each_other():
    """The office plan of 2026-11-15: lines ran back over the next line
    (SD-14 up and across to SD-15, then SD-15 across to SD-16), and into
    SD-17 along the line leaving it."""
    from firealarm.loops import fixed_loops
    points = [(313, 135), (208, 207), (186, 207), (165, 207), (110, 265), (162, 280), (313, 277),
              (346, 367), (433, 265), (433, 125), (533, 125), (533, 277), (685, 277), (848, 277),
              (693, 135), (868, 135), (1022, 118), (1022, 265), (1080, 262), (840, 367),
              (593, 367), (1080, 462), (1080, 580), (875, 462), (666, 462), (666, 580),
              (460, 580), (460, 462), (263, 520), (90, 520)]
    points = [(float(x), -float(y)) for x, y in points]
    boxes = [box(p, 6.0) for p in points]
    loop = fixed_loops(points, 0, [list(range(len(points)))], square=True)[0]
    lines = loop_lines(loop, points, points[0], boxes, None, 0.0, True, 0.0, None)
    assert _overlaps(lines) == []
    assert len(lines) >= len(points)


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


# ---------------------------------------------------------------- address order

from firealarm.addresses import DETECTION, SOUNDER, address_order  # noqa: E402
from firealarm.loops import fixed_loops  # noqa: E402


def test_address_order_groups_loops_and_sorts_by_number():
    marks = ["L2/SD-02", "L1/MCP-03", "L1/SD-01", "", "L2/SD-01", "L1/HD-02", "L1/BS-01", "224"]
    groups, missing, duplicates = address_order(marks, DETECTION)
    assert groups == [(1, [2, 5, 1]), (2, [4, 0])]
    assert missing == [3, 6, 7]                 # no address, a sounder, a plain Mark
    assert duplicates == []
    sounders, _, _ = address_order(marks, SOUNDER)
    assert sounders == [(1, [6])]


def test_address_order_reports_repeated_addresses():
    groups, _, duplicates = address_order(["L1/SD-01", "L1/HD-01", "L1/SD-02"], DETECTION)
    assert duplicates == ["L1/HD-01"]
    assert [n for n, _ in groups] == [1]


def test_fixed_loops_follow_the_order_from_the_panel():
    points = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    loops = fixed_loops(points, (-5.0, 0.0), [[2, 0, 3, 1]])
    assert loops[0].stops == [START, 2, 0, 3, 1]
    route = [(-5.0, 0.0)] + [points[i] for i in (2, 0, 3, 1)]
    expected = sum(math.hypot(route[i][0] - route[(i + 1) % 5][0],
                              route[i][1] - route[(i + 1) % 5][1]) for i in range(5))
    assert loops[0].length == pytest.approx(expected)


def test_fixed_loops_begin_at_the_start_device():
    points = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0)]
    loops = fixed_loops(points, 1, [[0, 1, 2]], square=True)
    assert loops[0].stops == [1, 2, 0]
    assert loops[0].length == pytest.approx(40.0)


# ---------------------------------------------------------------- loop to wires

from firealarm.wire_paths import runs  # noqa: E402


def test_runs_join_lines_between_devices_and_drop_straight_joints():
    lines = [((0.25, 0.0), (3.0, 0.0)), ((3.0, 0.0), (5.0, 0.0)),     # straight on, one run
             ((5.0, 0.0), (5.0, 4.75)),                                # bend up to a device
             ((5.25, 5.0), (8.0, 5.0)), ((8.0, 5.0), (8.0, 9.75))]     # next device, an L
    found = sorted(runs(lines))
    assert found == [[(0.25, 0.0), (5.0, 0.0), (5.0, 4.75)],
                     [(5.25, 5.0), (8.0, 5.0), (8.0, 9.75)]]


def test_runs_follow_lines_drawn_either_way_round():
    lines = [((5.0, 4.75), (5.0, 0.0)), ((0.25, 0.0), (5.0, 0.0))]
    run, = runs(lines)
    assert run in ([(5.0, 4.75), (5.0, 0.0), (0.25, 0.0)], [(0.25, 0.0), (5.0, 0.0), (5.0, 4.75)])


def test_runs_stop_where_three_lines_meet():
    lines = [((0.0, 0.0), (1.0, 0.0)), ((1.0, 0.0), (2.0, 0.0)), ((1.0, 0.0), (1.0, 1.0))]
    assert len(runs(lines)) == 3


def test_runs_of_the_square_loop_lines():
    points = [(0.0, 0.0), (5.0, 5.0), (10.0, 0.0)]
    boxes = [box(p) for p in points]
    loop = plan_loops(points, 0, square=True)[0]
    lines = loop_lines(loop, points, points[0], boxes, None, 0.0, True, 0.0, None)
    found = runs(lines)
    assert len(found) == 3                       # one wire device to device, round the loop
    assert sum(len(r) - 1 for r in found) <= len(lines)
