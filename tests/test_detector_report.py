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


class LoopResult(object):
    def __init__(self, number, devices, length, failed=()):
        self.number, self.devices, self.length = number, devices, length
        self.lines = devices + 1
        self.failed = list(failed)


def test_loop_summary():
    from firealarm.report import summarize_loops
    results = [LoopResult(1, 120, 431.4), LoopResult(2, 87, 250.0, failed=["too short"] * 2)]
    headline, details = summarize_loops("L1 - FIRE ALARM", results, "FACP : Main", False,
                                        replaced=12)
    assert headline == ("2 loops drawn in 'L1 - FIRE ALARM': 207 devices. "
                        "12 old loop lines replaced. Some lines could not be drawn.")
    lines = details.splitlines()
    assert lines[0] == "Start: FACP : Main (not counted)"
    assert lines[1] == "FA Loop 1: 120 devices, 431 m of line"
    assert lines[2] == "FA Loop 2: 87 devices, 250 m of line"
    assert lines[3] == "    not drawn (2): too short"
    headline, details = summarize_loops("L2", [LoopResult(3, 1, 12.0)], "Detector : Smoke", True)
    assert headline == "1 loop drawn in 'L2': 1 device."
    assert details.splitlines()[0] == "Start: Detector : Smoke (device 1 of loop 3)"
