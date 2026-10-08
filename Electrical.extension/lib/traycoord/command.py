# -*- coding: utf-8 -*-
"""Entry points for the ribbon buttons."""
from Autodesk.Revit.DB import Transaction
from pyrevit import forms, revit, script

from traycoord import report, revit_tray, route, settings

TITLE = "Cable Tray"

DRAW = "Draw the tray"
VIEW = "Cable trays shown in this view"
PICK = "Pick cable trays"

_SHOWN = {
    "prefer": {"shortest": "the shortest way round", "over": "over first",
               "under": "under first", "side": "left or right first"},
    "bends": {"90": "90 degree bends", "45": "45 degree bends"},
    "links": {"yes": "yes", "no": "no"},
}

_PROMPTS = {
    "width": "Tray width in mm:",
    "height": "Tray height in mm:",
    "elevation": "Middle elevation of the tray above the plan's level, in mm:",
    "clearance": "Clearance in mm, kept between the tray and anything in its way:",
    "headroom": "Headroom in mm: the lowest the bottom of the tray may go above its floor "
                "level when it dodges under something:",
    "slab": "Gap in mm kept under the level above (slab and finishes): the highest the top "
            "of the tray may go when it dodges over something:",
}


def _number(value):
    return ("%.1f" % value).rstrip("0").rstrip(".")


def _ask_number(values, key):
    """Asks for a number setting; True when it changed."""
    low, high = settings.RANGES[key]
    text = forms.ask_for_string(default=_number(values[key]), prompt=_PROMPTS[key],
                                title="%s Settings" % TITLE)
    if text is None:
        return False
    value = settings.valid(key, text.replace(",", ".").replace("mm", "").strip())
    if value is None:
        forms.alert("Enter a number from %s to %s mm." % (_number(low), _number(high)),
                    title=TITLE)
        return False
    values[key] = value
    return True


def _key(key):
    """Revit element id to link in the report, for a host or linked element."""
    return key[0] if isinstance(key, tuple) else key


def _show(routed, verb, failed):
    output = script.get_output()
    output.set_title(TITLE)
    output.print_md("# Cable tray coordination")
    output.print_md(report.headline(routed, verb))

    def link(key):
        return output.linkify(_key(key))

    rows = report.dodge_rows(routed, link)
    if rows:
        output.print_md("## Dodged")
        output.print_table(table_data=rows, columns=report.DODGE_COLUMNS)
    rows = report.crossing_rows(routed, link)
    if rows:
        output.print_md("## Walls the tray goes through")
        output.print_md("*Make an opening or a sleeve in each: the size includes the "
                        "clearance.*")
        output.print_table(table_data=rows, columns=report.CROSSING_COLUMNS)
    rows = report.unsolved_rows(routed, link)
    if rows:
        output.print_md("## Left for you")
        output.print_md("*The tray goes straight through these: move the tray or the "
                        "element, or change the headroom and slab gap in Tray Settings.*")
        output.print_table(table_data=rows, columns=report.UNSOLVED_COLUMNS)
    if failed:
        output.print_md("*%d bend%s could not be added: the pieces of tray there are too short "
                        "for the type's fittings. Join them by hand.*"
                        % (failed, "" if failed == 1 else "s"))
    output.print_md("*Click an element id to select it and zoom to it. Linked elements "
                    "link to their link.*")


def _check_doc(doc, what):
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to %s." % what, title=TITLE)
        return False
    return True


# ---------------------------------------------------------------- Route Tray

def _drawing_options(doc, values):
    """Asks what to draw; False when cancelled."""
    types = revit_tray.tray_types(doc)
    if not types:
        forms.alert("There are no cable tray types in this model. Load or make one first.",
                    title=TITLE)
        return False
    if values["tray_type"] not in types:
        values["tray_type"] = sorted(types)[0]
    while True:
        options = [
            DRAW,
            u"Type: %s" % values["tray_type"],
            u"Size: %s x %s mm" % (_number(values["width"]), _number(values["height"])),
            u"Middle elevation: %s mm above the level" % _number(values["elevation"]),
        ]
        choice = forms.CommandSwitchWindow.show(
            options, message="Click Draw, then click the tray's path in the plan:")
        if not choice:
            return False
        index = options.index(choice)
        if index == 0:
            settings.save(values)
            return True
        if index == 1:
            picked = forms.SelectFromList.show(sorted(types), title="Cable tray type",
                                               button_name="Use this type", multiselect=False)
            if picked:
                values["tray_type"] = picked
        elif index == 2:
            _ask_number(values, "width") and _ask_number(values, "height")
        else:
            _ask_number(values, "elevation")


def run_route():
    """Draw a new cable tray along clicked points, clear of what is in its way."""
    doc, uidoc = revit.doc, revit.uidoc
    if not _check_doc(doc, "draw a cable tray"):
        return
    view = doc.ActiveView
    if not revit_tray.is_plan(view):
        forms.alert("Open a floor plan or a ceiling plan: the tray's path is clicked in it.",
                    title=TITLE)
        return
    values = settings.load()
    if not _drawing_options(doc, values):
        return
    tray_type = revit_tray.tray_types(doc)[values["tray_type"]]
    level = view.GenLevel
    z = level.ProjectElevation * revit_tray.M_PER_FOOT + values["elevation"] / 1000.0

    if view.SketchPlane is None:
        t = Transaction(doc, "Cable tray work plane")
        t.Start()
        revit_tray.ensure_work_plane(doc, view)
        t.Commit()
    path = revit_tray.pick_path(uidoc, z)
    if len(path) < 2:
        return

    width, height = values["width"] / 1000.0, values["height"] / 1000.0
    bounds = revit_tray.limits(doc, z, values["headroom"] / 1000.0, values["slab"] / 1000.0)
    obstacles = revit_tray.read_obstacles(doc, path, bounds, settings.categories(values),
                                          links=values["links"] == "yes")
    runs = route.route_path(path, width, height, obstacles, limits=bounds,
                            **settings.options(values))
    points = [runs[0].points[0]]
    for r in runs:
        points += r.points[1:]

    t = Transaction(doc, "Route Cable Tray")
    t.Start()
    try:
        trays, failed = revit_tray.draw(doc, points, tray_type.Id, level.Id, width, height)
        t.Commit()
    except Exception as err:
        t.RollBack()
        forms.alert("The tray could not be drawn.", expanded=u"%s" % err, title=TITLE)
        return
    revit_tray.select(uidoc, [tray.Id for tray in trays])
    clearance = values["clearance"] / 1000.0
    routed, first = [], 0
    for r in runs:                      # each leg linked by its first piece of tray
        routed.append(report.Routed(r, trays[min(first, len(trays) - 1)].Id, width, height,
                                    clearance))
        first += len(revit_tray.segments(r.points))
    _show(routed, "Drew", failed)


# ---------------------------------------------------------------- Fix Trays

def _choose_trays(doc, uidoc):
    found = revit_tray.selected_trays(uidoc)
    if found:
        return found
    choice = forms.CommandSwitchWindow.show([VIEW, PICK],
                                            message="Which cable trays are rerouted?")
    if choice == VIEW:
        return revit_tray.view_trays(doc, doc.ActiveView)
    if choice == PICK:
        return revit_tray.pick_trays(uidoc)
    return []


def run_fix():
    """Reroute existing cable trays round what is in their way."""
    doc, uidoc = revit.doc, revit.uidoc
    if not _check_doc(doc, "reroute cable trays"):
        return
    trays = _choose_trays(doc, uidoc)
    if not trays:
        return
    values = settings.load()
    skip = revit_tray.neighbours(trays)
    clearance = values["clearance"] / 1000.0
    plans = []
    for tray in trays:
        start, end, start_joined, end_joined = revit_tray.ends(tray)
        width, height = revit_tray.size(tray)
        bounds = revit_tray.limits(doc, start[2], values["headroom"] / 1000.0,
                                   values["slab"] / 1000.0)
        obstacles = revit_tray.read_obstacles(doc, [start, end], bounds,
                                              settings.categories(values),
                                              links=values["links"] == "yes", skip=skip)
        result = route.route(start, end, width, height, obstacles, limits=bounds,
                             start_free=not start_joined, end_free=not end_joined,
                             **settings.options(values))
        plans.append((tray, result, width, height))

    changed = [p for p in plans if p[1].changed]
    failed = 0
    touched = []
    if changed:
        t = Transaction(doc, "Fix Cable Trays")
        t.Start()
        try:
            for tray, result, _, _ in changed:
                pieces, bad = revit_tray.reroute(doc, tray, result.points)
                touched += [piece.Id for piece in pieces]
                failed += bad
            t.Commit()
        except Exception as err:
            t.RollBack()
            forms.alert("The trays could not be rerouted, nothing was changed.",
                        expanded=u"%s" % err, title=TITLE)
            return
    if touched:
        revit_tray.select(uidoc, touched)
    routed = [report.Routed(result, tray.Id, width, height, clearance)
              for tray, result, width, height in plans]
    _show(routed, "Checked", failed)


# ---------------------------------------------------------------- Tray Settings

_SETTINGS = [
    ("clearance", "Clearance"),
    ("prefer", "Dodge"),
    ("bends", "Bends"),
    ("headroom", "Headroom"),
    ("slab", "Gap under the level above"),
    ("obstacles", "In the way"),
    ("links", "Linked models count"),
]


def _shown(values, key):
    if key in _SHOWN:
        return _SHOWN[key][values[key]]
    if key == "obstacles":
        chosen = values[key].split(",")
        names = [name.lower() for k, name, _ in settings.OBSTACLES if k in chosen]
        return ", ".join(names) or "nothing"
    return "%s mm" % _number(values[key])


def edit_settings():
    while True:
        values = settings.load()
        options = [u"%s: %s" % (label, _shown(values, key)) for key, label in _SETTINGS]
        choice = forms.CommandSwitchWindow.show(options, message="Click a setting to change it:")
        if not choice:
            return
        key, label = _SETTINGS[options.index(choice)]
        if key == "obstacles":
            names = [name for _, name, _ in settings.OBSTACLES]
            picked = forms.SelectFromList.show(
                names, title="What the tray dodges", button_name="Use these", multiselect=True)
            if picked is None:
                continue
            values[key] = ",".join(k for k, name, _ in settings.OBSTACLES if name in picked)
        elif key in settings.CHOICES:
            shown = [_SHOWN[key][v] for v in settings.CHOICES[key]]
            picked = forms.CommandSwitchWindow.show(shown, message=label + ":")
            if not picked:
                continue
            values[key] = settings.CHOICES[key][shown.index(picked)]
        elif not _ask_number(values, key):
            continue
        settings.save(values)
