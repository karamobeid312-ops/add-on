# -*- coding: utf-8 -*-
"""User settings, saved per user in the pyRevit configuration."""

SECTION = "ElectricalCopyCircuits"

DEFAULTS = {
    "tolerance": 50.0,          # mm: a copy this near the source spot in plan is its copy
    "wires": True,              # draw the wires again in the copied floors' plans
}

MAX_TOLERANCE = 1000.0          # mm


def _config():
    from pyrevit import script
    return script.get_config(SECTION)


def valid(key, value):
    """`value` converted to the setting's type, or None when not allowed."""
    if key == "wires":
        if isinstance(value, bool):
            return value
        text = (u"%s" % value).strip().lower()
        if text in ("true", "yes", "1", "on"):
            return True
        if text in ("false", "no", "0", "off"):
            return False
        return None
    try:
        value = float(u"%s" % value)
    except (TypeError, ValueError):
        return None
    return value if 0 < value <= MAX_TOLERANCE else None


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
