# -*- coding: utf-8 -*-
"""Revit side of Loop to Wires: the detail lines of a plan, of the line
styles chosen, swapped for wires along the same path, one straight wire
for each straight leg (firealarm.wire_paths: a wire with a bend in it
gets its corner cut or rounded by Revit), shown in the view in the line's colour and
weight. A wire made from FA Loop lines keeps its loop in its Comments
('FA Loop 1', 'FA Sounder Loop 2'...), so Draw FA Loop, Address Devices
and FA Riser read the wires as they read the lines. The wires are not
connected to the devices.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from Autodesk.Revit.DB import (
    BuiltInParameter, CurveElement, ElementId, FilteredElementCollector, GraphicsStyleType, Line,
    OverrideGraphicSettings, Transaction, XYZ,
)
from Autodesk.Revit.DB.Electrical import Wire, WireType, WiringType
from System.Collections.Generic import List

from firealarm.revit_loop import _STYLE_NAME, id_int, loop_name
from firealarm.wire_paths import legs


class WireResult(object):
    def __init__(self, style):
        self.style = style      # the line style the lines had
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


def view_lines(doc, view, only=None):
    """{line style name: [detail lines]} of the straight detail lines
    drawn in the view; only: ids (int) to keep to (the selection), or None."""
    found = {}
    for curve in FilteredElementCollector(doc, view.Id).OfClass(CurveElement):
        try:
            if id_int(curve.OwnerViewId) != id_int(view.Id):
                continue
            if only is not None and id_int(curve.Id) not in only:
                continue
            if not isinstance(curve.GeometryCurve, Line):
                continue                    # arcs and splines stay lines
            name = loop_name(curve)
        except Exception:
            continue
        if name:
            found.setdefault(name, []).append(curve)
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
    """Swap the lines of each line style (groups: view_lines) for wires
    of `wire_type`, one undo. Wires made from FA Loop lines get the loop in
    their Comments. A style whose wires cannot all be made keeps its
    lines. Returns [WireResult]."""
    results = []
    t = Transaction(doc, "Loop to Wires")
    t.Start()
    try:
        for style, curves in sorted(groups.items()):
            result = WireResult(style)
            results.append(result)
            segments, z = [], None
            for curve in curves:
                geometry = curve.GeometryCurve
                a, b = geometry.GetEndPoint(0), geometry.GetEndPoint(1)
                z = a.Z if z is None else z
                segments.append(((a.X, a.Y), (b.X, b.Y)))
            colour, weight = _look(curves[0])
            loop = style if _STYLE_NAME.match(style) else None
            made = []
            for run in legs(segments):          # straight wires: square corners
                points = List[XYZ]([XYZ(x, y, z) for x, y in run])
                try:
                    wire = Wire.Create(doc, wire_type.Id, view.Id, WiringType.Chamfer,
                                       points, None, None)
                except Exception as error:
                    result.failed.append(u"wire refused (%s)" % _first_line(error))
                    continue
                made.append(wire)
                if loop:                    # read back as the loop by the FA tools
                    comments = wire.get_Parameter(BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    if comments is None or comments.IsReadOnly:
                        result.failed.append(u"the wire's Comments cannot be written")
                        continue
                    comments.Set(loop)
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
    lines = sum(r.lines for r in done)
    headline = u"%d line%s in '%s' switched to %d wire%s." % (
        lines, "" if lines == 1 else "s", view_name, wires, "" if wires == 1 else "s")
    if len(done) < len(results):
        headline += u" Some kept their lines."
    details = []
    for r in results:
        if r.failed:
            details.append(u"%s: lines kept, %s" % (r.style, "; ".join(sorted(set(r.failed)))))
        else:
            details.append(u"%s: %d line%s -> %d wire%s" % (
                r.style, r.lines, "" if r.lines == 1 else "s", r.wires, "" if r.wires == 1 else "s"))
    if any(_STYLE_NAME.match(r.style) for r in done):
        details.append(u"Wires from FA Loop lines keep their loop in their Comments, so Address "
                       u"Devices, FA Riser and Draw FA Loop (Replace them) work with them as with "
                       u"the lines.")
    return headline, "\n".join(details)
