# -*- coding: utf-8 -*-
import pytest

from firealarm.addresses import (DETECTION, SOUNDER, address_code, first_number, format_address,
                                 loop_addresses, next_number, on_loop, parse_address)
from firealarm.riser_symbols import SYMBOLS, guess


def test_address_format():
    assert format_address(1, "SD", 1) == "L1/SD-01"
    assert format_address(12, "MCP", 99) == "L12/MCP-99"
    assert format_address(3, "SD", 120) == "L3/SD-120"          # 3 digits from 100 on


def test_one_count_per_loop_in_route_order():
    codes = ["SD", "SD", "MCP", "HD", "SDF", "CM"]
    assert loop_addresses(1, codes) == ["L1/SD-01", "L1/SD-02", "L1/MCP-03", "L1/HD-04",
                                        "L1/SD-05", "L1/CM-06"]


@pytest.mark.parametrize("symbol,code", [
    ("SD", "SD"), ("SDF", "SD"), ("SDR", "SD"), ("SDT", "SD"), ("HD", "HD"), ("DD", "DD"),
    ("BTX", "TX"), ("BRX", "RX"), ("MCP", "MCP"), ("BELL", "B"), ("BELLS", "BS"),
    ("STC", "ST"), ("STW", "ST"), ("HS", "HS"), ("J", "J"), ("WFS", "FS"), ("TS", "TS"),
    ("CM", "CM"), ("MM", "MM"), ("ZM", "ZM"), ("LHD", "LHD"), ("HSSD", "HSSD"),
    ("EOL", "EOL"), ("ISO", "ISO"),
])
def test_type_codes(symbol, code):
    assert address_code(symbol) == code


def test_every_symbol_has_a_type_code():
    for s in SYMBOLS:
        assert address_code(s.code)
    assert address_code(guess("Mystery Gadget : Type 1")) == "MGT1"


def test_detection_and_sounder_loops():
    sirens_and_flashers = ["BELL", "BELLS", "STC", "STW", "HS"]
    for code in sirens_and_flashers:
        assert on_loop(code, SOUNDER) and not on_loop(code, DETECTION)
    for code in ("SD", "HD", "MCP", "CM", "MM", "WFS", "TS", "BTX"):
        assert on_loop(code, DETECTION) and not on_loop(code, SOUNDER)
    assert on_loop(guess("Sounder Strobe : Wall"), SOUNDER)
    assert on_loop(guess("Horn Strobe : H1"), SOUNDER)
    assert on_loop(guess("Smoke Detector : Std"), DETECTION)


def test_parse():
    assert parse_address("L12/SD-07") == (12, "SD", 7)
    assert parse_address(" l3/mcp-120 ") == (3, "MCP", 120)
    assert parse_address("SD-07") is None
    assert parse_address("") is None


def test_a_loop_going_on_over_another_floor_goes_on_counting():
    others = ["L1/SD-01", "L1/SD-02", "L1/MCP-40", "L2/SD-99", "junk", ""]
    assert next_number(others, 1) == 41
    assert first_number(1, 5, others, own=["", "", "", "", ""]) == 41
    assert first_number(7, 3, others, own=[]) == 1                  # a new loop starts at 01


def test_a_redrawn_floor_keeps_its_numbers_when_they_fit():
    others = ["L1/HD-06", "L1/HD-07"]                               # the loop's other floor
    own = ["L1/SD-01", "L1/SD-02", "L1/SD-03", "L1/SD-04", "L1/MCP-05"]
    assert first_number(1, 5, others, own) == 1                      # 01-05 again
    assert first_number(1, 6, others, own) == 8                      # 01-06 would clash with 06
    assert first_number(1, 5, others, ["L4/SD-01"]) == 8             # addresses of another loop


def test_sounder_loop_summary():
    from firealarm.report import summarize_loops

    class Result(object):
        number, devices, length, lines, failed = 5, 3, 42.0, 4, []
        addresses = ("L5/BS-01", "L5/HS-03")
    headline, details = summarize_loops("L1 - FA", [Result()], "MFACP : Main", False,
                                        kind=SOUNDER, notes=["Addresses written: 3."])
    assert headline == "1 sounder loop drawn in 'L1 - FA': 3 devices."
    lines = details.splitlines()
    assert lines[1] == "FA Sounder Loop 5: 3 devices, 42 m of line, L5/BS-01 to L5/HS-03"
    assert lines[-1] == "Addresses written: 3."
