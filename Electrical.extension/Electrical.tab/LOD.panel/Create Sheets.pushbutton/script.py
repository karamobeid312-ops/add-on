# -*- coding: utf-8 -*-
"""Create a Revit sheet for every drawing of the List of Deliverables
(LOD) Excel file that the model does not have yet: sheet number, name,
revision and area from the LOD, and the key plan set from the name."""
__title__ = "Create\nSheets"

from lod.command import create_sheets

create_sheets()
