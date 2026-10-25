# -*- coding: utf-8 -*-
"""Revit side of the LOD tools: reading the sheets, writing their names and
parameters, creating sheets and switching their key plans."""
from Autodesk.Revit.DB import (
    BuiltInCategory, ElementId, FamilyInstance, FamilySymbol, FilteredElementCollector,
    StorageType, Transaction, ViewSheet,
)

from lod.compare import Sheet


def id_int(element_id):
    try:
        return element_id.Value             # Revit 2024+
    except AttributeError:
        return element_id.IntegerValue


# ------------------------------------------------------------ parameters

def param_text(element, name):
    """Text of the parameter `name`, '' when empty, None when the element
    does not have it."""
    if not name:
        return None
    p = element.LookupParameter(name)
    if p is None:
        return None
    if p.StorageType == StorageType.String:
        return p.AsString() or u""
    if p.StorageType == StorageType.Integer:
        return u"%d" % p.AsInteger() if p.HasValue else u""
    return p.AsValueString() or u""


def set_param(element, name, value):
    """Set the parameter `name`. Returns None when done, else why not."""
    p = element.LookupParameter(name)
    if p is None:
        return "no parameter"
    if p.IsReadOnly:
        return "read-only"
    try:
        if p.StorageType == StorageType.String:
            p.Set(u"%s" % value)
        elif p.StorageType == StorageType.Integer:
            if isinstance(value, bool):
                p.Set(1 if value else 0)
            else:
                p.Set(int(u"%s" % value))
        elif p.StorageType == StorageType.Double:
            p.SetValueString(u"%s" % value)
        else:
            return "not a text, number or Yes/No parameter"
    except Exception as error:
        return u"%s" % error
    return None


# ------------------------------------------------------------ sheets

def sheets(doc, rev_param=u"", area_param=u""):
    """[Sheet] of the model, placeholders too."""
    found = []
    for s in FilteredElementCollector(doc).OfClass(ViewSheet):
        if s.IsTemplate:
            continue
        found.append(Sheet(s.Id, s.SheetNumber, s.Name,
                           rev=param_text(s, rev_param), area=param_text(s, area_param),
                           placeholder=s.IsPlaceholder))
    return found


def title_blocks(doc):
    """{'Family : Type': type id} of the title block types."""
    found = {}
    for t in (FilteredElementCollector(doc).OfCategory(BuiltInCategory.OST_TitleBlocks)
              .WhereElementIsElementType()):
        if isinstance(t, FamilySymbol):
            found[u"%s : %s" % (t.FamilyName, _name(t))] = t.Id
    return found


def _name(element):
    try:
        return element.Name
    except Exception:
        from Autodesk.Revit.DB import Element
        return Element.Name.GetValue(element)


def create_sheets(doc, items, title_block_id, rev_param=u"", area_param=u"", keyplan=None):
    """Create a sheet for each (number, name, rev, area).

    keyplan: function(sheet name) -> [(parameter, value)], or None.
    Returns ([(number, sheet id)], [(number, why it failed)], [notes]).
    """
    made, failed, notes = [], [], []
    t = Transaction(doc, "Create Sheets from LOD")
    t.Start()
    try:
        for number, name, rev, area in items:
            sheet = None
            try:
                sheet = ViewSheet.Create(doc, title_block_id)
                sheet.SheetNumber = number
                sheet.Name = name
            except Exception as error:
                failed.append((number, u"%s" % error))
                try:
                    if sheet is not None and sheet.IsValidObject:
                        doc.Delete(sheet.Id)
                except Exception:
                    pass
                sheet = None
                continue
            if rev_param and rev:
                why = set_param(sheet, rev_param, rev)
                if why:
                    notes.append((number, rev_param, why))
            if area_param and area:
                why = set_param(sheet, area_param, area)
                if why:
                    notes.append((number, area_param, why))
            made.append((number, sheet.Id))
        if keyplan is not None and made:
            doc.Regenerate()
            for number, sheet_id in made:
                sheet = doc.GetElement(sheet_id)
                for _, param, why in apply_keyplan(doc, sheet, keyplan(sheet.Name)):
                    notes.append((number, param, why))
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    return made, failed, notes


def apply_changes(doc, changes, rev_param=u"", area_param=u""):
    """Write Compare's changes to the sheets. Returns [(change, why it failed)]."""
    from lod.compare import Change
    failed = []
    t = Transaction(doc, "Sync Sheets with LOD")
    t.Start()
    try:
        for c in changes:
            sheet = doc.GetElement(c.sheet.key)
            try:
                if c.field == Change.NAME:
                    sheet.Name = c.new
                    why = None
                elif c.field == Change.REV:
                    why = set_param(sheet, rev_param, c.new)
                else:
                    why = set_param(sheet, area_param, c.new)
            except Exception as error:
                why = u"%s" % error
            if why:
                failed.append((c, why))
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    return failed


# ------------------------------------------------------------ key plan

def holders(doc, sheet):
    """Family instances on the sheet that can carry key plan parameters:
    the title block first, then key plan or other annotation families."""
    found = list(FilteredElementCollector(doc, sheet.Id).OfClass(FamilyInstance))
    tb = id_int(ElementId(BuiltInCategory.OST_TitleBlocks))

    def rank(e):
        return 0 if e.Category is not None and id_int(e.Category.Id) == tb else 1
    return sorted(found, key=rank)


def apply_keyplan(doc, sheet, values):
    """Set the key plan parameters on the sheet's title block / key plan
    family (or the sheet itself). Returns [(sheet, parameter, why not set)]."""
    found = holders(doc, sheet) + [sheet]
    problems = []
    for name, value in values:
        targets = [e for e in found if e.LookupParameter(name) is not None]
        if not targets:
            problems.append((sheet, name, "not on the title block or key plan"))
            continue
        why = None
        for e in targets:
            why = set_param(e, name, value)
            if why is None:
                break
        if why:
            problems.append((sheet, name, why))
    return problems


def switch_keyplans(doc, sheet_list, keyplan):
    """Apply the key plan rules to each sheet in one transaction.
    Returns (number of sheets done, [(sheet, parameter, why not set)])."""
    problems = []
    t = Transaction(doc, "Set Key Plans from Sheet Names")
    t.Start()
    try:
        for sheet in sheet_list:
            problems.extend(apply_keyplan(doc, sheet, keyplan(sheet.Name)))
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    return len(sheet_list), problems


def parameters_on(doc, sheet):
    """[(element label, parameter, kind, value, read-only)] of the title block
    and other families on the sheet, to find the key plan parameter names."""
    rows = []
    for e in holders(doc, sheet):
        label = u"%s : %s" % (e.Symbol.FamilyName, _name(e.Symbol)) if e.Symbol else _name(e)
        for p in e.Parameters:
            d = p.Definition
            if p.StorageType == StorageType.Integer:
                try:
                    from Autodesk.Revit.DB import SpecTypeId
                    yes_no = d.GetDataType() == SpecTypeId.Boolean.YesNo
                except Exception:
                    try:
                        from Autodesk.Revit.DB import ParameterType
                        yes_no = d.ParameterType == ParameterType.YesNo
                    except Exception:
                        yes_no = False
                kind = u"Yes/No" if yes_no else u"Integer"
            elif p.StorageType == StorageType.String:
                kind = u"Text"
            else:
                continue
            rows.append((label, d.Name, kind, param_text(e, d.Name), p.IsReadOnly))
    rows.sort(key=lambda r: (r[0], r[2] != u"Yes/No", r[1].lower()))
    return rows


def selected_sheets(doc, uidoc):
    found = []
    for i in uidoc.Selection.GetElementIds():
        e = doc.GetElement(i)
        if isinstance(e, ViewSheet):
            found.append(e)
    return found


def all_sheets(doc):
    return [s for s in FilteredElementCollector(doc).OfClass(ViewSheet)
            if not s.IsTemplate and not s.IsPlaceholder]


# ------------------------------------------------------------ views

def _placeable_views(doc):
    """[(view, name)] of the views that can go on a sheet: plans, ceiling
    plans, sections, elevations, 3D, drafting views and legends."""
    from Autodesk.Revit.DB import View, ViewType
    kinds = set([ViewType.FloorPlan, ViewType.CeilingPlan, ViewType.EngineeringPlan,
                 ViewType.AreaPlan, ViewType.Section, ViewType.Elevation,
                 ViewType.Detail, ViewType.ThreeD, ViewType.DraftingView,
                 ViewType.Legend])
    found = []
    for v in FilteredElementCollector(doc).OfClass(View):
        if v.IsTemplate or v.ViewType not in kinds:
            continue
        found.append((v, v.Name))
    return found


def views_on_sheets(doc):
    """{view id int: set(sheet id ints)} of the views placed on sheets."""
    from Autodesk.Revit.DB import Viewport
    on = {}
    for vp in FilteredElementCollector(doc).OfClass(Viewport):
        on.setdefault(id_int(vp.ViewId), set()).add(id_int(vp.SheetId))
    return on


def view_list(doc):
    """[(view id int, name, set(sheet id ints it is on))]."""
    on = views_on_sheets(doc)
    return [(id_int(v.Id), name, on.get(id_int(v.Id), set()))
            for v, name in _placeable_views(doc)]


def views_by_id(doc):
    """{view id int: view} of the views that can go on a sheet."""
    return dict((id_int(v.Id), v) for v, _ in _placeable_views(doc))


def _sheet_centre(doc, sheet):
    """Middle of the drawing area: the title block's box, else the sheet's."""
    from Autodesk.Revit.DB import XYZ
    for e in holders(doc, sheet):
        if e.Category is not None and id_int(e.Category.Id) == id_int(
                ElementId(BuiltInCategory.OST_TitleBlocks)):
            box = e.get_BoundingBox(sheet)
            if box is not None:
                return (box.Min + box.Max) / 2.0
    out = sheet.Outline
    return XYZ((out.Min.U + out.Max.U) / 2.0, (out.Min.V + out.Max.V) / 2.0, 0)


def place_views(doc, pairs):
    """Put each view on its sheet, in the middle of the title block.

    pairs: [(sheet, view)]. Returns ([(sheet, view)] placed,
    [(sheet, view, why not)]).
    """
    from Autodesk.Revit.DB import Viewport
    placed, failed = [], []
    t = Transaction(doc, "Place Views on Sheets")
    t.Start()
    try:
        for sheet, view in pairs:
            try:
                if not Viewport.CanAddViewToSheet(doc, sheet.Id, view.Id):
                    failed.append((sheet, view, "Revit cannot add it (already on a sheet?)"))
                    continue
                Viewport.Create(doc, sheet.Id, view.Id, _sheet_centre(doc, sheet))
                placed.append((sheet, view))
            except Exception as error:
                failed.append((sheet, view, u"%s" % error))
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    return placed, failed
