# -*- coding: utf-8 -*-
"""Revit side of Loop to Wires: the FA Loop detail lines of a plan swapped
for wires, one wire for each run of lines between two devices
(firealarm.wire_paths), along the same path (chamfer wires: straight
between bends). Each wire keeps its loop in its Comments ('FA Loop 1',
'FA Sounder Loop 2'...), so Draw FA Loop, Address Devices and FA Riser
read the wires as they read the lines, and is shown in the view in the
line's colour and weight. The wires are not connected to the devices.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from Autodesk.Revit.DB import (
    BuiltInParameter, CurveElement, ElementId, FilteredElementCollector, GraphicsStyleType,
    OverrideGraphicSettings, Transaction, XYZ,
)
from Autodesk.Revit.DB.Electrical import Wire, WireType, WiringType
from System.Collections.Generic import List

from firealarm.addresses import SOUNDER
from firealarm.revit_loop import STYLES, _loop_style, id_int
from firealarm.wire_paths import runs


class WireResult(object):
    def __init__(self, number, kind):
        self.number = number
        self.kind = kind
        self.lines = 0          # detail lines replaced
        self.wires = 0          # wires made
        self.failed = []        # messages; the loop's lines are kept then


def _first_line(error):
    return (u"%s" % error).strip().splitlines()[0] if (u"%s" % error).strip() else u"refused"


def wire_types(doc):
    """({name: WireType}, the name used most by the model's wires)."""
    types = {}
    for t in FilteredElementCollector(doc).OfClass(WireType):
        p = t.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        name = (p.AsString() if p is not None else "") or u"Wire %d" % id_int(t.Id)
        types[name] = t
    counts = {}
    for w in FilteredElementCollector(doc).OfClass(Wire):
        counts[id_int(w.GetTypeId())] = counts.get(id_int(w.GetTypeId()), 0) + 1
    best = max(sorted(types), key=lambda n: counts.get(id_int(types[n].Id), 0)) if types else None
    return types, best


def loop_lines(doc, view, only=None):
    """{(loop number, kind): [detail lines]} of the FA Loop lines drawn in
    the view; only: ids (int) to keep to (the selection), or None."""
    found = {}
    for curve in FilteredElementCollector(doc, view.Id).OfClass(CurveElement):
        try:
            if id_int(curve.OwnerViewId) != id_int(view.Id):
                continue
            if only is not None and id_int(curve.Id) not in only:
                continue
            style = _loop_style(curve)
        except Exception:
            continue
        if style:
            found.setdefault(style, []).append(curve)
    return found


def _look(curve):
    """(Color, weight) of the line's style."""
    try:
        category = curve.LineStyle.GraphicsStyleCategory
        return category.LineColor, category.GetLineWeight(GraphicsStyleType.Projection)
    except Exception:
        return None, None


def _show_like(view, wire, colour, weight):
    settings = OverrideGraphicSettings()
    if colour is not None and colour.IsValid:
        settings.SetProjectionLineColor(colour)
    if weight:
        settings.SetProjectionLineWeight(weight)
    view.SetElementOverrides(wire.Id, settings)


def lines_to_wires(doc, view, wire_type, groups):
    """Swap each loop's lines (groups: loop_lines) for wires of
    `wire_type`, one undo. A loop whose wires cannot all be made keeps
    its lines. Returns [WireResult]."""
    results = []
    t = Transaction(doc, "Loop to Wires")
    t.Start()
    try:
        for (number, kind), curves in sorted(groups.items()):
            result = WireResult(number, kind)
            results.append(result)
            segments, z = [], None
            for curve in curves:
                geometry = curve.GeometryCurve
                a, b = geometry.GetEndPoint(0), geometry.GetEndPoint(1)
                z = a.Z if z is None else z
                segments.append(((a.X, a.Y), (b.X, b.Y)))
            colour, weight = _look(curves[0])
            name = STYLES[kind] % number
            made = []
            for run in runs(segments):
                points = List[XYZ]([XYZ(x, y, z) for x, y in run])
                try:
                    wire = Wire.Create(doc, wire_type.Id, view.Id, WiringType.Chamfer,
                                       points, None, None)
                except Exception as error:
                    result.failed.append(u"wire refused (%s)" % _first_line(error))
                    continue
                made.append(wire)
                comments = wire.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                if comments is None or comments.IsReadOnly:
                    result.failed.append(u"the wire's Comments cannot be written")
                    continue
                comments.Set(name)
                try:
                    _show_like(view, wire, colour, weight)
                except Exception:
                    pass                    # the wire type's own look
            if result.failed:               # keep the lines, drop the part-made wires
                if made:
                    doc.Delete(List[ElementId]([w.Id for w in made]))
                continue
            doc.Delete(List[ElementId]([c.Id for c in curves]))
            result.lines, result.wires = len(curves), len(made)
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    return results


def summarize(view_name, results):
    """(headline, details) after Loop to Wires."""
    done = [r for r in results if not r.failed]
    wires = sum(r.wires for r in done)
    headline = u"%d loop%s in '%s' switched to %d wire%s." % (
        len(done), "" if len(done) == 1 else "s", view_name, wires, "" if wires == 1 else "s")
    if len(done) < len(results):
        headline += u" Some loops kept their lines."
    lines = []
    for r in results:
        title = (u"FA Sounder Loop %d" if r.kind == SOUNDER else u"FA Loop %d") % r.number
        if r.failed:
            lines.append(u"%s: lines kept, %s" % (title, "; ".join(sorted(set(r.failed)))))
        else:
            lines.append(u"%s: %d line%s -> %d wire%s" % (
                title, r.lines, "" if r.lines == 1 else "s", r.wires, "" if r.wires == 1 else "s"))
    lines.append(u"Each wire keeps its loop in its Comments, so Address Devices, FA Riser and "
                 u"Draw FA Loop (Replace them) work with the wires as with the lines.")
    return headline, "\n".join(lines)

