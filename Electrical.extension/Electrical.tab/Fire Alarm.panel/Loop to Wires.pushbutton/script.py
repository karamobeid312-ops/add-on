# -*- coding: utf-8 -*-
"""Switch the FA Loop detail lines of this plan to wires along the same
path: one wire for each run of lines between two devices, in the loop's
colour. Select some loop lines first to switch only their loops. Each
wire keeps its loop in its Comments, so Address Devices, FA Riser and
Draw FA Loop work with the wires as they do with the lines."""
__title__ = "Loop to\nWires"

from firealarm.command import loop_to_wires

loop_to_wires()
