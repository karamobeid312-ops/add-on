# -*- coding: utf-8 -*-
"""Revit-independent model of the LV schematic.

Turns flat equipment/circuit lists (read from Revit) into boards with
numbered ways, following the office drawing standard:

* A *board* (MDB, SMDB, USMDB...) is drawn as a full switchboard with a
  busbar and every outgoing way. Equipment is a board when it feeds other
  equipment, is fed from a UPS/transformer, or has no upstream supply.
* A *main board* is a board with no upstream board (fed from a transformer
  or the utility). It is drawn in the SUBSTATION band with ACB, meters, SPD.
* A *DB* (LDB, PDB, DB-...) only feeds final circuits and is drawn as a
  box at the end of its way.
* A *UPS* (or a transformer fed from a board) is drawn between the ways
  that supply it and the board it feeds.

Kept free of Revit imports so it runs under IronPython 2.7, CPython 3 and
pytest.
"""
from __future__ import division

import re

from sld import style

# equipment roles
BOARD = "board"
MAIN_BOARD = "main_board"
DB = "db"
UPS = "ups"
TRANSFORMER = "transformer"

# way kinds
FEEDER = "feeder"          # to another board, via a riser
TO_UPS = "to_ups"          # into a UPS / pass-through box
DB_BOX = "db_box"          # final DB drawn as a box
ISOLATOR = "isolator"      # single piece of equipment / final circuit
SPARE = "spare"
PFC = "pfc"                # power factor correction bank

_SYMBOL_ROLES = {
    "BOARD": BOARD, "SMDB": BOARD, "MAIN": MAIN_BOARD, "MDB": MAIN_BOARD,
    "DB": DB, "UPS": UPS, "TRANSFORMER": TRANSFORMER, "TR": TRANSFORMER,
}
_SYMBOL_WAYS = {
    "ISOLATOR": ISOLATOR, "LOAD": ISOLATOR, "SPARE": SPARE, "PFC": PFC,
    "DB": DB_BOX,
}
_PFC_RE = re.compile(r"\bPFC\b|POWER\s*FACTOR|CAPACITOR", re.IGNORECASE)
_POLES = {1: "SP", 2: "DP", 3: "TP", 4: "TPN"}
_AMPS_RE = re.compile(r"\d+(?:[.,]\d+)?")


def parse_amps(text):
    """First number in '63 A', '63', '1600A'... or None."""
    if isinstance(text, (int, float)):
        return float(text) if text > 0 else None
    match = _AMPS_RE.search(u"%s" % (text or ""))
    if not match:
        return None
    value = float(match.group(0).replace(",", "."))
    return value if value > 0 else None


def frame_rating(trip, frames=None):
    """Smallest standard frame (AF) that takes the trip rating (AT)."""
    if trip is None:
        return None
    frames = frames or style.MCCB_FRAMES
    for f in frames:
        if f >= trip - 1e-6:
            return f
    return trip


def breaker_lines(rating, frame=None, device=None, frames=None):
    """['40AT', '100AF', 'MCCB'] printed beside a breaker; just the device
    when the rating is unknown. frame: typed frame (else the standard one)."""
    device = device or style.WAY_DEVICE
    trip = parse_amps(rating)
    if trip is None:
        return [device]
    af = parse_amps(frame) or frame_rating(trip, frames)
    return ["%sAT" % trim_number(trip, 1), "%sAF" % trim_number(af, 1), device]


class EquipmentInfo(object):
    """A piece of electrical equipment read from the model."""

    def __init__(self, id, name, level_name="", level_elevation=0.0,
                 location="", form="", ways=None, family_name="",
                 part_type="", symbol="", description=None,
                 incoming_cable="", details=None, connected_kw=None, demand_kw=None,
                 mains_rating=None, incomer_rating=None, incomer_frame="",
                 phases=3, neutral=True, fault_level=""):
        self.id = id
        self.name = name
        self.level_name = level_name or ""
        self.level_elevation = level_elevation or 0.0
        self.location = location or ""
        self.form = form or ""
        self.ways = ways                      # declared number of ways
        self.family_name = family_name or ""
        self.part_type = (part_type or "").lower()
        self.symbol = (symbol or "").strip().upper()   # 'SLD Symbol' override
        self.description = [d for d in (description or []) if d]
        self.incoming_cable = incoming_cable or ""
        self.details = [d for d in (details or []) if d]
        self.connected_kw = connected_kw      # CL of everything it feeds
        self.demand_kw = demand_kw            # DL (after demand factors)
        self.mains_rating = mains_rating      # busbar rating, A
        self.incomer_rating = incomer_rating  # incoming breaker trip, A
        self.incomer_frame = incomer_frame    # 'SLD Frame' typed on it
        self.phases = phases
        self.neutral = neutral
        self.fault_level = fault_level or ""  # e.g. '35 kA'

    def supply_text(self):
        """'160A,3PH+N+E,35kA FOR 1 SEC': busbar, system and fault level,
        the parts that are known."""
        parts = []
        if parse_amps(self.mains_rating):
            parts.append("%sA" % trim_number(parse_amps(self.mains_rating), 1))
        parts.append("%dPH%s+E" % (3 if self.phases != 1 else 1, "+N" if self.neutral else ""))
        fault = (self.fault_level or "").strip()
        if fault:
            ka = parse_amps(fault)
            if ka is not None and ka >= 1000 and "K" not in fault.upper():
                ka /= 1000.0                  # typed in amps
            text = "%skA" % trim_number(ka, 1) if ka is not None else fault.upper()
            parts.append("%s FOR 1 SEC" % text)
        return ",".join(parts)

    def incomer_lines(self, device=None, frames=None):
        return breaker_lines(self.incomer_rating, self.incomer_frame, device, frames)


class CircuitInfo(object):
    """A power circuit fed from `source_id`."""

    def __init__(self, id, source_id, circuit_number="", load_name="",
                 rating="", poles="", voltage="", load="", wire_size="",
                 fed_equipment_ids=None, branch_load_count=0, cable="",
                 start_slot=None, is_spare=False, symbol="", connected_kw=None,
                 length_m=None, vd_percent=None, frame=""):
        self.id = id
        self.source_id = source_id
        self.circuit_number = circuit_number or ""
        self.load_name = load_name or ""
        self.rating = rating or ""
        self.poles = poles or ""
        self.voltage = voltage or ""
        self.load = load or ""
        self.wire_size = wire_size or ""
        self.fed_equipment_ids = list(fed_equipment_ids or [])
        self.branch_load_count = branch_load_count
        self.cable = cable or ""  # e.g. 4Cx4mm² Cu/XLPE/PVC + 1Cx4mm² Cu/XLPE/PVC
        self.start_slot = start_slot
        self.is_spare = is_spare
        self.symbol = (symbol or "").strip().upper()
        self.connected_kw = connected_kw  # load of a final circuit
        self.length_m = length_m          # cable length (VD Length)
        self.vd_percent = vd_percent      # cumulative voltage drop at its end
        self.frame = frame or ""          # 'SLD Frame' typed on it, e.g. 250

    def cable_text(self):
        """BS/IEC cable description, or Revit's raw wire size as fallback."""
        return self.cable or self.wire_size

    def cable_lines(self):
        """Cable text split so the earth core ('+ 1Cx...') gets its own line."""
        parts = [p for p in self.cable_text().split(" + ") if p]
        return parts[:1] + ["+ " + p for p in parts[1:]]

    def breaker_text(self):
        """e.g. '63A TP'."""
        rating = re.sub(r"\s+", "", self.rating or "")
        try:
            poles = _POLES.get(int(self.poles), "%sP" % self.poles)
        except (TypeError, ValueError):
            poles = ""
        return " ".join(p for p in (rating, poles) if p)

    def breaker_lines(self):
        """['40AT', '100AF', 'MCCB'], printed beside its breaker."""
        return breaker_lines(self.rating, self.frame)


class Way(object):
    def __init__(self, circuit, kind, label, name, target=None):
        self.circuit = circuit
        self.kind = kind
        self.label = label        # way number printed at the busbar: 1, R9...
        self.name = name          # text at the end of the way
        self.target = target      # EquipmentInfo fed by this way, if any

    @property
    def target_id(self):
        return self.target.id if self.target is not None else None

    def rating_lines(self):
        """Cable, length and voltage drop, printed along the way (the
        breaker rating is printed beside the breaker)."""
        if self.circuit is None or self.kind in (SPARE, PFC):
            return []
        lines = list(self.circuit.cable_lines())
        vd = self.vd_text()
        if vd:
            lines.append(vd)
        return lines

    def vd_text(self):
        """'L:100m  V.D:2.97%', or the part that is known."""
        c = self.circuit
        if c is None or self.kind == SPARE:
            return ""
        parts = []
        if c.length_m is not None:
            parts.append("L:%sm" % trim_number(c.length_m, 1))
        if c.vd_percent is not None:
            parts.append("V.D:%.2f%%" % c.vd_percent)
        return "  ".join(parts)

    def loads(self):
        """(CL kW, DL kW) of what the way feeds; None when unknown.

        Equipment uses its own totals; a final circuit has no demand
        factor, so its DL is its CL.
        """
        if self.circuit is None or self.kind in (SPARE, PFC):
            return None, None
        if self.target is not None:
            return self.target.connected_kw, self.target.demand_kw
        return self.circuit.connected_kw, self.circuit.connected_kw


class PassThrough(object):
    """A UPS (or transformer fed from a board) drawn above its input ways."""

    def __init__(self, equipment, board, input_ways, kind=UPS):
        self.equipment = equipment
        self.kind = kind                # UPS or TRANSFORMER
        self.board = board              # Board whose ways feed it
        self.input_ways = input_ways
        self.outputs = []               # Boards it feeds


class Board(object):
    def __init__(self, equipment, role):
        self.equipment = equipment
        self.role = role
        self.ways = []
        self.pass_throughs = []
        self.feed_way = None            # Way on the parent board feeding this
        self.feed_pass_through = None   # or the PassThrough feeding this
        self.parent = None              # parent Board
        self.transformer = None         # EquipmentInfo drawn under a main board
        self.children = []              # Boards fed from this one

    @property
    def id(self):
        return self.equipment.id

    @property
    def name(self):
        return self.equipment.name

    @property
    def is_main(self):
        return self.role == MAIN_BOARD

    def load_totals(self):
        """(connected kW, diversity factor, demand kW) summed over the ways,
        each piece of equipment counted once; None when no way has a load."""
        seen, cl, dl, any_load = set(), 0.0, 0.0, False
        for w in self.ways:
            if w.target_id is not None:
                if w.target_id in seen:
                    continue
                seen.add(w.target_id)
            c, d = w.loads()
            if c is None:
                continue
            any_load = True
            cl += c
            dl += d if d is not None else c
        if not any_load:
            return None
        return cl, (dl / cl if cl > 0 else None), dl

    def iter_tree(self):
        yield self
        for child in self.children:
            for b in child.iter_tree():
                yield b


class Schematic(object):
    def __init__(self, roots, warnings):
        self.roots = roots
        self.warnings = warnings

    def boards(self):
        for root in self.roots:
            for b in root.iter_tree():
                yield b


def trim_number(value, decimals=1):
    """'2.5', '100': no trailing zeros."""
    text = ("%%.%df" % decimals) % value
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def natural_key(text):
    """Sort key so that '2' < '10' and '1,3,5' < '2,4,6'."""
    return [(0, int(tok), "") if tok.isdigit() else (1, 0, tok.lower())
            for tok in re.findall(r"\d+|\D+", text or "")]


def _circuit_sort_key(c):
    slot = c.start_slot if c.start_slot is not None else 10 ** 6
    return (slot, natural_key(c.circuit_number), (c.load_name or "").lower())


def way_labels(circuits, phases=3, numbering="slots"):
    """Way numbers as printed on the board, for circuits in slot order.

    Ways are numbered 1, 2, 3... in order, whatever the panel's slot
    numbering. On a three-phase board consecutive single-pole circuits share
    a way, one per phase: R9, Y9, B9. With numbering='revit' Revit's circuit
    numbers are printed unchanged.
    """
    if numbering == "revit":
        return [c.circuit_number for c in circuits]
    labels, way, phase = [], 0, 3
    for c in circuits:
        try:
            poles = int(c.poles)
        except (TypeError, ValueError):
            poles = 3
        if phases == 3 and poles == 1:
            if phase >= 3:
                way, phase = way + 1, 0
            labels.append("RYB"[phase] + str(way))
            phase += 1
        else:
            way, phase = way + 1, 3
            labels.append(str(way))
    return labels


def _role(eq, fed_by_role, feeds_equipment, has_feeder, fed_from_root_transformer):
    if eq.symbol in _SYMBOL_ROLES:
        return _SYMBOL_ROLES[eq.symbol]
    family = eq.family_name.upper()
    if eq.part_type == "transformer" or "TRANSFORMER" in family:
        return TRANSFORMER
    if "UPS" in family:
        return UPS
    if not has_feeder or fed_from_root_transformer:
        return MAIN_BOARD
    if (feeds_equipment or fed_by_role in (UPS, TRANSFORMER) or eq.part_type == "switchboard"
            or re.search(style.BOARD_NAME_PATTERN, eq.name or "", re.IGNORECASE)):
        return BOARD
    return DB


def build_schematic(equipment, circuits, phases_of=None, numbering="slots"):
    """Build boards/ways from flat equipment and circuit lists.

    phases_of: optional {equipment id: phase count} used for way numbering.
    """
    warnings = []
    eq_by_id = dict((e.id, e) for e in equipment)
    phases_of = phases_of or {}

    by_source = {}
    feeders = {}   # equipment id -> [circuits feeding it]
    for c in sorted(circuits, key=_circuit_sort_key):
        if c.source_id not in eq_by_id:
            continue
        by_source.setdefault(c.source_id, []).append(c)
        for fed in c.fed_equipment_ids:
            if fed != c.source_id and fed in eq_by_id:
                feeders.setdefault(fed, []).append(c)

    def primary_feeder(eq_id):
        lst = feeders.get(eq_id)
        return lst[0] if lst else None

    feeds_equipment = set(c.source_id for c in circuits
                          if c.source_id in eq_by_id and
                          any(f in eq_by_id and f != c.source_id for f in c.fed_equipment_ids))

    # Roles need the role of the upstream equipment; resolve top-down lazily.
    roles = {}

    def role_of(eq_id, stack=()):
        if eq_id in roles:
            return roles[eq_id]
        feeder = primary_feeder(eq_id)
        up_role, from_root_tr = None, False
        if feeder is not None and feeder.source_id not in stack:
            up_role = role_of(feeder.source_id, stack + (eq_id,))
            # Only a transformer with no supply of its own (the utility
            # transformer) makes a main board; one fed from a board is drawn
            # between that board and the panel it feeds.
            from_root_tr = up_role == TRANSFORMER and primary_feeder(feeder.source_id) is None
        roles[eq_id] = _role(eq_by_id[eq_id], up_role, eq_id in feeds_equipment,
                             feeder is not None, from_root_tr)
        return roles[eq_id]

    for e in equipment:
        role_of(e.id)

    for eq_id, lst in feeders.items():
        extra = [c for c in lst[1:]
                 if not (roles[eq_id] in (UPS, TRANSFORMER) and c.source_id == lst[0].source_id)]
        for c in extra:
            warnings.append("%s is fed by more than one circuit; using %s." % (
                eq_by_id[eq_id].name, _describe(lst[0], eq_by_id)))

    boards = {}
    for e in equipment:
        if roles[e.id] in (BOARD, MAIN_BOARD):
            boards[e.id] = Board(e, roles[e.id])
    pass_throughs = {}

    def is_primary(c, eq_id):
        lst = feeders.get(eq_id, [])
        if not lst:
            return False
        if roles[eq_id] in (UPS, TRANSFORMER):
            return c.source_id == lst[0].source_id
        return lst[0] is c

    for board in boards.values():
        phases = phases_of.get(board.id, 3)
        board_circuits = by_source.get(board.id, [])
        labels = way_labels(board_circuits, phases, numbering)
        for c, label in zip(board_circuits, labels):
            target = None
            for fed in c.fed_equipment_ids:
                if fed in eq_by_id and fed != board.id and is_primary(c, fed):
                    target = fed
                    break
            if c.symbol in _SYMBOL_WAYS:
                kind = _SYMBOL_WAYS[c.symbol]
            elif c.is_spare:
                kind = SPARE
            elif target is not None:
                kind = {BOARD: FEEDER, MAIN_BOARD: FEEDER, DB: DB_BOX,
                        UPS: TO_UPS, TRANSFORMER: TO_UPS}[roles[target]]
            elif _PFC_RE.search(c.load_name or ""):
                kind = PFC
            else:
                kind = ISOLATOR
            if kind == SPARE:
                name = "SPARE"
            elif target is not None:
                name = eq_by_id[target].name
            else:
                name = c.load_name or ("CKT %s" % c.circuit_number)
            board.ways.append(Way(c, kind, label, name,
                                  eq_by_id[target] if target is not None else None))

    # Pass-through boxes (UPS) sit on the board that feeds them.
    for board in boards.values():
        groups = {}
        for w in board.ways:
            if w.kind == TO_UPS:
                groups.setdefault(w.target_id, []).append(w)
        for target_id, ways in groups.items():
            pt = PassThrough(eq_by_id[target_id], board, ways, roles[target_id])
            board.pass_throughs.append(pt)
            pass_throughs[target_id] = pt

    # Link boards to what feeds them.
    for board in boards.values():
        feeder = primary_feeder(board.id)
        if feeder is None:
            continue
        src = feeder.source_id
        if src in boards:
            parent = boards[src]
            way = next((w for w in parent.ways if w.target_id == board.id), None)
            if way is not None and way.kind == FEEDER:
                board.feed_way = way
                board.parent = parent
        elif src in pass_throughs:
            pt = pass_throughs[src]
            pt.outputs.append(board)
            board.feed_pass_through = pt
            board.parent = pt.board
        elif roles.get(src) == TRANSFORMER:
            board.transformer = eq_by_id[src]
            board.equipment.incoming_cable = (board.equipment.incoming_cable or
                                              feeder.cable_text())

    for board in boards.values():
        if board.parent is not None:
            board.parent.children.append(board)
    for board in boards.values():
        board.children.sort(key=lambda b: _child_order(board, b))

    roots = sorted([b for b in boards.values() if b.parent is None],
                   key=lambda b: natural_key(b.name))
    for b in boards.values():
        if b.parent is not None and b.role == MAIN_BOARD:
            b.role = BOARD
    for b in roots:
        b.role = MAIN_BOARD
    # Feed loops: boards never reached from a root.
    reached = set()
    for r in roots:
        for b in r.iter_tree():
            reached.add(b.id)
    for b in sorted(boards.values(), key=lambda b: natural_key(b.name)):
        if b.id not in reached:
            warnings.append("%s is part of a feed loop; drawn as a separate source." % b.name)
            if b.parent is not None:
                b.parent.children.remove(b)
            b.parent, b.feed_way, b.feed_pass_through = None, None, None
            b.role = MAIN_BOARD
            roots.append(b)
            for x in b.iter_tree():
                reached.add(x.id)

    return Schematic(roots, warnings)


def _child_order(parent, child):
    if child.feed_way is not None:
        return (parent.ways.index(child.feed_way), 0)
    if child.feed_pass_through is not None:
        pt = child.feed_pass_through
        return (parent.ways.index(pt.input_ways[0]), pt.outputs.index(child) + 1)
    return (10 ** 6, 0)


def _describe(circuit, eq_by_id):
    src = eq_by_id.get(circuit.source_id)
    return "%s CKT %s" % (src.name if src else "?", circuit.circuit_number)
