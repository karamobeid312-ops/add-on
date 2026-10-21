# -*- coding: utf-8 -*-
"""RCD sections, spares, spaces and the number of ways of a board (no Revit).

A board is laid out in two RCD sections: lighting and FCU circuits on a
100 mA RCD, then the other (power) circuits on a 30 mA RCD. Each section
gets 10 % spares (of its circuits, rounded up) right after its circuits;
section 2 starts on a new way, and a section takes at least 6 slots. The board's ways (slots) are the standard size
holding all that, and every other slot of those ways is a space. Each
RCD is the smallest standard RCCB carrying its section's load."""
from __future__ import division

import math

SPARE_SHARE = 0.10
# standard boards, in rows of R, Y, B (a way is one slot: R1, or Y1)
ROW_SIZES = [4, 6, 8, 12, 16, 18, 24, 30, 36, 42]
RCCB_SIZES = [25, 40, 63, 80, 100, 125]                # A
VOLTS_3PH, VOLTS_1PH = 400.0, 230.0

CIRCUIT, SPARE, SPACE = "circuit", "spare", "space"

SECTION_100MA, SECTION_30MA = 1, 2
MIN_SECTION_SLOTS = 6           # an RCD section takes at least 6 slots (2 ways)
SENSITIVITY = {SECTION_100MA: 100, SECTION_30MA: 30}    # mA


def spares_needed(circuits):
    """Spares for `circuits` circuits: 10 %, rounded up."""
    return int(math.ceil(circuits * SPARE_SHARE - 1e-9)) if circuits > 0 else 0


def ways_for(slots, per_row=3):
    """The ways (slots) of the standard board holding `slots` slots: 32
    slots take a 12 row board, 36 ways."""
    rows = int(math.ceil(slots / per_row)) if slots > 0 else 0
    for size in ROW_SIZES:
        if size >= rows:
            return size * per_row
    return rows * per_row


def rcd_text(load_va, section, per_way=3):
    """'RCCB 40A 4P 100mA': the smallest standard RCCB carrying the load."""
    phases = 3 if per_way == 3 else 1
    amps = load_va / (math.sqrt(3) * VOLTS_3PH) if phases == 3 else load_va / VOLTS_1PH
    rating = next((size for size in RCCB_SIZES if size >= amps - 1e-9), RCCB_SIZES[-1])
    return u"RCCB %dA %dP %dmA" % (rating, 4 if phases == 3 else 2, SENSITIVITY[section])


class Item(object):
    """A circuit of the board: where it is now, its poles, section and load."""

    def __init__(self, key, slot, poles, section, load_va=0.0, name=u""):
        self.key = key
        self.slot = slot
        self.poles = max(int(poles or 1), 1)
        self.section = section
        self.load_va = load_va or 0.0
        self.name = name


class BoardPlan(object):
    """The new layout of one board's slots.

    `items` are its circuits; `spares` and `spaces` the slots holding a
    spare or a space now; `max_slots` its Max #1 Pole Breakers; `rcds`
    what its Section1/2_Protection say now."""

    def __init__(self, ref, panel, items, spares, spaces, max_slots, per_way=3, rcds=None):
        self.ref = ref
        self.panel = panel
        self.items = sorted(items, key=lambda i: i.slot)
        self.per_way = per_way
        self.old_slots = max_slots
        self.old_ways = max_slots
        self.old_spares = sorted(spares)
        self.old_spaces = sorted(spaces)
        self.old_rcds = dict(rcds or {})

        self.targets = {}               # item key -> new start slot
        self.spare_slots = {}           # section -> [slots]
        self.counts = {}                # section -> circuits
        self.rcds = {}                  # section -> 'RCCB 40A 4P 100mA'
        used = set()
        slot = first = 1
        for section in (SECTION_100MA, SECTION_30MA):
            members = [i for i in self.items if i.section == section]
            if not members:
                continue
            if used:                    # a new section starts on a new way,
                slot = self._next_way(max(slot, first + MIN_SECTION_SLOTS))
            first = slot                # at least 6 slots after the last one
            for item in members:
                start = slot
                if item.poles > 1:      # multi-pole breakers start on a way
                    start = self._next_way(start)
                while any(s in used for s in range(start, start + item.poles)):
                    start += 1
                self.targets[item.key] = start
                used.update(range(start, start + item.poles))
                slot = self._first_free(used, slot)
            spares = []
            for _ in range(spares_needed(len(members))):
                slot = self._first_free(used, slot)
                spares.append(slot)
                used.add(slot)
            self.spare_slots[section] = spares
            self.counts[section] = len(members)
            self.rcds[section] = rcd_text(sum(i.load_va for i in members), section, per_way)
            slot = self._first_free(used, slot)

        last = max(used) if used else 0
        if used:                        # the last section takes 6 slots too
            last = max(last, first + MIN_SECTION_SLOTS - 1)
        self.ways = self.slots = ways_for(last, per_way)
        self.spaces = [s for s in range(1, self.slots + 1) if s not in used]
        self.moved = [i for i in self.items if self.targets[i.key] != i.slot]

    def _next_way(self, slot):
        rest = (slot - 1) % self.per_way
        return slot if rest == 0 else slot + self.per_way - rest

    @staticmethod
    def _first_free(used, slot):
        while slot in used:
            slot += 1
        return slot

    @property
    def new_spares(self):
        return sorted(s for slots in self.spare_slots.values() for s in slots)

    @property
    def changed(self):
        if not self.items:
            return False                    # an empty board is left as it is
        return bool(self.moved or self.new_spares != self.old_spares or
                    self.spaces != self.old_spaces or self.slots != self.old_slots or
                    any(self.old_rcds.get(s) != t for s, t in self.rcds.items()))

    def text(self):
        """'36 ways, 100mA RCCB 40A 4P: 14 circuits + 2 spares, ...' for the preview."""
        parts = [u"%d ways (was %d)" % (self.ways, self.old_ways)]
        for section in sorted(self.rcds):
            spares = len(self.spare_slots[section])
            parts.append(u"%s: %d circuits + %d spare%s" % (
                self.rcds[section], self.counts[section], spares, "" if spares == 1 else "s"))
        parts.append(u"%d space%s" % (len(self.spaces), "" if len(self.spaces) == 1 else "s"))
        if self.moved:
            parts.append(u"%d circuit%s moved" % (len(self.moved),
                                                   "" if len(self.moved) == 1 else "s"))
        return u", ".join(parts)
