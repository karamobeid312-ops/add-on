# -*- coding: utf-8 -*-
"""Write the List of Deliverables from the Revit sheets as a new .xlsx:
the old LOD updated (its order and stage ticks kept, changes marked) or a
new list of the model's sheets."""
__title__ = "Export\nLOD"

from lod.command import export_lod

export_lod()
