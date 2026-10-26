# -*- coding: utf-8 -*-
"""Set the diversity factor of every FCU circuit to 0.9 (FCU in the
family or type name of a fixture on the circuit). Select boards or open
a panel schedule first to do only those boards. Shows the circuits
before writing."""
__title__ = "FCU\nDF 0.9"

from circuitdesc.command import fcu_df

fcu_df()
