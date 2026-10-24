# -*- coding: utf-8 -*-
"""Entry point of the Mirror Tower buttons: Electrical (Circuits panel),
Mechanical, Plumbing and Firefighting."""
import time

from Autodesk.Revit.DB import CurveElement, ElementId, Grid, TransactionGroup
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from pyrevit import forms, revit, script
from System.Collections.Generic import List

from copycircuits.placement import Placement
from mepmirror import electrical, revit_mep, rules
from mepmirror import window_ui as wui
from mirrortower import geometry, revit_mirror

SECTIONS = {rules.ELECTRICAL: "ElectricalMirrorTower",       # the earlier electrical tool's
            rules.MECHANICAL: "MepMirrorTowerMechanical",
            rules.PLUMBING: "MepMirrorTowerPlumbing",
            rules.FIRE: "MepMirrorTowerFirefighting"}
STRETCH = 0.3 / 0.3048      # ft: the two pairs of points must be this near the same apart


class _Config(object):
    def __init__(self, domain):
        self.section = SECTIONS[domain]

    def get(self, name, default):
        try:
            value = script.get_config(self.section).get_option(name, default)
            return value if value is not None else default
        except Exception:
            return default

    def keep(self, values):
        try:
            cfg = script.get_config(self.section)
            for k, v in values.items():
                setattr(cfg, k, v)
            script.save_config()
        except Exception:
            pass


def _timed(result, name, start):
    result.seconds[name] = result.seconds.get(name, 0.0) + time.time() - start


def _placement_text(placement):
    return u"%.9f|%d|%.9f|%.9f" % (placement.angle, 1 if placement.mirrored else 0,
                                   placement.tx, placement.ty)


def _placement_from(text):
    try:
        a, m, x, y = (text or u"").split(u"|")
        return Placement(float(a), m == u"1", float(x), float(y))
    except Exception:
        return None


def _describe(placement, mode):
    shift = (placement.tx ** 2 + placement.ty ** 2) ** 0.5 * 0.3048
    if mode == wui.BY_POINTS:
        return u"mirrored and moved (from the 2 + 2 points clicked)"
    return u"mirrored about the line picked (%.1f m from the origin)" % shift


class _LinesOnly(ISelectionFilter):
    __namespace__ = "MepMirrorTower"       # needed by the CPython engine

    def AllowElement(self, element):
        return isinstance(element, (Grid, CurveElement))

    def AllowReference(self, reference, point):
        return False


def _point(uidoc, prompt):
    p = uidoc.Selection.PickPoint(prompt)
    return p.X, p.Y


def pick_placement(doc, uidoc, mode, title):
    """The Placement taking Tower 1 to Tower 2 (mirrored), or None."""
    try:
        if mode == wui.BY_POINTS:
            forms.alert("Click 2 points of Tower 1 that are easy to find again, like two "
                        "corners of the core. Then click the SAME 2 points in Tower 2 "
                        "(its mirrored corners), in the same order.\n\nSnaps to the "
                        "linked model work.", title=title)
            s1 = _point(uidoc, "Tower 1: first point (e.g. a core corner)")
            s2 = _point(uidoc, "Tower 1: second point (e.g. the core corner across)")
            t1 = _point(uidoc, "Tower 2: the same first point")
            t2 = _point(uidoc, "Tower 2: the same second point")
            placement, stretch = geometry.from_points(s1, s2, t1, t2)
            if placement is None:
                forms.alert("The two Tower 1 points are the same point. Pick again.",
                            title=title)
                return None
            if abs(stretch) > STRETCH:
                forms.alert("The Tower 2 points are %.2f m %s apart than the Tower 1 points, "
                            "so they are not the same two points. Pick again."
                            % (abs(stretch) * 0.3048, "further" if stretch > 0 else "nearer"),
                            title=title)
                return None
            return placement
        if mode == wui.LINE_HERE:
            ref = uidoc.Selection.PickObject(ObjectType.Element, _LinesOnly(),
                                             "Pick the grid or line between the towers")
            ends = revit_mirror.line_ends(doc.GetElement(ref.ElementId))
        else:
            ref = uidoc.Selection.PickObject(ObjectType.LinkedElement,
                                             "Pick the grid or line between the towers "
                                             "in the linked model")
            link = doc.GetElement(ref.ElementId)
            linked = link.GetLinkDocument().GetElement(ref.LinkedElementId)
            ends = revit_mirror.line_ends(linked, link.GetTotalTransform())
    except OperationCanceledException:
        return None
    placement = geometry.mirror_placement(*ends) if ends is not None else None
    if placement is None:
        forms.alert("That is not a straight line (a grid or line with two ends). Pick "
                    "another.", title=title)
    return placement


def _electrical(doc, model, keys, sides, results, placement, tolerance, state, step, tags,
                inside=None):
    """Boards named for Tower 2 (B1 -> B2) on every floor, then Tower 1's
    circuits made again there (after all the boards, as a board may feed
    another floor)."""
    swap = state.get("swap") or (u"", u"")
    by_name = revit_mirror.boards_by_name(doc)
    for key, result in zip(keys, results):
        step(u"Board names, %s..." % result.floor, 0)
        start = time.time()
        electrical.name_boards(doc, model, sides[key], result, swap, by_name)
        _timed(result, "board names", start)
    if not state.get("circuits", True):
        return
    by_name = revit_mirror.boards_by_name(doc)       # with the boards just made
    for key, result in zip(keys, results):
        step(u"Circuits and wires, %s..." % result.floor, len(sides[key].tower1))
        start = time.time()
        electrical.make_circuits(doc, model, key, sides[key], result, placement, tolerance,
                                 swap, by_name, state.get("wires", True), tags, inside)
        if result.circuits is not None:
            result.seconds.update(getattr(result.circuits, "seconds", {}))
        _timed(result, "circuits, wires and their tags (all)", start)


def _work(model, keys, sides, state):
    """How much each step weighs on the progress bar: the elements it
    mirrors (a floor with none still counts 1), the circuits after."""
    total = sum(len(sides[k].missing) + 1 for k in keys)
    if model.domain == rules.ELECTRICAL:
        total += len(keys)
        if state.get("circuits", True):
            total += sum(len(sides[k].tower1) + 1 for k in keys)
    return total


def _mirror(doc, title, model, keys, sides, placement, about, tolerance, join, state,
            progress=None):
    floors = dict((f[0], f) for f in model.floors)
    results = []
    total = _work(model, keys, sides, state)
    done = [0, 0]                   # work done, weight of the step running

    def step(text, weight):
        done[0] += done[1]
        done[1] = weight + 1
        if progress is not None:
            progress(done[0], total, text)

    def inside(share, text):
        """Part of the step running done (share 0 to 1)."""
        if progress is not None:
            progress(done[0] + share * done[1], total, text)
    tags = revit_mep.Tags(doc)
    group = TransactionGroup(doc, title)
    group.Start()
    try:
        for key in keys:
            step(u"Mirroring %s: %d elements..." % (model.names.get(key, u""),
                                                   len(sides[key].missing)),
                 len(sides[key].missing))
            start = time.time()
            results.append(revit_mep.mirror_floor(doc, model, floors[key], sides[key], placement,
                                                  about, tolerance, join, tags, inside))
            _timed(results[-1], "mirroring elements and tags", start)
        if model.domain == rules.ELECTRICAL:
            _electrical(doc, model, keys, sides, results, placement, tolerance, state, step,
                        tags, inside)
        step(u"Saving...", 0)
        group.Assimilate()
    except Exception:
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        raise
    return results


def run(domain):
    doc, uidoc = revit.doc, revit.uidoc
    title = wui.TEXT[domain][0]
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to mirror a tower.", title=title)
        return
    start = time.time()
    config = _Config(domain)
    boxes = revit_mirror.scope_boxes(doc)
    if not boxes:
        forms.alert("The model has no scope boxes. Draw one around Tower 1 first.", title=title)
        return
    by_name = dict(boxes)
    outlines = {}

    def outline(name):
        if name not in outlines:
            box = by_name.get(name)
            outlines[name] = revit_mirror.outline(box) if box is not None else []
        return outlines[name]

    mode = config.get("mode", wui.BY_POINTS)
    placement = _placement_from(config.get("placement", u""))
    unticked = set(n for n in (config.get("unticked", u"") or u"").split(u"|") if n)
    try:
        join = config.get("join", True) not in (False, u"False", u"false", 0, u"0")
    except Exception:
        join = True
    try:
        tolerance_mm = float(config.get("tolerance_mm", 50.0))
    except Exception:
        tolerance_mm = 50.0
    def flag(name):
        return config.get(name, True) not in (False, u"False", u"false", 0, u"0")

    state = {
        "box": config.get("box", None) or config.get("scope_box", None), "mode": mode,
        "placement": placement,
        "placement_text": (u"last used: " + _describe(placement, mode)) if placement else u"",
        "unticked": unticked, "read_with": set(unticked), "tolerance_mm": tolerance_mm,
        "join": join and domain != rules.ELECTRICAL, "model": None,
        "swap": (config.get("swap_from", u"B1") or u"", config.get("swap_to", u"B2") or u""),
        "circuits": flag("circuits"), "wires": flag("wires"), "ticked": None, "results": [],
        "new_ids": [],
    }

    def select(ids):
        found = List[ElementId]()
        for i in ids:
            if doc.GetElement(i) is not None:
                found.Add(i)
        uidoc.Selection.SetElementIds(found)
        return found.Count

    def label_of(key):
        e = revit_mirror._get(doc, key)
        if e is None:
            return u"(deleted)"
        return revit_mep._label(e, None)

    callbacks = {
        "domain": domain,
        "boxes": [name for name, _ in boxes],
        "categories": [name for name, _ in rules.CATEGORIES[domain]
                       if revit_mep._bic(name) is not None],
        "outline": outline,
        "read": lambda unticked: revit_mep.read_model(doc, domain, unticked),
        "in_links": lambda unticked: [] if domain == rules.MECHANICAL else
        revit_mep.in_links(doc, domain, unticked),
        "after": lambda results: revit_mep.add_new(doc, state["model"], results),
        "mirror": lambda keys, sides, placement, about, tolerance, join, progress=None: _mirror(
            doc, title, state["model"], keys, sides, placement, about, tolerance,
            join and domain != rules.ELECTRICAL, state, progress),
        "label_of": label_of,
        "key_of": lambda element_id: revit_mep.id_int(element_id),
        "select": select,
        "keep": config.keep,
        "model_text": doc.Title,
    }
    if domain == rules.ELECTRICAL:
        names = {}

        def adjust(sides):
            if not names:
                names.update(electrical.board_names(doc))
            electrical.pair_by_name(sides, names, state.get("swap"))

        def after(results):
            revit_mep.add_new(doc, state["model"], results)
            names.clear()                   # boards just made or renamed
        callbacks.update(adjust=adjust, after=after)
    state["open_s"] = time.time() - start
    while True:
        win = wui.MirrorWindow(callbacks, state)
        if win.show() != "pick":
            break
        found = pick_placement(doc, uidoc, state["mode"], title)
        if found is not None:
            state["placement"] = found
            state["placement_text"] = _describe(found, state["mode"])
            config.keep({"placement": _placement_text(found), "mode": state["mode"]})
