# -*- coding: utf-8 -*-
from firealarm.loop_diagram import (DETECTION_STYLE, SOUNDER_STYLE, Device, group_loops,
                                    loop_diagram)
from firealarm.report import summarize_loop_diagram


def devices():
    out = [Device("L1/SD-%02d" % k) for k in (3, 1, 2)]
    out += [Device("l2/sb-%02d" % k) for k in (1, 2)]
    out += [Device(""), Device("SMOKE 1"), Device("L1/MCP-04", "MCP")]
    return out


def test_grouped_by_loop_in_address_order():
    loops, bad = group_loops(devices())
    assert [l.number for l in loops] == [1, 2]
    assert [d.address for d in loops[0].devices] == ["L1/SD-01", "L1/SD-02", "L1/SD-03",
                                                     "L1/MCP-04"]
    assert not loops[0].sounder and loops[1].sounder
    assert len(bad) == 2


def test_addresses_drawn_under_devices_and_loop_colours():
    diagram = loop_diagram(devices(), "SFACP-01")
    texts = [t.text for t in diagram.drawing.texts]
    for address in ("L1/SD-01", "L1/MCP-04", "L2/SB-02"):
        assert address in texts
    assert texts.count("START") == 2 and texts.count("END") == 2
    styles = set(l.style for l in diagram.drawing.lines)
    assert DETECTION_STYLE in styles and SOUNDER_STYLE in styles
    assert any("SFACP-01" in t for t in texts)


def test_long_loop_comes_back_on_a_second_row_in_order():
    items = [Device("L1/SD-%02d" % k) for k in range(1, 8)]
    diagram = loop_diagram(items, per_row=4)
    loop = diagram.loops[0]
    assert [len(r) for r in loop.rows] == [4, 3]
    at = dict((t.text, (t.x, t.y)) for t in diagram.drawing.texts if t.text.startswith("L1/"))
    # row 1 left to right, row 2 above it right to left, continuing the order
    assert at["L1/SD-01"][0] < at["L1/SD-04"][0]
    assert at["L1/SD-05"][1] > at["L1/SD-04"][1]
    assert at["L1/SD-05"][0] == at["L1/SD-04"][0]
    assert at["L1/SD-07"][0] < at["L1/SD-05"][0]


def test_duplicates_warned():
    diagram = loop_diagram([Device("L1/SD-01"), Device("L1/HD-01")])
    assert diagram.warnings and "used twice" in diagram.warnings[0]


class Run(object):
    def __init__(self, diagram):
        self.diagram = diagram
        self.view_name = "FA Loop Diagram"
        self.panel = "SFACP-01"
        self.unaddressed = [(1, "Smoke : Photo", "")]


def test_summary():
    items = [Device("L1/SD-01"), Device("L1/SD-03"), Device("L2/SB-01")]
    headline, details = summarize_loop_diagram(Run(loop_diagram(items)))
    assert headline == ("Loop diagram drawn in 'FA Loop Diagram': 2 loops, 3 devices. "
                        "1 device without an address left out.")
    assert "L1: 2 devices, L1/SD-01 to L1/SD-03" in details
    assert "numbers missing: 02" in details
    assert "L2 (sounders)" in details
