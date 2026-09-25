# -*- coding: utf-8 -*-
"""Generate a single line diagram that also shows every branch circuit
under its panel."""
__title__ = "SLD With\nCircuits"

from sld.command import run

run(include_branch_circuits=True)
