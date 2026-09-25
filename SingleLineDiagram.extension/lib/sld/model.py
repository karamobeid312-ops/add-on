# -*- coding: utf-8 -*-
"""Revit-independent data model and tree builder for the single line diagram.

Kept free of any Revit imports so it runs under IronPython 2.7 (pyRevit's
default engine), CPython 3 and plain CPython for unit tests.
"""
from __future__ import division

import re

EQUIPMENT = "equipment"
BRANCH_CIRCUIT = "branch_circuit"


class EquipmentInfo(object):
    """A piece of electrical equipment (panel, switchboard, transformer...)."""

    def __init__(self, id, name, details=None):
        self.id = id
        self.name = name
        self.details = [d for d in (details or []) if d]


class CircuitInfo(object):
    """A power circuit fed from `source_id`.

    `fed_equipment_ids` are downstream equipment on the circuit (a feeder);
    `branch_load_count` counts ordinary loads (lights, receptacles...).
    """

    def __init__(self, id, source_id, circuit_number="", load_name="",
                 rating="", poles="", voltage="", load="", wire_size="",
                 fed_equipment_ids=None, branch_load_count=0):
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

    def breaker_text(self):
        """e.g. '20 A / 3P'."""
        parts = []
        if self.rating:
            parts.append(self.rating)
        if self.poles:
            parts.append("%sP" % self.poles)
        return " / ".join(parts)

    def feeder_label_lines(self):
        """Lines printed next to the breaker symbol of a feeder."""
        lines = []
        if self.circuit_number:
            lines.append("CKT %s" % self.circuit_number)
        if self.breaker_text():
            lines.append(self.breaker_text())
        if self.wire_size:
            lines.append(self.wire_size)
        return lines


class DiagramNode(object):
    def __init__(self, kind, id, title, details=None, feeder=None):
        self.kind = kind
        self.id = id
        self.title = title
        self.details = list(details or [])
        self.feeder = feeder  # CircuitInfo feeding this node, None for roots
        self.children = []

    def iter_nodes(self):
        yield self
        for child in self.children:
            for n in child.iter_nodes():
                yield n


class Diagram(object):
    def __init__(self, roots, warnings):
        self.roots = roots
        self.warnings = warnings

    def iter_nodes(self):
        for root in self.roots:
            for n in root.iter_nodes():
                yield n


def natural_key(text):
    """Sort key so that '2' < '10' and '1,3,5' < '2,4,6'."""
    return [(0, int(tok), "") if tok.isdigit() else (1, 0, tok.lower())
            for tok in re.findall(r"\d+|\D+", text or "")]


def _circuit_sort_key(circuit):
    return (natural_key(circuit.circuit_number), (circuit.load_name or "").lower())


def build_diagram(equipment, circuits, include_branch_circuits=False):
    """Turn flat equipment/circuit lists into a forest of DiagramNodes.

    Roots are equipment not fed from any other known equipment. Equipment
    left unreached (i.e. part of a feed loop) is promoted to a root and a
    warning is recorded, so every piece of equipment appears exactly once.
    """
    warnings = []
    equipment_by_id = {}
    for eq in equipment:
        equipment_by_id[eq.id] = eq

    circuits_by_source = {}
    feeder_of = {}  # equipment id -> CircuitInfo feeding it
    for c in sorted(circuits, key=_circuit_sort_key):
        if c.source_id not in equipment_by_id:
            continue
        circuits_by_source.setdefault(c.source_id, []).append(c)
        for fed_id in c.fed_equipment_ids:
            if fed_id == c.source_id or fed_id not in equipment_by_id:
                continue
            if fed_id in feeder_of:
                warnings.append(
                    "%s is fed by more than one circuit; using %s." % (
                        equipment_by_id[fed_id].name,
                        _describe(feeder_of[fed_id], equipment_by_id)))
                continue
            feeder_of[fed_id] = c

    visited = set()

    def make_equipment_node(eq_id, feeder):
        eq = equipment_by_id[eq_id]
        visited.add(eq_id)
        node = DiagramNode(EQUIPMENT, eq.id, eq.name, eq.details, feeder)
        for c in circuits_by_source.get(eq_id, []):
            for fed_id in c.fed_equipment_ids:
                if feeder_of.get(fed_id) is c and fed_id not in visited:
                    node.children.append(make_equipment_node(fed_id, c))
            if include_branch_circuits and c.branch_load_count > 0:
                node.children.append(_branch_node(c))
        return node

    roots = []
    ordered = sorted(equipment_by_id.values(), key=lambda e: natural_key(e.name))
    for eq in ordered:
        if eq.id not in feeder_of:
            roots.append(make_equipment_node(eq.id, None))
    for eq in ordered:
        if eq.id not in visited:
            warnings.append(
                "%s is part of a feed loop; drawn as a separate source." % eq.name)
            roots.append(make_equipment_node(eq.id, None))

    return Diagram(roots, warnings)


def _branch_node(circuit):
    title = circuit.load_name or ("Circuit %s" % circuit.circuit_number)
    details = []
    first = []
    if circuit.circuit_number:
        first.append("CKT %s" % circuit.circuit_number)
    if circuit.breaker_text():
        first.append(circuit.breaker_text())
    if first:
        details.append(", ".join(first))
    if circuit.load:
        details.append(circuit.load)
    return DiagramNode(BRANCH_CIRCUIT, circuit.id, title, details, circuit)


def _describe(circuit, equipment_by_id):
    src = equipment_by_id.get(circuit.source_id)
    return "%s CKT %s" % (src.name if src else "?", circuit.circuit_number)
