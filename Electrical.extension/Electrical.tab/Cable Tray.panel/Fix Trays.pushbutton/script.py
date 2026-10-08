# -*- coding: utf-8 -*-
"""Reroute cable trays already drawn round the pipes, ducts, beams,
columns and other trays in their way. Select the trays first, or after
clicking take all in this view or pick them. Their ends stay joined."""
__title__ = "Fix\nTrays"

from traycoord.command import run_fix

run_fix()
