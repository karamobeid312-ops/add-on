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
    "loop_square": True,        # loop lines at right angles (else straight device to device)
    "loop_gap": 2.0,            # mm on paper between a loop line and a device's centre, at least
    "riser_symbols": "",        # {'Family : Type': symbol code} chosen for the riser (JSON)
    "address_tag": "",          # 'Family : Type' of the address tag, NO_TAG, or '' (ask)
}

NO_TAG = "(no tag)"


def _config():
    from pyrevit import script
    return script.get_config(SECTION)


def _coerce(key, value):
    default = DEFAULTS[key]
    try:
        if isinstance(default, bool):
            if isinstance(value, bool):
                return value
            return u"%s" % value in ("True", "true", "1", "yes")
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


def chosen_symbols(values):
    """{'Family : Type': symbol code} chosen in FA Settings."""
    import json
    raw = values.get("riser_symbols") or ""
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


def choose_symbol(values, name, code):
    """Remember the symbol `code` for 'Family : Type' `name` (None: guess it)."""
    import json
    data = chosen_symbols(values)
    if code:
        data[name] = code
    else:
        data.pop(name, None)
    values["riser_symbols"] = json.dumps(data, sort_keys=True)


def save(values):
    from pyrevit import script
    cfg = _config()
    for key in DEFAULTS:
        setattr(cfg, key, values[key])
    script.save_config()
