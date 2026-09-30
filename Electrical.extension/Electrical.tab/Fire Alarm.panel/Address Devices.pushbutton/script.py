# -*- coding: utf-8 -*-
"""Give the fire alarm devices their addresses (FA Address, e.g. L1/SD-01)
and tag them, device after device along each loop from the panel: the
loops drawn in this plan or in all plans (a loop going on over several
floors counts on, the floor furthest from the panel first), or devices
without a loop line, in the order Draw FA Loop would connect them.
Detection and sounder loops share the loop numbers."""
__title__ = "Address\nDevices"

from firealarm.command import address_devices

address_devices()
