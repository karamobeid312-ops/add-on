# -*- coding: utf-8 -*-
"""User settings, saved per user in the pyRevit configuration."""

SECTION = "ElectricalLOD"

DEFAULTS = {
    "lod_path": "",             # last LOD workbook used
    "title_prefix": "",         # left out of the sheet names, e.g. 'KEZAD Two Building - '
    "rev_param": "LOD Revision",    # sheet parameter that holds the LOD revision ('' = none)
    "area_param": "",           # sheet parameter for 'Area/Building References' ('' = none)
    "title_block": "",          # 'Family : Type' of the title block for new sheets
    "keyplan_rules": "",        # JSON list of key plan rules ('' = the default rules)
}


def _config():
    from pyrevit import script
    return script.get_config(SECTION)


def _coerce(key, value):
    if value is None:
        return ""
    return u"%s" % value


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
