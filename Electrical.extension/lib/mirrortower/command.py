# -*- coding: utf-8 -*-
"""Entry point for the Mirror Tower button."""
from Autodesk.Revit.DB import CurveElement, ElementId, Grid, TransactionGroup
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from pyrevit import forms, revit, script
from System.Collections.Generic import List

from copycircuits import revit_copy as rc
from copycircuits import settings as copy_settings
from copycircuits.command import _show
from mirrortower import geometry, revit_mirror

TITLE = "Mirror Tower"
MM_PER_FOOT = 304.8
SECTION = "ElectricalMirrorTower"

BY_POINTS = "Click 2 points in Tower 1, then the same 2 points in Tower 2"
LINE_HERE = "Plain mirror about a grid or line in this model"
LINE_LINK = "Plain mirror about a grid or line in a linked model"
STRETCH = 0.3 / 0.3048      # ft: the two pairs of points must be this near the same apart


def _config():
    return script.get_config(SECTION)


def _remembered(name, default):
    try:
        value = _config().get_option(name, default)
        return value if value is not None else default
    except Exception:
        return default


def _remember(values):
    try:
        cfg = _config()
        for k, v in values.items():
            setattr(cfg, k, v)
        script.save_config()
    except Exception:
        pass


class _LinesOnly(ISelectionFilter):
    __namespace__ = "ElectricalMirrorTower"       # needed by the CPython engine

    def AllowElement(self, element):
        return isinstance(element, (Grid, CurveElement))

    def AllowReference(self, reference, point):
        return False


def _pick_box(doc, title, last):
    boxes = revit_mirror.scope_boxes(doc)
    if not boxes:
        forms.alert("The model has no scope boxes. Draw one around Tower 1 first.", title=TITLE)
        return None, None
    names = [n for n, _ in boxes]
    ordered = ([last] if last in names else []) + [n for n in names if n != last]
    picked = forms.SelectFromList.show(ordered, title=title, button_name="Next",
                                       multiselect=False)
    if not picked:
        return None, None
    return picked, dict(boxes)[picked]


def _point(uidoc, prompt):
    p = uidoc.Selection.PickPoint(prompt)
    return p.X, p.Y


def _pick_placement(doc, uidoc):
    """The Placement taking Tower 1 to Tower 2 (mirrored), or None."""
    how = forms.CommandSwitchWindow.show(
        [BY_POINTS, LINE_HERE, LINE_LINK],
        message="Where is Tower 2? (towers that sit diagonally: click points)")
    if not how:
        return None
    try:
        if how == BY_POINTS:
            forms.alert("Click 2 points of Tower 1 that are easy to find again, like two "
                        "corners of the core. Then click the SAME 2 points in Tower 2 "
                        "(its mirrored corners), in the same order.\n\nSnaps to the "
                        "linked model work.", title=TITLE)
            s1 = _point(uidoc, "Tower 1: first point (e.g. a core corner)")
            s2 = _point(uidoc, "Tower 1: second point (e.g. the core corner across)")
            t1 = _point(uidoc, "Tower 2: the same first point")
            t2 = _point(uidoc, "Tower 2: the same second point")
            placement, stretch = geometry.from_points(s1, s2, t1, t2)
            if placement is None:
                forms.alert("The two Tower 1 points are the same point. Run Mirror Tower "
                            "again.", title=TITLE)
                return None
            if abs(stretch) > STRETCH:
                forms.alert("The Tower 2 points are %.2f m %s apart than the Tower 1 points, "
                            "so they are not the same two points. Run Mirror Tower again."
                            % (abs(stretch) * 0.3048, "further" if stretch > 0 else "nearer"),
                            title=TITLE)
                return None
            return placement
        if how == LINE_HERE:
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
        forms.alert("That is not a straight line (a grid or line with two ends). "
                    "Run Mirror Tower again and pick another.", title=TITLE)
    return placement


def _pick_levels(doc, view):
    all_levels = rc.levels(doc)
    names = [l.Name for l in all_levels]
    picked = forms.SelectFromList.show(
        names, title="%s: mirror Tower 1 on which floors?" % TITLE,
        button_name="Next", multiselect=True)
    if not picked:
        return None
    return [l for l in all_levels if l.Name in picked]


def _pick_swap():
    old = forms.ask_for_string(
        default=_remembered("swap_from", "B1"),
        prompt="Text in Tower 1's board names that changes for Tower 2 "
               "(DB-B1-L4-01 -> DB-B2-L4-01: B1). Leave empty to keep the names:",
        title=TITLE)
    if old is None:
        return None
    old = old.strip()
    if not old:
        return (u"", u"")
    new = forms.ask_for_string(
        default=_remembered("swap_to", "B2"),
        prompt="Replace %s in Tower 2's board names with:" % old, title=TITLE)
    if new is None:
        return None
    return (old, new.strip())


def _count(n, word, plural=None):
    return "%d %s" % (n, word if n == 1 else (plural or word + "s"))


def _show_mirror(output, m):
    output.print_md("## %s: elements" % m.floor)
    if not m.tower1:
        output.print_md("No electrical elements of Tower 1 on this floor.")
        return
    text = "%s of Tower 1: %d already in Tower 2, %d mirrored now" % (
        _count(m.tower1, "element"), m.already, len(m.mirrored))
    if m.refused or m.no_wall:
        text += ", %d not mirrored" % (len(m.refused) + len(m.no_wall))
    output.print_md(text + ".")
    if m.mirrored:
        output.print_md(output.linkify(m.mirrored, "Select the %d new elements"
                                       % len(m.mirrored)))
    if m.rehosted:
        output.print_md("%s on walls placed again on Tower 2's walls (%d wall faces read "
                        "there)." % (_count(m.rehosted, "element"), m.wall_faces))
    if m.moved_off:
        output.print_md("%s mirrored but kept off their Tower 2 spot by Revit (still on "
                        "their Tower 1 host's plane): removed, and placed again on Tower 2's "
                        "walls where one is found." % _count(m.moved_off, "copy", "copies"))
    if m.no_wall:
        output.print_md("**No wall at their Tower 2 spot** (within 300 mm, facing the same "
                        "way): %s, not placed. %d wall faces read there." % (
                            output.linkify(m.no_wall, "select them in Tower 1"),
                            m.wall_faces))
    if m.why:
        output.print_table(
            table_data=[[label, why, n] for (label, why), n in sorted(m.why.items())],
            columns=["Family : type", "Not placed because", "Count"])
    if m.on_line:
        output.print_md("%s whose mirrored spot is themselves (on the mirror line), shared "
                        "by both towers, not mirrored."
                        % _count(m.on_line, "element"))
    if m.refused:
        output.print_md("**Not mirrored** (Revit refused): %s. %s" % (
                            output.linkify(m.refused, "select them in Tower 1"),
                            "; ".join(m.errors[:3])))
    for old, new in m.renamed:
        output.print_md("- Board %s: Tower 2's copy named **%s**" % (old, new))
    for old, new in m.by_name:
        output.print_md("- Board %s: Tower 2 has it already, **%s**" % (old, new))
    for old in m.not_renamed:
        output.print_md("- Board **%s**: the swap text is not in its name (or the new name "
                        "is taken): check its name by hand." % old)


def run():
    doc, uidoc = revit.doc, revit.uidoc
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a project model to mirror a tower.", title=TITLE)
        return
    box_name, box = _pick_box(doc, "%s: which scope box is Tower 1?" % TITLE,
                              _remembered("scope_box", None))
    if box is None:
        return
    box_outline = revit_mirror.outline(box)
    if len(box_outline) < 3:
        forms.alert("Could not read the outline of scope box %s." % box_name, title=TITLE)
        return
    placement = _pick_placement(doc, uidoc)
    if placement is None:
        return
    values = copy_settings.load()
    tolerance = values["tolerance"] / MM_PER_FOOT
    if geometry.inside(box_outline, *placement.apply(*geometry.centre(box_outline))):
        forms.alert("That puts Tower 2 on top of Tower 1 (inside scope box %s). Run Mirror "
                    "Tower again: the points or line should take Tower 1 to the other tower."
                    % box_name, title=TITLE)
        return
    targets = _pick_levels(doc, doc.ActiveView)
    if not targets:
        return
    swap = _pick_swap()
    if swap is None:
        return
    _remember({"scope_box": box_name, "swap_from": swap[0] or "", "swap_to": swap[1] or ""})
    all_levels = rc.levels(doc)

    mirrored, circuits = [], []
    group = TransactionGroup(doc, TITLE)
    group.Start()
    try:
        sides = [revit_mirror.split(doc, level, all_levels, box_outline, placement,
                                    tolerance) for level in targets]
        if not any(s.tower1 for s in sides):
            group.RollBack()
            forms.alert("No electrical elements found in scope box %s on the floors "
                        "picked." % box_name, title=TITLE)
            return
        by_name = revit_mirror.boards_by_name(doc)
        for side in sides:
            mirrored.append(revit_mirror.mirror_floor(doc, side, placement,
                                                      geometry.centre(box_outline),
                                                      tolerance, swap, by_name))
        by_name = revit_mirror.boards_by_name(doc)       # with the boards just made
        for side in sides:
            if side.tower1:
                circuits.append(revit_mirror.circuit_floor(doc, side, placement, tolerance,
                                                           swap, by_name, values["wires"]))
        group.Assimilate()
    except Exception:
        if group.HasStarted() and not group.HasEnded():
            group.RollBack()
        raise

    new = [i for m in mirrored for i in m.mirrored]
    if new:
        uidoc.Selection.SetElementIds(List[ElementId](new))
    output = script.get_output()
    output.set_title(TITLE)
    output.print_md("# Tower 1 (%s) mirrored" % box_name)
    output.print_md("Elements in scope box %s, mirrored and moved to Tower 2; a copy "
                    "already in Tower 2 is the same family type at the mirrored spot "
                    "(within %s mm) or, for a board, named with %s." % (
                        box_name, ("%.1f" % values["tolerance"]).rstrip("0").rstrip("."),
                        ("%s -> %s" % swap) if swap[0] else "the same name"))
    for m in mirrored:
        _show_mirror(output, m)
    for result, source in circuits:
        output.print_md("---")
        _show(output, result, source)
        if result.onto_boards:
            output.print_md("%s already in Tower 2 but on no board, now put on their board: "
                            "%s" % (_count(len(result.onto_boards), "circuit"),
                                    output.linkify(result.onto_boards, "select them")))
        for label, error in result.onto_failed:
            output.print_md("- Circuit copying %s is on no board, and Revit refused to put it "
                            "on its board: %s" % (label, error))
    output.print_md("*The new elements are selected in Revit. Undo once to take the whole "
                    "run back. Run Circuit Description for Tower 2's room names, and check "
                    "the circuit numbers in the panel schedules.*")
