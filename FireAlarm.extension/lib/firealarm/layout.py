# -*- coding: utf-8 -*-
"""Detector layout inside a room outline (pure Python, no Revit).

Spacing rule, spacing S (9 m smoke, 4.5 m heat by default): detectors at
most S apart and at most S/2 from the walls, so every point of the ceiling
is within S/sqrt(2) (0.71 S, the corner of an S x S square) of a detector.

1. The grid is lined up with the room's main wall direction.
2. Along each axis the room's extent L is split into n = ceil(L / S) equal
   bays of L / n with a detector in the middle of each bay, so the first
   detector is half a bay from the wall.
3. Grid points inside the room and clear of the walls are kept.
4. Grid cells that straddle a wall (L-shapes, notches, columns, shafts)
   and are not covered yet get a detector in the middle of the part of the
   cell that is inside the room.
5. The whole ceiling is checked on a fine grid of points plus points along
   every wall; a detector is added wherever a point is out of reach.

Rooms whose walls are all square to the grid (L, T, U shapes, corridors)
are also cut into rectangles, across and along, each with its own grid;
the layout with the fewest detectors wins.

Lengths are in any unit (the Revit side uses metres). Keep this module
compatible with IronPython 2.7.
"""
from __future__ import division

import math

DEFAULT_CLEARANCE = 0.5      # min distance from walls and columns (m)
CHECKS_PER_SPACING = 20      # checking grid pitch = spacing / 20 (0.45 m at 9 m)
EPS = 1e-9


class Grid(object):
    """A regular grid of bays, in the layout's own (rotated) frame."""

    def __init__(self, x0, y0, px, py, nx, ny):
        self.x0, self.y0 = x0, y0
        self.px, self.py = px, py      # bay width, bay depth
        self.nx, self.ny = nx, ny      # bays along, across


class DetectorLayout(object):
    """Result of layout_detectors()."""

    def __init__(self, points, spacing, angle=0.0, grids=None, on_grid=0, uncovered=0):
        self.points = points        # [(x, y)] in the outline's coordinates
        self.spacing = spacing
        self.reach = reach(spacing)
        self.angle = angle          # grid direction (radians)
        self.grids = grids or []    # [Grid] (one per rectangle when cut up)
        self.on_grid = on_grid      # detectors on the regular grid(s)
        self.uncovered = uncovered  # checking points out of reach (0 = covered)

    @property
    def added(self):
        """Detectors added off the grid to cover notches, columns..."""
        return len(self.points) - self.on_grid


def reach(spacing):
    """Farthest a point of the ceiling may be from its nearest detector."""
    return spacing / math.sqrt(2.0)


# ---------------------------------------------------------------- polygons

def clean_loop(loop, tol=1e-6):
    """Points as float tuples, without repeats or a closing point."""
    out = []
    for p in loop:
        p = (float(p[0]), float(p[1]))
        if not out or abs(p[0] - out[-1][0]) > tol or abs(p[1] - out[-1][1]) > tol:
            out.append(p)
    while len(out) > 1 and abs(out[0][0] - out[-1][0]) <= tol and abs(out[0][1] - out[-1][1]) <= tol:
        out.pop()
    return out


def loop_area(loop):
    """Signed area (positive when counter-clockwise)."""
    a = 0.0
    n = len(loop)
    for i in range(n):
        x0, y0 = loop[i]
        x1, y1 = loop[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def segments(loops):
    segs = []
    for loop in loops:
        n = len(loop)
        for i in range(n):
            segs.append((loop[i], loop[(i + 1) % n]))
    return segs


def point_in_loops(x, y, loops):
    """Inside the outline and outside its holes (even-odd over all loops)."""
    return point_inside(x, y, segments(loops))


def point_inside(x, y, segs):
    """point_in_loops() on the segments() of the loops."""
    inside = False
    for (ax, ay), (bx, by) in segs:
        if (ay > y) != (by > y):
            if ax + (y - ay) * (bx - ax) / (by - ay) > x:
                inside = not inside
    return inside


def wall_distance(x, y, segs):
    best = float("inf")
    for (ax, ay), (bx, by) in segs:
        dx, dy = bx - ax, by - ay
        l2 = dx * dx + dy * dy
        t = 0.0 if l2 < EPS else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / l2))
        ex, ey = ax + t * dx - x, ay + t * dy - y
        d2 = ex * ex + ey * ey
        if d2 < best:
            best = d2
    return math.sqrt(best)


def main_direction(loops):
    """Direction (radians, 0 <= a < pi/2) shared by most of the wall length;
    0 (the model's axes) when no direction has a quarter of it (round rooms)."""
    quarter = math.pi / 2
    walls = []
    for (ax, ay), (bx, by) in segments(loops):
        length = math.hypot(bx - ax, by - ay)
        if length > EPS:
            walls.append((math.atan2(by - ay, bx - ax) % quarter, length))
    if not walls:
        return 0.0
    tol = math.radians(1.0)
    best, best_weight = 0.0, -1.0
    for angle, length in sorted(walls, key=lambda w: -w[1]):
        weight = 0.0
        for other, other_length in walls:
            d = abs(other - angle)
            if min(d, quarter - d) <= tol:
                weight += other_length
        if weight > best_weight + EPS:
            best, best_weight = angle, weight
    if min(best, quarter - best) < 1e-7 or best_weight < 0.25 * sum(w[1] for w in walls):
        return 0.0
    return best


def _rotate(p, angle):
    c, s = math.cos(angle), math.sin(angle)
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


def _bays(length, spacing):
    return max(1, int(math.ceil(length / spacing - 1e-9)))


# ---------------------------------------------------------------- checking

class _Checker(object):
    """Checking points over the ceiling, which detectors cover which."""

    def __init__(self, segs, box, step, radius):
        x0, y0, x1, y1 = box
        self.segs = segs
        self.radius = radius
        self.r2 = radius * radius * (1 + 1e-9)
        self.x0, self.y0 = x0, y0
        self.points = []            # (x, y)
        self.interior = []          # False for points on the walls
        # fine grid inside the outline (scanlines: one pass over the walls per row)
        nx = max(1, int(math.ceil((x1 - x0) / step)))
        ny = max(1, int(math.ceil((y1 - y0) / step)))
        sx, sy = (x1 - x0) / nx, (y1 - y0) / ny
        for j in range(ny):
            y = y0 + (j + 0.5) * sy
            crossings = sorted(ax + (y - ay) * (bx - ax) / (by - ay)
                               for (ax, ay), (bx, by) in segs if (ay > y) != (by > y))
            k, inside = 0, False
            for i in range(nx):
                x = x0 + (i + 0.5) * sx
                while k < len(crossings) and crossings[k] <= x:
                    inside = not inside
                    k += 1
                if inside:
                    self.points.append((x, y))
                    self.interior.append(True)
        # points along every wall (corners included)
        for (ax, ay), (bx, by) in segs:
            n = max(1, int(math.ceil(math.hypot(bx - ax, by - ay) / (step / 2))))
            for k in range(n):
                t = k / n
                self.points.append((ax + t * (bx - ax), ay + t * (by - ay)))
                self.interior.append(False)
        self.covered = [False] * len(self.points)
        self.buckets = {}
        for idx, p in enumerate(self.points):
            self.buckets.setdefault(self._bucket(p), []).append(idx)
        self._clearance = {}

    def _bucket(self, p):
        return (int(math.floor((p[0] - self.x0) / self.radius)),
                int(math.floor((p[1] - self.y0) / self.radius)))

    def near(self, p):
        """Indices of the checking points in reach of p, and some more."""
        bi, bj = self._bucket(p)
        out = []
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                out.extend(self.buckets.get((bi + di, bj + dj), ()))
        return out

    def reaches(self, a, b):
        dx, dy = a[0] - b[0], a[1] - b[1]
        return dx * dx + dy * dy <= self.r2

    def cover(self, p):
        """Mark what a detector at p covers; returns how many were new."""
        new = 0
        for idx in self.near(p):
            if not self.covered[idx] and self.reaches(p, self.points[idx]):
                self.covered[idx] = True
                new += 1
        return new

    def gain(self, p):
        return sum(1 for idx in self.near(p)
                   if not self.covered[idx] and self.reaches(p, self.points[idx]))

    def clearance(self, idx):
        c = self._clearance.get(idx)
        if c is None:
            x, y = self.points[idx]
            c = self._clearance[idx] = wall_distance(x, y, self.segs)
        return c

    def uncovered(self):
        return [idx for idx, done in enumerate(self.covered) if not done]


def _centroid(points):
    n = len(points)
    return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n)


def _nearest(points, target):
    return min(points, key=lambda p: (p[0] - target[0]) ** 2 + (p[1] - target[1]) ** 2)


# ---------------------------------------------------------------- layout

class _Result(object):
    def __init__(self, points, grids, on_grid, uncovered):
        self.points, self.grids = points, grids
        self.on_grid, self.uncovered = on_grid, uncovered


def _grid_layout(loops, spacing, clearance):
    """Steps 2-5 on loops already turned to the grid direction."""
    segs = segments(loops)
    xs = [p[0] for loop in loops for p in loop]
    ys = [p[1] for loop in loops for p in loop]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    width, depth = x1 - x0, y1 - y0
    nx, ny = _bays(width, spacing), _bays(depth, spacing)
    px, py = width / nx, depth / ny

    step = min(spacing / CHECKS_PER_SPACING, min(width, depth) / 4.0)
    check = _Checker(segs, (x0, y0, x1, y1), step, reach(spacing))
    detectors = []

    def inside(p):
        return point_inside(p[0], p[1], segs)

    def to_wall(p):
        return wall_distance(p[0], p[1], segs)

    def clear(p):
        return inside(p) and to_wall(p) >= clearance - 1e-6

    def place(p):
        detectors.append(p)
        check.cover(p)

    def grid_point(i, j):
        return (x0 + (i + 0.5) * px, y0 + (j + 0.5) * py)

    def cell(p):
        i = min(max(int((p[0] - x0) / px), 0), nx - 1)
        j = min(max(int((p[1] - y0) / py), 0), ny - 1)
        return i, j

    # 2-3. the regular grid
    on_grid = set()
    for j in range(ny):
        for i in range(nx):
            if clear(grid_point(i, j)):
                place(grid_point(i, j))
                on_grid.add((i, j))

    # 4. cells cut by a wall: a detector in the middle of their inside part
    cells = {}
    for idx, p in enumerate(check.points):
        cells.setdefault(cell(p), []).append(idx)
    pending = set(c for c in cells if c not in on_grid)

    def open_points(c):
        return sum(1 for idx in cells[c] if not check.covered[idx])

    while pending:
        best = max(sorted(pending), key=open_points)
        pending.discard(best)
        if open_points(best) == 0:
            break
        spots = [check.points[idx] for idx in cells[best] if check.interior[idx]]
        if not spots:
            continue
        middle = _centroid(spots)
        if not clear(middle):
            roomy = [check.points[idx] for idx in cells[best]
                     if check.interior[idx] and check.clearance(idx) >= clearance - 1e-6]
            if roomy:
                middle = _nearest(roomy, middle)
            else:           # too narrow for the clearance: as central as it gets
                g = grid_point(*best)
                if inside(g):
                    spots.append(g)
                target = middle
                middle = max(spots, key=lambda p: (round(to_wall(p), 6),
                                                   -math.hypot(p[0] - target[0], p[1] - target[1])))
        if check.gain(middle):
            place(middle)

    # 5. anything still out of reach
    for idx in check.uncovered():
        if check.covered[idx]:
            continue
        target = check.points[idx]
        nearby = [n for n in check.near(target)
                  if check.interior[n] and check.reaches(target, check.points[n])]
        if not nearby:
            continue
        spots = [n for n in nearby if check.clearance(n) >= clearance - 1e-6]
        if not spots:       # too narrow for the clearance: as far from the walls as it gets
            far = max(check.clearance(n) for n in nearby)
            spots = [n for n in nearby if check.clearance(n) >= far - 1e-6]
        spots = [check.points[n] for n in spots]
        # aim at the middle of what is still open around the target
        todo = [check.points[n] for n in check.near(target)
                if not check.covered[n] and check.reaches(target, check.points[n])]
        middle = _centroid(todo)
        if clear(middle) and check.reaches(middle, target):
            place(middle)
        else:
            place(_nearest(spots, middle))

    return _Result(detectors, [Grid(x0, y0, px, py, nx, ny)], len(on_grid),
                   len(check.uncovered()))


def _is_orthogonal(loops, tol):
    for (ax, ay), (bx, by) in segments(loops):
        if abs(bx - ax) > tol and abs(by - ay) > tol:
            return False
    return True


def _strips(loops, tol):
    """Cut an outline with square walls into rectangles (x0, y0, x1, y1)
    with horizontal cuts at its corners, merging rectangles stacked with
    the same width."""
    segs = segments(loops)
    levels = []
    for y in sorted(p[1] for loop in loops for p in loop):
        if not levels or y - levels[-1] > tol:
            levels.append(y)
    done, open_ = [], {}
    for ya, yb in zip(levels, levels[1:]):
        if yb - ya <= tol:
            continue
        y = (ya + yb) / 2
        cuts = sorted(ax + (y - ay) * (bx - ax) / (by - ay)
                      for (ax, ay), (bx, by) in segs if (ay > y) != (by > y))
        now = {}
        for xa, xb in zip(cuts[0::2], cuts[1::2]):
            if xb - xa <= tol:
                continue
            key = (int(round(xa / tol)), int(round(xb / tol)))
            rect = open_.pop(key, None)
            if rect is not None and abs(rect[3] - ya) <= tol:
                rect[3] = yb
            else:
                rect = [xa, ya, xb, yb]
            now[key] = rect
        done.extend(open_.values())
        open_ = now
    done.extend(open_.values())
    return sorted(tuple(r) for r in done)


def _pieces_layout(rects, spacing, clearance, swap):
    points, grids, on_grid, uncovered = [], [], 0, 0
    for x0, y0, x1, y1 in rects:
        part = _grid_layout([[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]], spacing, clearance)
        points.extend(part.points)
        grids.extend(part.grids)
        on_grid += part.on_grid
        uncovered += part.uncovered
    if swap:
        points = [(y, x) for x, y in points]
        grids = [Grid(g.y0, g.x0, g.py, g.px, g.ny, g.nx) for g in grids]
    return _Result(points, grids, on_grid, uncovered)


def layout_detectors(loops, spacing, clearance=DEFAULT_CLEARANCE):
    """Detector points for a room.

    loops: the room outline and any holes (columns, shafts) as lists of
    (x, y); direction and order do not matter.
    spacing: max distance between detectors (half of it from the walls).
    clearance: min distance from walls and columns, relaxed only where the
    room is too narrow for it.
    """
    loops = [clean_loop(loop) for loop in loops]
    loops = [loop for loop in loops if len(loop) >= 3 and abs(loop_area(loop)) > EPS]
    if not loops or spacing <= 0:
        return DetectorLayout([], spacing)

    angle = main_direction(loops)
    local = [[_rotate(p, -angle) for p in loop] for loop in loops]
    best = _grid_layout(local, spacing, clearance)

    tol = spacing * 1e-3
    if best.points and _is_orthogonal(local, tol):
        swapped = [[(y, x) for x, y in loop] for loop in local]
        for swap, outline in ((False, local), (True, swapped)):
            rects = _strips(outline, tol)
            if len(rects) < 2:
                continue
            other = _pieces_layout(rects, spacing, clearance, swap)
            if other.uncovered <= best.uncovered and \
                    (len(other.points), len(other.points) - other.on_grid) < \
                    (len(best.points), len(best.points) - best.on_grid):
                best = other

    points = [_rotate(p, angle) for p in best.points]
    return DetectorLayout(points, spacing, angle, best.grids, best.on_grid, best.uncovered)
