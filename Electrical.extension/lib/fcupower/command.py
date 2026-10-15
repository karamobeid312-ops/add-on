# -*- coding: utf-8 -*-
"""FCU Power: fill Real_Power_W of the FCUs from the mechanical schedule."""
from pyrevit import forms, revit

SECTION = "ElectricalFcuPower"


def _last_path():
    try:
        from pyrevit import script
        return script.get_config(SECTION).get_option("schedule", "") or ""
    except Exception:
        return ""


def _keep_path(path):
    from pyrevit import script
    cfg = script.get_config(SECTION)
    cfg.schedule = path
    script.save_config()


def _last_families():
    try:
        from pyrevit import script
        text = script.get_config(SECTION).get_option("families", "") or ""
        return [n for n in text.split("|") if n]
    except Exception:
        return []


def _keep_families(names):
    try:
        from pyrevit import script
        cfg = script.get_config(SECTION)
        cfg.families = "|".join(sorted(names))
        script.save_config()
    except Exception:
        pass


def run():
    doc = revit.doc
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to use FCU Power.", exitscript=True)

    from fcupower import revit_fcu
    from fcupower.window_ui import show_window
    fams = revit_fcu.families(doc)
    if not fams:
        forms.alert("No family in this model has a Real_Power_W parameter or FCU in its name.",
                    exitscript=True)
    models = revit_fcu.room_models(doc)
    rooms, elements = {}, {}
    linked = revit_fcu.LinkedFcus(doc)      # the tags are on the FCUs of the mechanical link
    callbacks = {
        "families": fams,
        "read": lambda ticked, progress: revit_fcu.read_fcus(doc, ticked, models, rooms,
                                                             elements, progress, linked),
        "write": lambda fcus: revit_fcu.write(doc, fcus, elements),
        "path": _last_path(),
        "keep_path": _keep_path,
        "families_ticked": _last_families(),
        "keep_families": _keep_families,
    }
    links = len(models) - 1
    show_window(callbacks, u"%s\n%d FCUs with Comments in the links · rooms from %s" % (
        doc.Title, len(linked.units), u"%d link(s) and this model" % links if links else u"this model"))
