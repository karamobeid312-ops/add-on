# -*- coding: utf-8 -*-
"""Data behind the LV Schematic Editor window, kept free of Revit and WPF.

Boards and their ways are shown as text values the user can change:
breakers (AT / AF / type), cables (runs, cores, size, conductor,
insulation, armour, earth) and lengths. The voltage drop is worked out
again with the Voltage Drop tool after every change. `changes()` lists
what Save to Revit has to write (see revit_edit).
"""
from __future__ import division

from sld import cablespec, style
from sld.model import (PFC, SPARE, add_spares, breaker_lines, frame_rating, is_sub_main,
                       parse_amps, parse_protection, trim_number, way_positions)

FIELDS = ("at", "af", "device", "runs", "cores", "size", "material", "insulation",
          "armour", "earth", "length")
CABLE_FIELDS = ("runs", "cores", "size", "material", "insulation", "armour", "earth")
BREAKER_FIELDS = ("at", "af", "device")
BOARD_FIELDS = ("incomer_at", "incomer_af", "incomer_device", "fault_level", "ways",
                "spares", "spare_at", "spare_af", "spare_device")

TRIPS = ("6", "10", "16", "20", "25", "32", "40", "50", "63", "80", "100", "125", "160",
         "200", "250", "315", "400", "500", "630", "800", "1000", "1250", "1600", "2000",
         "2500", "3200", "4000")
SIZES = ("1.5", "2.5", "4", "6", "10", "16", "25", "35", "50", "70", "95", "120", "150",
         "185", "240", "300", "400", "500", "630")
DEVICES = ("MCCB", "MCB", "ACB", "MCS", "RCBO")
CHOICES = {
    "at": TRIPS, "af": tuple(str(f) for f in style.ACB_FRAMES[:0] + style.MCCB_FRAMES) +
    ("2000", "2500", "3200", "4000"),
    "device": DEVICES, "runs": ("1", "2", "3", "4", "5", "6"),
    "cores": ("1", "2", "3", "4", "5"), "size": SIZES, "earth": SIZES,
    "material": cablespec.MATERIALS, "insulation": cablespec.INSULATIONS,
    "armour": ("SWA", "AWA", "NONE"),
    "spares": ("0", "1", "2", "3", "4", "5", "6"),
}
CHOICES["incomer_at"], CHOICES["spare_at"] = TRIPS, TRIPS
CHOICES["incomer_af"] = CHOICES["spare_af"] = CHOICES["af"]
CHOICES["incomer_device"] = CHOICES["spare_device"] = DEVICES
CHOICES["fault_level"] = ("6kA", "10kA", "16kA", "25kA", "35kA", "50kA", "65kA")
_TEXT = ("material", "insulation", "armour", "device", "incomer_device", "spare_device")


def _num(value):
    return trim_number(value, 2) if value is not None else ""


def _poles_text(poles):
    try:
        return {1: "SP", 2: "DP", 3: "TP", 4: "TPN"}.get(int(poles), "%sP" % poles)
    except (TypeError, ValueError):
        return ""


def _number(text):
    text = (u"%s" % (text or "")).strip().replace(",", ".")
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        value = parse_amps(text)
        if value is None:
            raise ValueError("not a number")
    if value <= 0:
        raise ValueError("must be more than 0")
    return value


def _cable_values(spec):
    if spec is None:
        return dict((f, "") for f in CABLE_FIELDS)
    return {"runs": str(spec.runs or 1), "cores": str(spec.cores or ""),
            "size": _num(spec.size), "material": spec.material or "",
            "insulation": spec.insulation or "", "armour": spec.armour or "NONE",
            "earth": _num(spec.earth_size)}


class Change(object):
    """One thing to write to Revit: kind is breaker, cable, length,
    incomer, fault_level, ways or spares."""

    def __init__(self, kind, element_id, circuit_id=None, **values):
        self.kind = kind
        self.element_id = element_id     # fed panel (or board) UniqueId, None for a final circuit
        self.circuit_id = circuit_id     # circuit UniqueId
        self.values = values

    def __repr__(self):
        return "Change(%s, %s, %s, %r)" % (self.kind, self.element_id, self.circuit_id,
                                          self.values)


class WayItem(object):
    """A way of a board as shown in the grid."""

    def __init__(self, way, board):
        c = way.circuit
        self.way = way
        self.board = board
        self.key = c.id
        self.label = way.label
        self.feeds = way.name
        self.kind = way.kind
        self.poles = _poles_text(c.poles)
        self.spare = way.kind == SPARE
        self.added = c.id.startswith("spare:")
        self.errors = {}
        self.vd, self.vd_over, self.vd_tip = "", False, ""
        trip, frame, device = self._breaker()
        self.values = {"at": _num(trip), "af": _num(frame or frame_rating(trip)),
                       "device": device or style.WAY_DEVICE,
                       "length": _num(c.length_m)}
        self.spec = cablespec.parse(c.cable) if not (self.spare or way.kind == PFC) else None
        self.values.update(_cable_values(self.spec))
        if c.vd_percent is not None:
            self.vd = "%.2f" % c.vd_percent
        self.saved = dict(self.values)

    @property
    def target_id(self):
        return self.way.target_id

    def _breaker(self):
        w, c = self.way, self.way.circuit
        if w.target is not None and w.target.upstream_protection:
            trip, frame, device = parse_protection(w.target.upstream_protection)
            if trip is not None:
                return trip, frame or parse_amps(c.frame), device
        return parse_amps(c.rating), parse_amps(c.frame), c.device or None

    def editable(self, field):
        if self.added:
            return False
        if field in BREAKER_FIELDS:
            return True
        return field in FIELDS and not self.spare and self.kind != PFC

    def cable(self):
        """CableSpec from the values shown, None when there is no size."""
        v = self.values
        size = _try(_number, v["size"])
        if size is None:
            return None
        armour = v["armour"].upper()
        return cablespec.CableSpec(
            cores=int(_try(_number, v["cores"]) or 4), size=size,
            runs=int(_try(_number, v["runs"]) or 1), material=v["material"] or "CU",
            insulation=v["insulation"] or "XLPE",
            armour="" if armour in ("", "NONE", "-") else armour,
            sheath=self.spec.sheath if self.spec is not None else "PVC",
            earth_size=_try(_number, v["earth"]))

    def breaker(self):
        """(trip, frame, device) from the values shown."""
        v = self.values
        return _try(_number, v["at"]), _try(_number, v["af"]), v["device"] or None

    def breaker_text(self):
        trip, frame, device = self.breaker()
        return " / ".join(breaker_lines(trip, frame, device))


def _try(fn, value):
    try:
        return fn(value)
    except (TypeError, ValueError):
        return None


class BoardItem(object):
    def __init__(self, board, depth, parent_id):
        e = board.equipment
        self.board = board
        self.id = board.id
        self.name = board.name
        self.depth = depth
        self.parent_id = parent_id
        self.children = []
        self.warnings = []
        trip, frame, device = e._incomer()
        spare = next((w.circuit for w in board.ways if w.circuit is not None and
                      w.circuit.id.startswith("spare:")), None)
        s_trip, s_frame, s_device = parse_protection(e.spare_rating)
        if spare is not None and s_trip is None:
            s_trip, s_frame, s_device = (parse_amps(spare.rating), parse_amps(spare.frame),
                                         spare.device or None)
        self.values = {
            "incomer_at": _num(trip), "incomer_af": _num(frame or frame_rating(trip)),
            "incomer_device": device or "", "fault_level": e.fault_level or "",
            "ways": u"%s" % (e.ways or ""),
            "spares": str(sum(1 for w in board.ways if w.kind == SPARE)),
            "spare_at": _num(s_trip), "spare_af": _num(s_frame or frame_rating(s_trip)),
            "spare_device": s_device or (style.WAY_DEVICE if s_trip else ""),
        }
        self.saved = dict(self.values)


class Editor(object):
    """vd: optional dict(feeders=[calc.Feeder], settings=calc.Settings,
    kinds={panel id: source kind}) from revit_sld.extract(live=...)."""

    def __init__(self, schematic, vd=None, numbering="slots"):
        self.schematic = schematic
        self.numbering = numbering
        self.vd = vd or None
        self.boards, self.roots, self._ways, self._by_key = [], [], {}, {}
        for root in schematic.roots:
            self.roots.append(self._add_board(root, 0, None))
        self._recalculate()

    def _add_board(self, board, depth, parent_id):
        item = BoardItem(board, depth, parent_id)
        self.boards.append(item)
        self._load_ways(item)
        for child in board.children:
            item.children.append(self._add_board(child, depth + 1, board.id))
        return item

    def _load_ways(self, item):
        ways = [WayItem(w, item.board) for w in item.board.ways if w.circuit is not None]
        old = dict((w.key, w) for w in self._ways.get(item.id, []))
        for w in ways:
            if w.key in old and not w.added:     # keep what was typed
                w.values, w.saved, w.errors = old[w.key].values, old[w.key].saved, \
                    old[w.key].errors
            self._by_key[w.key] = w
        self._ways[item.id] = ways

    def board(self, board_id):
        return next(b for b in self.boards if b.id == board_id)

    def ways(self, board_id):
        return self._ways.get(board_id, [])

    def way(self, key):
        return self._by_key[key]

    # ------------------------------------------------------------ editing

    def set_way(self, key, field, text):
        """Store a typed value. Returns the keys of the ways whose values
        changed (the way, ways sharing its breaker, and V.D downstream)."""
        w = self._by_key[key]
        if not w.editable(field):
            return []
        text = (u"%s" % (text if text is not None else "")).strip()
        if field in _TEXT:
            text = text.upper()
        w.errors.pop(field, None)
        if field in ("at", "af", "size", "earth", "length", "runs", "cores") and text:
            try:
                value = _number(text)
                text = trim_number(value, 2)
            except ValueError as error:
                w.errors[field] = u"%s: %s" % (text, error)
        w.values[field] = text
        changed = [key]
        if field in BREAKER_FIELDS and w.target_id:
            for other in self._by_key.values():
                if other is not w and other.target_id == w.target_id:
                    other.values[field] = text
                    changed.append(other.key)
        if field in BREAKER_FIELDS + CABLE_FIELDS + ("length",):
            before = dict((k, (x.vd, x.vd_over)) for k, x in self._by_key.items())
            self._recalculate()
            changed += [k for k, x in self._by_key.items()
                        if (x.vd, x.vd_over) != before[k] and k not in changed]
        return changed

    def set_board(self, board_id, field, text):
        """Store a board value. Returns True when its ways changed (spares)."""
        b = self.board(board_id)
        text = (u"%s" % (text if text is not None else "")).strip()
        if field in _TEXT:
            text = text.upper()
        b.values[field] = text
        if field not in ("spares", "spare_at", "spare_af", "spare_device"):
            return False
        e = b.board.equipment
        e.spares = text if field == "spares" else b.values["spares"]
        e.spare_rating = self._spare_rating(b)
        b.board.ways = [w for w in b.board.ways
                        if w.circuit is None or not w.circuit.id.startswith("spare:")]
        b.warnings = add_spares(b.board, self.numbering, b.board.phases)
        self._load_ways(b)
        return True

    def _spare_rating(self, b):
        v = b.values
        trip = _try(_number, v["spare_at"])
        if trip is None:
            return ""
        frame = _try(_number, v["spare_af"])
        text = "%sAT" % trim_number(trip, 1)
        if frame:
            text += "/%sAF" % trim_number(frame, 1)
        return (text + " " + (v["spare_device"] or "")).strip()

    def preview(self, key):
        w = self._by_key[key]
        spec = w.cable()
        return (spec.text() if spec is not None else ""), w.breaker_text()

    # ------------------------------------------------------------ voltage drop

    def _feeder_id(self, w, by_id):
        if w.target_id and w.target_id in by_id:
            return w.target_id
        return w.key

    def _recalculate(self):
        if not self.vd:
            return
        from vdrop import calc
        feeders = self.vd["feeders"]
        by_id = dict((f.id, f) for f in feeders)
        for w in self._by_key.values():
            if w.spare or w.kind == PFC:
                continue
            fid = self._feeder_id(w, by_id)
            f = by_id.get(fid)
            if f is None:
                length = _try(_number, w.values["length"])
                if length is None or w.target_id:
                    continue
                c = w.way.circuit
                f = calc.Feeder(
                    fid, w.board.id, w.board.name, w.feeds, length=length,
                    phases=3 if w.poles in ("TP", "TPN") else 1, tcl_kw=c.connected_kw,
                    source_kind=self.vd.get("kinds", {}).get(w.board.id, calc.BOARD))
                feeders.append(f)
                by_id[fid] = f
            spec = w.cable()
            if spec is not None:
                f.cable = spec.vd_cable()
                f.notes = [n for n in f.notes if not n.startswith(("VD Cable", "wire size",
                                                                   "no wire size"))]
            length = _try(_number, w.values["length"])
            if length is not None:
                f.length = length
                f.notes = [n for n in f.notes if not n.startswith(("VD Length",
                                                                   "Feeder_Length"))]
            trip = w.breaker()[0]
            if trip is not None:
                f.breaker = trip
        result = calc.calculate(feeders, self.vd["settings"])
        rows = dict((r.feeder.id, r) for r in result.rows())
        for w in self._by_key.values():
            r = rows.get(self._feeder_id(w, by_id))
            if r is None or w.spare:
                continue
            if r.total_percent is None:
                w.vd, w.vd_over = "n/a", False
            else:
                w.vd, w.vd_over = "%.2f" % r.total_percent, r.vd_ok is False
            tip = []
            if r.vd_percent is not None:
                tip.append(u"This cable %.2f%%, limit %s%%" % (r.vd_percent,
                                                              trim_number(r.limit, 2)))
            try:
                tip += list(r.remarks())
            except Exception:
                pass
            w.vd_tip = u"\n".join(t for t in tip if t)

    # ------------------------------------------------------------ results

    def warnings(self):
        out = []
        for b in self.boards:
            out += b.warnings
            if is_sub_main(b.board) and way_positions(b.board.ways, b.board.phases) > \
                    style.MAX_WAYS:
                out.append(u"%s has more than %d ways." % (b.name, style.MAX_WAYS))
        for b in self.boards:
            for w in self.ways(b.id):
                if w.vd_over:
                    out.append(u"%s way %s (%s): V.D %s%% is over the limit." % (
                        b.name, w.label, w.feeds, w.vd))
                for message in w.errors.values():
                    out.append(u"%s way %s: %s" % (b.name, w.label, message))
        return out

    def dirty(self):
        return bool(self.changes())

    def changes(self):
        out, seen = [], set()
        for b in self.boards:
            out += self._board_changes(b)
            for w in self.ways(b.id):
                if w.added:
                    continue
                v, s = w.values, w.saved
                if any(v[f] != s[f] for f in BREAKER_FIELDS):
                    trip, frame, device = w.breaker()
                    key = ("breaker", w.target_id or w.key)
                    if trip is not None and key not in seen:
                        seen.add(key)
                        out.append(Change("breaker", w.target_id, w.key, trip=trip,
                                          frame=frame, device=v["device"]))
                if any(v[f] != s[f] for f in CABLE_FIELDS):
                    spec = w.cable()
                    if spec is not None:
                        out.append(Change("cable", w.target_id, w.key, text=spec.text()))
                if v["length"] != s["length"]:
                    length = _try(_number, v["length"])
                    if length is not None:
                        out.append(Change("length", w.target_id, w.key, length=length))
        return out

    def _board_changes(self, b):
        v, s, out = b.values, b.saved, []
        if any(v[f] != s[f] for f in ("incomer_at", "incomer_af", "incomer_device")):
            trip = _try(_number, v["incomer_at"])
            if trip is not None:
                out.append(Change("incomer", b.id, trip=trip,
                                  frame=_try(_number, v["incomer_af"]),
                                  device=v["incomer_device"]))
        if v["fault_level"] != s["fault_level"] and v["fault_level"]:
            out.append(Change("fault_level", b.id, text=v["fault_level"]))
        if v["ways"] != s["ways"] and v["ways"]:
            out.append(Change("ways", b.id, text=v["ways"]))
        if any(v[f] != s[f] for f in ("spares", "spare_at", "spare_af", "spare_device")):
            out.append(Change("spares", b.id, count=v["spares"],
                              rating=self._spare_rating(b)))
        return out

    def mark_saved(self):
        for b in self.boards:
            b.saved = dict(b.values)
        for w in self._by_key.values():
            w.saved = dict(w.values)
