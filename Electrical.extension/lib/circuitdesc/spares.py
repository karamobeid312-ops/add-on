# -*- coding: utf-8 -*-
"""Spares, spaces and the number of ways of a board (no Revit).

A board gets 10 % spares (of its circuits, rounded up), in the first free
slots. Its ways are then the standard size that holds its circuits and
spares, and every other slot of those ways is a space."""
from __future__ import division

import math

SPARE_SHARE = 0.10
WAY_SIZES = [4, 6, 8, 12, 16, 18, 24, 30, 36, 42]      # standard boards (ways)

CIRCUIT, SPARE, SPACE = "circuit", "spare", "space"


def spares_needed(circuits):
    """Spares for a board with `circuits` circuits: 10 %, rounded up."""
    return int(math.ceil(circuits * SPARE_SHARE - 1e-9)) if circuits > 0 else 0


def ways_for(slots, per_way=3):
    """The standard number of ways holding `slots` slots."""
    ways = int(math.ceil(slots / per_way)) if slots > 0 else 0
    for size in WAY_SIZES:
        if size >= ways:
            return size
    return ways


class BoardPlan(object):
    """What happens to the slots of one board.

    `taken` maps each slot now in use to CIRCUIT, SPARE or SPACE (every
    slot of a multi-pole circuit). `circuits` is how many circuits it has."""

    def __init__(self, ref, panel, taken, circuits, max_slots, per_way=3):
        self.ref = ref
        self.panel = panel
        self.taken = dict(taken)
        self.circuits = circuits
        self.per_way = per_way
        self.old_slots = max_slots
        self.old_ways = max_slots // per_way if per_way else max_slots

        have = sorted(s for s, kind in self.taken.items() if kind == SPARE)
        need = spares_needed(circuits)
        fixed = set(s for s, kind in self.taken.items() if kind == CIRCUIT)
        fixed.update(have)
        self.new_spares = []
        slot = 1
        while len(have) + len(self.new_spares) < need:
            if slot not in fixed:
                self.new_spares.append(slot)
            slot += 1
        fixed.update(self.new_spares)

        self.ways = ways_for(max(fixed) if fixed else 0, per_way)
        self.slots = self.ways * per_way
        self.spares = len(have) + len(self.new_spares)
        # spaces on every free slot of the ways; spares and spaces past them go
        self.new_spaces = [s for s in range(1, self.slots + 1)
                           if s not in fixed and self.taken.get(s) != SPACE]
        self.spaces_to_spares = [s for s in self.new_spares if self.taken.get(s) == SPACE]
        self.removed = sorted(s for s, kind in self.taken.items()
                              if kind in (SPARE, SPACE) and s > self.slots)
        self.spaces = sum(1 for s in range(1, self.slots + 1)
                          if s not in fixed) if self.slots else 0

    @property
    def changed(self):
        if not self.circuits:
            return False                    # an empty board is left as it is
        return bool(self.new_spares or self.new_spaces or self.removed or
                    self.slots != self.old_slots)

    def text(self):
        """'12 ways: 29 circuits, 3 spares (+3), 4 spaces' for the preview."""
        added = len(self.new_spares)
        return u"%d ways (was %d): %d circuits, %d spare%s%s, %d space%s" % (
            self.ways, self.old_ways, self.circuits, self.spares,
            "" if self.spares == 1 else "s", u" (+%d)" % added if added else u"",
            self.spaces, "" if self.spaces == 1 else "s")
