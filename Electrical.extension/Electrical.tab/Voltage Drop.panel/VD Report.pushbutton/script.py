# -*- coding: utf-8 -*-
"""Save the voltage drop calculation as an Excel report in the office
format (S.N, FROM, TO ... CUMULATIVE V.D %) and as PDF (made by Excel)."""
__title__ = "VD\nReport"

from vdrop.command import export_report

export_report()
