# -*- coding: utf-8 -*-
"""Export every panel schedule of the model to one Excel workbook: an Index
sheet, then one sheet per panel laid out as in Revit."""
__title__ = "Export Panel\nSchedules"

from panelsched.command import export

export()
