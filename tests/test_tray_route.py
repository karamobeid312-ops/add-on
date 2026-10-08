# -*- coding: utf-8 -*-
import math

from traycoord.route import (
    AT_END, LEFT, NO_ROOM, NOT_LEVEL, OVER, RIGHT, UNDER, box_obstacle, linear_obstacles,
    route, route_path, through_walls,
)

W, H = 0.3, 0.1             # a 300 x 100 tray
Z = 3.0                     # its middle elevation
LIMITS = (2.4, 3.6)         # headroom, underside of the slab


def pipe(x, z=Z, d=0.1, key="pipe", y0=-5.0, y1=5.0):
    """A pipe crossing the run at x, along y."""
    r = d / 2.0
    points = []
    for y in (y0, y1):
        points += [(x - r, y, z), (x + r, y, z), (x, y, z - r), (x, y, z + r)]
    return linear_obstacles(key, "Pipes : Standard", (x, y0, z), (x, y1, z), points)


def box(key, x0, y0, x1, y1, z0, z1, wall=False):
    return box_obstacle(key, key, [(x0, y0, z0), (x1, y1, z1)], wall=wall)


def run(obstacles, **options):
    return route((0.0, 0.0, Z), (10.0, 0.0, Z), W, H, obstacles, **options)


def zs(result):
    return [round(p[2], 4) for p in result.points]


def test_clear_run_stays_straight():
    result = run(pipe(5.0, z=4.0))
    assert not result.changed
    assert result.points == [(0.0, 0.0, Z), (10.0, 0.0, Z)]


def test_goes_over_a_pipe():
    result = run(pipe(5.0))
    assert result.changed
    (dodge,) = result.dodges
    assert dodge.kind == OVER
    assert abs(dodge.offset - 0.15) < 1e-9          # pipe top 50 + clearance 50 + half tray 50
    assert zs(result) == [3.0, 3.0, 3.15, 3.15, 3.0, 3.0]
    assert abs(dodge.extra - 0.3) < 1e-9
    xs = [round(p[0], 4) for p in result.points]
    assert xs == [0.0, 4.6, 4.6, 5.4, 5.4, 10.0]    # bends a tray width + clearance off
    assert [o.key for o in dodge.obstacles] == ["pipe"]


def test_goes_under_when_no_room_over():
    result = run(pipe(5.0), limits=(2.4, 3.1))
    assert result.dodges[0].kind == UNDER
    assert zs(result)[2] == 2.85


def test_preferred_direction():
    assert run(pipe(5.0), prefer=UNDER).dodges[0].kind == UNDER


def test_beam_above_the_pipe_sends_it_under():
    beam = box("beam", 4.5, -5, 5.5, 5, 3.2, 3.5)
    result = run(pipe(5.0) + [beam], limits=LIMITS)
    (dodge,) = result.dodges
    assert dodge.kind == UNDER
    assert [o.key for o in dodge.obstacles] == ["pipe"]


def test_climbs_over_both_when_there_is_room():
    beam = box("beam", 4.5, -5, 5.5, 5, 3.2, 3.5)
    result = run(pipe(5.0) + [beam], limits=(2.95, 4.5))
    (dodge,) = result.dodges
    assert dodge.kind == OVER
    assert abs(dodge.offset - 0.6) < 1e-9
    assert sorted(o.key for o in dodge.obstacles) == ["beam", "pipe"]


def test_column_is_passed_on_its_shorter_side():
    column = box("column", 4.8, -0.1, 5.2, 0.3, 0.0, 4.0)
    result = run([column], limits=LIMITS)
    (dodge,) = result.dodges
    assert dodge.kind == RIGHT
    assert abs(dodge.offset + 0.3) < 1e-9
    assert all(abs(p[2] - Z) < 1e-9 for p in result.points)
    assert round(min(p[1] for p in result.points), 4) == -0.3


def test_column_preferred_side():
    column = box("column", 4.8, -0.1, 5.2, 0.3, 0.0, 4.0)
    assert run([column], limits=LIMITS, prefer=LEFT).dodges[0].kind == LEFT
    assert run([column], limits=LIMITS, prefer="side").dodges[0].kind == RIGHT


def test_full_height_wall_is_crossed():
    wall = box("wall", 4.9, -5, 5.1, 5, 0.0, 4.0, wall=True)
    result = run([wall], limits=LIMITS)
    assert not result.changed
    assert not result.unsolved
    (crossing,) = result.crossings
    assert crossing.obstacle.key == "wall"
    assert abs(crossing.at[0] - 5.0) < 1e-9


def test_wall_is_never_passed_sideways():
    # a short full-height wall: going round it would be shorter, but walls are crossed
    wall = box("wall", 4.9, -0.5, 5.1, 0.5, 0.0, 4.0, wall=True)
    result = run([wall], limits=LIMITS)
    assert not result.dodges
    assert len(result.crossings) == 1


def test_bulkhead_is_dodged_under():
    bulkhead = box("bulkhead", 4.9, -5, 5.1, 5, 2.95, 4.0, wall=True)
    assert not through_walls([bulkhead], Z, H, LIMITS)
    result = run([bulkhead], limits=LIMITS)
    assert result.dodges[0].kind == UNDER
    assert abs(result.dodges[0].offset + 0.15) < 1e-9
    assert not result.crossings


def test_pipe_next_to_a_wall_dodged_and_wall_crossed():
    wall = box("wall", 3.9, -5, 4.1, 5, 0.0, 4.0, wall=True)
    result = run([wall] + pipe(6.0), limits=LIMITS)
    assert [d.kind for d in result.dodges] == [OVER]
    assert [c.obstacle.key for c in result.crossings] == ["wall"]


def test_close_pipes_take_one_dodge():
    result = run(pipe(5.0, key="a") + pipe(5.3, key="b"))
    (dodge,) = result.dodges
    assert sorted(o.key for o in dodge.obstacles) == ["a", "b"]
    assert len(result.points) == 6


def test_far_pipes_take_two_dodges():
    result = run(pipe(3.0, key="a") + pipe(7.0, key="b"))
    assert [d.kind for d in result.dodges] == [OVER, OVER]
    assert len(result.points) == 10


def test_45_degree_bends():
    result = run(pipe(5.0), bends=45)
    (dodge,) = result.dodges
    assert abs(dodge.extra - 2 * 0.15 * (math.sqrt(2) - 1)) < 1e-9
    xs = [round(p[0], 4) for p in result.points]
    assert xs == [0.0, 4.45, 4.6, 5.4, 5.55, 10.0]


def test_clash_at_a_joined_end_is_left():
    result = run(pipe(0.2), start_free=False)
    assert not result.dodges
    (unsolved,) = result.unsolved
    assert unsolved.reason == AT_END


def test_clash_with_no_room_is_reported():
    slab = box("slab", 4, -5, 6, 5, 3.04, 3.3)          # tight under a slab, headroom below
    column = box("column", 4.5, -0.5, 5.5, 0.5, 0.0, 3.04)
    sides = [box("duct L", 0, 0.6, 10, 1.0, 2.9, 3.1), box("duct R", 0, -1.0, 10, -0.6, 2.9, 3.1)]
    result = run([slab, column] + sides, limits=(2.95, 3.3))
    assert not result.changed
    (unsolved,) = result.unsolved
    assert unsolved.reason == NO_ROOM
    assert sorted(o.key for o in unsolved.obstacles) == ["column", "slab"]


def test_sloping_run_not_rerouted():
    result = route((0.0, 0.0, Z), (10.0, 0.0, Z + 0.5), W, H, pipe(5.0, z=3.25))
    assert not result.changed
    assert result.unsolved[0].reason == NOT_LEVEL


def test_sloping_pipe_follows_its_slope():
    a, b = (0.0, 0.0, 3.0), (10.0, 0.0, 2.9)
    pieces = linear_obstacles("drain", "Pipes", a, b,
                              [(0, 0, 2.95), (0, 0, 3.05), (10, 0, 2.85), (10, 0, 2.95),
                               (0, -0.05, 3.0), (0, 0.05, 3.0)], chunk=1.0)
    assert len(pieces) == 10
    assert abs(pieces[0].top - 3.05) < 1e-9
    assert abs(pieces[-1].bottom - 2.85) < 1e-9
    assert pieces[0].top > pieces[-1].top


def test_diagonal_run():
    s = math.sqrt(0.5)
    result = route((0.0, 0.0, Z), (10 * s, 10 * s, Z), W, H, pipe(5 * s, y0=-20, y1=20))
    assert result.dodges[0].kind == OVER
    assert result.points[0] == (0.0, 0.0, Z)
    end = result.points[-1]
    assert abs(end[0] - 10 * s) < 1e-9 and abs(end[1] - 10 * s) < 1e-9


def test_path_keeps_its_corners():
    path = [(0.0, 0.0, Z), (10.0, 0.0, Z), (10.0, 10.0, Z)]
    obstacles = pipe(5.0) + linear_obstacles(
        "duct", "Ducts", (5, 5, Z), (15, 5, Z), [(5, 5 - 0.2, Z - 0.2), (15, 5 + 0.2, Z + 0.2)])
    runs = route_path(path, W, H, obstacles)
    assert [len(r.dodges) for r in runs] == [1, 1]
    assert runs[0].points[-1] == (10.0, 0.0, Z) and runs[1].points[0] == (10.0, 0.0, Z)


def test_path_corner_keeps_room_for_its_bend():
    path = [(0.0, 0.0, Z), (10.0, 0.0, Z), (10.0, 10.0, Z)]
    runs = route_path(path, W, H, pipe(9.8))
    assert runs[0].unsolved and runs[0].unsolved[0].reason == AT_END


def test_dodges_too_close_to_split_are_merged():
    # two pipes 600 mm apart: the bends back down after the first would
    # be where the second needs its bends up, so both take one dodge
    result = run(pipe(5.0, key="a") + pipe(5.6, key="b"))
    assert len(result.dodges) == 1
    assert sorted(o.key for o in result.dodges[0].obstacles) == ["a", "b"]
    assert not result.unsolved
