# -*- coding: utf-8 -*-
from firealarm.report import summarize


class Hit(object):
    def __init__(self, ceiling=True):
        self.ceiling = ceiling


class Layout(object):
    uncovered = 0


class Plan(object):
    def __init__(self, label, placed=0, heights=(), problem="", failed=(), existing=0,
                 on_slab=0):
        self.label, self.problem = label, problem
        self.placed = list(range(placed))
        self.failed = list(failed)
        self.existing = list(range(existing))
        self.layout = None if problem else Layout()
        self.spots = [(0, 0, Hit()) for _ in range(placed - on_slab)] + \
                     [(0, 0, Hit(False)) for _ in range(on_slab)]
        self._heights = list(heights)

    def ceiling_heights(self):
        return self._heights


def test_summary_lines():
    plans = [
        Plan("101 OFFICE", placed=6, heights=[2.7] * 6),
        Plan("102 LOBBY", placed=3, heights=[3.0, 3.6, 3.6], on_slab=1),
        Plan("103 SHAFT", problem="not placed or not enclosed"),
        Plan("104 STORE", placed=1, heights=[2.4],
             failed=["no ceiling or slab above"] * 2),
    ]
    headline, details = summarize(plans, "smoke")
    assert headline == "10 smoke detectors placed in 3 spaces. 2 spaces need a look."
    lines = details.splitlines()
    assert lines[0] == "101 OFFICE: 6 detectors, ceiling 2.70 m"
    assert lines[1] == "102 LOBBY: 3 detectors, ceiling 3.00-3.60 m, 1 on the slab (no ceiling found)"
    assert lines[2] == "103 SHAFT: skipped, not placed or not enclosed"
    assert lines[3] == "104 STORE: 1 detector, ceiling 2.40 m"
    assert lines[4] == "    not placed (2): no ceiling or slab above"


def test_summary_existing():
    plans = [Plan("101", placed=2, heights=[2.7, 2.7], existing=2)]
    assert summarize(plans, "heat", replaced=True)[0] == \
        "2 heat detectors placed in 1 space. 2 existing ones replaced."
    assert summarize(plans, "heat", replaced=False)[0] == \
        "2 heat detectors placed in 1 space. 2 existing ones kept."
