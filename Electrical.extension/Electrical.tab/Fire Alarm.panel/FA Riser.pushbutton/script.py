# -*- coding: utf-8 -*-
"""Draw the fire alarm riser diagram in a new drafting view: floors bottom
to top, the main panel, and every loop drawn with Draw FA Loop with its
OUT and RETURN lines and the symbols of its devices, floor by floor, with
their quantities. A loop drawn on two floors with the same number goes
over both. Symbols follow the office legend (change them in FA
Settings > Riser symbols)."""
__title__ = "FA\nRiser"

from firealarm.command import draw_riser

draw_riser()
