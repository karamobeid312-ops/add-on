# -*- coding: utf-8 -*-
"""Calculate the voltage drop of every cable, from the transformer to the
final loads, with the lengths typed in VD Length. Results go to VD Percent
and VD Total Percent and are listed in the output window."""
__title__ = "Calculate\nVD"

from vdrop.command import calculate

calculate()
