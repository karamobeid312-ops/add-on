# -*- coding: utf-8 -*-
"""Place lighting fixtures on the light blocks of a linked or imported
DWG. Open the plan that shows the CAD, click the CAD, then pick the
fixture type for each block name. Lights go on the ceiling above (also
ceilings in linked models), turned like the blocks; spots that already
have a light are skipped."""
__title__ = "CAD\nLights"

from cadlights.command import run

run()
