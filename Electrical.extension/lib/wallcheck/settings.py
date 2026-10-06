# -*- coding: utf-8 -*-
"""User settings, saved per user in the pyRevit configuration."""

SECTION = "ElectricalWallCheck"

DEFAULTS = {
    "tolerance": 10.0,          # mm: a fixture this near its wall face is on it
}

MAX_TOLERANCE = 100.0           # mm


def _config():
    from pyrevit import script
    return script.get_config(SECTION)


def valid(key, value):
    """`value` converted to the setting's type, or None when not allowed."""
    try:
        value = float(u"%s" % value)
    except (TypeError, ValueError):
        return None
    return value if 0 <= value <= MAX_TOLERANCE else None


def coerce(key, value):
    """`value` for the setting, or the default when it is not valid."""
    value = valid(key, value)
    return DEFAULTS[key] if value is None else value


def load():
    values = dict(DEFAULTS)
    try:
        cfg = _config()
        for key, default in DEFAULTS.items():
            values[key] = coerce(key, cfg.get_option(key, default))
    except Exception:
        pass
    return values


def save(values):
    from pyrevit import script
    cfg = _config()
    for key in DEFAULTS:
        setattr(cfg, key, values[key])
    script.save_config()
