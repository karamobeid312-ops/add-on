# -*- coding: utf-8 -*-
"""Pure logic of CAD Lights (no Revit): block names, grouping, spots that
already have a light, and the summary text. Units are feet, like Revit."""
from __future__ import division

import math
import re

MM_PER_FOOT = 304.8
SKIP = "(skip)"


class Block(object):
    """One block insert read from the CAD, in this model's coordinates."""

    def __init__(self, name, x, y, angle=0.0, layer=""):
        self.name = name
        self.x = x
        self.y = y
        self.angle = angle          # radians, about the vertical
        self.layer = layer


# Revit gives every insert of a dynamic block its own name, ending in a
# variant number and the drawing: '...-600x600mm-V457-L2', '...-V108-GROUND'.
_VARIANT = re.compile(r"-V\d+(-[^-\s]+)?$")


def clean_name(raw):
    """Block name without the DWG file name Revit may put in front of it
    ('Plan-L1.dwg.LT-600' -> 'LT-600') and without the dynamic block
    variant suffix ('LT - 600x600mm-V457-L2' -> 'LT - 600x600mm')."""
    name = (raw or "").strip()
    lower = name.lower()
    i = lower.rfind(".dwg.")
    if i >= 0:
        name = name[i + 5:]
    name = _VARIANT.sub("", name.strip())
    return name.strip() or "(unnamed block)"


def normal_angle(angle):
    """Angle in [0, 2 pi)."""
    turn = 2 * math.pi
    angle = angle % turn
    return 0.0 if abs(angle - turn) < 1e-9 else angle


def group(blocks):
    """[(name, [Block], [layers])] by block name, most inserts first."""
    found = {}
    for block in blocks:
        found.setdefault(block.name, []).append(block)
    rows = []
    for name, items in found.items():
        layers = sorted(set(b.layer for b in items if b.layer))
        rows.append((name, items, layers))
    rows.sort(key=lambda r: (-len(r[1]), r[0].lower()))
    return rows


class _Grid(object):
    """Points bucketed by cell for 'anything within tol?' lookups."""

    def __init__(self, tol):
        self.tol = tol
        self.cells = {}

    def _cell(self, x, y):
        return int(math.floor(x / self.tol)), int(math.floor(y / self.tol))

    def add(self, x, y, tag=None):
        self.cells.setdefault(self._cell(x, y), []).append((x, y, tag))

    def near(self, x, y):
        """(True, tag of the point found) or (False, None)."""
        cx, cy = self._cell(x, y)
        for i in (cx - 1, cx, cx + 1):
            for j in (cy - 1, cy, cy + 1):
                for px, py, tag in self.cells.get((i, j), ()):
                    if math.hypot(px - x, py - y) <= self.tol:
                        return True, tag
        return False, None


def split_spots(blocks, existing, tol):
    """(new, already, duplicates) from `blocks`: `already` have a light
    within tol (ft) in `existing` [(x, y, tag)], as (block, tag) pairs;
    `duplicates` sit on an earlier block of this list (twice in the CAD)."""
    tol = max(tol, 1e-6)
    grid = _Grid(tol)
    for item in existing:
        grid.add(item[0], item[1], item[2] if len(item) > 2 else None)
    new, already, duplicates = [], [], []
    for block in blocks:
        found, tag = grid.near(block.x, block.y)
        if not found:
            new.append(block)
            grid.add(block.x, block.y, _CAD)
        elif tag is _CAD:
            duplicates.append(block)
        else:
            already.append((block, tag))
    return new, already, duplicates


_CAD = object()                 # tag of a spot taken by a block of this run


class Result(object):
    """What happened to one block name."""

    def __init__(self, name, type_label):
        self.name = name
        self.type_label = type_label
        self.kind = ""              # face-based / ceiling-hosted / level-based
        self.placed = 0
        self.on_slab = 0            # placed on the slab: no ceiling there
        self.already = 0
        self.blockers = []          # ids of the lights already at those spots
        self.duplicates = 0         # blocks twice at the same spot in the CAD
        self.failed = {}            # reason -> count

    def fail(self, reason):
        self.failed[reason] = self.failed.get(reason, 0) + 1


def _plural(n, word):
    return "%d %s%s" % (n, word, "" if n == 1 else "s")


def summarize(results, skipped_names, timings=()):
    """(headline, details) for the end-of-run message."""
    placed = sum(r.placed for r in results)
    already = sum(r.already for r in results)
    failed = sum(sum(r.failed.values()) for r in results)
    head = "Placed %s." % _plural(placed, "light")
    extra = []
    if already:
        extra.append("%d spot%s already had a light" % (already, "" if already == 1 else "s"))
    if failed:
        extra.append("%d could not be placed" % failed)
    if extra:
        head += " " + ", ".join(extra).capitalize() + "."
    lines = []
    for r in results:
        line = u"%s -> %s: %d placed" % (r.name, r.type_label, r.placed)
        if r.on_slab:
            line += u" (%d under the slab, no ceiling)" % r.on_slab
        if r.already:
            line += u", %d already had a light in this model" % r.already
        if r.duplicates:
            line += u", %d duplicate blocks in the CAD" % r.duplicates
        lines.append(line)
        if r.blockers:
            ids = [u"%s" % i for i in r.blockers[:15]]
            more = u" ..." if len(r.blockers) > 15 else u""
            lines.append(u"    lights already there (element ids): " + u", ".join(ids) + more)
        if r.kind == "level-based":
            lines.append(u"    This family is level-based, so Revit cannot host it: the lights "
                         u"are set at ceiling height but not attached. Use a face-based "
                         u"family to have them on the ceiling.")
        for reason, count in sorted(r.failed.items()):
            lines.append(u"    %d not placed: %s" % (count, reason))
    if skipped_names:
        lines.append(u"")
        lines.append(u"Skipped blocks: " + u", ".join(skipped_names))
    if timings:
        lines.append(u"")
        lines.append(u"Time: " + u", ".join(u"%s %.1f s" % (step, sec) for step, sec in timings))
    return head, u"\n".join(lines)
