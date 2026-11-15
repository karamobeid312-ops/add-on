# -*- coding: utf-8 -*-
"""Switch detail lines of this plan to wires along the same path: choose
the line types (FA Loop 1, your own line styles...), then the wire type.
One wire for each run of lines between two devices, in the line's
colour. Select some lines first to choose only among them. Wires from FA
Loop lines keep their loop in their Comments, so Address Devices, FA
Riser and Draw FA Loop work with them as with the lines."""
__title__ = "Loop to\nWires"

from firealarm.command import loop_to_wires

loop_to_wires()
