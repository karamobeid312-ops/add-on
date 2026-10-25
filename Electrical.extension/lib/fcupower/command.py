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


def _option(key):
    try:
        from pyrevit import script
        return script.get_config(SECTION).get_option(key, "") or ""
    except Exception:
        return ""


def _keep_option(key, value):
    try:
        from pyrevit import script
        cfg = script.get_config(SECTION)
        setattr(cfg, key, value)
        script.save_config()
    except Exception:
        pass


def _names(found):
    types, best = found
    return sorted(types), best


def _circuit(doc, elements, keys, panel_name, wire_name, tag_name):
    """Circuit and wire the outlets (element ids), each on its own circuit."""
    from fcupower import circuit, revit_fcu
    panel = circuit.panels(doc).get(panel_name)
    if panel is None:
        return 0, 0, 0, [u"Panel %s not found" % panel_name]
    wires = circuit.wire_types(doc)[0]
    tags = circuit.tag_types(doc)[0]
    views = {}

    def view_for(element):
        point = revit_fcu._location(element)
        if point is None:
            return None
        key = round(point.Z, 1)
        if key not in views:
            views[key] = circuit.plan_of(doc, point.Z)
        return views[key]
    outlets = [(label, elements[k]) for k, label in keys if k in elements]
    return circuit.circuit_and_wire(doc, outlets, panel, wires.get(wire_name), tags.get(tag_name),
                                    view_for)


def _levels(doc):
    """[(name, elevation)] of the model's levels, low to high."""
    from Autodesk.Revit.DB import FilteredElementCollector, Level
    levels = list(FilteredElementCollector(doc).OfClass(Level))
    return [(l.Name, l.ProjectElevation) for l in sorted(levels, key=lambda l: l.ProjectElevation)]


def _active_level(doc):
    try:
        return doc.ActiveView.GenLevel.Name
    except Exception:
        return None


def _busiest_level(doc, fams):
    """Level holding the most FCUs of the default families: the floor shown
    when the active view has no level (rooms are found per floor, all floors
    at once is the slow case)."""
    counts = {}
    for fam in fams:
        if not fam.default:
            continue
        for e in fam.elements:
            level_id = getattr(e, "LevelId", None)
            if level_id is not None:
                counts[level_id] = counts.get(level_id, 0) + 1
    if not counts:
        return None
    level = doc.GetElement(max(counts, key=lambda k: counts[k]))
    return level.Name if level is not None else None


def run():
    doc = revit.doc
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to use FCU Power.", exitscript=True)

    import time
    from fcupower import circuit, place, revit_fcu
    from fcupower.window_ui import show_window
    start = time.time()
    fams = revit_fcu.families(doc)
    families_s = time.time() - start
    if not fams:
        forms.alert("No family in this model has a Real_Power_W parameter or FCU in its name.",
                    exitscript=True)
    models = revit_fcu.room_models(doc)
    rooms, elements = {}, {}
    linked = revit_fcu.LinkedFcus(doc)      # the tags are on the FCUs of the mechanical link
    links_s = time.time() - start - families_s
    callbacks = {
        "families": fams,
        "read": lambda ticked, progress, span=None: revit_fcu.read_fcus(
            doc, ticked, models, rooms, elements, progress, linked, span),
        "write": lambda fcus: revit_fcu.write(doc, fcus, elements),
        "path": _last_path(),
        "keep_path": _keep_path,
        "families_ticked": _last_families(),
        "units": linked.units,
        "levels": _levels(doc),
        "active_level": _active_level(doc) or _busiest_level(doc, fams),
        "timing": [(u"families", families_s), (u"links", links_s)],
        "socket_types": lambda names: place.socket_types(doc, names),
        "default_type": lambda labels, fams: place.most_used(
            labels, [e for f in fams for e in f.elements]),
        "add": lambda units, label, names: place.add_sockets(
            doc, units, place.socket_types(doc, names)[label]),
        "reload_families": lambda: revit_fcu.families(doc),
        "panels": lambda: sorted(circuit.panels(doc)),
        "wire_types": lambda: _names(circuit.wire_types(doc)),
        "tag_types": lambda: _names(circuit.tag_types(doc)),
        "circuit": lambda keys, panel, wire, tag: _circuit(doc, elements, keys, panel, wire, tag),
        "panel": _option("panel"),
        "keep_panel": lambda name: _keep_option("panel", name),
        "keep_families": _keep_families,
    }
    links = len(models) - 1
    show_window(callbacks, u"%s\n%d FCUs with Comments in the links · rooms from %s" % (
        doc.Title, len(linked.units), u"%d link(s) and this model" % links if links else u"this model"))
