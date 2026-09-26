# -*- coding: utf-8 -*-
"""Place smoke detectors on the ceiling of the selected spaces: at most
9 m apart and 4.5 m from the walls (change the spacing in Settings).
Select the spaces first, or after clicking pick them in this model or
in a linked model, or take all spaces on a level."""
__title__ = "Smoke\nDetectors"

from firealarm.command import run

run("smoke")
