# -*- coding: utf-8 -*-
"""What Route Tray and Fix Trays show (no Revit needed)."""
from traycoord.route import AT_END, LEFT, NO_ROOM, NOT_LEVEL, OVER, RIGHT, UNDER

WENT = {OVER: "over", UNDER: "under", LEFT: "left round", RIGHT: "right round"}

WHY = {
    NO_ROOM: "no way over, under or round fits between the headroom and the slab",
    AT_END: "too near the end of the tray, where it joins a fitting",
    NOT_LEVEL: "sloping or vertical tray, not rerouted",
}

DODGE_COLUMNS = ["Tray", "Went", "By", "Around", "Tray added"]
CROSSING_COLUMNS = ["Wall", "Tray", "Opening (w x h)", "At (x, y, z in m)"]
UNSOLVED_COLUMNS = ["Tray", "In the way", "Why"]


def _count(n, word, plural=None):
    return "%d %s" % (n, word if n == 1 else (plural or word + "s"))


def _mm(metres):
    return "%d mm" % int(round(abs(metres) * 1000))


def _labels(obstacles, limit=4):
    labels = []
    for o in obstacles:
        if o.label not in labels:
            labels.append(o.label)
    shown = ", ".join(labels[:limit])
    return shown + (" and %d more" % (len(labels) - limit) if len(labels) > limit else "")


def _at(point):
    return "%.2f, %.2f, %.2f" % point


class Routed(object):
    """A routed run and its tray (the key the report links to)."""

    def __init__(self, run, key, width, height, clearance):
        self.run = run
        self.key = key
        self.width = width
        self.height = height
        self.clearance = clearance


def headline(routed, verb="Routed"):
    runs = [r.run for r in routed]
    dodges = sum(len(r.dodges) for r in runs)
    crossings = sum(len(r.crossings) for r in runs)
    unsolved = sum(len(r.unsolved) for r in runs)
    parts = [_count(dodges, "clash dodged", "clashes dodged")]
    if crossings:
        parts.append(_count(crossings, "wall opening") + " to make")
    if unsolved:
        parts.append(_count(unsolved, "clash", "clashes") + " left for you")
    return "%s %s: %s." % (verb, _count(len(runs), "tray run"), ", ".join(parts))


def dodge_rows(routed, link):
    rows = []
    for r in routed:
        for d in r.run.dodges:
            rows.append([link(r.key), WENT[d.kind], _mm(d.offset), _labels(d.obstacles),
                         _mm(d.extra)])
    return rows


def crossing_rows(routed, link):
    rows = []
    for r in routed:
        size = "%s x %s" % (_mm(r.width + 2 * r.clearance), _mm(r.height + 2 * r.clearance))
        for c in r.run.crossings:
            rows.append([link(c.obstacle.key), link(r.key), size, _at(c.at)])
    return rows


def unsolved_rows(routed, link):
    rows = []
    for r in routed:
        for u in r.run.unsolved:
            things = ", ".join(link(o.key) for o in u.obstacles[:6])
            rows.append([link(r.key), u"%s (%s)" % (things, _labels(u.obstacles)), WHY[u.reason]])
    return rows
