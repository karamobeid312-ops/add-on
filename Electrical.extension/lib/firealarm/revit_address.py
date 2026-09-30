# -*- coding: utf-8 -*-
"""Revit side of the fire alarm addresses: the device symbol (type) of a
family instance, the 'FA Address' parameter (a shared parameter from
'FA shared parameters.txt', added to Fire Alarm Devices on first use) and
the address tags placed by Draw FA Loop.

Works with pyRevit's IronPython 2.7 and CPython 3 engines.
"""
from __future__ import division

import os

from Autodesk.Revit.DB import (
    BuiltInCategory, BuiltInParameter, ElementId, FamilyInstance, FamilySymbol,
    FilteredElementCollector, IndependentTag, Reference, StorageType, TagOrientation,
)
from System.Collections.Generic import List

from firealarm.addresses import first_number, loop_addresses
from firealarm.revit_loop import id_int, label
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


def _old_tags(doc, view, tag_type, device_ids):
    """Tags of `tag_type` in the view on any of the devices."""
    found = []
    for tag in FilteredElementCollector(doc, view.Id).OfClass(IndependentTag):
        if id_int(tag.GetTypeId()) != id_int(tag_type.Id):
            continue
        if any(i in device_ids for i in _tagged_ids(tag)):
            found.append(tag.Id)
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

class Addresser(object):
    """Writes the addresses of the loops drawn by Draw FA Loop and tags them.

    codes: {device id (int): symbol code}; tag_type: the tag FamilySymbol or
    None (only the parameter is filled)."""

    def __init__(self, doc, view, codes, tag_type=None):
        self.doc, self.view, self.codes, self.tag_type = doc, view, codes, tag_type
        self.parameter_added = False
        self.written = 0
        self.tagged = 0
        self.tags_replaced = 0
        self.ranges = {}            # loop number -> (first address, last address)
        self.problems = []

    def _existing(self, skip):
        """FA Address values of the fire alarm devices not being addressed now."""
        found = []
        for element in FilteredElementCollector(self.doc) \
                .OfCategory(BuiltInCategory.OST_FireAlarmDevices).OfClass(FamilyInstance):
            if id_int(element.Id) in skip:
                continue
            value = _text(element, PARAMETER)
            if value:
                found.append(value)
        return found

    def apply(self, numbered):
        """numbered: [(loop number, [devices in route order])]. Inside the
        Draw FA Loop transaction."""
        self.parameter_added = bool(add_parameter(self.doc))
        ids = set(id_int(d.Id) for _, devices in numbered for d in devices)
        existing = self._existing(ids)
        for number, devices in numbered:
            own = [_text(d, PARAMETER) for d in devices]
            first = first_number(number, len(devices), existing, own)
            addresses = loop_addresses(number, [self.codes[id_int(d.Id)] for d in devices], first)
            for device, address in zip(devices, addresses):
                p = device.LookupParameter(PARAMETER)
                if p is None or p.IsReadOnly:
                    self.problems.append(u"%s has no editable %s parameter" % (label(device), PARAMETER))
                    continue
                p.Set(address)
                self.written += 1
            if addresses:
                self.ranges[number] = (addresses[0], addresses[-1])
        if self.tag_type is not None:
            self._tag([d for _, devices in numbered for d in devices], ids)

    def _tag(self, devices, ids):
        old = _old_tags(self.doc, self.view, self.tag_type, ids)
        if old:
            self.doc.Delete(List[ElementId](old))
            self.tags_replaced = len(old)
        if not self.tag_type.IsActive:
            self.tag_type.Activate()
        for device in devices:
            try:
                IndependentTag.Create(self.doc, self.tag_type.Id, self.view.Id, Reference(device),
                                      False, TagOrientation.Horizontal, _tag_point(device, self.view))
                self.tagged += 1
            except Exception as err:
                self.problems.append(u"tag not placed on %s: %s" % (label(device), err))
