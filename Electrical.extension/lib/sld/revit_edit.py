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
  cable                         Feeder_Size + Feeder_Type on the fed panel,
                                VD Cable / SLD Cable where they exist
  length                        Feeder_Length_m (and the panel's VD Length when
                                it has a value); final circuits:
                                Feeder_Length_m (or VD Length) on its loads,
                                VD Length on the circuit, where they exist
  incomer of a main board       Upstream_Protection_Rating_A / _Type, else
                                Incomer_Rating_A + Incomer_Type, panel SLD
                                Frame; else MCB Rating (a fed board's incomer
                                is the breaker of the way feeding it)
  fault level / ways            SLD Fault Level / SLD Ways when typed, else
                                SC_Rating_kA / No_Of_Ways, else the SLD one
  spares                        SLD Spares + SLD Spare Rating (drawing only)

Only parameters already in the model are written: nothing is added to the
project. What could not be written is listed for the user.
"""
from __future__ import division

import re

from Autodesk.Revit.DB import BuiltInParameter, StorageType, Transaction

from sld.model import trim_number
from vdrop import revit_vd

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
        p = _param(element, name)
        if _set(p, value):
            self.written += 1
            return True
        reason = "not in the model" if p is None else "read-only"
        self.skipped.append(u"%s: %s %s" % (what, name, reason))
        return False

    def first(self, places, value, what):
        """Write to the first (element, name) that exists and is writable."""
        for element, name in places:
            p = _param(element, name)
            if p is not None and not p.IsReadOnly and _set(p, value):
                self.written += 1
                return True
        self.skipped.append(u"%s: none of %s in the model" % (
            what, ", ".join(n for _, n in places)))
        return False


def _name(element):
    try:
        return element.Name
    except Exception:
        return "?"


def _circuit_name(circuit):
    """'SMDB-GF-01 CKT 1 (AHU-B-A)' rather than the bare circuit number."""
    try:
        text = u"%s CKT %s" % (circuit.BaseEquipment.Name, circuit.CircuitNumber)
        return text + (u" (%s)" % circuit.LoadName if circuit.LoadName else u"")
    except Exception:
        return _name(circuit)


def _breaker_text(trip, frame):
    text = "%sAT" % trim_number(trip, 1)
    return text + ("/%sAF" % trim_number(frame, 1) if frame else "")


def _apply(w, change):
    v = change.values
    panel = w.element(change.element_id)
    circuit = w.element(change.circuit_id)
    what = _name(panel) if panel is not None else _circuit_name(circuit)

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
        from sld import cablespec
        done = 0
        spec = cablespec.parse(v["text"])
        if panel is not None and spec is not None:
            for name, value in zip(revit_vd.P_FEEDER_CABLE, spec.feeder_fields()):
                if _param(panel, name) is not None:
                    done += w.write(panel, name, value, what)
        for element, name in ((panel, revit_vd.P_CABLE), (circuit, "SLD Cable"),
                              (circuit, revit_vd.P_CABLE)):
            if element is not None and _param(element, name) is not None:
                done += w.write(element, name, v["text"], what)
        if not done:
            w.skipped.append(u"%s: cable %s - no Feeder_Size / VD Cable / SLD Cable "
                             u"to write to" % (what, v["text"]))

    elif change.kind == "length":
        length = v["length"]
        if panel is not None:
            # Feeder_Length_m, and VD Length too when it holds a value (it is read first)
            if _has_value(_param(panel, revit_vd.P_LENGTH)):
                w.write(panel, revit_vd.P_LENGTH, length, what)
            w.first([(panel, revit_vd.P_FEEDER_LENGTH), (panel, revit_vd.P_LENGTH),
                     (circuit, revit_vd.P_LENGTH)], length, what)
            return
        # A final circuit: its loads' length (read first by the VD tool),
        # else the circuit's VD Length; whichever of them exist.
        try:
            loads = list(circuit.Elements)
        except Exception:
            loads = []
        done = 0
        for load in loads:
            names = [revit_vd.P_FEEDER_LENGTH]
            if _has_value(_param(load, revit_vd.P_LENGTH)):
                names.append(revit_vd.P_LENGTH)
            for name in names:
                if _param(load, name) is not None:
                    done += w.write(load, name, length, what)
        if _param(circuit, revit_vd.P_LENGTH) is not None:
            done += w.write(circuit, revit_vd.P_LENGTH, length, what)
        if not done:
            w.skipped.append(u"%s: length - no Feeder_Length_m on its loads / VD Length "
                             u"to write to" % what)

    elif change.kind == "incomer":
        from sld.revit_sld import P_INCOMER, P_INCOMER_TYPE
        rating, kind = revit_vd.P_UPSTREAM
        p = _param(panel, rating)
        if p is not None and not p.IsReadOnly:
            w.write(panel, rating, _breaker_text(v["trip"], v["frame"]), what)
            if v.get("device"):
                w.write(panel, kind, v["device"], what)
            return
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
    """Write the changes in one undo step. Returns (written, skipped
    messages, [] - no parameter is ever added)."""
    if not changes:
        return 0, [], []
    t = Transaction(doc, "LV Schematic Editor: Save")
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
    return w.written, w.skipped, []
