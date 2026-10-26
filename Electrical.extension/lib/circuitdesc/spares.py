# -*- coding: utf-8 -*-
"""RCD sections, spares, spaces and the number of ways of a board (no Revit).

A board is laid out in two RCD sections: lighting and FCU circuits on a
100 mA RCD, then the other (power) circuits on a 30 mA RCD. Each section
gets 10 % spares (of its circuits, rounded up) right after its circuits;
section 2 starts on a new R row, and a section takes at least 6 ways. On
a three phase board the circuits are spread over R, Y and B to balance
the phase loads. The board's ways (a way is one slot) are the smallest of
12, 18, 24, 30, 36 and 42 holding all that, and every other slot is a space. Each RCD is the
smallest standard RCCB carrying its section's load."""
from __future__ import division

import math

SPARE_SHARE = 0.10
RCCB_SIZES = [25, 40, 63, 80, 100, 125]                # A
VOLTS_3PH, VOLTS_1PH = 400.0, 230.0

CIRCUIT, SPARE, SPACE = "circuit", "spare", "space"

SECTION_100MA, SECTION_30MA = 1, 2
MIN_SECTION_SLOTS = 6           # an RCD section takes at least 6 slots (2 ways)
SENSITIVITY = {SECTION_100MA: 100, SECTION_30MA: 30}    # mA


def spares_needed(circuits):
    """Spares for `circuits` circuits: 10 %, rounded up."""
    return int(math.ceil(circuits * SPARE_SHARE - 1e-9)) if circuits > 0 else 0


WAY_SIZES = [12, 18, 24, 30, 36, 42]       # the only boards there are (ways)
WAY_STEP = 6


def ways_for(slots, per_row=3):
    """The ways (a way is one slot: R1, or Y1) of the board holding `slots`
    slots: the smallest of 12, 18, 24, 30, 36, 42 (25 slots take 30 ways)."""
    if slots <= 0:
        return 0
    for size in WAY_SIZES:
        if size >= slots:
            return size
    return int(math.ceil(slots / WAY_STEP)) * WAY_STEP     # too big: see too_big


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
        self.phase_loads = [0.0, 0.0, 0.0]     # VA on R, Y, B
        for section in (SECTION_100MA, SECTION_30MA):
            members = [i for i in self.items if i.section == section]
            if not members:
                continue
            if used:                    # a new section starts on a new way,
                slot = self._next_way(max(slot, first + MIN_SECTION_SLOTS))
            first = slot                # at least 6 slots after the last one
            if per_way == 3:
                spares = self._balanced(members, slot, used)
            else:
                spares = self._in_order(members, slot, used)
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

    def _in_order(self, members, slot, used):
        """Circuits one after the other in their order, then the spares."""
        for item in members:
            start = slot
            if item.poles > 1:          # multi-pole breakers start on a way
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
        return spares

    def _add_load(self, slot, va):
        self.phase_loads[(slot - 1) % 3] += va

    def _balanced(self, members, slot, used):
        """Three phase board: multi-pole circuits first, each from an R row;
        then the single-pole circuits, the biggest first, each on the phase
        (R, Y or B) of the board carrying the least load so far; in a phase
        they go in the order they were made. The spares take the slots left in the rows."""
        row = slot
        for item in [i for i in members if i.poles > 1]:
            while any(s in used for s in range(row, row + item.poles)):
                row += 3
            self.targets[item.key] = row
            used.update(range(row, row + item.poles))
            for s in range(row, row + item.poles):
                self._add_load(s, item.load_va / item.poles)
            row += 3 * int(math.ceil(item.poles / 3))
        singles = [i for i in members if i.poles == 1]
        n_spares = spares_needed(len(members))
        free = [s for s in range(slot, row) if s not in used]
        need = len(singles) + n_spares - len(free)
        if need > 0:
            free += list(range(row, row + 3 * int(math.ceil(need / 3))))
        queues = [[s for s in free if (s - 1) % 3 == p] for p in range(3)]
        chosen = [[], [], []]
        # by key, not slot, so running it again gives the same layout
        for item in sorted(singles, key=lambda i: (-i.load_va, i.key)):
            open_ = [p for p in range(3) if len(chosen[p]) < len(queues[p])]
            p = min(open_, key=lambda q: (self.phase_loads[q], -len(queues[q]) + len(chosen[q]), q))
            chosen[p].append(item)
            self.phase_loads[p] += item.load_va
        for p in range(3):
            for item, s in zip(sorted(chosen[p], key=lambda i: i.key), queues[p]):
                self.targets[item.key] = s
                used.add(s)
        spares = [s for s in sorted(free) if s not in used][:n_spares]
        used.update(spares)
        return spares

    def _next_way(self, slot):
        rest = (slot - 1) % self.per_way
        return slot if rest == 0 else slot + self.per_way - rest

    @staticmethod
    def _first_free(used, slot):
        while slot in used:
            slot += 1
        return slot

    @property
    def too_big(self):
        """More ways than the biggest board: it has to be split."""
        return self.ways > WAY_SIZES[-1]

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
        parts = [u"%d ways (was %d)%s" % (self.ways, self.old_ways,
                                          u" MORE THAN 42: SPLIT THE BOARD" if self.too_big else u"")]
        for section in sorted(self.rcds):
            spares = len(self.spare_slots[section])
            parts.append(u"%s: %d circuits + %d spare%s" % (
                self.rcds[section], self.counts[section], spares, "" if spares == 1 else "s"))
        parts.append(u"%d space%s" % (len(self.spaces), "" if len(self.spaces) == 1 else "s"))
        if self.per_way == 3:
            parts.append(u"R/Y/B %s kVA" % u"/".join(
                u"%.1f" % (va / 1000.0) for va in self.phase_loads))
        if self.moved:
            parts.append(u"%d circuit%s moved" % (len(self.moved),
                                                   "" if len(self.moved) == 1 else "s"))
        return u", ".join(parts)
