# -*- coding: utf-8 -*-
"""Which Tower 1 elements Tower 2 has already, and which board feeds
Tower 2's copy of a circuit (no Revit needed)."""
from __future__ import division

from copycircuits import placement as placing
from copycircuits import plan

# how a Tower 1 board's Tower 2 board was found (plan.PanelMatch.how)
BY_NAME = plan.BY_NAME          # named like it with the text swapped (B1 -> B2)
BY_SPOT = plan.BY_SPOT          # same family type at its mirrored spot
ITSELF = plan.ITSELF            # on the mirror line: it feeds both towers
FALLBACK = plan.FALLBACK        # no Tower 2 board found: it feeds both towers


def pair_up(tower1, pool, placement, tolerance, z_tolerance, by_name=None):
    """({Tower 1 key: Tower 2 key}, [Tower 1 keys with no copy yet]).

    tower1: plan.Items of Tower 1; pool: plan.Items they may already have
    a copy among (the floor's other elements). A copy is of the same family
    type (else family) at the mirrored spot, at the same height. by_name:
    {Tower 1 key: Tower 2 key} of boards found by name, which win."""
    by_name = dict(by_name or {})
    rest = [i for i in tower1 if i.key not in by_name]
    taken = set(by_name.values())
    free = [i for i in pool if i.key not in taken]
    copies = plan.match(placing.moved(rest, placement), free, tolerance, 0.0, z_tolerance)
    copies.update(by_name)
    missing = [i.key for i in tower1 if i.key not in copies]
    return copies, missing


def board_for(key, copies, by_name, by_spot, named=()):
    """(Tower 2 board key, how) feeding Tower 2's copy of a circuit fed
    by board `key`: its copy made or found on the floor, else the board
    named like it (B1 -> B2), else the board at its mirrored spot, else
    the board itself (one board for both towers). named: Tower 1 keys
    whose copy in `copies` was found by name."""
    if key in copies:
        if key in named:
            return copies[key], BY_NAME
        return copies[key], (ITSELF if copies[key] == key else BY_SPOT)
    if by_name is not None:
        return by_name, BY_NAME
    if by_spot is not None:
        return by_spot, (ITSELF if by_spot == key else BY_SPOT)
    return key, FALLBACK
