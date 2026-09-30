# -*- coding: utf-8 -*-
"""Connect the fire alarm devices of this plan with detail lines: each
loop runs from the start (the panel, or the device you click) through up
to 120 devices and back, on the shortest route found, with lines at right
angles along the devices' rows and columns. More devices are split into
several loops, each one area. Detection loops take every device but
sirens and flashers; sounder loops only sirens and flashers. Every device
gets its address (FA Address, e.g. L1/SD-01) and its tag. Select the
devices first, or choose them after clicking, then click the start."""
__title__ = "Draw\nFA Loop"

from firealarm.command import draw_loop

draw_loop()
