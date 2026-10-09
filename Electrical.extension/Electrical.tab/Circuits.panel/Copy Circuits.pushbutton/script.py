# -*- coding: utf-8 -*-
"""Make the circuits of one floor again on the floors copied from it
(Revit does not copy circuits). Copies are found by family type and
spot in plan; panels on the floor are matched to their copies, panels
on other floors feed the copies too. Wires are drawn again in the
copied floors' plans. Select fixtures, circuits or panels first to copy
just their circuits."""
__title__ = "Copy\nCircuits"

from copycircuits.command import run

run()
