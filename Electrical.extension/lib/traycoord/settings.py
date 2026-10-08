# -*- coding: utf-8 -*-
"""User settings, saved per user in the pyRevit configuration."""

SECTION = "ElectricalCableTray"

# What counts as in the tray's way: key -> (label, Revit categories)
OBSTACLES = (
    ("pipes", "Pipes and their fittings", (
        "OST_PipeCurves", "OST_PipeFitting", "OST_PipeAccessory", "OST_FlexPipeCurves")),
    ("ducts", "Ducts and their fittings", (
        "OST_DuctCurves", "OST_DuctFitting", "OST_DuctAccessory", "OST_FlexDuctCurves")),
    ("trays", "Other cable trays and conduits", (
        "OST_CableTray", "OST_CableTrayFitting", "OST_Conduit", "OST_ConduitFitting")),
    ("framing", "Beams and bracing", ("OST_StructuralFraming",)),
    ("columns", "Columns", ("OST_StructuralColumns", "OST_Columns")),
    ("walls", "Walls", ("OST_Walls",)),
    ("ceilings", "Ceilings", ("OST_Ceilings",)),
    ("equipment", "Mechanical equipment", ("OST_MechanicalEquipment",)),
)

DEFAULTS = {
    # drawing a new tray
    "tray_type": "",            # cable tray type name, "" = the first one
    "width": 300.0,             # mm
    "height": 100.0,            # mm
    "elevation": 3000.0,        # mm, middle elevation above the view's level
    # routing
    "clearance": 50.0,          # mm, kept between the tray and anything in its way
    "prefer": "shortest",       # dodge picked: the shortest, or over / under / side first
    "bends": "90",              # 90 or 45 degree bends in and out of a dodge
    "headroom": 2400.0,         # mm, lowest the tray's bottom may go above its floor
    "slab": 300.0,              # mm, kept under the level above (slab and finishes)
    "links": "yes",             # linked models count as obstacles too
    "obstacles": ",".join(key for key, _, _ in OBSTACLES),
}

# key -> allowed values (settings picked from a list)
CHOICES = {
    "prefer": ("shortest", "over", "under", "side"),
    "bends": ("90", "45"),
    "links": ("yes", "no"),
}

# key -> (lowest, highest) for numbers, in mm
RANGES = {
    "width": (25.0, 2000.0),
    "height": (10.0, 500.0),
    "elevation": (0.0, 20000.0),
    "clearance": (0.0, 500.0),
    "headroom": (0.0, 10000.0),
    "slab": (0.0, 3000.0),
}


def _config():
    from pyrevit import script
    return script.get_config(SECTION)


def valid(key, value):
    """`value` converted to the setting's type, or None when not allowed."""
    if key in RANGES:
        try:
            value = float(u"%s" % value)
        except (TypeError, ValueError):
            return None
        low, high = RANGES[key]
        return value if low <= value <= high else None
    value = "" if value is None else u"%s" % value
    if key in CHOICES and value not in CHOICES[key]:
        return None
    if key == "obstacles":
        known = [k for k, _, _ in OBSTACLES]
        return ",".join(k for k in known if k in value.split(","))
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


def categories(values):
    """Revit category names (OST_...) of the obstacles chosen."""
    chosen = values["obstacles"].split(",")
    return [name for key, _, names in OBSTACLES if key in chosen for name in names]


def options(values):
    """Keyword options of route.route from the settings."""
    return {
        "clearance": values["clearance"] / 1000.0,
        "bends": int(values["bends"]),
        "prefer": values["prefer"],
    }
