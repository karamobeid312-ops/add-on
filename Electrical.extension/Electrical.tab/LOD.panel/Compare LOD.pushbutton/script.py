# -*- coding: utf-8 -*-
"""Compare the List of Deliverables with the sheets of the model:
drawings missing in Revit, sheets missing from the LOD, and different
names, revisions or areas."""
__title__ = "Compare\nLOD"

from lod.command import compare_lod

compare_lod()
