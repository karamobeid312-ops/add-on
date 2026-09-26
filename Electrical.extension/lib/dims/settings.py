# -*- coding: utf-8 -*-
"""User settings, saved per user in the pyRevit configuration."""

SECTION = "ElectricalDimensions"

DEFAULTS = {
    "dim_type": "",             # linear dimension type name, "" = the model's default
    "line_offset": 8.0,         # mm on the printed sheet, devices to the dimension line
    "strings": "every",         # 'every' row and column, or only what is 'needed'
    "ends": "nearest",          # 'nearest' wall, 'both' walls, or 'none': devices only
}

# key -> allowed values (settings picked from a list)
CHOICES = {
    "strings": ("every", "needed"),
    "ends": ("nearest", "both", "none"),
}

MAX_OFFSET = 50.0               # mm


def _config():
    from pyrevit import script
    return script.get_config(SECTION)


def valid(key, value):
    """`value` converted to the setting's type, or None when not allowed."""
    if isinstance(DEFAULTS[key], float):
        try:
            value = float(u"%s" % value)
        except (TypeError, ValueError):
            return None
        return value if 0 <= value <= MAX_OFFSET else None
    value = "" if value is None else u"%s" % value
    if key in CHOICES and value not in CHOICES[key]:
        return None
    return value


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
