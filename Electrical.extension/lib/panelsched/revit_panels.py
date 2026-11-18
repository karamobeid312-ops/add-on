# -*- coding: utf-8 -*-
"""Reading the panel schedule views of a Revit model."""
from Autodesk.Revit.DB import FilteredElementCollector, SectionType
from Autodesk.Revit.DB.Electrical import PanelScheduleView

from panelsched.workbook import BODY, FOOTER, HEADER, SUMMARY, Schedule, Section

_SECTIONS = ((HEADER, SectionType.Header), (BODY, SectionType.Body),
             (SUMMARY, SectionType.Summary), (FOOTER, SectionType.Footer))


def schedule_views(doc):
    """Every panel schedule view in the model (templates left out)."""
    views = []
    for view in FilteredElementCollector(doc).OfClass(PanelScheduleView):
        try:
            if view.IsTemplate or view.IsPanelScheduleTemplate():
                continue
        except Exception:
            pass
        views.append(view)
    return views


def panel_of(doc, view):
    try:
        return doc.GetElement(view.GetPanel())
    except Exception:
        return None


def panel_name(doc, view):
    panel = panel_of(doc, view)
    name = getattr(panel, "Name", None) if panel is not None else None
    return name or view.Name


def _level(doc, panel):
    try:
        level = doc.GetElement(panel.LevelId)
        return level.Name if level is not None else u""
    except Exception:
        return u""


def _circuits(panel):
    try:
        mep = panel.MEPModel
        try:
            systems = mep.GetAssignedElectricalSystems()
        except Exception:
            systems = mep.ElectricalSystems   # before Revit 2021
        return len(list(systems or []))
    except Exception:
        return 0


def _text(view, kind, row, col):
    try:
        return view.GetCellText(kind, row, col) or u""
    except Exception:
        return u""


def _section(view, table, label, kind):
    try:
        data = table.GetSectionData(kind)
    except Exception:
        return None
    if data is None or data.NumberOfRows < 1 or data.NumberOfColumns < 1:
        return None
    r0, c0 = data.FirstRowNumber, data.FirstColumnNumber
    r_last, c_last = data.LastRowNumber, data.LastColumnNumber
    rows, merges, seen = [], [], set()
    for r in range(r0, r_last + 1):
        rows.append([_text(view, kind, r, c) for c in range(c0, c_last + 1)])
        for c in range(c0, c_last + 1):
            if (r, c) in seen:
                continue
            try:
                m = data.GetMergedCell(r, c)
            except Exception:
                m = None
            if m is None or (m.Bottom <= m.Top and m.Right <= m.Left):
                continue
            for mr in range(m.Top, m.Bottom + 1):
                for mc in range(m.Left, m.Right + 1):
                    seen.add((mr, mc))
            top, left = max(m.Top, r0), max(m.Left, c0)
            bottom, right = min(m.Bottom, r_last), min(m.Right, c_last)
            if (bottom, right) != (top, left):
                merges.append((top - r0, left - c0, bottom - r0, right - c0))
    return Section(label, rows, merges)


def read(doc, view):
    """The schedule as shown in Revit, cell by cell."""
    table = view.GetTableData()
    sections = []
    for label, kind in _SECTIONS:
        section = _section(view, table, label, kind)
        if section is not None:
            sections.append(section)
    panel = panel_of(doc, view)
    return Schedule(panel=panel_name(doc, view), view=view.Name, sections=sections,
                    level=_level(doc, panel) if panel is not None else u"",
                    circuits=_circuits(panel) if panel is not None else 0)
