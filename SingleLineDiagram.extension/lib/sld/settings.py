# -*- coding: utf-8 -*-
"""User settings, saved per user in the pyRevit configuration."""
from sld import style
from sld.layout import LayoutSettings

SECTION = "SingleLineDiagram"

DEFAULTS = {
    "utility": style.DEFAULT_UTILITY,         # FROM TAQA / MV CABLE FROM TAQA
    "substation_label": style.SUBSTATION_LABEL,
    "show_ratings": True,                     # breaker rating + cable along ways
    "numbering": "slots",                     # 'slots' (1, 2, R9...) or 'revit'
}


def _config():
    from pyrevit import script
    return script.get_config(SECTION)


def load():
    values = dict(DEFAULTS)
    try:
        cfg = _config()
        for key, default in DEFAULTS.items():
            values[key] = cfg.get_option(key, default)
    except Exception:
        pass
    return values


def save(values):
    from pyrevit import script
    cfg = _config()
    for key in DEFAULTS:
        setattr(cfg, key, values[key])
    script.save_config()


def layout_settings(values):
    return LayoutSettings(utility=values["utility"],
                          substation_label=values["substation_label"],
                          show_ratings=values["show_ratings"])
