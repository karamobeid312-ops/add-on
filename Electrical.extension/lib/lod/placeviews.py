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


def key(name):
    """Name reduced for matching."""
    low = _WORDS.sub(u" ", text(name).lower())
    return _ZEROS.sub(r"\1", low).strip()


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
