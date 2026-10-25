# -*- coding: utf-8 -*-
"""Matching views to sheets by name: each view is named after its drawing
title in the LOD, e.g. the view

    KEZAD Two Building Lighting System Setting Out Plan - Part 01

goes on the sheet 'Lighting System Setting Out Plan - Part 1' (the LOD title
without the title prefix). Names are compared ignoring case, dashes and
other punctuation, spacing and leading zeros ('Part 01' = 'Part 1').

Plain Python (no Revit), so it is tested outside Revit.
"""
import re

from lod.table import full_title, text

_WORDS = re.compile(r"[^0-9a-z&]+")
_ZEROS = re.compile(r"\b0+(\d)")


_ORDINALS = ((u"first", u"1st"), (u"second", u"2nd"), (u"third", u"3rd"), (u"fourth", u"4th"),
             (u"fifth", u"5th"), (u"sixth", u"6th"), (u"seventh", u"7th"), (u"eighth", u"8th"),
             (u"ninth", u"9th"), (u"tenth", u"10th"))
_DIGITS = re.compile(r"\d+")


def key(name):
    """Name reduced for matching: 'First Floor' = '1st Floor', 'Part 01' = 'Part 1'."""
    low = u" %s " % _WORDS.sub(u" ", text(name).lower())
    for word, short in _ORDINALS:
        low = low.replace(u" %s " % word, u" %s " % short)
    return u" ".join(_ZEROS.sub(r"\1", low).split())


def closest(sheet_name, views, prefix=u"", least=0.6):
    """(view id, score) of the view whose name shares the most words with
    the sheet's, with the same numbers in it (Part 1 never matches Part 2);
    None below `least` (0..1).

    views: [(view id, view name)]
    """
    best = None
    for k in sheet_keys(sheet_name, prefix):
        words = set(k.split())
        numbers = set(_DIGITS.findall(k))
        for view_id, name in views:
            vk = key(name)
            if set(_DIGITS.findall(vk)) != numbers:
                continue
            other = set(vk.split())
            score = len(words & other) / float(len(words | other) or 1)
            if score >= least and (best is None or score > best[1]):
                best = (view_id, score)
    return best


def sheet_keys(sheet_name, prefix=u""):
    """Keys a view name may have for this sheet: the sheet name, and the
    full LOD title with the prefix put back."""
    keys = [key(sheet_name)]
    if prefix:
        keys.append(key(full_title(sheet_name, prefix)))
    return [k for k in keys if k]


def match(sheets, views, prefix=u""):
    """Pair sheets with views by name.

    sheets: [(sheet id, sheet name)]
    views:  [(view id, view name, ids of the sheets it is on already)]
    Returns ({sheet id: [view ids, best first]}): views not on any sheet come
    first, then those already on this sheet, then those on other sheets.
    Sheets with no matching view are left out.
    """
    by_key = {}
    for view_id, name, on in views:
        k = key(name)
        if k:
            by_key.setdefault(k, []).append((view_id, on))
    found = {}
    for sheet_id, name in sheets:
        candidates, seen = [], set()
        for k in sheet_keys(name, prefix):
            for view_id, on in by_key.get(k, []):
                if view_id in seen:
                    continue
                seen.add(view_id)
                rank = 0 if not on else (1 if sheet_id in on else 2)
                candidates.append((rank, len(candidates), view_id))
        if candidates:
            found[sheet_id] = [v for _, _, v in sorted(candidates)]
    return found


# ------------------------------------------------------------ by plan

_BUILDINGS = ((u"parking", u"parking"), (u"service", u"service"), (u"substation", u"substation"),
              (u"guard room", u"guard room"))
_DROP = set(u"""kezad two building buildings main floor floors plan plans system systems
overall part tower typical ground roof layout of the and & level""".split())
_ORDINAL = re.compile(r"\b(\d+)(?:st|nd|rd|th)\b")


def fingerprint(name):
    """What a sheet or view shows, whatever the wording: (building, tower,
    floors, part, overall, system).

    'KEZAD Two Building Floor Plans Power System - Tower 1 - 3rd-5th floor Plan'
    and 'KEZAD Two Building - Main Building Tower 1 - Power Plan - Typical
    Floor 01 (3rd & 5th)' both give ('main', '1', '3 5', '', False, 'power').
    """
    k = key(name)
    building = next((b for word, b in _BUILDINGS if word in k), u"main")
    tower = re.search(r"\btower (\d+)\b", k)
    part = re.search(r"\bpart (\d+)\b", k)
    floors = set(_ORDINAL.findall(k))
    if re.search(r"\bground\b|\bgf\b", k):
        floors.add(u"g")
    if re.search(r"\broof\b", k):
        floors.add(u"r")
    rest = _ORDINAL.sub(u" ", k)
    rest = re.sub(r"\b(tower|part) \d+\b", u" ", rest)
    for word, _ in _BUILDINGS:
        rest = rest.replace(word, u" ")
    system = u" ".join(w for w in rest.split() if w not in _DROP and not w.isdigit()
                       and w != u"gf")
    return (building, tower.group(1) if tower else u"", u" ".join(sorted(floors)),
            part.group(1) if part else u"", u"overall" in k.split(), system)


def match_by_plan(sheets, views):
    """Like match(), for the sheets whose views are worded differently: a
    view goes with a sheet when both show the same system, building, tower,
    floor(s) and part. Returns {sheet id: [view ids, best first]}."""
    by_print = {}
    for view_id, name, on in views:
        fp = fingerprint(name)
        if fp[5] and fp[2]:                 # a system and a floor at least
            by_print.setdefault(fp, []).append((view_id, on))
    found = {}
    for sheet_id, name in sheets:
        fp = fingerprint(name)
        candidates = [(0 if not on else (1 if sheet_id in on else 2), i, v)
                      for i, (v, on) in enumerate(by_print.get(fp, []))]
        if not candidates and fp[4]:
            # 'Overall Ground Floor' sheet, view without the word overall
            loose = fp[:4] + (False,) + fp[5:]
            candidates = [(0 if not on else (1 if sheet_id in on else 2), i, v)
                          for i, (v, on) in enumerate(by_print.get(loose, []))]
        if candidates:
            found[sheet_id] = [v for _, _, v in sorted(candidates)]
    return found
