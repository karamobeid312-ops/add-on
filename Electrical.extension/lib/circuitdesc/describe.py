# -*- coding: utf-8 -*-
"""Circuit descriptions from the rooms or spaces of their fixtures (no Revit)."""
import re

NUMBER_NAME = "number name"
NAME = "name"
NAME_NUMBER = "name number"
STYLES = [NUMBER_NAME, NAME, NAME_NUMBER]

SEPARATOR = ", "

# what happens to a circuit
CHANGE = "change"           # gets a new description
SAME = "same"               # already says it
NOT_FOUND = "not found"     # none of its fixtures is in a room or space
NO_FIXTURES = "no fixtures"
FEEDER = "feeder"           # feeds another board: keeps its description


def _clean(text):
    return u" ".join((text or u"").split())


def label(number, name, style=NUMBER_NAME, upper=True):
    """What a room or space is called in a description: '012 PUMP ROOM'."""
    number, name = _clean(number), _clean(name)
    if style == NAME:
        parts = [name or number]
    elif style == NAME_NUMBER:
        parts = [name, number]
    else:
        parts = [number, name]
    text = u" ".join(p for p in parts if p)
    return text.upper() if upper else text


def describe(labels):
    """The description of a circuit whose fixtures are in `labels` (one per
    fixture, None when it is in no room): each room once, in order."""
    seen, out = set(), []
    for text in labels:
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return SEPARATOR.join(out)


class Circuit(object):
    """A circuit of a board, as read from the model."""

    def __init__(self, ref, panel, number, slot, old, labels, feeder=False):
        self.ref = ref                  # the Revit circuit
        self.panel = panel              # board name
        self.number = number            # R1, 12...
        self.slot = slot
        self.old = old or u""
        self.labels = list(labels)      # one per fixture, None when not in a room
        self.feeder = feeder
        self.new = describe(self.labels)

    @property
    def status(self):
        if self.feeder:
            return FEEDER
        if not self.labels:
            return NO_FIXTURES
        if not self.new:
            return NOT_FOUND
        if self.new == self.old:
            return SAME
        return CHANGE

    @property
    def missing(self):
        """Fixtures of the circuit in no room or space."""
        return sum(1 for text in self.labels if not text)


def _natural(text):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", text or u"")]


def ordered(circuits):
    """Circuits by board, then by slot (as in the panel schedule)."""
    return sorted(circuits, key=lambda c: (_natural(c.panel),
                                           c.slot if c.slot is not None else 10 ** 6,
                                           _natural(c.number)))


def by_status(circuits, status):
    return [c for c in circuits if c.status == status]


def headline(circuits):
    n = len(by_status(circuits, CHANGE))
    boards = len(set(c.panel for c in circuits))
    return u"%d circuit%s of %d board%s to describe" % (
        n, "" if n == 1 else "s", boards, "" if boards == 1 else "s")
