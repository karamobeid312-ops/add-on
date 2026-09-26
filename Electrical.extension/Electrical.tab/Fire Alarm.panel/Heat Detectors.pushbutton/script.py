# -*- coding: utf-8 -*-
"""Place heat detectors on the ceiling of the selected spaces: at most
4.5 m apart and 2.25 m from the walls (change the spacing in Settings).
Select the spaces first, or after clicking pick them in this model or
in a linked model, or take all spaces on a level."""
__title__ = "Heat\nDetectors"

from firealarm.command import run

run("heat")
