# -*- coding: utf-8 -*-
import random

import pytest

from firealarm.layout import layout_detectors
from firealarm.loop_order import route_order
from firealarm.loops import grid_angle, loop_lines, plan_loops
from sample_rooms import rect

HALF = 0.45                 # half a device symbol (m)
REACH = HALF * 1.415 + 0.05


def boxes(points):
    return [(x - HALF, y - HALF, x + HALF, y + HALF) for x, y in points]


def draw(points, start, square, max_devices=120):
    """Loops as Draw FA Loop plans them, and their lines."""
    angle = grid_angle(points) if square else 0.0
    loops = plan_loops(points, start, max_devices, square, angle, HALF)
    start_xy = points[start] if isinstance(start, int) else start
    panel_box = None if isinstance(start, int) else (start_xy[0] - 1.1, start_xy[1] - 0.8,
                                                     start_xy[0] + 1.1, start_xy[1] + 0.8)
    drawn = []
    return [(loop, loop_lines(loop, points, start_xy, boxes(points), panel_box, 0.2, square,
                              angle, drawn)) for loop in loops]


def devices(points):
    return [(x, y, REACH) for x, y in points]


def spaced(n, seed, w=90.0, h=55.0, gap=1.5, panel=None):
    """Devices at least `gap` apart, and 2 m clear of the panel."""
    rng = random.Random(seed)
    found = []
    while len(found) < n:
        p = (rng.uniform(0, w), rng.uniform(0, h))
        if all((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 >= gap ** 2 for q in found) and \
                (panel is None or (p[0] - panel[0]) ** 2 + (p[1] - panel[1]) ** 2 >= 4.0):
            found.append(p)
    return found


@pytest.mark.parametrize("square", [True, False])
def test_drawn_loops_read_back_in_route_order_from_the_panel(square):
    points = layout_detectors([rect(0, 0, 60, 40)], 4.5).points
    panel = (0.0, 20.0)
    for loop, lines in draw(points, panel, square, max_devices=40):
        route = route_order(lines, devices(points), [(panel[0], panel[1], 1.4)])
        assert route.order == loop.devices
        assert route.closed and route.loose == []


@pytest.mark.parametrize("seed", range(4))
@pytest.mark.parametrize("square", [True, False])
def test_scattered_devices_read_back(seed, square):
    points = spaced(150, seed, panel=(45.0, 0.0))
    for loop, lines in draw(points, (45.0, 0.0), square):
        route = route_order(lines, devices(points), [(45.0, 0.0, 1.4)])
        assert route.order == loop.devices and route.closed


@pytest.mark.parametrize("square", [True, False])
def test_a_loop_from_a_device_starts_at_the_device_given(square):
    points = layout_detectors([[(0, 0), (70, 0), (70, 20), (30, 20), (30, 50), (0, 50)]],
                              5.0).points
    (loop, lines), = draw(points, 0, square)
    route = route_order(lines, devices(points), first=0)
    assert route.order == loop.devices and route.closed
    # without the panel in the plan: the device nearest a point (the panel upstairs)
    near = route_order(lines, devices(points), first=(points[0][0] - 0.3, points[0][1]))
    assert near.order[0] == 0


@pytest.mark.parametrize("square", [True, False])
def test_several_loops_from_a_device_all_start_at_it(square):
    points = layout_detectors([rect(0, 0, 60, 40)], 4.5).points        # 126: two loops
    loops = draw(points, 7, square)
    assert len(loops) == 2
    for loop, lines in loops:
        route = route_order(lines, devices(points), first=7)
        assert route.from_device and route.closed
        assert route.order == ([] if 7 in loop.devices else [7]) + loop.devices


@pytest.mark.parametrize("seed", range(3))
@pytest.mark.parametrize("square", [True, False])
def test_several_loops_from_the_panel_read_back(seed, square):
    panel = (75.0, 0.0)
    points = spaced(400, seed, w=150, h=100, panel=panel)
    loops = draw(points, panel, square)
    assert len(loops) == 4
    for loop, lines in loops:
        route = route_order(lines, devices(points), [(panel[0], panel[1], 1.4)])
        assert route.order == loop.devices and route.closed and not route.from_device


def test_free_line_ends_are_the_start_without_a_panel():
    points = [(float(x), 0.0) for x in range(2, 12, 2)]      # a row, drawn from the left
    (loop, lines), = draw(points, (0.0, 0.0), False)
    route = route_order(lines, devices(points))
    assert route.order == loop.devices and route.closed


def test_devices_the_route_cannot_reach_are_loose():
    points = [(float(x), 0.0) for x in range(2, 14, 2)]
    lines = [((0.0, 0.0), (1.5, 0.0)), ((2.5, 0.0), (3.5, 0.0)),        # panel -> 0 -> 1
             ((6.5, 0.0), (7.5, 0.0)), ((8.5, 0.0), (9.5, 0.0))]        # 2 -> 3 -> 4, apart
    route = route_order(lines, devices(points), [(0.0, 0.0, 1.0)])
    assert route.order == [0, 1]
    assert route.loose == [2, 3, 4]
    assert not route.closed


def test_lines_not_coming_back_are_not_closed():
    points = [(2.0, 0.0), (4.0, 0.0), (6.0, 0.0)]
    lines = [((0.0, 0.0), (1.5, 0.0)), ((2.5, 0.0), (3.5, 0.0)), ((4.5, 0.0), (5.5, 0.0))]
    route = route_order(lines, devices(points), [(0.0, 0.0, 1.0)])
    assert route.order == [0, 1, 2]
    assert not route.closed


def test_no_device_on_the_lines():
    route = route_order([((0.0, 0.0), (5.0, 0.0))], devices([(20.0, 20.0)]))
    assert route.order == [] and route.loose == [] and not route.closed
