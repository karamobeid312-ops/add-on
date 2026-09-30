# -*- coding: utf-8 -*-
"""Fire alarm device addresses and loop kinds (pure Python, no Revit).

An address is L<loop>/<type>-<number>, e.g. L1/SD-01: the loop, the device
type and the device's place on the loop, counted in route order from the
start: 01, 02 ... 99, 100 ... 120, one count for all types on the loop. A
loop going on over another floor goes on counting there.

Detection loops carry every device but sirens and flashers; sounder loops
only sirens and flashers. Both share the loop numbers (L1, L2...).
Keep compatible with IronPython 2.7.
"""
import re

from firealarm.riser_symbols import initials

DETECTION, SOUNDER = "detection", "sounder"

# riser symbol code -> type in the address
ADDRESS_CODES = {
    "SD": "SD", "SDF": "SD", "SDR": "SD", "SDT": "SD", "HD": "HD", "DD": "DD",
    "BTX": "TX", "BRX": "RX", "MCP": "MCP", "BELL": "B", "BELLS": "BS",
    "STC": "ST", "STW": "ST", "HS": "HS", "J": "J", "WFS": "FS", "TS": "TS",
    "CM": "CM", "MM": "MM", "ZM": "ZM", "LHD": "LHD", "LHDP": "LHD",
    "HSSD": "HSSD", "EOL": "EOL", "ISO": "ISO", "FARP": "FARP",
}
SIRENS_AND_FLASHERS = ("BELL", "BELLS", "STC", "STW", "HS")

_ADDRESS = re.compile(r"^L(\d+)/([A-Z0-9?]+)-(\d+)$")


def is_siren_or_flasher(symbol_code):
    return symbol_code in SIRENS_AND_FLASHERS


def on_loop(symbol_code, kind):
    """The device goes on a loop of this kind (DETECTION or SOUNDER)."""
    return is_siren_or_flasher(symbol_code) == (kind == SOUNDER)


def address_code(symbol_code):
    """Type in the address: SD, HD, MCP, B, BS, ST... or the initials of a
    type no symbol fits."""
    if symbol_code in ADDRESS_CODES:
        return ADDRESS_CODES[symbol_code]
    return initials(symbol_code[1:] if symbol_code.startswith("?") else symbol_code)


def format_address(loop, code, number):
    return u"L%d/%s-%02d" % (loop, code, number)


def parse_address(text):
    """(loop, type, number) of an address, or None."""
    match = _ADDRESS.match((text or "").strip().upper())
    if not match:
        return None
    return int(match.group(1)), match.group(2), int(match.group(3))


def next_number(addresses, loop):
    """The number after the highest one of `loop` among `addresses`."""
    numbers = [a[2] for a in (parse_address(t) for t in addresses) if a and a[0] == loop]
    return max(numbers) + 1 if numbers else 1


def first_number(loop, count, others, own):
    """Where a floor's `count` devices on `loop` start counting: after the
    loop's other devices (`others`: their addresses), unless the devices
    already had addresses on this loop (`own`, redrawn) and their range
    from the lowest one still fits without clashing."""
    taken = set(a[2] for a in (parse_address(t) for t in others) if a and a[0] == loop)
    before = [a[2] for a in (parse_address(t) for t in own) if a and a[0] == loop]
    if before:
        start = min(before)
        if not any(start + k in taken for k in range(count)):
            return start
    return max(taken) + 1 if taken else 1


def loop_addresses(loop, symbol_codes, first=1):
    """Addresses of a loop's devices, given their symbol codes in route order."""
    return [format_address(loop, address_code(c), first + k) for k, c in enumerate(symbol_codes)]
