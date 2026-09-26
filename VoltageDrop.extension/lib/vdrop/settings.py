# -*- coding: utf-8 -*-
"""User settings, saved per user in the pyRevit configuration."""
from vdrop import tables
from vdrop.calc import MDL, TCL, Settings

SECTION = "VoltageDrop"

DEFAULTS = {
    "voltage_3ph": 400.0,
    "voltage_1ph": 230.0,
    "voltage_source": "settings",  # 'settings' (as the office sheet) or 'model'
    "power_factor": 0.85,          # every cable, as the office sheet
    "pf_source": "settings",       # 'settings' (the value above) or 'model'
    "load_basis": MDL,             # MDL: board's demand load, TCL: connected load
    "limit_transformer": 2.5,      # % transformer -> main board
    "limit_total": 4.0,            # % transformer -> final load
    "insulation": tables.DEFAULT_INSULATION,
    "installation": tables.TRAY,
    "air_temperature": 35.0,       # °C, cable tray
    "ground_temperature": 35.0,    # °C, ground and duct bank
    "depth": 0.0,                  # mm, 0 = not applied
    "soil_resistivity": 0.0,       # K.m/W, 0 = not applied
    "grouping": 0.85,              # Cg
    "company": "",                 # report title block
    "revision": "00",
    "issue": "",                   # empty: the Revit project status
}

# key -> allowed values (settings picked from a list)
CHOICES = {
    "voltage_source": ("settings", "model"),
    "pf_source": ("settings", "model"),
    "load_basis": (MDL, TCL),
    "insulation": tables.INSULATION_NAMES,
    "installation": tables.INSTALLATIONS,
    "air_temperature": tuple(float(t) for t in tables.TEMPERATURES),
    "ground_temperature": tuple(float(t) for t in tables.TEMPERATURES),
    "depth": tuple(float(d) for d in tables.DEPTHS),
    "soil_resistivity": tuple(float(r) for r in tables.RESISTIVITIES),
}


def _config():
    from pyrevit import script
    return script.get_config(SECTION)


def valid(key, value):
    """`value` converted to the setting's type, or None when not allowed."""
    default = DEFAULTS[key]
    try:
        if isinstance(default, float):
            value = float(u"%s" % value)
            if key in CHOICES:
                return value if value in CHOICES[key] else None
            if key in ("power_factor", "grouping"):
                return value if 0 < value <= 1 else None
            return value if value > 0 else None
    except (TypeError, ValueError):
        return None
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


def calc_settings(values):
    return Settings(
        voltage_3ph=values["voltage_3ph"], voltage_1ph=values["voltage_1ph"],
        power_factor=values["power_factor"], limit_total=values["limit_total"],
        limit_transformer=values["limit_transformer"], insulation=values["insulation"],
        installation=values["installation"], air_temperature=values["air_temperature"],
        ground_temperature=values["ground_temperature"], depth=values["depth"],
        soil_resistivity=values["soil_resistivity"], grouping=values["grouping"])
