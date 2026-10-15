# -*- coding: utf-8 -*-
"""Transformer and PFC typed in Power Studio for an MDB or EMDB.

Most models have no transformer element, so the office SLD's transformer
under the MDB (and the PFC bank on one of its ways) is ticked in Power
Studio and every value is typed by hand. Kept per project (sld.settings);
nothing is read from or written to Revit for it. A spec:

    {"board": "MDB-01",
     "tx": {"name": "TR-01", "kva": "1000", "voltage": "11/0.4kV",
            "type": "OIL TYPE TRANSFORMER",
            "cable": "7 SC 630mm² Cu/XLPE/AWA/PVC", "mv": "MV CABLE FROM TAQA"},
     "pfc": {"kvar": "300", "rating": "600", "cable": "2X(4X150)mm² CU/XLPE/SWA/PVC"}}

tx / pfc: None (or missing) when not ticked.
"""
from __future__ import division

from sld.model import (MAIN_BOARD, PFC, SPARE, CircuitInfo, EquipmentInfo, Way,
                       _next_way_number, parse_amps, trim_number)

TX_FIELDS = (("name", "Name", "TR-01"), ("kva", "kVA", ""),
             ("voltage", "Voltage", "11/0.4kV"), ("type", "Type", "OIL TYPE TRANSFORMER"),
             ("cable", "Cable to the board", ""), ("mv", "MV cable text", "MV CABLE FROM TAQA"))
PFC_FIELDS = (("kvar", "kVAR", ""), ("rating", "Breaker (AT)", ""), ("cable", "Cable", ""))
PFC_ID = "pfc:"


def defaults(fields):
    return dict((k, v) for k, _, v in fields)


def board_supply(specs, board_name):
    """(tx dict or None, pfc dict or None) of a board."""
    key = (board_name or "").strip().upper()
    spec = next((s for s in specs or [] if (s.get("board") or "").strip().upper() == key), {})
    return spec.get("tx"), spec.get("pfc")


def set_supply(specs, board_name, part, values):
    """Specs with the board's 'tx' or 'pfc' set to values (None: removed)."""
    key = (board_name or "").strip().upper()
    out, found = [], False
    for s in specs or []:
        s = dict(s)
        if (s.get("board") or "").strip().upper() == key:
            found = True
            s[part] = dict(values) if values is not None else None
        out.append(s)
    if not found and values is not None:
        out.append({"board": board_name, part: dict(values)})
    return clean_specs(out)


def clean_specs(specs):
    out = []
    for s in specs or []:
        board = (s.get("board") or "").strip()
        tx, pfc = s.get("tx"), s.get("pfc")
        if not board or not (tx or pfc):
            continue
        spec = {"board": board}
        if tx:
            spec["tx"] = dict((k, (u"%s" % (tx.get(k) or "")).strip()) for k, _, _ in TX_FIELDS)
        if pfc:
            spec["pfc"] = dict((k, (u"%s" % (pfc.get(k) or "")).strip()) for k, _, _ in PFC_FIELDS)
        out.append(spec)
    return out


def tx_description(tx):
    """Lines beside the transformer: voltage, kVA, type."""
    lines = []
    if tx.get("voltage"):
        lines.append(tx["voltage"])
    kva = parse_amps(tx.get("kva"))
    if kva:
        lines.append("%sKVA" % trim_number(kva, 1))
    lines.extend(l for l in (tx.get("type") or "").split("\n") if l.strip())
    return lines


def pfc_text(pfc):
    kvar = parse_amps((pfc or {}).get("kvar"))
    return "(%s KVAR)" % trim_number(kvar, 1) if kvar else ""


def apply_supply(schematic, specs):
    """Put each spec's transformer under its board (drawn as the main supply,
    in the substation band) and add its PFC way. Returns warnings."""
    from sld.riser import _detach
    warnings = []
    by_name = dict((b.name.strip().upper(), b) for b in schematic.boards())
    for spec in specs or []:
        b = by_name.get((spec.get("board") or "").strip().upper())
        if b is None:
            warnings.append("Transformer / PFC: %s is not in the model." % spec.get("board"))
            continue
        tx, pfc = spec.get("tx"), spec.get("pfc")
        if tx:
            if b.parent is not None or b.feed_pass_through is not None:
                parent = b.parent
                _detach(schematic, b)
                warnings.append("%s: drawn fed from its transformer %s, not from %s." % (
                    b.name, tx.get("name") or "TR", parent.name if parent else "its supply"))
            if b not in schematic.roots:
                schematic.roots.append(b)
            b.role = MAIN_BOARD
            b.ats = None
            b.transformer = EquipmentInfo("tx:" + b.id, tx.get("name") or "TR",
                                          description=tx_description(tx))
            if tx.get("cable"):
                b.equipment.incoming_cable = tx["cable"]
            b.mv_cable = tx.get("mv") or ""
        if pfc:
            _add_pfc_way(b, pfc)
    # the MDB first, the life safety (E...) boards beside it on its right
    schematic.roots.sort(key=lambda r: (r.is_main and r.name.strip().upper().startswith("E")))
    return warnings


def _add_pfc_way(board, pfc):
    """The PFC bank on a new way, before the spares (they move up one)."""
    c = CircuitInfo(PFC_ID + board.id, board.id, "", "PFC", rating=pfc.get("rating") or "",
                    poles="3", cable=pfc.get("cable") or "")
    way = Way(c, PFC, "", "PFC")
    way.pfc_text = pfc_text(pfc)
    first_spare = next((i for i, w in enumerate(board.ways) if w.kind == SPARE), None)
    if first_spare is None:
        way.label = str(_next_way_number([w.label for w in board.ways]))
        board.ways.append(way)
    else:
        way.label = board.ways[first_spare].label
        for w in board.ways[first_spare:]:
            if (w.label or "").isdigit():
                w.label = str(int(w.label) + 1)
        board.ways.insert(first_spare, way)
