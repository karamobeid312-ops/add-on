# -*- coding: utf-8 -*-
"""Which tool takes which element: Mechanical, Plumbing or Firefighting
(no Revit needed). The electrical Mirror Tower takes the electrical
categories as they are (boards, lights, devices).

Ducts, duct fittings and accessories, flex ducts and air terminals are
mechanical. Sprinklers are firefighting. Plumbing fixtures and plumbing
equipment are plumbing, unless all their pipes are fire pipes or they are
named so (hose reel cabinets, landing valves): then firefighting. Pipes
(and their fittings, accessories and flex pipes) go by their piping
system:

- Hydronic supply / return, and any system named for chilled water,
  heating water, condensate or refrigerant, are mechanical (condensate
  drains are often drawn as a Sanitary system: the name wins);
- fire protection systems, and any system named for fire, sprinklers,
  hose reels, hydrants or wet / dry risers, are firefighting;
- domestic water, sanitary, vent, storm and the rest are plumbing.

A pipe whose system is not known (a fitting with no system yet) takes the
side of the pipes it is connected to, else plumbing. Mechanical equipment
is mechanical, unless all its connectors are plumbing pipes (a water pump,
a water heater, a tank: plumbing) or fire pipes (a fire pump: firefighting).
"""
from __future__ import division

MECHANICAL = "mechanical"
PLUMBING = "plumbing"
FIRE = "firefighting"
ELECTRICAL = "electrical"

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
FIXTURE_CATEGORIES = (
    ("OST_PlumbingFixtures", u"Plumbing fixtures"),
    ("OST_PlumbingEquipment", u"Plumbing equipment"),     # Revit 2024 and later
)
SPRINKLER_CATEGORIES = (
    ("OST_Sprinklers", u"Sprinklers"),
)

ELECTRICAL_CATEGORIES = (
    ("OST_ElectricalEquipment", u"Boards (electrical equipment)"),
    ("OST_LightingFixtures", u"Lighting fixtures"),
    ("OST_LightingDevices", u"Lighting devices (switches)"),
    ("OST_ElectricalFixtures", u"Electrical fixtures (sockets)"),
    ("OST_FireAlarmDevices", u"Fire alarm devices"),
    ("OST_DataDevices", u"Data devices"),
    ("OST_CommunicationDevices", u"Communication devices"),
    ("OST_SecurityDevices", u"Security devices"),
    ("OST_TelephoneDevices", u"Telephone devices"),
    ("OST_NurseCallDevices", u"Nurse call devices"),
)

# categories each tool looks at (pipes, equipment and fixtures are then split)
CATEGORIES = {
    MECHANICAL: DUCT_CATEGORIES + EQUIPMENT_CATEGORIES + PIPE_CATEGORIES,
    PLUMBING: PIPE_CATEGORIES + FIXTURE_CATEGORIES + EQUIPMENT_CATEGORIES,
    FIRE: PIPE_CATEGORIES + SPRINKLER_CATEGORIES + FIXTURE_CATEGORIES + EQUIPMENT_CATEGORIES,
    ELECTRICAL: ELECTRICAL_CATEGORIES,
}
NAMES = {MECHANICAL: u"Mechanical", PLUMBING: u"Plumbing", FIRE: u"Firefighting",
         ELECTRICAL: u"Electrical"}
PIPED = set(name for name, _ in PIPE_CATEGORIES)
EQUIPMENT = set(name for name, _ in EQUIPMENT_CATEGORIES)
FIXTURES = set(name for name, _ in FIXTURE_CATEGORIES)
FIXED = dict([(name, MECHANICAL) for name, _ in DUCT_CATEGORIES] +
             [(name, FIRE) for name, _ in SPRINKLER_CATEGORIES] +
             [(name, ELECTRICAL) for name, _ in ELECTRICAL_CATEGORIES])
LABELS = dict(DUCT_CATEGORIES + EQUIPMENT_CATEGORIES + PIPE_CATEGORIES + FIXTURE_CATEGORIES +
              SPRINKLER_CATEGORIES + ELECTRICAL_CATEGORIES)

# in the system's name, type name or abbreviation: a mechanical pipe
MECHANICAL_WORDS = (u"chilled", u"chw", u"hydronic", u"condensate", u"condensation",
                    u"condenser", u"refrigerant", u"heating", u"hhw", u"lthw", u"mthw",
                    u"cooling", u"glycol", u"fcu", u"ahu", u"hvac", u"ref liquid",
                    u"ref gas", u"drain pan")
MECHANICAL_CLASSES = (u"hydronic",)
# in the system's names (or a fixture's family / type name): firefighting
FIRE_WORDS = (u"fire", u"sprinkler", u"hose reel", u"hosereel", u"hydrant", u"wet riser",
              u"dry riser", u"landing valve", u"extinguisher", u"fhc", u"fdc", u"standpipe",
              u"deluge", u"foam", u"pre-action", u"preaction")
FIRE_CLASSES = (u"fireprotect", u"fireprot")


def _words(text):
    return (text or u"").replace(u"_", u" ").lower()


def _has_word(text, words):
    """A word of `words` in `text`: short abbreviations (fhc, fdc) only as
    a word of their own, the rest anywhere."""
    found = text.replace(u"-", u" ").replace(u"/", u" ").split()
    for w in words:
        if len(w) <= 3:
            if w in found:
                return True
        elif w in text:
            return True
    return False


def pipe_domain(classification, names=()):
    """MECHANICAL, PLUMBING or FIRE for a pipe of the system
    `classification` (Revit's System Classification: "Hydronic Supply",
    "Domestic Cold Water", "Fire Protection Wet"... or the PipeSystemType
    name "SupplyHydronic"), named `names` (system name, type name,
    abbreviation). None when nothing is known."""
    text = u" ".join(_words(n) for n in names if n)
    kind = _words(classification).replace(u" ", u"")
    if any(c in kind for c in FIRE_CLASSES) or _has_word(text, FIRE_WORDS):
        return FIRE
    if any(w in text for w in MECHANICAL_WORDS):
        return MECHANICAL
    if not kind and not text:
        return None
    if any(c in kind for c in MECHANICAL_CLASSES):
        return MECHANICAL
    if kind.startswith(u"undefined") or kind in (u"", u"none"):
        return None if not text else PLUMBING
    return PLUMBING


def _by_pipes(pipe_domains, default):
    known = [d for d in pipe_domains if d is not None]
    if known and all(d == FIRE for d in known):
        return FIRE
    if known and all(d in (PLUMBING, FIRE) for d in known):
        return PLUMBING
    return default


def equipment_domain(duct_connectors, pipe_domains, name=u""):
    """MECHANICAL, PLUMBING or FIRE for a piece of mechanical equipment with
    `duct_connectors` duct connectors and pipe connectors on the systems
    `pipe_domains` (pipe_domain() of each, None when not known), named
    `name` (family and type)."""
    if duct_connectors:
        return MECHANICAL
    if _has_word(_words(name), FIRE_WORDS):
        return FIRE                 # a fire pump, whatever system it is on yet
    return _by_pipes(pipe_domains, MECHANICAL)


def fixture_domain(pipe_domains, name=u""):
    """PLUMBING or FIRE for a plumbing fixture or plumbing equipment: fire
    when it is named so (a hose reel cabinet, a landing valve, an
    extinguisher: the name wins) or all its pipes are fire pipes."""
    if _has_word(_words(name), FIRE_WORDS):
        return FIRE
    return _by_pipes(pipe_domains, PLUMBING)


def settle(domains, neighbours, default=PLUMBING):
    """`domains` ({key: MECHANICAL, PLUMBING, FIRE or None}) with each None taken
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
