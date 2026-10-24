# -*- coding: utf-8 -*-
"""Build Tower 2 as the mirror of Tower 1: pick Tower 1's scope box and
Tower 2, tick the floors. The electrical elements Tower 2 has not got yet
are mirrored with their tags (boards renamed, e.g. B1 -> B2), then Tower
1's circuits are made again on Tower 2's copies and boards, and their
wires drawn."""
__title__ = "Mirror\nTower"

from mepmirror.command import run
from mepmirror.rules import ELECTRICAL

run(ELECTRICAL)
