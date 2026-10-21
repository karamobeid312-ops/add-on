# -*- coding: utf-8 -*-
"""Build Tower 2's water and drainage pipes, plumbing fixtures and sprinklers
as the mirror of Tower 1's: pick Tower 1's scope box, click 2 points in
Tower 1 and the same 2 in Tower 2, tick the floors."""
__title__ = "Mirror\nTower"

from mepmirror.command import run
from mepmirror.rules import PLUMBING

run(PLUMBING)
