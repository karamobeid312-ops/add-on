# -*- coding: utf-8 -*-
"""Smoke or heat detectors in the selected rooms or spaces, chosen from
each room's name as UAE Fire Code Table 8.14: heat in kitchens, pantries,
pump, garbage, generator and battery rooms and bathrooms over 5 m2, none in
small toilets, shafts and parking, smoke everywhere else. AHU and lift
machine rooms and rooms over 10 m high are listed to do by hand.
Change the room words in FA Settings."""
__title__ = "Auto\nDetectors"

from firealarm.command import run_auto

run_auto()
