# -*- coding: utf-8 -*-
"""Which tool takes which element: Mechanical or Plumbing (no Revit needed).

Ducts, duct fittings and accessories, flex ducts and air terminals are
mechanical. Plumbing fixtures, sprinklers and plumbing equipment are
plumbing. Pipes (and their fittings, accessories and flex pipes) go by
their piping system:

- Hydronic supply / return, and any system named for chilled water,
  heating water, condensate or refrigerant, are mechanical (condensate
  drains are often drawn as a Sanitary system: the name wins);
- domestic water, sanitary, vent, storm, fire protection and the rest are
  plumbing.

A pipe whose system is not known (a fitting with no system yet) takes the
side of the pipes it is connected to, else plumbing. Mechanical equipment
is mechanical, unless all its connectors are plumbing pipes (a water pump,
a water heater, a tank).
"""
from __future__ import division

MECHANICAL = "mechanical"
PLUMBING = "plumbing"

# (Revit BuiltInCategory name, label shown in the window)
DUCT_CATEGORIES = (
    ("OST_DuctCurves", u"Ducts"),
    ("OST_DuctFitting", u"Duct fittings"),
    ("OST_DuctAccessory", u"Duct accessories"),
    ("OST_FlexDuctCurves", u"Flex ducts"),
    ("OST_DuctTerminal", u"Air terminals"),
)
EQUIPMENT_CATEGORIES = (
    ("OST_MechanicalEquipment", u"Mechanical equipment"),
)
PIPE_CATEGORIES = (
    ("OST_PipeCurves", u"Pipes"),
    ("OST_PipeFitting", u"Pipe fittings"),
    ("OST_PipeAccessory", u"Pipe accessories"),
    ("OST_FlexPipeCurves", u"Flex pipes"),
)
PLUMBING_CATEGORIES = (
    ("OST_PlumbingFixtures", u"Plumbing fixtures"),
    ("OST_Sprinklers", u"Sprinklers"),
    ("OST_PlumbingEquipment", u"Plumbing equipment"),     # Revit 2024 and later
)

# categories each tool looks at (pipes and equipment are then split by system)
CATEGORIES = {
    MECHANICAL: DUCT_CATEGORIES + EQUIPMENT_CATEGORIES + PIPE_CATEGORIES,
    PLUMBING: PIPE_CATEGORIES + PLUMBING_CATEGORIES + EQUIPMENT_CATEGORIES,
}
PIPED = set(name for name, _ in PIPE_CATEGORIES)
EQUIPMENT = set(name for name, _ in EQUIPMENT_CATEGORIES)
FIXED = dict([(name, MECHANICAL) for name, _ in DUCT_CATEGORIES] +
             [(name, PLUMBING) for name, _ in PLUMBING_CATEGORIES])
LABELS = dict(DUCT_CATEGORIES + EQUIPMENT_CATEGORIES + PIPE_CATEGORIES + PLUMBING_CATEGORIES)

# in the system's name, type name or abbreviation: a mechanical pipe
MECHANICAL_WORDS = (u"chilled", u"chw", u"hydronic", u"condensate", u"condensation",
                    u"condenser", u"refrigerant", u"heating", u"hhw", u"lthw", u"mthw",
                    u"cooling", u"glycol", u"fcu", u"ahu", u"hvac", u"ref liquid",
                    u"ref gas", u"drain pan")
MECHANICAL_CLASSES = (u"hydronic",)


def _words(text):
    return (text or u"").replace(u"_", u" ").lower()


def pipe_domain(classification, names=()):
    """MECHANICAL or PLUMBING for a pipe of the system `classification`
    (Revit's System Classification: "Hydronic Supply", "Domestic Cold
    Water"... or the PipeSystemType name "SupplyHydronic"), named `names`
    (system name, type name, abbreviation). None when nothing is known."""
    text = u" ".join(_words(n) for n in names if n)
    for word in MECHANICAL_WORDS:
        if word in text:
            return MECHANICAL
    kind = _words(classification).replace(u" ", u"")
    if not kind and not text:
        return None
    if any(c in kind for c in MECHANICAL_CLASSES):
        return MECHANICAL
    if kind.startswith(u"undefined") or kind in (u"", u"none"):
        return None if not text else PLUMBING
    return PLUMBING


def equipment_domain(duct_connectors, pipe_domains):
    """MECHANICAL or PLUMBING for a piece of mechanical equipment with
    `duct_connectors` duct connectors and pipe connectors on the systems
    `pipe_domains` (pipe_domain() of each, None when not known)."""
    if duct_connectors:
        return MECHANICAL
    known = [d for d in pipe_domains if d is not None]
    if known and all(d == PLUMBING for d in known):
        return PLUMBING
    return MECHANICAL


def settle(domains, neighbours, default=PLUMBING):
    """`domains` ({key: MECHANICAL, PLUMBING or None}) with each None taken
    from the elements it is connected to (neighbours: {key: [keys]}),
    through runs of unknown ones too; `default` where no neighbour knows."""
    out = dict(domains)
    queue = [k for k, d in out.items() if d is not None]
    while queue:
        nxt = []
        for k in queue:
            for n in neighbours.get(k, ()):
                if n in out and out[n] is None:
                    out[n] = out[k]
                    nxt.append(n)
        queue = nxt
    for k, d in out.items():
        if d is None:
            out[k] = default
    return out
