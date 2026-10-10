# -*- coding: utf-8 -*-
"""Save to Revit: writes the LV Schematic Editor's changes into the
parameters the SLD and Voltage Drop tools read, so both agree and the
changes survive the next Generate SLD.

Where each change goes (the first place that exists and can be written,
in the order the tools read them):

  breaker of a way to a panel   Upstream_Protection_Rating_A (40AT/100AF)
                                + Upstream_Protection_Type on the fed panel;
                                else as a final circuit
  breaker of a final circuit    circuit Rating, SLD Frame, SLD Breaker Type
  cable                         circuit SLD Cable (printed as typed) and
                                VD Cable on the fed panel / circuit
  length                        VD Length (panel), Feeder_Length_m, VD Length
                                (circuit); final circuits: the circuit and
                                its loads that have one
  incomer                       Incomer_Rating_A + Incomer_Type, panel SLD
                                Frame; else MCB Rating
  fault level / ways            SLD Fault Level / SLD Ways when typed, else
                                SC_Rating_kA / No_Of_Ways, else the SLD one
  spares                        SLD Spares + SLD Spare Rating (drawing only)

Missing SLD / VD text parameters are added to the project; the office
panel family parameters are never created.
"""
from __future__ import division

import re

from Autodesk.Revit.DB import (BuiltInParameter, StorageType, Transaction,
                               TransactionGroup)

from sld.model import trim_number
from vdrop import revit_vd

_CIRCUITS = ("OST_ElectricalCircuit",)
_PANELS = ("OST_ElectricalEquipment",)
_BOTH = _PANELS + _CIRCUITS
SLD_PARAMETERS = [("SLD Cable", "text", _CIRCUITS), ("SLD Frame", "text", _BOTH),
                  ("SLD Breaker Type", "text", _CIRCUITS), ("SLD Spares", "text", _PANELS),
                  ("SLD Spare Rating", "text", _PANELS), ("SLD Fault Level", "text", _PANELS),
                  ("SLD Ways", "text", _PANELS)]
SLD_GROUP = "LV Schematic"
VD_NEEDED = (revit_vd.P_LENGTH, revit_vd.P_CABLE)
FEET_PER_M = 1 / 0.3048


def _param(element, name):
    if element is None:
        return None
    try:
        found = list(element.GetParameters(name))
    except Exception:
        found = []
    if found:
        return found[0]
    try:
        return element.LookupParameter(name)
    except Exception:
        return None


def _has_value(p):
    if p is None or not p.HasValue:
        return False
    if p.StorageType == StorageType.String:
        return bool((p.AsString() or "").strip())
    return True


def _is_length(p):
    try:
        from Autodesk.Revit.DB import SpecTypeId
        return p.Definition.GetDataType() == SpecTypeId.Length
    except Exception:
        return False


def _set(p, value):
    """Write text or a number whatever the parameter's storage."""
    if p is None or p.IsReadOnly:
        return False
    try:
        if p.StorageType == StorageType.String:
            text = trim_number(value, 3) if isinstance(value, float) else u"%s" % value
            return bool(p.Set(text)) or True
        number = float(value) if isinstance(value, (int, float)) else \
            float(re.search(r"\d+(?:[.,]\d+)?", u"%s" % value).group(0).replace(",", "."))
        if p.StorageType == StorageType.Double:
            p.Set(number * FEET_PER_M if _is_length(p) else number)
            return True
        if p.StorageType == StorageType.Integer:
            p.Set(int(round(number)))
            return True
    except Exception:
        return False
    return False


class _Writer(object):
    def __init__(self, doc):
        self.doc = doc
        self.written = 0
        self.skipped = []

    def element(self, unique_id):
        return self.doc.GetElement(unique_id) if unique_id else None

    def write(self, element, name, value, what):
        if _set(_param(element, name), value):
            self.written += 1
            return True
        self.skipped.append(u"%s: %s not written" % (what, name))
        return False

    def first(self, places, value, what):
        """Write to the first (element, name) that exists and is writable."""
        for element, name in places:
            p = _param(element, name)
            if p is not None and not p.IsReadOnly and _set(p, value):
                self.written += 1
                return True
        self.skipped.append(u"%s: no parameter to write to" % what)
        return False


def _name(element):
    try:
        return element.Name
    except Exception:
        return "?"


def _breaker_text(trip, frame):
    text = "%sAT" % trim_number(trip, 1)
    return text + ("/%sAF" % trim_number(frame, 1) if frame else "")


def _apply(w, change):
    v = change.values
    panel = w.element(change.element_id)
    circuit = w.element(change.circuit_id)
    what = _name(panel if panel is not None else circuit)

    if change.kind == "breaker":
        rating, kind = revit_vd.P_UPSTREAM
        p = _param(panel, rating)
        if panel is not None and p is not None and not p.IsReadOnly:
            w.write(panel, rating, _breaker_text(v["trip"], v["frame"]), what)
            if v.get("device"):
                w.write(panel, kind, v["device"], what)
            return
        p = circuit.get_Parameter(BuiltInParameter.RBS_ELEC_CIRCUIT_RATING_PARAM) \
            if circuit is not None else None
        if _set(p, float(v["trip"])):
            w.written += 1
        else:
            w.skipped.append(u"%s: circuit Rating not written" % what)
        if v.get("frame"):
            w.write(circuit, "SLD Frame", trim_number(v["frame"], 1), what)
        if v.get("device"):
            w.write(circuit, "SLD Breaker Type", v["device"], what)

    elif change.kind == "cable":
        w.write(circuit, "SLD Cable", v["text"], what)
        if panel is not None and _param(panel, revit_vd.P_CABLE) is not None:
            w.write(panel, revit_vd.P_CABLE, v["text"], what)
        if _param(circuit, revit_vd.P_CABLE) is not None:
            w.write(circuit, revit_vd.P_CABLE, v["text"], what)

    elif change.kind == "length":
        length = v["length"]
        if panel is not None:
            w.first([(panel, revit_vd.P_LENGTH), (panel, revit_vd.P_FEEDER_LENGTH),
                     (circuit, revit_vd.P_LENGTH)], length, what)
            return
        w.write(circuit, revit_vd.P_LENGTH, length, what)
        try:
            loads = list(circuit.Elements)
        except Exception:
            loads = []
        for load in loads:           # a load's own VD Length wins over the circuit's
            if _has_value(_param(load, revit_vd.P_LENGTH)):
                w.write(load, revit_vd.P_LENGTH, length, what)

    elif change.kind == "incomer":
        from sld.revit_sld import P_INCOMER, P_INCOMER_TYPE
        p = _param(panel, P_INCOMER)
        if p is not None and not p.IsReadOnly:
            old = p.AsString() if p.StorageType == StorageType.String else ""
            suffix = (old or "").split(",", 1)[1] if "," in (old or "") else ""
            text = "%sA" % trim_number(v["trip"], 1) + ("," + suffix if suffix else "")
            w.write(panel, P_INCOMER, text, what)
        else:
            mcb = panel.get_Parameter(BuiltInParameter.RBS_ELEC_PANEL_MCB_RATING_PARAM)
            if _set(mcb, float(v["trip"])):
                w.written += 1
            else:
                w.skipped.append(u"%s: incomer rating not written" % what)
        if v.get("frame"):
            w.write(panel, "SLD Frame", trim_number(v["frame"], 1), what)
        if v.get("device"):
            if _param(panel, P_INCOMER_TYPE) is not None:
                w.write(panel, P_INCOMER_TYPE, v["device"], what)
            else:
                w.skipped.append(u"%s: no Incomer_Type to write %s to" % (what, v["device"]))

    elif change.kind in ("fault_level", "ways"):
        from sld.revit_sld import P_SC_RATING, P_WAYS
        own, office = (("SLD Fault Level", P_SC_RATING) if change.kind == "fault_level"
                       else ("SLD Ways", P_WAYS))
        places = [(panel, office), (panel, own)]
        if _has_value(_param(panel, own)):
            places = [(panel, own)]
        w.first(places, v["text"], what)

    elif change.kind == "spares":
        w.write(panel, "SLD Spares", v["count"], what)
        w.write(panel, "SLD Spare Rating", v["rating"] or "", what)


def save(doc, changes):
    """Write the changes in one undo step. Returns (written, skipped messages,
    names of parameters added to the project)."""
    if not changes:
        return 0, [], []
    group = TransactionGroup(doc, "LV Schematic Editor: Save")
    group.Start()
    try:
        added = _ensure_parameters(doc)
        t = Transaction(doc, "Write SLD values")
        t.Start()
        w = _Writer(doc)
        try:
            for change in changes:
                try:
                    _apply(w, change)
                except Exception as error:
                    w.skipped.append(u"%s: %s" % (change.kind, error))
            t.Commit()
        except Exception:
            t.RollBack()
            raise
        group.Assimilate()
    except Exception:
        group.RollBack()
        raise
    return w.written, w.skipped, added


def _ensure_parameters(doc):
    bound = revit_vd._bindings(doc)
    sld_missing = [n for n, _, _ in SLD_PARAMETERS if n not in bound]
    vd_missing = [n for n in VD_NEEDED if n not in bound]
    if not sld_missing and not vd_missing:
        return []
    t = Transaction(doc, "Add SLD parameters")
    t.Start()
    try:
        if sld_missing:
            revit_vd._add_parameters(doc, sld_missing, SLD_PARAMETERS, SLD_GROUP)
        if vd_missing:
            revit_vd._add_parameters(doc, vd_missing)
        t.Commit()
    except Exception:
        t.RollBack()
        raise
    return sld_missing + vd_missing
