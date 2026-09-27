# -*- coding: utf-8 -*-
import pytest

import sample_riser
from firealarm.loops import loop_numbers
from firealarm.riser import SYMBOLS as SYMBOL_STYLE, WIRING, Segment, riser_layout
from firealarm.riser_symbols import BY_CODE, ORDER, guess, is_panel_name, resolve, symbol
from test_layout import overlaps


def sample():
    return riser_layout(*sample_riser.build())


# ---------------------------------------------------------------- symbols

@pytest.mark.parametrize("name,code", [
    ("Smoke Detector : Photoelectric", "SD"),
    ("FA_Optical Detector : Standard", "SD"),
    ("Smoke Detector : Above False Ceiling", "SDF"),
    ("Smoke Detector - Raised Floor : Std", "SDR"),
    ("Smoke Detector : Trench", "SDT"),
    ("Heat Detector : Rate of Rise", "HD"),
    ("Duct Smoke Detector : Duct", "DD"),
    ("Beam Detector : Transmitter", "BTX"),
    ("Optical Beam : RX", "BRX"),
    ("Manual Call Point : Break Glass", "MCP"),
    ("MCP : Standard", "MCP"),
    ("Fire Alarm Bell : 150mm", "BELL"),
    ("Sounder Strobe : Wall", "BELLS"),
    ("Strobe Light : Ceiling", "STC"),
    ("Visual Alarm Device : Wall", "STW"),
    ("Horn Strobe : H1", "HS"),
    ("Fire Telephone Jack : Std", "J"),
    ("Water Flow Switch : 100mm", "WFS"),
    ("Tamper Switch : Valve", "TS"),
    ("Monitor Module : Single Input", "MM"),
    ("Control Module : Relay", "CM"),
    ("Zone Module : Std", "ZM"),
    ("Linear Heat Detector : Cable", "LHD"),
    ("Linear Heat Detector Control Panel : Std", "LHDP"),
    ("VESDA : Aspirating", "HSSD"),
    ("Repeater Panel : FARP", "FARP"),
    ("End of Line : EOL", "EOL"),
    ("Loop Isolator : Std", "ISO"),
])
def test_symbol_guess(name, code):
    assert guess(name) == code


def test_unknown_type_gets_its_own_box():
    code = guess("Mystery Gadget : Type 1")
    assert code.startswith("?")
    assert symbol(code).description == "MYSTERY GADGET : TYPE 1"


def test_symbol_choice_order():
    name = "Smoke Detector : Photoelectric"
    assert resolve(name) == "SD"
    assert resolve(name, chosen="HD") == "HD"                     # chosen in FA Settings
    assert resolve(name, override="duct detector", chosen="HD") == "DD"   # FA Symbol parameter
    assert resolve(name, override="nonsense") == "SD"


def test_panels():
    assert is_panel_name("MFACP : 4 Loops")
    assert is_panel_name("Fire Alarm Control Panel : Main")
    assert is_panel_name("FACP : Std")
    assert not is_panel_name("Repeater Panel : FARP")
    assert not is_panel_name("Control Module : Relay")
    assert not is_panel_name("Smoke Detector : Std")


# ---------------------------------------------------------------- layout

def test_sample_loops_and_floors():
    riser = sample()
    floors = dict((l.number, l.floors) for l in riser.loops)
    assert floors[1] == ["PODIUM 01"]
    assert floors[2] == ["PODIUM 03", "PODIUM 02"]            # the furthest floor first
    assert floors[10] == ["ROOF FLOOR", "TYPICAL FLOOR 11"]
    assert [n for n, _ in riser.bands][0] == "GROUND FLOOR"
    ys = [y for _, y in riser.bands]
    assert ys == sorted(ys)
    assert riser.warnings == []


def test_no_text_overlaps():
    assert overlaps(sample().drawing) == []


def _wiring(drawing):
    return [l for l in drawing.lines if l.style == WIRING]


def _crosses(a, b, eps=1e-6):
    """Proper crossing or collinear overlap of two square lines."""
    a_flat, b_flat = abs(a.y1 - a.y2) < eps, abs(b.y1 - b.y2) < eps
    if a_flat != b_flat:
        h, v = (a, b) if a_flat else (b, a)
        return (min(h.x1, h.x2) + eps < v.x1 < max(h.x1, h.x2) - eps and
                min(v.y1, v.y2) + eps < h.y1 < max(v.y1, v.y2) - eps)
    if a_flat:
        same, a0, a1, b0, b1 = abs(a.y1 - b.y1) < eps, min(a.x1, a.x2), max(a.x1, a.x2), \
            min(b.x1, b.x2), max(b.x1, b.x2)
    else:
        same, a0, a1, b0, b1 = abs(a.x1 - b.x1) < eps, min(a.y1, a.y2), max(a.y1, a.y2), \
            min(b.y1, b.y2), max(b.y1, b.y2)
    return same and min(a1, b1) - max(a0, b0) > eps


def test_wiring_is_square_and_never_crosses():
    wires = _wiring(sample().drawing)
    for w in wires:
        assert abs(w.x1 - w.x2) < 1e-9 or abs(w.y1 - w.y2) < 1e-9
    assert [(a, b) for i, a in enumerate(wires) for b in wires[i + 1:] if _crosses(a, b)] == []


def test_every_loop_leaves_and_comes_back_to_the_panel():
    riser = sample()
    wires = _wiring(riser.drawing)
    vertical = [w for w in wires if abs(w.x1 - w.x2) < 1e-9]
    panel_top = min(min(w.y1, w.y2) for w in vertical)
    at_panel = [w for w in vertical if abs(min(w.y1, w.y2) - panel_top) < 1e-9]
    assert len(at_panel) == 2 * len(riser.loops)                  # OUT and RETURN each


def test_legend_quantities():
    floors, segments, panel, location = sample_riser.build()
    riser = riser_layout(floors, segments, panel, location)
    texts = [t.text for t in riser.drawing.texts]
    total_sd = sum(s.counts.get("SD", 0) for s in segments)
    i = texts.index(BY_CODE["SD"].description)
    assert texts[i + 1] == "%d" % total_sd
    assert "MAIN FIRE ALARM CONTROL PANEL" in texts
    assert "10 LOOPS\nLOC. FIRE COMMAND ROOM (GF-154)" in texts


def test_symbols_are_red_in_columns_and_legend_order():
    floors, segments, panel, location = sample_riser.build()
    riser = riser_layout(floors, segments, panel, location)
    assert any(l.style == SYMBOL_STYLE for l in riser.drawing.lines)
    used = set(c for s in segments for c, n in s.counts.items() if n)
    columns = set(round(t.x, 6) for t in riser.drawing.texts if t.text.startswith("NO."))
    assert len(columns) == len(used)                   # one column per symbol, on every floor
    texts = [t.text for t in riser.drawing.texts]
    legend = [d for d in texts if d in set(BY_CODE[c].description for c in used)]
    assert legend == [BY_CODE[c].description for c in sorted(used, key=lambda c: ORDER[c])]


def test_basement_loops_go_down():
    floors = [("BASEMENT 2", -8), ("BASEMENT 1", -4), ("GROUND FLOOR", 0), ("FIRST FLOOR", 4)]
    segments = [Segment(1, "FIRST FLOOR", {"SD": 20}), Segment(2, "BASEMENT 1", {"SD": 30}),
                Segment(2, "BASEMENT 2", {"SD": 25, "MCP": 3})]
    riser = riser_layout(floors, segments, "GROUND FLOOR")
    down = [l for l in riser.loops if not l.up]
    assert [l.number for l in down] == [2] and down[0].floors == ["BASEMENT 2", "BASEMENT 1"]
    assert overlaps(riser.drawing) == []
    wires = _wiring(riser.drawing)
    assert [(a, b) for i, a in enumerate(wires) for b in wires[i + 1:] if _crosses(a, b)] == []


def test_too_many_devices_on_a_loop():
    floors = [("GROUND FLOOR", 0), ("FIRST FLOOR", 4), ("SECOND FLOOR", 8)]
    segments = [Segment(1, "FIRST FLOOR", {"SD": 70}), Segment(1, "SECOND FLOOR", {"SD": 60})]
    riser = riser_layout(floors, segments, "GROUND FLOOR")
    assert riser.warnings == ["LOOP#1 has 130 devices, more than 120."]


def test_floors_without_loops_still_have_their_band():
    floors = [("GROUND FLOOR", 0), ("FIRST FLOOR", 4), ("SECOND FLOOR", 8)]
    riser = riser_layout(floors, [Segment(3, "SECOND FLOOR", {"SD": 5})], "GROUND FLOOR")
    assert [n for n, _ in riser.bands] == ["GROUND FLOOR", "FIRST FLOOR", "SECOND FLOOR"]


# ---------------------------------------------------------------- loop numbers

def test_loop_numbers_go_on_across_the_building():
    assert loop_numbers(2, []) == [1, 2]
    assert loop_numbers(2, [1, 2, 5]) == [6, 7]
    assert loop_numbers(3, [1, 2, 3], carry_on=2) == [2, 4, 5]      # first loop goes on from loop 2
    assert loop_numbers(1, [4], carry_on=4) == [4]
    assert loop_numbers(0, [1]) == []


def test_chosen_symbols_are_remembered():
    from firealarm import settings
    values = dict(settings.DEFAULTS)
    assert settings.chosen_symbols(values) == {}
    settings.choose_symbol(values, "Smoke : A", "HD")
    settings.choose_symbol(values, "Bell : B", "BELLS")
    assert settings.chosen_symbols(values) == {"Smoke : A": "HD", "Bell : B": "BELLS"}
    settings.choose_symbol(values, "Smoke : A", None)
    assert settings.chosen_symbols(values) == {"Bell : B": "BELLS"}
    # pyRevit may give back the dict's repr instead of the saved JSON
    values["riser_symbols"] = settings._coerce("riser_symbols", {"X : Y": "MM"})
    assert settings.chosen_symbols(values) == {"X : Y": "MM"}


def test_riser_summary():
    from firealarm.report import summarize_riser

    class Run(object):
        pass
    run = Run()
    run.riser = sample()
    run.view_name = "FA Riser Diagram"
    run.panel, run.panel_floor = "MFACP : 10 Loops", "GROUND FLOOR"
    run.off_loop = {"PODIUM 02": 3}
    run.two_loops = 0
    run.symbols = {"Smoke Detector : Std": "SD"}
    headline, details = summarize_riser(run, lambda c: symbol(c).description)
    assert headline.startswith("Riser drawn in 'FA Riser Diagram': 10 loops, ")
    assert headline.endswith(" 3 devices on no loop.")
    lines = details.splitlines()
    assert lines[0] == "Main panel: MFACP : 10 Loops on GROUND FLOOR"
    assert "LOOP#10: ROOF FLOOR + TYPICAL FLOOR 11, 57 devices" in lines
    assert "    PODIUM 02: 3" in lines
    assert "    Smoke Detector : Std -> PHOTOELECTRIC SMOKE DETECTOR" in lines
