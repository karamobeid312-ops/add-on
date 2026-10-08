# -*- coding: utf-8 -*-
"""Draw a cable tray along points clicked in a plan. Where a pipe, duct,
beam, column or other tray is in its way, the tray goes over it, under
it, or round it to the left or right. Walls it cannot pass over or under
are crossed and listed as openings to make."""
__title__ = "Route\nTray"

from traycoord.command import run_route

run_route()
