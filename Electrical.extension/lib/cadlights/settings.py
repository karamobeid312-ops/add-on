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


def _quote(text):
    """JSON string with every non-ASCII character escaped. IronPython's json
    module chokes on names like 'Ø600' read from a DWG, so this is done by hand."""
    out = [u'"']
    for ch in u"%s" % text:
        code = ord(ch)
        if ch == u'"':
            out.append(u'\\"')
        elif ch == u"\\":
            out.append(u"\\\\")
        elif code < 32 or code > 126:
            out.append(u"\\u%04x" % code)
        else:
            out.append(ch)
    out.append(u'"')
    return u"".join(out)


def dumps(data):
    """{text: text} as JSON (ASCII only)."""
    items = sorted(data.items())
    return u"{" + u", ".join(u"%s: %s" % (_quote(k), _quote(v)) for k, v in items) + u"}"


def save(values, chosen):
    """Save the settings; `chosen` {block: label} is merged into the saved
    mapping (a block set back to skip is forgotten)."""
    from cadlights.match import SKIP
    data = mapping(values)
    for name, label in chosen.items():
        if label == SKIP:
            data.pop(name, None)
        else:
            data[name] = label
    try:
        values["mapping"] = dumps(data)
        from pyrevit import script
        cfg = _config()
        for key in DEFAULTS:
            setattr(cfg, key, values[key])
        script.save_config()
    except Exception:
        pass
