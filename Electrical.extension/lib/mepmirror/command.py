# -*- coding: utf-8 -*-
"""Entry point of the Mirror Tower (Mechanical) and (Plumbing) buttons."""
import time

from Autodesk.Revit.DB import CurveElement, ElementId, Grid, TransactionGroup
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from pyrevit import forms, revit, script
from System.Collections.Generic import List

from copycircuits.placement import Placement
from mepmirror import revit_mep, rules
from mepmirror import window_ui as wui
from mirrortower import geometry, revit_mirror

SECTIONS = {rules.MECHANICAL: "MepMirrorTowerMechanical",
            rules.PLUMBING: "MepMirrorTowerPlumbing"}
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


def _mirror(doc, title, model, keys, sides, placement, about, tolerance, join):
    floors = dict((f[0], f) for f in model.floors)
    results = []
    group = TransactionGroup(doc, title)
    group.Start()
    try:
        for key in keys:
            results.append(revit_mep.mirror_floor(doc, model, floors[key], sides[key], placement,
                                                  about, tolerance, join))
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
    state = {
        "box": config.get("box", None), "mode": mode, "placement": placement,
        "placement_text": (u"last used: " + _describe(placement, mode)) if placement else u"",
        "unticked": unticked, "read_with": set(unticked), "tolerance_mm": tolerance_mm,
        "join": join, "model": None, "ticked": None, "results": [], "new_ids": [],
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
        "in_links": lambda unticked: revit_mep.in_links(doc, domain, unticked),
        "mirror": lambda keys, sides, placement, about, tolerance, join: _mirror(
            doc, title, state["model"], keys, sides, placement, about, tolerance, join),
        "label_of": label_of,
        "key_of": lambda element_id: revit_mep.id_int(element_id),
        "select": select,
        "keep": config.keep,
        "model_text": doc.Title,
    }
    state["open_s"] = time.time() - start
    while True:
        win = wui.MirrorWindow(callbacks, state)
        if win.show() != "pick":
            break
        found = pick_placement(doc, uidoc, state["mode"], title)
        if found is not None:
            state["placement"] = found
            state["placement_text"] = _describe(found, state["mode"])
            state["ticked"] = None
            config.keep({"placement": _placement_text(found), "mode": state["mode"]})
