# -*- coding: utf-8 -*-
"""Revit side of the fire alarm addresses: the device symbol (type) of a
family instance, the 'FA Address' parameter (a shared parameter from
'FA shared parameters.txt', added to Fire Alarm Devices on first use) and
the address tags, written and placed by Address Devices.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from __future__ import division

import os

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, FamilyInstance, FamilySymbol, FilteredElementCollector,
    IndependentTag, Reference, StorageType, TagOrientation, Transaction,
)

from firealarm.addresses import address_kind, first_number, loop_addresses, parse_address
from firealarm.revit_loop import id_int, label, level_of, model_levels
from firealarm.riser_symbols import resolve

PARAMETER = "FA Address"
GROUP = "Fire Alarm"
PARAMETER_FILE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                               "..", "..", "FA shared parameters.txt"))
MM_PER_FOOT = 304.8
TAG_OFFSET = 1.0            # mm on paper between a device and its tag


def _text(element, name):
    try:
        p = element.LookupParameter(name)
        if p is None or not p.HasValue:
            return ""
        return ((p.AsString() if p.StorageType == StorageType.String else p.AsValueString())
                or "").strip()
    except Exception:
        return ""


def symbol_of(element, chosen):
    """Symbol code of a device: its 'FA Symbol' parameter, else the one
    chosen in FA Settings > Riser symbols, else a guess from its name."""
    name = label(element)
    override = _text(element, "FA Symbol")
    if not override:
        try:
            override = _text(element.Symbol, "FA Symbol")
        except Exception:
            override = ""
    return resolve(name, override, chosen.get(name))


# ---------------------------------------------------------------- parameter

def has_parameter(doc):
    iterator = doc.ParameterBindings.ForwardIterator()
    while iterator.MoveNext():
        if iterator.Key.Name == PARAMETER:
            return True
    return False


def add_parameter(doc):
    """Add FA Address (text, instance) to Fire Alarm Devices from the shared
    parameter file of the add-in. Inside a transaction. True when added."""
    if has_parameter(doc):
        return False
    app = doc.Application
    before = app.SharedParametersFilename
    try:
        app.SharedParametersFilename = PARAMETER_FILE
        definition = app.OpenSharedParameterFile().Groups.get_Item(GROUP) \
            .Definitions.get_Item(PARAMETER)
    finally:
        try:
            app.SharedParametersFilename = before
        except Exception:
            pass
    categories = app.Create.NewCategorySet()
    categories.Insert(doc.Settings.Categories.get_Item(BuiltInCategory.OST_FireAlarmDevices))
    binding = app.Create.NewInstanceBinding(categories)
    try:
        from Autodesk.Revit.DB import GroupTypeId           # Revit 2022+
        return doc.ParameterBindings.Insert(definition, binding, GroupTypeId.IdentityData)
    except Exception:
        pass
    try:
        from Autodesk.Revit.DB import BuiltInParameterGroup
        return doc.ParameterBindings.Insert(definition, binding,
                                            BuiltInParameterGroup.PG_IDENTITY_DATA)
    except Exception:
        return doc.ParameterBindings.Insert(definition, binding)


# ---------------------------------------------------------------- tags

def tag_types(doc):
    """{'Family : Type': FamilySymbol} of the fire alarm device tags loaded."""
    found = {}
    for symbol in FilteredElementCollector(doc).OfClass(FamilySymbol) \
            .OfCategory(BuiltInCategory.OST_FireAlarmDeviceTags):
        try:
            name = symbol.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM).AsString() or ""
        except Exception:
            name = ""
        found[u"%s : %s" % (symbol.FamilyName, name)] = symbol
    return found


def _tagged_ids(tag):
    try:
        return [id_int(i) for i in tag.GetTaggedLocalElementIds()]      # Revit 2022+
    except Exception:
        try:
            return [id_int(tag.TaggedLocalElementId)]
        except Exception:
            return []


def _tagged_in(doc, view, tag_type):
    """Ids of the elements tagged with `tag_type` in the view."""
    found = set()
    for tag in FilteredElementCollector(doc, view.Id).OfClass(IndependentTag):
        if id_int(tag.GetTypeId()) == id_int(tag_type.Id):
            found.update(_tagged_ids(tag))
    return found


def _tag_point(device, view):
    """Above and to the right of the device, clear of its symbol."""
    p = device.Location.Point
    right, up = view.RightDirection, view.UpDirection
    half = 0.0
    box = device.get_BoundingBox(view)
    if box is not None:
        half = max(box.Max.X - p.X, p.X - box.Min.X, box.Max.Y - p.Y, p.Y - box.Min.Y, 0.0)
    off = half + TAG_OFFSET / MM_PER_FOOT * view.Scale
    return p + right.Multiply(off) + up.Multiply(off)


# ---------------------------------------------------------------- addresses

def _addressed(doc, skip=()):
    """[(device, FA Address)] of the fire alarm devices with an address,
    but those in `skip` (ids)."""
    found = []
    for element in FilteredElementCollector(doc) \
            .OfCategory(BuiltInCategory.OST_FireAlarmDevices).OfClass(FamilyInstance):
        if id_int(element.Id) in skip:
            continue
        value = _text(element, PARAMETER)
        if value:
            found.append((element, value))
    return found


def addressed_loops(doc, skip=()):
    """{loop number: (set of kinds, set of floor names)} of the addresses of
    the fire alarm devices but those in `skip` (ids): loops addressed
    without loop lines take their numbers too."""
    levels = model_levels(doc)
    found = {}
    for element, value in _addressed(doc, skip):
        parsed = parse_address(value)
        if not parsed:
            continue
        kinds, floors = found.setdefault(parsed[0], (set(), set()))
        kinds.add(address_kind(value))
        try:
            floors.add(level_of(doc, element, levels).Name)
        except Exception:
            pass
    return found


class AddressedLoop(object):
    def __init__(self, number, kind, floors, addresses):
        self.number = number
        self.kind = kind            # DETECTION / SOUNDER
        self.floors = floors        # names of its plans, in counting order
        self.devices = len(addresses)
        self.first = addresses[0] if addresses else ""
        self.last = addresses[-1] if addresses else ""


class Addresser(object):
    """Writes the addresses of loops, device after device in route order,
    and tags them. chosen: {'Family : Type': symbol code} from FA Settings;
    tag_type: the tag FamilySymbol, or None (only FA Address is filled)."""

    def __init__(self, doc, chosen, tag_type=None):
        self.doc, self.chosen, self.tag_type = doc, chosen, tag_type
        self.parameter_added = False
        self.written = 0
        self.tagged = 0
        self.already_tagged = 0     # devices with a tag of that type already (kept)
        self.loops = []             # [AddressedLoop]
        self.twice = []             # devices on two loops' routes, addressed on the first
        self.clashes = []           # other devices with an address written now
        self.problems = []
        self._codes = {}
        self._tagged = {}           # view id -> ids of the devices tagged in it

    def code(self, device):
        key = id_int(device.Id)             # an instance may have its own FA Symbol
        if key not in self._codes:
            self._codes[key] = symbol_of(device, self.chosen)
        return self._codes[key]

    def run(self, loops, skip=(), keep_ranges=True):
        """Address and tag the loops, one undo. loops: [(loop number, kind,
        [(view, [devices in route order])])], a loop's parts in counting
        order (floor after floor). A loop counts on after the addresses the
        loop has on other devices, but those in `skip` (ids: devices whose
        old addresses do not count). keep_ranges: devices addressed before
        on the same loop keep their range when it still fits
        (addresses.first_number); else the count starts afresh."""
        ids = set(id_int(d.Id) for _, _, parts in loops for _, devices in parts for d in devices)
        skip = set(skip) | ids
        t = Transaction(self.doc, "Address FA Devices")
        t.Start()
        try:
            self.parameter_added = bool(add_parameter(self.doc))
            others = _addressed(self.doc, ids)
            existing = [value for element, value in others if id_int(element.Id) not in skip]
            written, done = set(), set()
            for number, kind, parts in loops:
                chain, shown = [], []
                for view, devices in parts:
                    fresh = []
                    for device in devices:
                        if id_int(device.Id) in done:
                            self.twice.append(device)
                            continue
                        done.add(id_int(device.Id))
                        fresh.append(device)
                    chain.extend(fresh)
                    if fresh:
                        shown.append((view, fresh))
                if not chain:
                    continue
                own = [_text(d, PARAMETER) for d in chain] if keep_ranges else []
                first = first_number(number, len(chain), existing, own)
                addresses = loop_addresses(number, [self.code(d) for d in chain], first)
                self._write(chain, addresses)
                existing.extend(addresses)
                written.update((number, first + k) for k in range(len(chain)))
                self.loops.append(AddressedLoop(number, kind, [v.Name for v, _ in shown], addresses))
                if self.tag_type is not None:
                    for view, devices in shown:
                        self._tag(view, devices)
            for element, value in others:
                parsed = parse_address(value)
                if parsed and (parsed[0], parsed[2]) in written:
                    self.clashes.append(element)
            t.Commit()
        except Exception:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            raise

    def _write(self, devices, addresses):
        for device, address in zip(devices, addresses):
            p = device.LookupParameter(PARAMETER)
            if p is None or p.IsReadOnly:
                self.problems.append(u"%s has no editable %s parameter" % (label(device), PARAMETER))
                continue
            p.Set(address)
            self.written += 1

    def _tag(self, view, devices):
        key = id_int(view.Id)
        if key not in self._tagged:
            self._tagged[key] = _tagged_in(self.doc, view, self.tag_type)
        tagged = self._tagged[key]
        if not self.tag_type.IsActive:
            self.tag_type.Activate()
        for device in devices:
            if id_int(device.Id) in tagged:
                self.already_tagged += 1
                continue
            try:
                IndependentTag.Create(self.doc, self.tag_type.Id, view.Id, Reference(device),
                                      False, TagOrientation.Horizontal, _tag_point(device, view))
                tagged.add(id_int(device.Id))
                self.tagged += 1
            except Exception as err:
                self.problems.append(u"tag not placed on %s: %s" % (label(device), err))
