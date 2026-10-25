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
