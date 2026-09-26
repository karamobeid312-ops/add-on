# -*- coding: utf-8 -*-
"""Place smoke detectors on the ceiling of the selected spaces: at most
9 m apart and 4.5 m from the walls (change the spacing in Settings).
Select the spaces first, or pick them after clicking."""
__title__ = "Smoke\nDetectors"

from firealarm.command import run

run("smoke")
