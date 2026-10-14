# -*- coding: utf-8 -*-
"""User settings, saved per user in the pyRevit configuration."""
from sld import style
from sld.layout import LayoutSettings

SECTION = "SingleLineDiagram"

DEFAULTS = {
    "utility": style.DEFAULT_UTILITY,         # FROM TAQA / MV CABLE FROM TAQA
    "substation_label": style.SUBSTATION_LABEL,
    "show_ratings": True,                     # breaker rating + cable along ways
    "meter_label": style.DEFAULT_METER,       # utility meter under the cable; '' = none
    "numbering": "slots",                     # 'slots' (1, 2, R9...) or 'revit'
    "balance_warn": 10.0,                     # phase unbalance %: amber above
    "balance_bad": 20.0,                      # red above
    "new_view": False,                        # Draw SLD: new view each time
    "sheet_size": "A1",                       # Draw SLD fills this paper; '1:1' = as drawn
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
                          show_ratings=values["show_ratings"],
                          meter_label=values.get("meter_label", style.DEFAULT_METER))


# ---------------------------------------------------------------- spares
# Spare ways typed in Power Studio, per project, for models without the
# 'SLD Spares' / 'SLD Spare Rating' parameters (no parameter is ever added).

def _spares_key(project):
    import re
    return "spares_" + (re.sub(r"[^A-Za-z0-9]+", "_", project or "").strip("_") or "model")


def load_spares(project):
    """{board name: (spare count, spare rating, space count)} as text"""
    import json
    try:
        text = _config().get_option(_spares_key(project), "")
        data = json.loads(text) if text else {}
        return dict((k, tuple(v)) for k, v in data.items())
    except Exception:
        return {}


def save_spares(project, spares):
    import json
    from pyrevit import script
    cfg = _config()
    setattr(cfg, _spares_key(project), json.dumps(spares, ensure_ascii=True, sort_keys=True))
    script.save_config()


def apply_spares(equipment, spares):
    """Put stored spares on boards whose panel has no SLD Spares value."""
    for e in equipment:
        stored = spares.get(e.name)
        if stored and e.spares in (None, ""):
            e.spares, e.spare_rating = stored[0], stored[1] or e.spare_rating
        if stored and len(stored) > 2 and stored[2] not in (None, "", "0"):
            e.spaces = stored[2]
