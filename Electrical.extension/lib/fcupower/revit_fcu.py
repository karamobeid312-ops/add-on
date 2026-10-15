# -*- coding: utf-8 -*-
"""The FCUs of the model: their tag (Comments), the room they are in (in
the architectural link, else a room or space of this model) and their
Real_Power_W, read and written. No parameter is ever created."""
from Autodesk.Revit.DB import (
    BuiltInParameter, FamilyInstance, FilteredElementCollector, LocationCurve, LocationPoint,
    RevitLinkInstance, StorageType, Transaction, XYZ,
)

from fcupower.match import Fcu

PARAM = "Real_Power_W"
DEFAULT_WORD = "FCU"             # families ticked at first: name has FCU

FEET = 0.3048
SIDE_STEP = 0.3 / FEET
# heights tried around the FCU: ceiling units sit above the room's upper limit
HEIGHT_STEPS = [h / FEET for h in (0.0, -0.5, -1.0, -1.5, -2.0, -2.5, -3.0, 0.3)]
ABOVE_LEVEL = 0.1 / FEET


def id_int(element_id):
    try:
        return element_id.Value            # Revit 2024+
    except AttributeError:
        return element_id.IntegerValue


def _bip_text(element, name):
    try:
        p = element.get_Parameter(getattr(BuiltInParameter, name))
        return (p.AsString() or p.AsValueString() or u"") if p is not None else u""
    except Exception:
        return u""


def family_name(element):
    try:
        return element.Symbol.Family.Name
    except Exception:
        return u""


def comments(element):
    return _bip_text(element, "ALL_MODEL_INSTANCE_COMMENTS").strip()


TYPE_PREFIX = u"Type: "


def _texts_of(owner, prefix, out):
    try:
        params = list(owner.Parameters)
    except Exception:
        return
    for p in params:
        try:
            if p.StorageType != StorageType.String:
                continue
            value = (p.AsString() or u"").strip()
            name = prefix + p.Definition.Name
        except Exception:
            continue
        if value and name not in out:
            out[name] = value


def text_values(element):
    """{parameter name: text} of the element's filled-in text parameters,
    type parameters as 'Type: name'. Comments is always there."""
    out = {u"Comments": comments(element)}
    _texts_of(element, u"", out)
    try:
        _texts_of(element.Symbol, TYPE_PREFIX, out)
    except Exception:
        pass
    return out


# ---------------------------------------------------------------- families

class Family(object):
    def __init__(self, name):
        self.name = name
        self.elements = []
        self.with_param = 0

    @property
    def default(self):
        return DEFAULT_WORD.lower() in self.name.lower()


def families(doc):
    """[Family] of the model's family instances that have Real_Power_W,
    or whose name has FCU; by name."""
    found = {}
    for element in FilteredElementCollector(doc).OfClass(FamilyInstance) \
            .WhereElementIsNotElementType():
        name = family_name(element)
        if not name:
            continue
        fam = found.get(name)
        if fam is None:
            fam = found[name] = Family(name)
        fam.elements.append(element)
        if element.LookupParameter(PARAM) is not None:
            fam.with_param += 1
    out = [f for f in found.values() if f.with_param or f.default]
    return sorted(out, key=lambda f: (not f.default, f.name.lower()))


# ---------------------------------------------------------------- rooms

class Model(object):
    """A model whose rooms and spaces are looked up: a link, or this one."""

    def __init__(self, doc, link=None):
        self.doc = doc
        self.to_model = link.GetTotalTransform().Inverse if link is not None else None
        self.spaces = link is None

    def find(self, point):
        p = self.to_model.OfPoint(point) if self.to_model is not None else point
        if self.spaces:
            try:
                space = self.doc.GetSpaceAtPoint(p)
                if space is not None:
                    return space
            except Exception:
                pass
        try:
            return self.doc.GetRoomAtPoint(p)
        except Exception:
            return None


def room_models(doc):
    """The loaded links (the architectural model among them), then this model."""
    found = []
    for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
        try:
            link_doc = link.GetLinkDocument()
        except Exception:
            link_doc = None
        if link_doc is not None:
            found.append(Model(link_doc, link))
    found.append(Model(doc))
    return found


def _location(element):
    loc = element.Location
    if isinstance(loc, LocationPoint):
        return loc.Point
    if isinstance(loc, LocationCurve):
        return loc.Curve.Evaluate(0.5, True)
    box = element.get_BoundingBox(None)
    if box is not None:
        return box.Min.Add(box.Max).Multiply(0.5)
    return None


def _floor(element):
    doc = element.Document
    level_id = getattr(element, "LevelId", None)
    if level_id is not None and id_int(level_id) > 0:
        level = doc.GetElement(level_id)
        if level is not None:
            return level.Elevation
    for name in ("FAMILY_LEVEL_PARAM", "INSTANCE_REFERENCE_LEVEL_PARAM",
                 "INSTANCE_SCHEDULE_ONLY_LEVEL_PARAM"):
        try:
            p = element.get_Parameter(getattr(BuiltInParameter, name))
            level = doc.GetElement(p.AsElementId()) if p is not None else None
            if level is not None:
                return level.Elevation
        except Exception:
            pass
    return None


def _candidates(element):
    point = _location(element)
    if point is None:
        return []
    sides = [XYZ.Zero]
    try:
        facing = element.FacingOrientation
        flat = XYZ(facing.X, facing.Y, 0)
        if flat.GetLength() > 0.5:
            flat = flat.Normalize().Multiply(SIDE_STEP)
            sides += [flat, flat.Negate()]
    except Exception:
        pass
    floor = _floor(element)
    out = []
    for dz in HEIGHT_STEPS:
        z = point.Z + dz
        if dz < 0 and floor is not None and z < floor + ABOVE_LEVEL:
            continue
        for side in sides:
            out.append(XYZ(point.X + side.X, point.Y + side.Y, z))
    return out


def find_room(element, models):
    """(number, name) of the room or space the FCU is in, or ('', '')."""
    points = _candidates(element)
    for model in models:
        for p in points:
            found = model.find(p)
            if found is not None:
                return (_bip_text(found, "ROOM_NUMBER").strip(),
                        _bip_text(found, "ROOM_NAME").strip())
    return (u"", u"")


# ---------------------------------------------------------------- Real_Power_W

def _watts_unit():
    try:
        from Autodesk.Revit.DB import UnitTypeId
        return UnitTypeId.Watts
    except Exception:
        from Autodesk.Revit.DB import DisplayUnitType
        return DisplayUnitType.DUT_WATTS


def _is_plain_number(param):
    try:
        from Autodesk.Revit.DB import SpecTypeId
        return param.Definition.GetDataType() == SpecTypeId.Number
    except Exception:
        return False


def _to_watts(param, value):
    if _is_plain_number(param):
        return value
    try:
        from Autodesk.Revit.DB import UnitUtils
        return UnitUtils.ConvertFromInternalUnits(value, _watts_unit())
    except Exception:
        return value


def _from_watts(param, watts):
    if _is_plain_number(param):
        return watts
    try:
        from Autodesk.Revit.DB import UnitUtils
        return UnitUtils.ConvertToInternalUnits(watts, _watts_unit())
    except Exception:
        return watts


def power_param(element):
    """(parameter, problem): the instance's Real_Power_W, or why not."""
    param = element.LookupParameter(PARAM)
    if param is None:
        try:
            if element.Symbol.LookupParameter(PARAM) is not None:
                return None, u"Real_Power_W is a type parameter"
        except Exception:
            pass
        return None, u"No Real_Power_W parameter"
    if param.IsReadOnly:
        return None, u"Real_Power_W is read-only (formula?)"
    if param.StorageType not in (StorageType.Double, StorageType.Integer, StorageType.String):
        return None, u"Real_Power_W is not a number"
    return param, u""


def read_watts(param):
    if param is None or not param.HasValue:
        return None
    kind = param.StorageType
    if kind == StorageType.Double:
        return _to_watts(param, param.AsDouble())
    if kind == StorageType.Integer:
        return float(param.AsInteger())
    try:
        return float((param.AsString() or u"").replace(u",", u"").split()[0])
    except (ValueError, IndexError):
        return None


def _set_watts(param, watts):
    kind = param.StorageType
    if kind == StorageType.Double:
        return param.Set(_from_watts(param, watts))
    if kind == StorageType.Integer:
        return param.Set(int(round(watts)))
    from fcupower.match import watts_text
    return param.Set(watts_text(watts))


# ---------------------------------------------------------------- FCUs

# ---------------------------------------------------------------- linked FCUs

LINKED_TAG = u"Linked FCU Comments"
NEAR = 3.0 / FEET               # how far the linked FCU may be from the socket (plan)


class LinkedFcus(object):
    """The FCUs (mechanical equipment with Comments) of the loaded links,
    in this model's coordinates; each socket takes the nearest one on its
    floor."""

    def __init__(self, doc):
        from Autodesk.Revit.DB import BuiltInCategory, Level
        self.units = []                 # (x, y, z, comments)
        for link in FilteredElementCollector(doc).OfClass(RevitLinkInstance):
            try:
                link_doc = link.GetLinkDocument()
                to_host = link.GetTotalTransform()
            except Exception:
                continue
            if link_doc is None:
                continue
            for element in FilteredElementCollector(link_doc) \
                    .OfCategory(BuiltInCategory.OST_MechanicalEquipment) \
                    .WhereElementIsNotElementType():
                tag = comments(element)
                point = _location(element) if tag else None
                if point is not None:
                    p = to_host.OfPoint(point)
                    self.units.append((p.X, p.Y, p.Z, tag))
        self.levels = sorted(l.Elevation for l in FilteredElementCollector(doc).OfClass(Level))

    def _storey(self, element):
        floor = _floor(element)
        if floor is None:
            point = _location(element)
            below = [e for e in self.levels if point is not None and e <= point.Z + 0.01]
            floor = below[-1] if below else None
        if floor is None:
            return None, None
        above = [e for e in self.levels if e > floor + 1.0 / FEET]
        return floor, (above[0] if above else floor + 6.0 / FEET)

    def nearest(self, element):
        """(comments, distance in m, index in units) of the nearest linked
        FCU on the socket's floor within NEAR, or ('', None, None)."""
        point = _location(element)
        if point is None or not self.units:
            return u"", None, None
        floor, top = self._storey(element)
        best = None
        for i, (x, y, z, tag) in enumerate(self.units):
            if floor is not None and not (floor - 0.3 / FEET <= z < top):
                continue
            d = ((x - point.X) ** 2 + (y - point.Y) ** 2) ** 0.5
            if d <= NEAR and (best is None or d < best[0]):
                best = (d, tag, i)
        if best is None:
            return u"", None, None
        return best[1], best[0] * FEET, best[2]


def read_fcus(doc, fams, models, rooms_cache, elements, progress=None, linked=None):
    """[Fcu] of the ticked families (rooms cached by element id; `elements`
    gets {element id: element} for writing)."""
    out = []
    todo = [e for f in fams for e in f.elements]
    for i, element in enumerate(todo):
        key = id_int(element.Id)
        elements[key] = element
        if key not in rooms_cache:
            rooms_cache[key] = find_room(element, models)
            if progress is not None and i % 25 == 0:
                progress(i, len(todo))
        number, name = rooms_cache[key]
        param, problem = power_param(element)
        fcu = Fcu(key, comments(element), number, name, read_watts(param),
                  family=family_name(element), problem=problem)
        fcu.texts = text_values(element)
        if linked is not None:
            tag, distance, unit = linked.nearest(element)
            fcu.texts[LINKED_TAG] = tag
            fcu.linked_distance = distance
            fcu.linked_unit = unit
        out.append(fcu)
    return out


def write(doc, fcus, elements):
    """Write Real_Power_W of the FCUs ticked to write. Returns
    (written, [failures])."""
    written, failed = 0, []
    t = Transaction(doc, "FCU Power from schedule")
    t.Start()
    try:
        for fcu in fcus:
            if not fcu.write or fcu.watts is None:
                continue
            element = elements.get(fcu.key)
            param, why = power_param(element) if element is not None else (None, u"element gone")
            if param is not None:
                try:
                    if _set_watts(param, fcu.watts):
                        written += 1
                        continue
                    why = u"Revit refused the value"
                except Exception as error:
                    why = u"%s" % error
            failed.append(u"%s (id %d): %s" % (fcu.tag or u"no tag", fcu.key, why))
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    return written, failed
