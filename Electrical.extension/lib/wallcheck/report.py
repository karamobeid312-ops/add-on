# -*- coding: utf-8 -*-
"""What the Wall Fixtures check shows (no Revit needed)."""
from wallcheck.check import (
    EMBEDDED, FACES_IN, FLAT, FLOATING, INSIDE, LINK_MISSING, NO_HOST, NOT_WALL, OFF_WALL,
    OTHER_HOST, PROBLEMS, TILTED, UNHOSTED, UNREADABLE,
)

TITLES = {
    NO_HOST: "Lost their wall",
    LINK_MISSING: "On a wall in a link that is not loaded, or no longer in it",
    OFF_WALL: "Off the end or the top of their wall, or in an opening",
    FLOATING: "Floating off the wall face",
    EMBEDDED: "Set into the wall",
    INSIDE: "Inside the wall",
    FACES_IN: "Facing into the wall",
    TILTED: "Not square to the wall",
    NOT_WALL: "On a work plane, not on a wall",
}

FIXES = {
    NO_HOST: "the wall they were on was deleted: pick a new host (Modify > Pick New Host) "
             "or place them again",
    LINK_MISSING: "load the link, or pick a new host if the wall was deleted from it",
    OFF_WALL: "the wall was shortened, lowered or opened where they are: move them back "
              "onto the wall",
    FLOATING: "move them back onto the wall face; on a linked wall, the wall probably "
              "moved: Modify > Pick New Host",
    EMBEDDED: "move them out to the wall face; the wall probably got thicker or moved",
    INSIDE: "the whole fixture is behind the wall face: flip it, or move it to the face",
    FACES_IN: "flip them (Flip work plane) so they face the room",
    TILTED: "the wall was turned after they were placed: pick a new host",
    NOT_WALL: "they will not move with the wall: Modify > Pick New Host, and pick the wall",
}

NOTES = {
    UNREADABLE: "the faces of their wall could not be read (curtain walls, in-place walls)",
    UNHOSTED: "not hosted (not wall-based nor face-based families)",
    FLAT: "on ceilings, floors or roofs",
    OTHER_HOST: "on columns, curtain panels, furniture or other hosts that are not walls",
}

COLUMNS = ["Element", "Family : Type", "Category", "Level", "Detail"]


def _count(n, word, plural=None):
    return "%d %s" % (n, word if n == 1 else (plural or word + "s"))


def _mm(metres):
    return "%d mm" % int(round(metres * 1000))


def detail(finding):
    """One line saying what is wrong with the fixture."""
    d, status = finding.distance, finding.status
    if status == FLOATING:
        return u"%s in front of the wall face" % _mm(d)
    if status == EMBEDDED:
        return u"insertion point %s into the wall" % _mm(d)
    if status == INSIDE:
        return u"the whole fixture is %s or more behind the wall face" % _mm(d)
    if status == OFF_WALL:
        return (u"past the wall face, %s from its plane" % _mm(d)) if d is not None \
            else u"past the wall face"
    if status == TILTED:
        return u"turned %.0f° from the wall face" % d
    if status == FACES_IN:
        return u"faces into the wall"
    if status == NO_HOST:
        return u"no host"
    if status == LINK_MISSING:
        return u"host wall not found in its link"
    if status == NOT_WALL:
        return u"hosted by a level or reference plane"
    return u""


def headline(result):
    checked = len(result.checked())
    problems = len(result.problems())
    if not checked:
        return "No fixtures on walls found."
    if not problems:
        return "All %s on %s wall%s, within %s." % (
            _count(checked, "wall fixture"), "its" if checked == 1 else "their",
            "" if checked == 1 else "s", _mm(result.tolerance))
    return "%d of %s need%s a look (tolerance %s)." % (
        problems, _count(checked, "wall fixture"), "s" if problems == 1 else "",
        _mm(result.tolerance))


def sections(result):
    """[(title, fix, [finding])] of the problems, in PROBLEMS order, each
    sorted by level and family."""
    found = []
    for status in PROBLEMS:
        items = result.of(status)
        if items:
            items.sort(key=lambda f: (f.fixture.level, f.fixture.label, -(f.distance or 0)))
            found.append(("%s (%d)" % (TITLES[status], len(items)), FIXES[status], items))
    return found


def notes(result):
    """Lines about the fixtures that were not checked."""
    lines = []
    for status in (UNREADABLE, UNHOSTED, FLAT, OTHER_HOST):
        n = len(result.of(status))
        if n:
            lines.append("%s %s: not checked." % (_count(n, "fixture"), NOTES[status]))
    return lines


def row(finding, link):
    f = finding.fixture
    return [link, f.label, f.category, f.level, detail(finding)]
