# -*- coding: utf-8 -*-
"""User settings, saved per user in the pyRevit configuration."""
from circuitdesc.describe import NUMBER_NAME, STYLES

SECTION = "ElectricalCircuitDescription"

DEFAULTS = {
    "style": NUMBER_NAME,       # how a room is written: '012 PUMP ROOM'
    "upper": True,              # in capitals, as the panel schedules
    "host_spaces": True,        # rooms / spaces of this model when not in a link
}


def _config():
    from pyrevit import script
    return script.get_config(SECTION)


def coerce(key, value):
    """`value` for the setting, or the default when it is not valid."""
    if key == "style":
        return value if value in STYLES else DEFAULTS[key]
    if isinstance(value, bool):
        return value
    text = u"%s" % value
    if text.lower() in ("true", "1", "yes"):
        return True
    if text.lower() in ("false", "0", "no"):
        return False
    return DEFAULTS[key]


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
