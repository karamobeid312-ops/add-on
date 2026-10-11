# -*- coding: utf-8 -*-
"""User settings, saved per user in the pyRevit configuration."""
import json

SECTION = "CadLights"

DEFAULTS = {
    "mapping": "",          # {block name: 'Family : Type' or '(skip)'} (JSON)
    "height_mm": 3000.0,    # height of level-based (unhosted) lights above the level
    "tolerance_mm": 50.0,   # a spot with a light this close already is skipped
}


def _config():
    from pyrevit import script
    return script.get_config(SECTION)


def _number(value, default):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return default
    return value if value >= 0 else default


def load():
    values = dict(DEFAULTS)
    try:
        cfg = _config()
        values["mapping"] = cfg.get_option("mapping", "") or ""
        for key in ("height_mm", "tolerance_mm"):
            values[key] = _number(cfg.get_option(key, DEFAULTS[key]), DEFAULTS[key])
    except Exception:
        pass
    return values


def mapping(values):
    raw = values.get("mapping") or ""
    if isinstance(raw, dict):
        return dict(raw)
    try:
        data = json.loads(raw)
    except ValueError:
        try:
            import ast
            data = ast.literal_eval(raw)     # pyRevit may hand back the dict's repr
        except (ValueError, SyntaxError):
            data = {}
    return dict(data) if isinstance(data, dict) else {}


def save(values, chosen):
    """Save the settings; `chosen` {block: label} is merged into the saved mapping."""
    from pyrevit import script
    data = mapping(values)
    data.update(chosen)
    values["mapping"] = json.dumps(data, sort_keys=True)
    try:
        cfg = _config()
        for key in DEFAULTS:
            setattr(cfg, key, values[key])
        script.save_config()
    except Exception:
        pass
