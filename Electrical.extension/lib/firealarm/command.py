# -*- coding: utf-8 -*-
"""Entry points for the ribbon buttons."""
from Autodesk.Revit.DB import ElementId
from pyrevit import forms, revit
from System.Collections.Generic import List

from firealarm import revit_address, revit_loop, revit_riser, revit_routes, settings
from firealarm.addresses import DETECTION, SOUNDER, on_loop
from firealarm.loops import loop_count, loop_numbers
from firealarm.report import summarize, summarize_addresses, summarize_loops, summarize_riser
from firealarm.riser_symbols import SYMBOLS, guess, resolve, symbol
from firealarm.revit_fa import (by_level, detector_types, linked_models,
                                pick_linked_spaces, pick_spaces, place_detectors,
                                placement_kind, selected_spaces, space_sources)

TITLE = "Fire Alarm"

LOOP_ALL = "All fire alarm devices in this view"
LOOP_PICK = "Pick devices"

PICK_HERE = "Pick spaces in this model"
PICK_LINKED = "Pick spaces or rooms in a linked model"
BY_LEVEL = "All spaces or rooms on a level"


def _spaces_on_levels(doc):
    sources = space_sources(doc)
    if not sources:
        forms.alert("There are no placed spaces or rooms in this model or its links.",
                    title=TITLE)
        return []
    if len(sources) == 1:
        refs = sources[0][1]
    else:
        chosen = forms.SelectFromList.show([label for label, _ in sources], title="Spaces from",
                                           button_name="Next", multiselect=False)
        if not chosen:
            return []
        refs = dict(sources)[chosen]
    levels = by_level(refs)
    chosen = forms.SelectFromList.show([label for label, _ in levels], title="Levels",
                                       button_name="Place detectors", multiselect=True)
    if not chosen:
        return []
    found = dict(levels)
    return [ref for label in chosen for ref in found[label]]


def _choose_spaces(doc, uidoc):
    """Spaces selected before clicking, or picked / taken by level now."""
    spaces = selected_spaces(uidoc)
    if spaces:
        return spaces
    options = [PICK_HERE] + ([PICK_LINKED] if linked_models(doc) else []) + [BY_LEVEL]
    choice = forms.CommandSwitchWindow.show(options, message="Which spaces get detectors?")
    if choice == PICK_HERE:
        return pick_spaces(uidoc)
    if choice == PICK_LINKED:
        return pick_linked_spaces(uidoc)
    if choice == BY_LEVEL:
        return _spaces_on_levels(doc)
    return []


def _detector_type(doc, kind, values, ask=False):
    """The saved detector type, or the one picked from the loaded types."""
    types = detector_types(doc)
    if not types:
        forms.alert("No detector family is loaded in this model.\n\n"
                    "Load your detector family (Fire Alarm Devices category) and try again.",
                    title=TITLE)
        return None
    key = kind + "_type"
    if not ask and values[key] in types:
        return types[values[key]]
    label = forms.SelectFromList.show(sorted(types), title="%s detector type" % kind.title(),
                                      button_name="Use this type", multiselect=False)
    if not label:
        return None
    values[key] = label
    settings.save(values)
    return types[label]


def _ask_replace(count, spaces):
    answer = forms.alert(
        "%d detector%s of this type %s already in %d of the selected spaces."
        % (count, "" if count == 1 else "s", "is" if count == 1 else "are", spaces),
        options=["Replace them", "Keep them and add the new ones"], title=TITLE)
    if not answer:
        return None
    return answer.startswith("Replace")


def run(kind):
    """Place smoke or heat detectors in the selected spaces."""
    doc, uidoc = revit.doc, revit.uidoc
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to place detectors.", title=TITLE)
        return
    values = settings.load()

    spaces = _choose_spaces(doc, uidoc)
    if not spaces:
        return
    symbol = _detector_type(doc, kind, values)
    if symbol is None:
        return
    if placement_kind(symbol) is None:
        forms.alert("'%s' cannot be placed on a ceiling.\n\nUse a face-based, ceiling-hosted "
                    "or level-based family (change it in FA Settings)." % values[kind + "_type"],
                    title=TITLE)
        return

    answers = []

    def ask_replace(count, space_count):
        answers.append(_ask_replace(count, space_count))
        return answers[-1]

    plans = place_detectors(doc, spaces, symbol, values[kind + "_spacing"], values["clearance"],
                            "Place %s Detectors" % kind.title(), ask_replace)
    if plans is None:
        return

    placed = [i for p in plans for i in p.placed]
    if placed:
        uidoc.Selection.SetElementIds(List[ElementId](placed))
    headline, details = summarize(plans, kind, replaced=bool(answers and answers[0]))
    forms.alert(headline, expanded=details, title=TITLE)


# ---------------------------------------------------------------- loops

def _loop_devices(doc, uidoc, view, least=2, message="Which devices go on the loop?"):
    """Devices selected before clicking (at least `least`), or all the
    fire alarm devices of the view, or picked now."""
    devices = revit_loop.selected_devices(uidoc)
    if len(devices) >= least:
        return devices
    choice = forms.CommandSwitchWindow.show([LOOP_ALL, LOOP_PICK], message=message)
    if choice == LOOP_ALL:
        devices = revit_loop.view_devices(doc, view)
        if not devices:
            forms.alert("No fire alarm devices are shown in this view.", title=TITLE)
        return devices
    if choice == LOOP_PICK:
        return revit_loop.pick_devices(uidoc)
    return []


KIND_DETECTION = "Detection loop: detectors, manual stations, modules... (no sirens or flashers)"
KIND_SOUNDER = "Sounder loop: sirens and flashers only"


def _loop_kind(devices, codes):
    """DETECTION or SOUNDER, and the devices for it; (None, []) cancelled."""
    choice = forms.CommandSwitchWindow.show([KIND_DETECTION, KIND_SOUNDER],
                                            message="Which loop?")
    if not choice:
        return None, []
    kind = SOUNDER if choice == KIND_SOUNDER else DETECTION
    chosen = [d for d in devices if on_loop(codes[revit_loop.id_int(d.Id)], kind)]
    if not chosen:
        forms.alert("None of these devices go on a %s loop%s." % (
            kind, " (sirens and flashers: bells, sounders, horns, strobes, beacons)"
            if kind == SOUNDER else ""), title=TITLE)
    return kind, chosen


def _loop_numbers(doc, view, devices, max_devices, kind, kept, skip, here_too=False):
    """Loop numbers for this floor: new ones, going on across the building
    (detection and sounder loops share them), or the first loop continuing
    a loop of the same kind on another floor. kept: numbers staying in this
    view; skip: ids of the devices whose addresses do not count (the ones
    being connected or addressed now); here_too: loops drawn in this view
    can be continued too. None: cancelled."""
    def elsewhere(drawn):
        found = dict((n, views - (set() if here_too else set([view.Name])))
                     for n, views in drawn.items())
        return dict((n, views) for n, views in found.items() if views)
    others = elsewhere(revit_loop.loop_views(doc))
    same_kind = elsewhere(revit_loop.loop_views(doc, kind))
    for number, (kinds, floors) in revit_address.addressed_loops(doc, skip).items():
        others.setdefault(number, set()).update(floors)
        if kind in kinds:                   # addressed, maybe without loop lines
            same_kind.setdefault(number, set()).update(floors or ["addressed"])
    taken = set(others) | set(kept)
    count = loop_count(devices, max_devices)
    new = loop_numbers(count, taken)
    if not same_kind:
        return new
    fresh = "New loop numbers: L%s" % (
        "%d" % new[0] if len(new) == 1 else "%d to L%d" % (new[0], new[-1]))
    options = [fresh] + ["Continue L%d (%s)" % (n, ", ".join(sorted(views)))
                         for n, views in sorted(same_kind.items())]
    choice = forms.CommandSwitchWindow.show(
        options, message="Loop numbers on this floor (a loop going on from another floor "
                         "keeps its number and its addresses go on):")
    if not choice:
        return None
    if choice == fresh:
        return new
    carry_on = int(choice.split()[1][1:])
    return loop_numbers(count, taken, carry_on)


def _address_tag(doc, values):
    """The tag type for the addresses: the one chosen before, or asked the
    first time; None: no tag (or none loaded)."""
    types = revit_address.tag_types(doc)
    saved = values["address_tag"]
    if saved == settings.NO_TAG or not types:
        return None
    if saved in types:
        return types[saved]
    options = sorted(types) + [settings.NO_TAG]
    choice = forms.SelectFromList.show(options, title="Tag for the addresses (FA Address)",
                                       button_name="Use this tag", multiselect=False)
    if not choice:
        return None
    values["address_tag"] = choice
    settings.save(values)
    return types.get(choice)


def draw_loop():
    """Connect the fire alarm devices of the active plan with detail
    lines, loop by loop, from the start and back."""
    doc, uidoc = revit.doc, revit.uidoc
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to draw the loop.", title=TITLE)
        return
    view = doc.ActiveView
    if not revit_loop.is_plan(view):
        forms.alert("Open the floor or ceiling plan to draw the loop in.", title=TITLE)
        return
    devices = _loop_devices(doc, uidoc, view)
    if not devices:
        return
    values = settings.load()
    chosen_symbols = settings.chosen_symbols(values)
    codes = dict((revit_loop.id_int(d.Id), revit_address.symbol_of(d, chosen_symbols))
                 for d in devices)
    kind, devices = _loop_kind(devices, codes)
    if not devices:
        return
    start = revit_loop.pick_start(uidoc)
    if start is None:
        return
    start_id = revit_loop.id_int(start.Id)
    if revit_loop.is_panel(start):          # the panel is where loops start, not a device
        devices = [d for d in devices if revit_loop.id_int(d.Id) != start_id]
    if not devices:
        forms.alert("There are no devices to connect.", title=TITLE)
        return
    counted = any(revit_loop.id_int(d.Id) == start_id for d in devices)

    old = revit_loop.existing_loop_lines(doc, view, kind)
    other_kind = revit_loop.existing_loop_lines(doc, view, SOUNDER if kind == DETECTION else DETECTION)
    replace = []
    if old:
        count = sum(len(ids) for ids in old.values())
        numbers = ", ".join("L%d" % n for n in sorted(old))
        answer = forms.alert(
            "This view already has %d %s loop line%s (%s)." % (
                count, kind, "" if count == 1 else "s", numbers),
            options=["Replace them", "Keep them and add new loops"], title=TITLE)
        if not answer:
            return
        if answer.startswith("Replace"):
            replace = [i for ids in old.values() for i in ids]

    # the addresses of this floor's devices are redone after the loops
    shown = set(revit_loop.id_int(d.Id) for d in revit_loop.view_devices(doc, view))
    numbers = _loop_numbers(doc, view, len(devices), values["loop_devices"], kind,
                            kept=list(other_kind) + ([] if replace else list(old)),
                            skip=shown | set(revit_loop.id_int(d.Id) for d in devices))
    if numbers is None:
        return
    results = revit_loop.draw_loops(doc, view, devices, start, values["loop_devices"],
                                    values["loop_gap"], numbers, replace,
                                    square=values["loop_square"], kind=kind)
    headline, details = summarize_loops(
        view.Name, results, revit_loop.label(start), counted, replaced=len(replace), kind=kind,
        notes=[u"Give the devices their addresses (FA Address and tags) with Address Devices."])
    forms.alert(headline, expanded=details, title=TITLE)


# ---------------------------------------------------------------- addresses

ADDRESS_VIEW = "Loops drawn in this plan"
ADDRESS_ALL = "Loops drawn in all plans"
ADDRESS_FREE = "Devices without a loop line"


def _address_notes(addresser, tag_loaded):
    notes = []
    if addresser.parameter_added:
        notes.append(u"The FA Address parameter was added to Fire Alarm Devices.")
    if addresser.tag_type is not None:
        notes.append(u"Address tags placed: %d%s." % (
            addresser.tagged, " (%d device%s had one already, kept)" % (
                addresser.already_tagged, "" if addresser.already_tagged == 1 else "s")
            if addresser.already_tagged else ""))
    elif not tag_loaded:
        notes.append(u"No fire alarm device tag is loaded: make one with a label showing "
                     u"FA Address (see the README) to tag the addresses.")
    else:
        notes.append(u"No address tags (choose one in FA Settings > Address tag).")
    for problem in sorted(set(addresser.problems)):
        notes.append(u"    %s" % problem)
    return notes


def _ids(devices):
    """'id 12, 15, 40...' of the devices, for Select by ID."""
    ids = sorted(set(revit_loop.id_int(d.Id) for d in devices))
    return u", ".join(u"%d" % i for i in ids[:12]) + (u"..." if len(ids) > 12 else u"")


def _plural(count, word):
    return u"%d %s%s" % (count, word, "" if count == 1 else "s")


def _drawn_loops(doc, view, values):
    """The loops drawn in `view` (None: in every plan), in route order ->
    (loops for Addresser.run, ids of the devices shown in their plans,
    warnings, notes, devices that need a look)."""
    panel = revit_riser.main_panel(revit_riser.devices_and_panels(doc)[1])
    drawn = revit_routes.read_loops(doc, values["loop_gap"], panel, view)
    warnings, notes, look = [], [], []
    for loop in drawn:
        where = u"L%d%s in %s" % (loop.number, " sounder" if loop.kind == SOUNDER else "",
                                  loop.view.Name)
        counted = [revit_loop.id_int(d.Id) for d in loop.devices[:1]]
        if loop.start is not None and counted == [revit_loop.id_int(loop.start.Id)]:
            notes.append(u"%s starts at a device (no line end at a panel): counted from %s "
                         u"(id %d)." % (where, revit_loop.label(loop.start),
                                        revit_loop.id_int(loop.start.Id)))
        if not loop.devices:
            warnings.append(u"%s: its lines reach no fire alarm device." % where)
        elif loop.loose:
            look.extend(loop.loose)
            warnings.append(u"%s: %s at its lines not on one line from the start (lines not "
                            u"joined?), not addressed: ids %s." % (
                                where, _plural(len(loop.loose), "device"), _ids(loop.loose)))
        elif not loop.closed:
            warnings.append(u"%s: its lines do not come back to the start (addressed as far "
                            u"as they go)." % where)
    parts = {}
    for loop in drawn:
        if loop.devices:
            parts.setdefault((loop.number, loop.kind), []).append(loop)
    elevation = revit_routes.panel_elevation(doc, panel)
    loops = [(number, kind, [(p.view, p.devices)
                             for p in revit_routes.counting_order(found, elevation)])
             for (number, kind), found in sorted(parts.items())]
    shown = set()
    for plan in dict((revit_loop.id_int(l.view.Id), l.view) for l in drawn).values():
        shown.update(revit_loop.id_int(d.Id) for d in revit_loop.view_devices(doc, plan))
    return loops, shown, warnings, notes, look


def _free_loops(doc, uidoc, view, values):
    """Devices without loop lines, in the order Draw FA Loop would connect
    them -> (loops for Addresser.run, a note on the start); (None, None)
    when cancelled."""
    devices = _loop_devices(doc, uidoc, view, least=1, message="Which devices get addresses?")
    if not devices:
        return None, None
    chosen_symbols = settings.chosen_symbols(values)
    codes = dict((revit_loop.id_int(d.Id), revit_address.symbol_of(d, chosen_symbols))
                 for d in devices)
    kind, devices = _loop_kind(devices, codes)
    if not devices:
        return None, None
    start = revit_loop.pick_start(uidoc)
    if start is None:
        return None, None
    start_id = revit_loop.id_int(start.Id)
    if revit_loop.is_panel(start):
        devices = [d for d in devices if revit_loop.id_int(d.Id) != start_id]
    if not devices:
        forms.alert("There are no devices to address.", title=TITLE)
        return None, None
    counted = any(revit_loop.id_int(d.Id) == start_id for d in devices)
    numbers = _loop_numbers(doc, view, len(devices), values["loop_devices"], kind,
                            kept=list(revit_loop.existing_loop_lines(doc, view)),
                            skip=set(revit_loop.id_int(d.Id) for d in devices), here_too=True)
    if numbers is None:
        return None, None
    routes = revit_loop.Plan(view, devices, start, values["loop_devices"], values["loop_gap"],
                             values["loop_square"]).routes()
    numbers = list(numbers) + loop_numbers(len(routes) - len(numbers), numbers)
    loops = [(number, kind, [(view, route)]) for number, route in zip(numbers, routes)]
    note = u"Start: %s%s; the devices are counted in the order Draw FA Loop would " \
           u"connect them." % (revit_loop.label(start), " (device 1)" if counted else "")
    return loops, note


def address_devices():
    """Write FA Address on the fire alarm devices, loop by loop in route
    order (L1/SD-01...), and tag them."""
    doc, uidoc = revit.doc, revit.uidoc
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to address the devices.", title=TITLE)
        return
    view = doc.ActiveView
    plan = revit_loop.is_plan(view)
    owners = set(owner for _, owner, _, _ in revit_loop.loop_curves(doc))
    options = ([ADDRESS_VIEW] if plan and revit_loop.id_int(view.Id) in owners else []) + \
        ([ADDRESS_ALL] if owners else []) + ([ADDRESS_FREE] if plan else [])
    if not options:
        forms.alert("No loop lines are drawn in this model.\n\nDraw the loops with Draw FA "
                    "Loop, or open a floor or ceiling plan to address its devices without "
                    "loop lines.", title=TITLE)
        return
    choice = options[0] if len(options) == 1 else forms.CommandSwitchWindow.show(
        options, message="Which devices get their addresses? (A loop over several floors "
                         "counts on, the floor furthest from the panel first.)")
    if not choice:
        return
    values = settings.load()
    look, notes = [], []
    if choice == ADDRESS_FREE:
        loops, note = _free_loops(doc, uidoc, view, values)
        if loops is None:
            return
        skip, keep_ranges, warnings, notes = (), True, [], [note]
    else:
        loops, skip, warnings, notes, look = _drawn_loops(
            doc, view if choice == ADDRESS_VIEW else None, values)
        keep_ranges = choice == ADDRESS_VIEW    # all plans: every loop counts afresh from 01
        if not loops:
            forms.alert("The loop lines reach no fire alarm devices.",
                        expanded="\n".join(warnings), title=TITLE)
            return
    tag_type = _address_tag(doc, values)
    addresser = revit_address.Addresser(doc, settings.chosen_symbols(values), tag_type)
    addresser.run(loops, skip, keep_ranges)
    if addresser.twice:
        look.extend(addresser.twice)
        warnings.append(u"%s on the routes of two loops, addressed on the first: ids %s." % (
            _plural(len(addresser.twice), "device"), _ids(addresser.twice)))
    if addresser.clashes:
        look.extend(addresser.clashes)
        warnings.append(u"%s already had an address given now (left from before?): ids %s." % (
            _plural(len(addresser.clashes), "other device"), _ids(addresser.clashes)))
    if look:
        uidoc.Selection.SetElementIds(List[ElementId]([d.Id for d in look]))
        warnings.append(u"The devices that need a look are selected.")
    notes += _address_notes(addresser, bool(revit_address.tag_types(doc)))
    headline, details = summarize_addresses(addresser.loops, warnings, notes)
    forms.alert(headline, expanded=details, title=TITLE)


# ---------------------------------------------------------------- riser

def draw_riser():
    """Draw the fire alarm riser diagram from the loops drawn in the plans."""
    doc = revit.doc
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to draw the riser.", title=TITLE)
        return
    values = settings.load()
    view, run = revit_riser.generate(doc, settings.chosen_symbols(values), values["loop_gap"],
                                     values["loop_devices"])
    if view is not None:
        revit.uidoc.ActiveView = view
    headline, details = summarize_riser(run, lambda code: symbol(code).description)
    forms.alert(headline, expanded=details, title=TITLE)


AUTOMATIC = u"Automatic: %s"


def _edit_riser_symbols(doc, values):
    """Pick a fire alarm type placed in the model, then its riser symbol."""
    names = revit_riser.type_names(doc)
    if not names:
        forms.alert("No fire alarm devices are placed in this model.", title=TITLE)
        return
    while True:
        chosen = settings.chosen_symbols(values)
        items = [u"%s  ->  %s%s" % (name, symbol(resolve(name, None, chosen.get(name))).description,
                                   "" if name in chosen else "  (automatic)") for name in names]
        pick = forms.SelectFromList.show(items, title="Riser symbols: pick a type to change",
                                         button_name="Change symbol", multiselect=False)
        if not pick:
            return
        name = names[items.index(pick)]
        options = [AUTOMATIC % symbol(guess(name)).description] + [s.description for s in SYMBOLS]
        choice = forms.SelectFromList.show(options, title=name, button_name="Use this symbol",
                                           multiselect=False)
        if not choice:
            continue
        code = None if choice == options[0] else SYMBOLS[options.index(choice) - 1].code
        settings.choose_symbol(values, name, code)
        settings.save(values)


# ---------------------------------------------------------------- settings

_SETTINGS = [
    ("smoke_spacing", "Smoke detector spacing", "m"),
    ("heat_spacing", "Heat detector spacing", "m"),
    ("clearance", "Min distance from walls", "m"),
    ("smoke_type", "Smoke detector type", ""),
    ("heat_type", "Heat detector type", ""),
    ("loop_devices", "Devices per loop", ""),
    ("loop_square", "Loop lines", ""),
    ("loop_gap", "Loop line gap at devices", "mm"),
    ("riser_symbols", "Riser symbols", ""),
    ("address_tag", "Address tag", ""),
]

_PROMPTS = {
    "smoke_spacing": "Max distance between smoke detectors (m).\n"
                     "Detectors are at most half of it from the walls.",
    "heat_spacing": "Max distance between heat detectors (m).\n"
                    "Detectors are at most half of it from the walls.",
    "clearance": "Min distance from walls and columns (m).\n"
                 "Relaxed only in spaces too narrow for it.",
    "loop_devices": "Most devices on one fire alarm loop.\n"
                    "More devices are split into several loops.",
    "loop_gap": "Gap between a loop line and the centre of a device, at least\n"
                "(mm on the printed sheet). Lines also stop at the edge of the device.",
}


def _number(value):
    return ("%.2f" % value).rstrip("0").rstrip(".")


def edit_settings():
    doc = revit.doc
    while True:
        values = settings.load()
        options = []
        for key, name, unit in _SETTINGS:
            value = values[key]
            if key == "loop_square":
                value = "square (right angles)" if value else "straight device to device"
            elif key == "address_tag":
                value = value or "asked on first use"
            elif key == "riser_symbols":
                count = len(settings.chosen_symbols(values))
                value = "%d type%s set by you, the rest automatic" % (count, "" if count == 1 else "s")
            elif unit:
                value = "%s %s" % (_number(value), unit)
            options.append(u"%s: %s" % (name, value or "asked on first use"))
        choice = forms.CommandSwitchWindow.show(options, message="Click a setting to change it:")
        if not choice:
            return
        key = _SETTINGS[options.index(choice)][0]
        if key == "loop_square":                # a switch: square <-> straight
            values[key] = not values[key]
            settings.save(values)
            continue
        if key == "address_tag":
            if doc is None or doc.IsFamilyDocument:
                forms.alert("Open the project model to pick the address tag.", title=TITLE)
                continue
            types = revit_address.tag_types(doc)
            if not types:
                forms.alert("No fire alarm device tag is loaded in this model.\n\nMake one "
                            "with a label showing FA Address (see the README) and load it.",
                            title=TITLE)
                continue
            choice = forms.SelectFromList.show(sorted(types) + [settings.NO_TAG],
                                               title="Tag for the addresses (FA Address)",
                                               button_name="Use this tag", multiselect=False)
            if choice:
                values[key] = choice
                settings.save(values)
            continue
        if key == "riser_symbols":
            if doc is None or doc.IsFamilyDocument:
                forms.alert("Open the project model to set the riser symbols.", title=TITLE)
            else:
                _edit_riser_symbols(doc, values)
            continue
        if key.endswith("_type"):
            if doc is None or doc.IsFamilyDocument:
                forms.alert("Open the project model to pick the detector type.", title=TITLE)
                continue
            _detector_type(doc, key[:-len("_type")], values, ask=True)
            continue
        text = forms.ask_for_string(default=_number(values[key]), prompt=_PROMPTS[key],
                                    title="%s Settings" % TITLE)
        if text is None:
            continue
        try:
            value = float(text.replace(",", ".").replace("m", "").strip())
        except ValueError:
            forms.alert("'%s' is not a number." % text, title=TITLE)
            continue
        if value < 0 or (value == 0 and key not in ("clearance", "loop_gap")):
            forms.alert("Enter a positive number.", title=TITLE)
            continue
        if key == "loop_devices":
            value = max(1, int(round(value)))
        values[key] = value
        settings.save(values)
