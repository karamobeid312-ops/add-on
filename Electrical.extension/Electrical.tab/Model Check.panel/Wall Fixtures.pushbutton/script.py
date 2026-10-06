# -*- coding: utf-8 -*-
"""Check that wall fixtures (sockets, switches, wall lights, panels,
fire alarm and data devices...) sit on their wall face in 3D: not
floating off it, not set into or inside the wall, not past its end or
top, not turned, and still hosted. Select the fixtures first, or after
clicking take all in the model, those in this view, or pick them."""
__title__ = "Wall\nFixtures"

from wallcheck.command import run

run()
