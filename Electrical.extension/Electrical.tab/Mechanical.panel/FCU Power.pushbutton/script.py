# -*- coding: utf-8 -*-
"""FCU Power: fill Real_Power_W of the FCUs from the mechanical schedule
(Excel). Each FCU's Comments is its tag; the room it is in is checked
against the schedule's served space."""
__title__ = "FCU\nPower"

from fcupower.command import run

run()
