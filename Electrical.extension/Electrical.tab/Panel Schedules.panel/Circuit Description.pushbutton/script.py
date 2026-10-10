# -*- coding: utf-8 -*-
"""Fill the circuit description (Load Name) of the panel schedules with
the room the circuit's fixtures are in, read from the architectural
link: '012 PUMP ROOM'. Open a panel schedule or select boards first, or
pick the boards after clicking. Shows every change before writing."""
__title__ = "Circuit\nDescription"

from circuitdesc.command import run

run()
