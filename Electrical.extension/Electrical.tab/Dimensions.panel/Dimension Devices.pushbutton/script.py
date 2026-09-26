# -*- coding: utf-8 -*-
"""Dimension the devices in the active floor or ceiling plan: a string
along each row and column of devices, from the nearest wall, device to
device. Devices on walls (sockets, switches) get a string along their
wall from the nearest corner. Select the devices (or spaces) first, or
after clicking take all the devices in the view, or pick them."""
__title__ = "Dimension\nDevices"

from dims.command import run

run()
