# -*- coding: utf-8 -*-
"""User settings, saved per user in the pyRevit configuration."""
from firealarm.layout import DEFAULT_CLEARANCE
from firealarm.loops import MAX_DEVICES

SECTION = "FireAlarmDetectors"

KINDS = ("smoke", "heat")

DEFAULTS = {
    "smoke_spacing": 9.0,       # m between detectors, half of it from the walls
    "heat_spacing": 4.5,
    "clearance": DEFAULT_CLEARANCE,   # m min from walls and columns
    "smoke_type": "",           # 'Family : Type' of the detector, asked on first use
    "heat_type": "",
    "loop_devices": MAX_DEVICES,    # most devices on one loop
    "loop_gap": 2.0,            # mm on paper between a loop line and a device's centre, at least
}


def _config():
    from pyrevit import script
    return script.get_config(SECTION)


def _coerce(key, value):
    default = DEFAULTS[key]
    try:
        if isinstance(default, float):
            value = float(value)
            allowed = value >= 0 if key in ("clearance", "loop_gap") else value > 0
            return value if allowed else default
        if isinstance(default, int):
            value = int(float(value))
            return value if value >= 1 else default
        return "" if value is None else u"%s" % value
    except (TypeError, ValueError):
        return default


def load():
    values = dict(DEFAULTS)
    try:
        cfg = _config()
        for key, default in DEFAULTS.items():
            values[key] = _coerce(key, cfg.get_option(key, default))
    except Exception:
        pass
    return values


def save(values):
    from pyrevit import script
    cfg = _config()
    for key in DEFAULTS:
        setattr(cfg, key, values[key])
    script.save_config()
