# -*- coding: utf-8 -*-
"""Reading the panel schedule views of a Revit model."""
from Autodesk.Revit.DB import FilteredElementCollector, SectionType
from Autodesk.Revit.DB.Electrical import PanelScheduleView

from panelsched.workbook import BODY, FOOTER, HEADER, SUMMARY, CellStyle, Schedule, Section

_SECTIONS = ((HEADER, SectionType.Header), (BODY, SectionType.Body),
             (SUMMARY, SectionType.Summary), (FOOTER, SectionType.Footer))

# PanelScheduleData flags for the "Show in panel schedule" template options
_HIDDEN_FLAG = {HEADER: "IsHeaderSectionHidden", SUMMARY: "IsSummarySectionHidden",
                FOOTER: "IsFooterSectionHidden"}
_ALIGN = {"Left": "left", "Center": "center", "Right": "right"}


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


def _hidden(table, data, label):
    """True when the template hides this section (e.g. the Loads Summary)."""
    flag = _HIDDEN_FLAG.get(label)
    for owner, name in ((table, flag), (data, "HideSection")):
        if not name:
            continue
        try:
            if getattr(owner, name):
                return True
        except Exception:
            pass
    return False


def _color(color, skip):
    try:
        if color is None or not color.IsValid:
            return None
        rgb = u"%02X%02X%02X" % (color.Red, color.Green, color.Blue)
    except Exception:
        return None
    return None if rgb == skip else rgb


def _has_line(element_id):
    try:
        return element_id is not None and element_id.IntegerValue > 0
    except Exception:
        try:
            return element_id is not None and element_id.Value > 0   # Revit 2024+
        except Exception:
            return False


def _style(data, row, col):
    try:
        st = data.GetTableCellStyle(row, col)
    except Exception:
        return None
    if st is None:
        return None

    def get(name, default=None):
        try:
            return getattr(st, name)
        except Exception:
            return default

    align = get("FontHorizontalAlignment")
    return CellStyle(bold=bool(get("IsFontBold", False)), italic=bool(get("IsFontItalic", False)),
                     size=get("TextSize"), halign=_ALIGN.get(str(align)) if align is not None else None,
                     fill=_color(get("BackgroundColor"), u"FFFFFF"),
                     color=_color(get("TextColor"), u"000000"),
                     borders=(_has_line(get("BorderLeftLineStyle")),
                              _has_line(get("BorderRightLineStyle")),
                              _has_line(get("BorderTopLineStyle")),
                              _has_line(get("BorderBottomLineStyle"))))


def _size(fn, index):
    try:
        return float(fn(index))
    except Exception:
        return None


def _section(view, table, label, kind):
    try:
        data = table.GetSectionData(kind)
    except Exception:
        return None
    if data is None or data.NumberOfRows < 1 or data.NumberOfColumns < 1:
        return None
    if _hidden(table, data, label):
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
    widths = [_size(data.GetColumnWidth, c) for c in range(c0, c_last + 1)]
    heights = [_size(data.GetRowHeight, r) for r in range(r0, r_last + 1)]
    if any(w is None for w in widths):
        widths = None
    styles = {}
    for r in range(r0, r_last + 1):
        for c in range(c0, c_last + 1):
            st = _style(data, r, c)
            if st is not None:
                styles[(r - r0, c - c0)] = st
    return Section(label, rows, merges, widths=widths, heights=heights, styles=styles)


def _fallback_borders(sections):
    """If Revit gave no cell border at all (old versions), grid the circuit
    table and box every cell that has text, so the sheet is still ruled."""
    for section in sections:
        for st in section.styles.values():
            if st.borders and any(st.borders):
                return
    for section in sections:
        for r, cells in enumerate(section.rows):
            for c in range(section.columns):
                text = cells[c] if c < len(cells) else u""
                st = section.styles.setdefault((r, c), CellStyle())
                if section.kind == BODY or text.strip():
                    st.borders = (True, True, True, True)


def read(doc, view):
    """The schedule as shown in Revit, cell by cell."""
    table = view.GetTableData()
    sections = []
    for label, kind in _SECTIONS:
        section = _section(view, table, label, kind)
        if section is not None:
            sections.append(section)
    _fallback_borders(sections)
    panel = panel_of(doc, view)
    return Schedule(panel=panel_name(doc, view), view=view.Name, sections=sections,
                    level=_level(doc, panel) if panel is not None else u"",
                    circuits=_circuits(panel) if panel is not None else 0)
