# -*- coding: utf-8 -*-
"""Electrical side of Mirror Tower: board names and circuits.

The elements are mirrored as for Mechanical and Plumbing
(revit_mep.mirror_floor: one Revit Mirror per floor, tags with them, wall
items placed again on Tower 2's walls). Then, as the electrical Mirror
Tower always did:

1. Tower 2's boards are named like Tower 1's with the swap text
   (DB-B1-L4 -> DB-B2-L4); a Tower 1 board whose Tower 2 board is already
   named so is not mirrored again (plan.pair_by_name).
2. Tower 1's circuits are made again on Tower 2's copies and boards, and
   their wires drawn (mirrortower.revit_mirror.circuit_floor).

No parameter is created: only existing ones are read and set.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from __future__ import division

from copycircuits import revit_copy as rc
from mepmirror import plan, revit_mep
from mirrortower import revit_mirror

BOARDS = "OST_ElectricalEquipment"


def board_names(doc):
    """{board key: name} of the model's boards."""
    return dict((rc.id_int(e.Id), rc.panel_name(e))
                for e in revit_mirror.boards_by_name(doc).values())


def pair_by_name(sides, names, swap):
    for side in sides.values():
        plan.pair_by_name(side, names, swap)
    return sides


def name_boards(doc, model, side, result, swap, by_name):
    """Tower 2's boards named like Tower 1's with the swap (B1 -> B2): the
    copies just made, and the ones found at the mirrored spot that still
    carry Tower 1's name. by_name: revit_mirror.boards_by_name(doc)."""
    jobs = []
    for k, i in result.made.items():
        if model.categories.get(k) == BOARDS:
            jobs.append((k, doc.GetElement(i), True))
    for k, t in side.copies.items():
        if k == t or model.categories.get(k) != BOARDS:
            continue
        board = revit_mirror._get(doc, t)
        if board is None:
            continue
        if k in side.named:
            result.by_name.append((rc.panel_name(model.elements[k]), rc.panel_name(board)))
        elif swap and swap[0] and k not in result.made:
            jobs.append((k, board, False))
    if not jobs:
        return
    t = revit_mirror._transaction(doc, "Mirror Tower: board names, %s" % result.floor)
    t.Start()
    try:
        for k, board, new in jobs:
            if board is not None:
                revit_mirror._rename(model.elements[k], board, swap, result, by_name, new)
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise


def _pair(doc, model, key):
    e = model.elements.get(key) or revit_mirror._get(doc, key)
    item = rc._item(e) if e is not None else None
    return (item, e) if item is not None else None


def make_circuits(doc, model, floor_key, side, result, placement, tolerance, swap, by_name,
                  wires, tags=None):
    """Tower 1's circuits on this floor made again on Tower 2's copies and
    boards (and their wires drawn when `wires`, with their tags when
    `tags`, a revit_mep.Tags): result.circuits."""
    level = model.levels.get(floor_key)
    if level is None or not side.tower1:
        return
    eside = revit_mirror.Side(level, None)
    for things, into in ((side.tower1, eside.tower1), (side.shared, eside.on_line),
                         (side.pool, eside.pool)):
        for t in things:
            found = _pair(doc, model, t.key)
            if found is not None:
                into[t.key] = found
    copies = dict(side.copies)
    for t in side.shared:
        copies[t.key] = t.key
    for k, i in result.made.items():
        e = doc.GetElement(i)
        item = rc._item(e) if e is not None else None
        if item is not None:
            copies[k] = item.key
            eside.pool[item.key] = (item, e)
    eside.copies = copies
    eside.named = set(side.named)
    result.circuits, _ = revit_mirror.circuit_floor(doc, eside, placement, tolerance, swap,
                                                    by_name, wires)
    pairs = [(rc.id_int(old.Id), new) for old, new in result.circuits.wire_pairs]
    if tags is None or not pairs:
        return
    t = revit_mirror._transaction(doc, "Mirror Tower: wire tags, %s" % result.floor)
    t.Start()
    try:
        result.tags += revit_mep.mirror_tags(doc, tags, pairs, placement)
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
